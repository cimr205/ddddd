import asyncio
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from agents.scraper_agent import ScraperAgent
from agents.outreach_agent import OutreachAgent
from agents.email_sender_agent import EmailSenderAgent
from agents.qa_agent import QAAgent
from core.database import SessionLocal, Campaign, EmailLog, Lead
from core.monitor import monitor
from sqlalchemy import select, func

# Google Maps returnerer typisk max ~80 resultater per søgning.
# CEO-agenten splitter automatisk på tværs af byer hvis målet er højere.
MAPS_PER_SEARCH = 75

# Danske byer sorteret efter befolkningstal
DK_CITIES = [
    "København", "Aarhus", "Odense", "Aalborg", "Esbjerg",
    "Randers", "Kolding", "Horsens", "Vejle", "Herning",
    "Helsingør", "Silkeborg", "Næstved", "Fredericia", "Viborg",
    "Køge", "Holstebro", "Taastrup", "Slagelse", "Hillerød",
    "Sønderborg", "Svendborg", "Hjørring", "Holbæk", "Haderslev",
    "Frederiksberg", "Glostrup", "Herlev", "Lyngby", "Ballerup",
]

# Store europæiske byer hvis location er et land
COUNTRY_CITIES: Dict[str, List[str]] = {
    "danmark": DK_CITIES,
    "denmark": DK_CITIES,
    "sverige": ["Stockholm", "Göteborg", "Malmö", "Uppsala", "Västerås", "Örebro", "Linköping"],
    "sweden": ["Stockholm", "Gothenburg", "Malmö", "Uppsala", "Västerås"],
    "norge": ["Oslo", "Bergen", "Trondheim", "Stavanger", "Drammen", "Fredrikstad"],
    "norway": ["Oslo", "Bergen", "Trondheim", "Stavanger"],
    "tyskland": ["Berlin", "Hamburg", "München", "Köln", "Frankfurt", "Stuttgart", "Düsseldorf"],
    "germany": ["Berlin", "Hamburg", "Munich", "Cologne", "Frankfurt", "Stuttgart"],
}


def _is_country(location: str) -> bool:
    return location.lower().strip() in COUNTRY_CITIES


def _get_city_list(location: str) -> List[str]:
    return COUNTRY_CITIES.get(location.lower().strip(), [location])


def _plan_searches(query: str, location: str, count: int) -> List[Dict]:
    """
    CEO tænker: hvor mange søgninger skal der til for at nå målet?
    Splitter automatisk på tværs af byer.
    """
    if count <= MAPS_PER_SEARCH and not _is_country(location):
        return [{"query": query, "location": location, "count": count}]

    cities = _get_city_list(location)
    per_city = max(MAPS_PER_SEARCH, -(-count // max(len(cities), 1)))  # ceiling division
    return [{"query": query, "location": city, "count": per_city} for city in cities]


class CEOAgent:
    def __init__(self):
        self.scraper = ScraperAgent()
        self.outreach = OutreachAgent()
        self.sender = EmailSenderAgent()
        self.qa = QAAgent()

    async def run_scrape_pipeline(self, query: str, location: str, count: int, niche: str) -> Dict:
        searches = _plan_searches(query, location, count)
        multi = len(searches) > 1

        if multi:
            await monitor.emit(
                "ceo", "Orchestrator",
                f"Mål: {count} leads → splitter i {len(searches)} søgninger på tværs af byer",
                "running",
            )
            await monitor.emit_chat(
                "agent",
                f"Forstår – {count} leads kræver flere søgninger.\n"
                f"Planlægger **{len(searches)} søgninger** på tværs af: "
                + ", ".join(s['location'] for s in searches[:6])
                + ("..." if len(searches) > 6 else ""),
            )
        else:
            await monitor.emit("ceo", "Orchestrator", f"Starter scrape: {query} i {location}", "running")

        total_found = 0
        all_leads: List[Dict] = []

        for i, search in enumerate(searches):
            current = await self._total_leads()
            if current >= count and count < 9999:
                await monitor.emit("ceo", "Orchestrator", f"Mål nået ({current} leads) – stopper", "success", score=1.0)
                break

            remaining = (count - current) if count < 9999 else search["count"]
            if remaining <= 0:
                break

            if multi:
                await monitor.emit(
                    "ceo", "Orchestrator",
                    f"[{i+1}/{len(searches)}] {search['query']} i {search['location']} (mål: {remaining})",
                    "running",
                )

            task = {
                "query": search["query"],
                "location": search["location"],
                "count": min(remaining, MAPS_PER_SEARCH),
                "niche": niche,
                "goal": f"Find leads i {search['location']}",
            }
            result = await self.scraper.run(task)
            found = result.get("leads_found", 0)
            total_found += found
            all_leads.extend(result.get("leads", []))

            await self.qa.run({"agent": "scraper", "result": result, "goal": task["goal"]})

            if multi and found < 10:
                await monitor.emit(
                    "ceo", "Orchestrator",
                    f"{search['location']}: kun {found} fundet – fortsætter til næste by",
                    "warning",
                )

        final_total = await self._total_leads()
        score = min(1.0, final_total / max(count, 1)) if count < 9999 else 1.0

        await monitor.emit(
            "ceo", "Orchestrator",
            f"Færdig: {total_found} leads gemt (total i DB: {final_total})",
            "success",
            score=score,
        )

        if multi:
            await monitor.emit_chat(
                "agent",
                f"Scraping færdig.\n\n"
                f"Søgte i **{len(searches)} byer** og gemte **{total_found} leads**.\n"
                f"Total i database: **{final_total}**",
                "result",
            )

        return {"score": score, "leads_found": total_found, "leads_target": count, "leads": all_leads}

    async def run_campaign_pipeline(
        self, campaign_id: int, lead_ids: List[int], context: str, from_name: str
    ) -> Dict:
        await monitor.emit("ceo", "Orchestrator", f"Kampagne {campaign_id}: {len(lead_ids)} emails", "running")

        await self._generate_email_logs(campaign_id, lead_ids, context)

        outreach_result = {"score": 0.9, "emails_prepared": len(lead_ids)}
        await self.qa.run({"agent": "outreach", "result": outreach_result, "goal": "Write emails"})

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

        await monitor.emit(
            "ceo", "Orchestrator",
            f"Kampagne done: {send_result.get('sent', 0)} sendt",
            "success",
            score=send_result.get("score", 0),
        )
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
