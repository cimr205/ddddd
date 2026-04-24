from datetime import datetime
from typing import Any, Dict, List

from agents.base_agent import BaseAgent
from mailer.sender import sender
from core.database import SessionLocal, EmailLog, Campaign, Lead
from core.monitor import monitor
from sqlalchemy import select


class EmailSenderAgent(BaseAgent):
    name = "email_sender"

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        campaign_id: int = task.get("campaign_id")
        from_name: str = task.get("from_name", "Lead System")

        async with SessionLocal() as db:
            campaign = await db.get(Campaign, campaign_id)
            if not campaign:
                return {"score": 0.0, "error": "Campaign not found"}

            result = await db.execute(
                select(EmailLog).where(
                    EmailLog.campaign_id == campaign_id,
                    EmailLog.status == "pending",
                )
            )
            pending = result.scalars().all()

        if not pending:
            return {"score": 1.0, "sent": 0, "detail": "No pending emails"}

        await self.emit("running", f"Sending {len(pending)} emails for campaign '{campaign.name}'")

        sent = 0
        failed = 0

        for log in pending:
            lead = None
            async with SessionLocal() as db:
                lead = await db.get(Lead, log.lead_id)

            if not lead or not lead.email:
                continue

            try:
                await sender.send(
                    to_email=lead.email,
                    subject=log.subject,
                    body=log.body,
                    from_name=from_name,
                )
                async with SessionLocal() as db:
                    log_obj = await db.get(EmailLog, log.id)
                    if log_obj:
                        log_obj.status = "sent"
                        log_obj.sent_at = datetime.utcnow()
                    camp = await db.get(Campaign, campaign_id)
                    if camp:
                        camp.sent_count = (camp.sent_count or 0) + 1
                    lead_obj = await db.get(Lead, log.lead_id)
                    if lead_obj:
                        lead_obj.status = "contacted"
                    await db.commit()

                sent += 1
                await self.emit("running", f"Sent {sent}/{len(pending)} – {lead.email}", score=sent / len(pending))
                await monitor.update_stats(emails_sent=await self._total_sent())

            except Exception as e:
                async with SessionLocal() as db:
                    log_obj = await db.get(EmailLog, log.id)
                    if log_obj:
                        log_obj.status = "failed"
                        log_obj.error = str(e)
                    camp = await db.get(Campaign, campaign_id)
                    if camp:
                        camp.failed_count = (camp.failed_count or 0) + 1
                    await db.commit()
                failed += 1
                await self.emit("warning", f"Failed: {lead.email} – {e}")

        score = sent / max(len(pending), 1)
        return {"score": score, "sent": sent, "failed": failed}

    async def _total_sent(self) -> int:
        async with SessionLocal() as db:
            result = await db.execute(select(EmailLog).where(EmailLog.status == "sent"))
            return len(result.scalars().all())
