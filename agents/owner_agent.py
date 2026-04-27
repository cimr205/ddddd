"""
Owner Finder Agent – finder virksomhedsejere via Google-søgning.
Kører i browser panel 2 (owner1) og 3 (owner2).
"""
import asyncio
from typing import Any, Dict, List

from agents.base_agent import BaseAgent
from scrapers.google_search import find_company_owner, find_linkedin_email
from core.database import SessionLocal, Lead
from core.monitor import monitor
from sqlalchemy import select


class OwnerFinderAgent(BaseAgent):
    name = "owner_finder"

    def __init__(self, panel_id: str = "owner1"):
        super().__init__()
        self.panel_id = panel_id

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        leads: List[Dict] = task.get("leads", [])
        await self.emit("running", f"Finder ejere til {len(leads)} firmaer...", panel=self.panel_id)

        enriched = 0
        for lead in leads:
            company = lead.get("company", "")
            if not company:
                continue

            await self.emit("running", f"Søger ejer: {company}", panel=self.panel_id)
            result = await find_company_owner(company, mon=monitor, panel_id=self.panel_id)

            if result.get("owner_name") or result.get("linkedin_url"):
                enriched += 1
                lead["owner_name"] = result.get("owner_name", "")
                lead["linkedin_url"] = result.get("linkedin_url", "")
                await self._update_lead(lead)

            await asyncio.sleep(1.5)

        await self.emit("success", f"Fandt ejere for {enriched}/{len(leads)} firmaer", panel=self.panel_id)
        return {"enriched": enriched, "leads": leads}

    async def _update_lead(self, lead: Dict):
        company = lead.get("company", "")
        owner_name = lead.get("owner_name", "")
        linkedin_url = lead.get("linkedin_url", "")

        if not company:
            return

        async with SessionLocal() as db:
            result = await db.execute(select(Lead).where(Lead.company == company))
            db_lead = result.scalar_one_or_none()
            if db_lead:
                if owner_name and not db_lead.name:
                    db_lead.name = owner_name
                await db.commit()
