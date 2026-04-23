import os
from typing import Any, Dict, List
import anthropic

from agents.base_agent import BaseAgent
from core.database import SessionLocal, Lead, Campaign
from sqlalchemy import select


SYSTEM_PROMPT = """You are an elite cold email copywriter.
Write short, hyper-personalized cold emails that get replies — NOT impressions.
Rules:
- Under 100 words total
- Use their company name and niche naturally
- No filler: no "I hope this email finds you well"
- One specific insight about their situation or industry
- One clear, low-friction CTA
- Sound human, not automated
- Subject line: max 7 words, curiosity or problem-driven
Output ONLY valid JSON: {"subject": "...", "body": "..."}"""


class OutreachAgent(BaseAgent):
    name = "outreach"

    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self._client = anthropic.Anthropic(api_key=api_key) if api_key else None

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        campaign_id: int = task.get("campaign_id")
        lead_ids: List[int] = task.get("lead_ids", [])
        context: str = task.get("context", "")

        await self.emit("running", f"Writing personalized emails for {len(lead_ids)} leads")

        written = 0
        async with SessionLocal() as db:
            campaign = await db.get(Campaign, campaign_id)
            if not campaign:
                return {"score": 0.0, "error": "Campaign not found"}

            for lead_id in lead_ids:
                lead = await db.get(Lead, lead_id)
                if not lead or not lead.email:
                    continue

                email = await self._write_email(lead, campaign, context)
                if email:
                    written += 1

        score = min(1.0, written / max(len(lead_ids), 1))
        return {"score": score, "emails_written": written}

    async def _write_email(self, lead: Lead, campaign: Campaign, context: str) -> Dict:
        import json
        import asyncio

        if not self._client:
            return self._template_fallback(lead, campaign)

        prompt = f"""Write a cold email for this lead:
Company: {lead.company}
Niche: {lead.niche or campaign.niche}
Contact: {lead.name or "the owner"}
Website: {lead.website or "unknown"}
Context about us: {context}

Make it feel personal to their specific business."""

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=400,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": prompt}],
                ),
            )
            raw = response.content[0].text.strip()
            # Strip markdown code blocks if present
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw)
        except Exception as e:
            return self._template_fallback(lead, campaign)

    def _template_fallback(self, lead: Lead, campaign: Campaign) -> Dict:
        company = lead.company or "your business"
        niche = lead.niche or campaign.niche or "your industry"
        return {
            "subject": f"Quick question about {company}",
            "body": (
                f"Hi,\n\n"
                f"I noticed {company} – and had a quick thought.\n\n"
                f"Most {niche} businesses are leaving leads on the table "
                f"with their current setup. We help fix exactly that.\n\n"
                f"Worth a 15-min call this week?\n\n"
                f"Best,"
            ),
        }
