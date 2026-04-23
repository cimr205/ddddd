import asyncio
from typing import Any, Dict, List
from datetime import datetime

from agents.scraper_agent import ScraperAgent
from agents.outreach_agent import OutreachAgent
from agents.email_sender_agent import EmailSenderAgent
from agents.qa_agent import QAAgent
from core.database import SessionLocal, Campaign, EmailLog, Lead
from core.monitor import monitor
from sqlalchemy import select


class CEOAgent:
    """
    Orchestrates all agents.
    OBSERVE → THINK → ACT → EVALUATE for every pipeline run.
    """

    def __init__(self):
        self.scraper = ScraperAgent()
        self.outreach = OutreachAgent()
        self.sender = EmailSenderAgent()
        self.qa = QAAgent()

    async def run_scrape_pipeline(self, query: str, location: str, count: int, niche: str) -> Dict:
        await monitor.emit("ceo", "Orchestrator", f"Starting scrape: {query} in {location}", "running")

        task = {"query": query, "location": location, "count": count, "niche": niche, "goal": f"Find {count} leads"}
        result = await self.scraper.run(task)

        eval_result = await self.qa.run({"agent": "scraper", "result": result, "goal": task["goal"]})

        await monitor.emit(
            "ceo", "Orchestrator",
            f"Scrape done: {result.get('leads_found', 0)} leads saved",
            "success",
            score=result.get("score", 0),
        )
        return {"scrape": result, "evaluation": eval_result.get("evaluation", {})}

    async def run_campaign_pipeline(
        self,
        campaign_id: int,
        lead_ids: List[int],
        context: str,
        from_name: str,
    ) -> Dict:
        await monitor.emit("ceo", "Orchestrator", f"Campaign {campaign_id}: writing {len(lead_ids)} emails", "running")

        # Step 1: Write personalized emails
        outreach_task = {
            "campaign_id": campaign_id,
            "lead_ids": lead_ids,
            "context": context,
            "goal": f"Write personalized emails for {len(lead_ids)} leads",
        }
        outreach_result = await self.outreach.run(outreach_task)

        # Step 2: Generate EmailLog records from outreach
        await self._generate_email_logs(campaign_id, lead_ids, context)

        # Step 3: QA check on outreach
        await self.qa.run({"agent": "outreach", "result": outreach_result, "goal": outreach_task["goal"]})

        # Step 4: Send
        send_task = {
            "campaign_id": campaign_id,
            "from_name": from_name,
            "goal": f"Send campaign {campaign_id} emails",
        }
        send_result = await self.sender.run(send_task)

        # Step 5: QA check on sending
        await self.qa.run({"agent": "email_sender", "result": send_result, "goal": send_task["goal"]})

        # Update campaign status
        async with SessionLocal() as db:
            camp = await db.get(Campaign, campaign_id)
            if camp:
                camp.status = "done" if send_result.get("score", 0) >= 0.8 else "paused"
                await db.commit()

        await monitor.emit("ceo", "Orchestrator", f"Campaign done: {send_result.get('sent', 0)} sent", "success", score=send_result.get("score", 0))
        return {"outreach": outreach_result, "sending": send_result}

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

                email_content = await self.outreach._write_email(lead, campaign, context)

                log = EmailLog(
                    lead_id=lead_id,
                    campaign_id=campaign_id,
                    subject=email_content.get("subject", campaign.subject_template or ""),
                    body=email_content.get("body", campaign.body_template or ""),
                    status="pending",
                    created_at=datetime.utcnow(),
                )
                db.add(log)
            await db.commit()
