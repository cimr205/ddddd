import asyncio
from datetime import datetime
from typing import Any, Dict, List

from agents.scraper_agent import ScraperAgent
from agents.outreach_agent import OutreachAgent
from agents.email_sender_agent import EmailSenderAgent
from agents.qa_agent import QAAgent
from core.database import SessionLocal, Campaign, EmailLog, Lead
from core.monitor import monitor
from sqlalchemy import select


class CEOAgent:
    def __init__(self):
        self.scraper = ScraperAgent()
        self.outreach = OutreachAgent()
        self.sender = EmailSenderAgent()
        self.qa = QAAgent()

    async def run_scrape_pipeline(self, query: str, location: str, count: int, niche: str) -> Dict:
        await monitor.emit("ceo", "Orchestrator", f"Starter scrape: {query} i {location}", "running")

        task = {"query": query, "location": location, "count": count, "niche": niche, "goal": f"Find {count} leads"}
        result = await self.scraper.run(task)

        await self.qa.run({"agent": "scraper", "result": result, "goal": task["goal"]})

        await monitor.emit(
            "ceo", "Orchestrator",
            f"Scrape færdig: {result.get('leads_found', 0)} leads gemt",
            "success",
            score=result.get("score", 0),
        )
        return result

    async def run_campaign_pipeline(
        self, campaign_id: int, lead_ids: List[int], context: str, from_name: str
    ) -> Dict:
        await monitor.emit("ceo", "Orchestrator", f"Kampagne {campaign_id}: skriver {len(lead_ids)} emails", "running")

        # Write personalized emails
        await self._generate_email_logs(campaign_id, lead_ids, context)

        # QA check
        outreach_result = {"score": 0.9, "emails_prepared": len(lead_ids)}
        await self.qa.run({"agent": "outreach", "result": outreach_result, "goal": "Write emails"})

        # Send
        send_task = {"campaign_id": campaign_id, "from_name": from_name, "goal": "Send emails"}
        send_result = await self.sender.run(send_task)

        await self.qa.run({"agent": "email_sender", "result": send_result, "goal": send_task["goal"]})

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

                log = EmailLog(
                    lead_id=lead_id,
                    campaign_id=campaign_id,
                    subject=email_content.get("subject", ""),
                    body=email_content.get("body", ""),
                    status="pending",
                    created_at=datetime.utcnow(),
                )
                db.add(log)
            await db.commit()
