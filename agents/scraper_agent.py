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

        await self.emit("running", f"Åbner Google Maps: '{query}' i '{location}'")

        # Pass monitor so scraper can stream screenshots
        raw = await scrape_google_maps(query, location, count, mon=monitor)
        await self.emit("running", f"Fandt {len(raw)} firmaer – finder emails...")

        tasks = [self._enrich(r, niche) for r in raw]
        enriched = await asyncio.gather(*tasks, return_exceptions=True)

        leads = [item for item in enriched if isinstance(item, dict)]
        saved = await self._save_leads(leads)
        score = min(1.0, saved / max(count, 1))

        await monitor.update_stats(total_leads=await self._total_leads())
        await self.emit("success", f"Gemt {saved} leads i databasen", score=score)

        return {"score": score, "leads_found": saved, "leads_target": count, "leads": leads}

    async def _enrich(self, raw: Dict, niche: str) -> Dict:
        website = raw.get("website", "")
        email = None
        confidence = 0.1

        if website:
            email = await scrape_website_email(website)
            if email:
                confidence = 0.95
            else:
                domain = urlparse(website).netloc.lstrip("www.")
                email = guess_email(raw.get("name", ""), domain)
                confidence = 0.4

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
            for ld in leads:
                if not ld.get("company"):
                    continue
                existing = await db.execute(select(Lead).where(Lead.company == ld["company"]))
                if existing.scalar_one_or_none():
                    continue
                db.add(Lead(**{k: v for k, v in ld.items() if k in Lead.__table__.columns.keys()}))
                saved += 1
            await db.commit()
        return saved

    async def _total_leads(self) -> int:
        async with SessionLocal() as db:
            result = await db.execute(select(Lead))
            return len(result.scalars().all())
