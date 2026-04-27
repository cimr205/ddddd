import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from agents.scraper_agent import ScraperAgent
from agents.outreach_agent import OutreachAgent
from agents.email_sender_agent import EmailSenderAgent
from agents.qa_agent import QAAgent
from agents.owner_agent import OwnerFinderAgent
from agents.linkedin_agent import LinkedInAgent
from core.database import SessionLocal, Campaign, EmailLog, Lead
from core.monitor import monitor
from sqlalchemy import select, func

MAPS_PER_SEARCH = 75

DK_CITIES = [
    "København", "Aarhus", "Odense", "Aalborg", "Esbjerg",
    "Randers", "Kolding", "Horsens", "Vejle", "Herning",
    "Helsingør", "Silkeborg", "Næstved", "Fredericia", "Viborg",
    "Køge", "Holstebro", "Taastrup", "Slagelse", "Hillerød",
    "Sønderborg", "Svendborg", "Hjørring", "Holbæk", "Haderslev",
    "Frederiksberg", "Glostrup", "Herlev", "Lyngby", "Ballerup",
]

COUNTRY_CITIES: Dict[str, List[str]] = {
    "danmark": DK_CITIES,
    "denmark": DK_CITIES,
    "sverige": ["Stockholm", "Göteborg", "Malmö", "Uppsala", "Västerås", "Örebro", "Linköping"],
    "sweden": ["Stockholm", "Gothenburg", "Malmö", "Uppsala", "Västerås"],
    "norge": ["Oslo", "Bergen", "Trondheim", "Stavanger", "Drammen", "Fredrikstad"],
    "norway": ["Oslo", "Bergen", "Trondheim", "Stavanger"],
    "tyskland": ["Berlin", "Hamburg", "München", "Köln", "Frankfurt", "Stuttgart", "Düsseldorf"],
    "germany": ["Berlin", "Hamburg", "Munich", "Cologne", "Frankfurt", "Stuttgart"],
    "united states": ["New York", "Los Angeles", "Chicago", "Houston", "Phoenix", "Philadelphia",
                      "San Antonio", "San Diego", "Dallas", "San Jose", "Austin", "Jacksonville",
                      "Seattle", "Denver", "Boston", "Miami", "Atlanta", "Minneapolis"],
    "usa": ["New York", "Los Angeles", "Chicago", "Houston", "Phoenix", "Philadelphia",
            "San Antonio", "San Diego", "Dallas", "San Jose", "Austin", "Jacksonville",
            "Seattle", "Denver", "Boston", "Miami", "Atlanta", "Minneapolis"],
    "united kingdom": ["London", "Birmingham", "Manchester", "Glasgow", "Liverpool",
                       "Bristol", "Sheffield", "Leeds", "Edinburgh", "Leicester"],
    "uk": ["London", "Birmingham", "Manchester", "Glasgow", "Liverpool",
           "Bristol", "Sheffield", "Leeds", "Edinburgh"],
}


def _is_country(location: str) -> bool:
    return location.lower().strip() in COUNTRY_CITIES


def _get_city_list(location: str) -> List[str]:
    return COUNTRY_CITIES.get(location.lower().strip(), [location])


def _query_variations(query: str) -> List[str]:
    """Lav synonymer til søgeforespørgslen så vi får flere resultater."""
    q = query.lower().strip()
    variations = [query]  # original altid først

    synonyms = {
        "marketing": ["marketing agency", "digital marketing", "marketing bureau", "reklamebureau"],
        "rengøring": ["rengøringsservice", "rengøringsfirma", "cleaning service", "erhvervsrengøring"],
        "tandlæge": ["tandlæger", "dental clinic", "dentist", "tandklinik"],
        "advokat": ["advokatfirma", "law firm", "lawyers", "juridisk rådgivning"],
        "revisor": ["revisorfirma", "accounting", "bogholder", "bogføring"],
        "tømrer": ["tømrerfirma", "snedker", "carpenter", "byggefirma"],
        "maler": ["malerfirma", "painter", "malerservice"],
        "elektriker": ["el-installatør", "electrician", "elfirma"],
        "VVS": ["VVS-firma", "plumber", "blikkenslager", "VVS-installatør"],
        "restaurant": ["restaurant", "cafe", "spisested", "bistro"],
        "frisør": ["frisørsalon", "hair salon", "barber"],
        "webshop": ["e-commerce", "online shop", "netbutik"],
        "IT": ["IT-firma", "software company", "tech startup"],
    }

    for key, syns in synonyms.items():
        if key in q:
            for s in syns:
                if s.lower() != q and s not in variations:
                    variations.append(s)
            break  # kun match første nøgleord

    return variations


def _plan_searches(query: str, location: str, count: int) -> List[Dict]:
    """
    CEO planlægger søgninger:
    - Splitter på byer hvis location er et land
    - Tilføjer query-variationer for at finde flere resultater
    - count=9999 = ingen grænse, kør alt
    """
    cities = _get_city_list(location)
    queries = _query_variations(query)

    searches = []
    for city in cities:
        for q in queries:
            searches.append({"query": q, "location": city, "count": MAPS_PER_SEARCH})

    return searches


class CEOAgent:
    def __init__(self):
        self.scraper = ScraperAgent(panel_id="maps")
        self.scraper2 = ScraperAgent(panel_id="maps2")
        self.outreach = OutreachAgent()
        self.sender = EmailSenderAgent()
        self.qa = QAAgent()
        self.owner1 = OwnerFinderAgent(panel_id="owner")
        self.owner2 = OwnerFinderAgent(panel_id="owner")
        self.linkedin = LinkedInAgent()

    async def run_scrape_pipeline(self, query: str, location: str, count: int, niche: str) -> Dict:
        searches = _plan_searches(query, location, count)
        unlimited = (count >= 9999)

        cities = _get_city_list(location)
        queries = _query_variations(query)

        await monitor.emit_chat(
            "agent",
            f"Starter søgning: **{query}** i **{location}**\n"
            + (f"Ingen grænse – kører til Maps løber tør\n" if unlimited else f"Mål: **{count} leads**\n")
            + f"Plan: **{len(cities)} {'by' if len(cities)==1 else 'byer'}** × **{len(queries)} søgeterm{'er' if len(queries)>1 else ''}**",
        )

        await monitor.emit("ceo", "Orchestrator",
            f"Plan: {len(searches)} søgninger ({len(cities)} byer × {len(queries)} termer)",
            "running")

        total_found = 0
        all_leads: List[Dict] = []
        search_num = 0

        # Build flat list of (query, city) pairs for dual-parallel scraping
        search_pairs = [(q, city) for city in cities for q in queries]
        i = 0
        goal_reached = False

        while i < len(search_pairs) and not goal_reached:
            current = await self._total_leads()
            if not unlimited and current >= count:
                await monitor.emit("ceo", "Orchestrator",
                    f"Mål nået: {current} leads – stopper", "success", score=1.0)
                break

            pair_a = search_pairs[i]
            pair_b = search_pairs[i + 1] if i + 1 < len(search_pairs) else None
            i += 2

            search_num += 1
            await monitor.emit("ceo", "Orchestrator",
                f"[{search_num}] '{pair_a[0]}' i {pair_a[1]}" +
                (f" + '{pair_b[0]}' i {pair_b[1]}" if pair_b else ""),
                "running")

            task_a = {
                "query": pair_a[0],
                "location": pair_a[1],
                "count": MAPS_PER_SEARCH,
                "niche": niche,
                "goal": f"Find leads: {pair_a[0]} i {pair_a[1]}",
            }

            if pair_b:
                task_b = {
                    "query": pair_b[0],
                    "location": pair_b[1],
                    "count": MAPS_PER_SEARCH,
                    "niche": niche,
                    "goal": f"Find leads: {pair_b[0]} i {pair_b[1]}",
                }
                results = await asyncio.gather(
                    self.scraper.execute(task_a),
                    self.scraper2.execute(task_b),
                    return_exceptions=True,
                )
            else:
                results = await asyncio.gather(
                    self.scraper.execute(task_a),
                    return_exceptions=True,
                )

            for result in results:
                if isinstance(result, dict):
                    found = result.get("leads_found", 0)
                    total_found += found
                    all_leads.extend(result.get("leads", []))
                    if found < 5:
                        await monitor.emit("ceo", "Orchestrator",
                            f"Kun {found} leads fra søgning – prøver næste", "warning")

        final_total = await self._total_leads()
        score = min(1.0, final_total / count) if not unlimited else 1.0

        await monitor.emit("ceo", "Orchestrator",
            f"Færdig: {total_found} nye leads gemt (total: {final_total})", "success", score=score)

        await monitor.emit_chat("agent",
            f"Søgning færdig.\n\n"
            f"Nye leads gemt: **{total_found}**\n"
            f"Total i database: **{final_total}**\n"
            f"Søgninger kørt: **{search_num}**",
            "result")

        return {"score": score, "leads_found": total_found, "leads_target": count, "leads": all_leads}

    async def run_full_pipeline(self, query: str, location: str, count: int, niche: str) -> Dict:
        """
        4-browser pipeline:
        1. (maps) Google Maps → find companies
        2. (owner1 + owner2) Find owners in parallel
        3. (linkedin) Find LinkedIn + email
        """
        await monitor.emit_chat("agent",
            f"**4-Browser Pipeline startet**\n"
            f"Browser 1: Google Maps → firmaer\n"
            f"Browser 2+3: Finder ejere\n"
            f"Browser 4: LinkedIn + emails")

        # Phase 1: Scrape companies
        result = await self.run_scrape_pipeline(query, location, count, niche)
        all_leads = result.get("leads", [])

        if not all_leads:
            return result

        # Split leads between owner1 and owner2 agents
        mid = len(all_leads) // 2
        batch1 = all_leads[:mid]
        batch2 = all_leads[mid:]

        await monitor.emit_chat("agent",
            f"Fandt **{len(all_leads)} firmaer** – starter ejer-søgning på 2 browsere parallelt...")

        # Phase 2: Find owners in parallel (browser 2 + 3)
        owner_results = await asyncio.gather(
            self.owner1.execute({"leads": batch1}),
            self.owner2.execute({"leads": batch2}),
            return_exceptions=True,
        )

        enriched_leads = []
        for r in owner_results:
            if isinstance(r, dict):
                enriched_leads.extend(r.get("leads", []))

        owners_found = sum(
            1 for l in enriched_leads if l.get("owner_name") or l.get("linkedin_url")
        )
        await monitor.emit_chat("agent",
            f"Ejere fundet: **{owners_found}/{len(enriched_leads)}** – starter LinkedIn-søgning...")

        # Phase 3: LinkedIn + email (browser 4)
        linkedin_result = await self.linkedin.execute({"leads": enriched_leads})
        emails_found = linkedin_result.get("found_emails", 0)

        final_total = await self._total_leads()
        await monitor.emit_chat("agent",
            f"**4-Browser Pipeline færdig**\n\n"
            f"Firmaer fundet: **{len(all_leads)}**\n"
            f"Ejere identificeret: **{owners_found}**\n"
            f"Emails fundet via LinkedIn: **{emails_found}**\n"
            f"Total leads i database: **{final_total}**",
            "result")

        return {
            "score": result.get("score", 0),
            "leads_found": len(all_leads),
            "owners_found": owners_found,
            "emails_found": emails_found,
            "leads": enriched_leads,
        }

    async def run_campaign_pipeline(
        self, campaign_id: int, lead_ids: List[int], context: str, from_name: str
    ) -> Dict:
        await monitor.emit("ceo", "Orchestrator",
            f"Kampagne {campaign_id}: {len(lead_ids)} emails", "running")

        await self._generate_email_logs(campaign_id, lead_ids, context)

        await self.qa.run({"agent": "outreach",
            "result": {"score": 0.9, "emails_prepared": len(lead_ids)},
            "goal": "Write emails"})

        send_result = await self.sender.run({
            "campaign_id": campaign_id,
            "from_name": from_name,
            "goal": "Send emails",
        })

        await self.qa.run({"agent": "email_sender", "result": send_result, "goal": "Send emails"})

        async with SessionLocal() as db:
            camp = await db.get(Campaign, campaign_id)
            if camp:
                camp.status = "done" if send_result.get("score", 0) >= 0.8 else "paused"
                await db.commit()

        await monitor.emit("ceo", "Orchestrator",
            f"Kampagne done: {send_result.get('sent', 0)} sendt",
            "success", score=send_result.get("score", 0))

        return {"sending": send_result}

    async def _generate_email_logs(self, campaign_id: int, lead_ids: List[int], context: str):
        async with SessionLocal() as db:
            campaign = await db.get(Campaign, campaign_id)
            if not campaign:
                return
            for lead_id in lead_ids:
                existing = await db.execute(
                    select(EmailLog).where(
                        EmailLog.campaign_id == campaign_id,
                        EmailLog.lead_id == lead_id,
                    )
                )
                if existing.scalar_one_or_none():
                    continue
                lead = await db.get(Lead, lead_id)
                if not lead or not lead.email:
                    continue
                email_content = await self.outreach.write_email_for_lead(lead, campaign, context)
                db.add(EmailLog(
                    lead_id=lead_id,
                    campaign_id=campaign_id,
                    subject=email_content.get("subject", ""),
                    body=email_content.get("body", ""),
                    status="pending",
                    created_at=datetime.utcnow(),
                ))
            await db.commit()

    async def _total_leads(self) -> int:
        async with SessionLocal() as db:
            return (await db.execute(select(func.count(Lead.id)))).scalar() or 0
