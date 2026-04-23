import asyncio
from typing import Any, Dict, List
from urllib.parse import urlparse

from agents.base_agent import BaseAgent
from scrapers.google_maps import scrape_google_maps
from scrapers.website import scrape_website_email, guess_email
from core.database import SessionLocal, Lead
from core.monitor import monitor
from sqlalchemy import select


class ScraperAgent(BaseAgent):
    name = "scraper"

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        query: str = task.get("query", "")
        location: str = task.get("location", "")
        count: int = task.get("count", 50)
        niche: str = task.get("niche", query)

        await self.emit("running", f"Searching Google Maps: '{query}' in '{location}'")

        raw = await scrape_google_maps(query, location, count)
        await self.emit("running", f"Found {len(raw)} listings – enriching with emails...")

        leads = []
        tasks = [self._enrich(r, niche) for r in raw]
        enriched = await asyncio.gather(*tasks, return_exceptions=True)

        for item in enriched:
            if isinstance(item, dict):
                leads.append(item)

        saved = await self._save_leads(leads)
        score = min(1.0, saved / max(count, 1))

        await monitor.update_stats(total_leads=await self._total_leads())
        return {
            "score": score,
            "leads_found": saved,
            "leads_target": count,
            "leads": leads,
        }

    async def _enrich(self, raw: Dict, niche: str) -> Dict:
        website = raw.get("website", "")
        email = None

        if website:
            email = await scrape_website_email(website)

        if not email and website:
            domain = urlparse(website).netloc.lstrip("www.")
            email = guess_email(raw.get("name", ""), domain)
            confidence = 0.4
        elif email:
            confidence = 0.95
        else:
            confidence = 0.1

        return {
            "name": raw.get("name", ""),
            "company": raw.get("name", ""),
            "email": email or "",
            "phone": raw.get("phone", ""),
            "website": website,
            "address": raw.get("address", ""),
            "niche": niche,
            "email_confidence": confidence,
            "source": "google_maps",
        }

    async def _save_leads(self, leads: List[Dict]) -> int:
        saved = 0
        async with SessionLocal() as db:
            for lead_data in leads:
                if not lead_data.get("company"):
                    continue
                existing = await db.execute(
                    select(Lead).where(Lead.company == lead_data["company"])
                )
                if existing.scalar_one_or_none():
                    continue

                lead = Lead(**{k: v for k, v in lead_data.items()
                               if k in Lead.__table__.columns.keys()})
                db.add(lead)
                saved += 1
            await db.commit()
        return saved

    async def _total_leads(self) -> int:
        async with SessionLocal() as db:
            result = await db.execute(select(Lead))
            return len(result.scalars().all())
