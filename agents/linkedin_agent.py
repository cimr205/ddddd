"""
LinkedIn Agent – finder ejers LinkedIn-profil og email.
Kører i browser panel 4 (linkedin).
Bruger Google til at finde LinkedIn-URL'er (undgår LinkedIn login-krav).
"""
import asyncio
from typing import Any, Dict, List

from agents.base_agent import BaseAgent
from scrapers.google_search import find_linkedin_email, google_search_text
from core.database import SessionLocal, Lead
from core.monitor import monitor
from sqlalchemy import select
import re


class LinkedInAgent(BaseAgent):
    name = "linkedin"

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        leads: List[Dict] = task.get("leads", [])
        await self.emit("running", f"LinkedIn søgning for {len(leads)} kontakter...", panel="linkedin")

        found_emails = 0
        for lead in leads:
            company = lead.get("company", "")
            owner_name = lead.get("owner_name", "")
            linkedin_url = lead.get("linkedin_url", "")

            if not company:
                continue

            await self.emit("running", f"LinkedIn: {owner_name or company}", panel="linkedin")

            # If we don't have a LinkedIn URL yet, search for it
            if not linkedin_url and owner_name:
                text = await google_search_text(
                    f'site:linkedin.com/in "{owner_name}" "{company}"',
                    mon=monitor,
                    panel_id="linkedin"
                )
                matches = re.findall(r'linkedin\.com/in/([a-zA-Z0-9\-_]+)', text)
                if matches:
                    linkedin_url = f"https://www.linkedin.com/in/{matches[0]}"
                    lead["linkedin_url"] = linkedin_url

            # Try to find email
            if not lead.get("email") or lead.get("email_confidence", 0) < 0.5:
                email = await find_linkedin_email(
                    linkedin_url, owner_name, company,
                    mon=monitor, panel_id="linkedin"
                )
                if email:
                    lead["email"] = email
                    lead["email_confidence"] = 0.7
                    found_emails += 1
                    await self._update_lead_email(lead, email)

            await asyncio.sleep(2.0)

        await self.emit("success", f"LinkedIn: fandt {found_emails} emails", panel="linkedin")
        return {"found_emails": found_emails, "leads": leads}

    async def _update_lead_email(self, lead: Dict, email: str):
        company = lead.get("company", "")
        if not company:
            return

        async with SessionLocal() as db:
            result = await db.execute(select(Lead).where(Lead.company == company))
            db_lead = result.scalar_one_or_none()
            if db_lead and (not db_lead.email or db_lead.email_confidence < 0.5):
                db_lead.email = email
                db_lead.email_confidence = 0.7
                await db.commit()
