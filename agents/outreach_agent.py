"""
AI email writer – kaskade uden betalte keys:
  1. Groq   → gratis API (console.groq.com, kun email-signup)
  2. Ollama → lokal AI  (ollama.ai, ingen signup overhovedet)
  3. Template → altid virker, ingen internet krævet
"""
import json
import re
import httpx
from typing import Any, Dict, Optional

from agents.base_agent import BaseAgent
from core.config import settings
from core.database import SessionLocal, Lead, Campaign


SYSTEM_PROMPT = """Du er verdens bedste cold email copywriter.
Skriv korte, hyper-personaliserede cold emails der får svar – IKKE bare åbninger.
Regler:
- Max 90 ord i brødteksten
- Brug firmanavn og niche naturligt
- Ingen filler: ingen "Håber denne email finder dig vel"
- Ét specifikt indsigt om deres situation
- Ét klart, lavt-friktions CTA
- Lyd menneskelig, ikke automatiseret
- Emnelinjen: max 7 ord, nysgerrighed eller problem-drevet
Output KUN valid JSON: {"subject": "...", "body": "..."}"""


def _clean_json(raw: str) -> Optional[Dict]:
    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        return json.loads(raw)
    except Exception:
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass
    return None


async def _groq_write(prompt: str) -> Optional[Dict]:
    try:
        from groq import Groq
        client = Groq(api_key=settings.groq_api_key)
        response = client.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=400,
            temperature=0.7,
        )
        return _clean_json(response.choices[0].message.content)
    except Exception:
        return None


async def _ollama_write(prompt: str) -> Optional[Dict]:
    try:
        url = f"{settings.ollama_url.rstrip('/')}/api/chat"
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(url, json={
                "model": settings.ollama_model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
            })
            data = r.json()
            content = data.get("message", {}).get("content", "")
            return _clean_json(content)
    except Exception:
        return None


def _smart_template(lead: Lead, campaign: Campaign) -> Dict:
    import hashlib
    company = lead.company or "jeres virksomhed"
    niche = lead.niche or campaign.niche or "jeres branche"
    name = (lead.name or "").split()[0] if lead.name else ""
    greeting = f"Hej {name}," if name else "Hej,"
    website = lead.website or ""

    templates = [
        {
            "subject": f"Spørgsmål til {company}",
            "body": (
                f"{greeting}\n\n"
                f"Jeg stødte på {company} og lagde mærke til noget.\n\n"
                f"De fleste virksomheder inden for {niche} går glip af leads "
                f"med deres nuværende setup – vi hjælper med at fixe præcis det.\n\n"
                f"Passer det med en kort snak i denne uge?\n\nBedste hilsner"
            ),
        },
        {
            "subject": f"Hurtig idé til {company}",
            "body": (
                f"{greeting}\n\n"
                f"Vi arbejder specifikt med {niche}-virksomheder og har hjulpet lignende "
                f"firmaer med at øge omsætningen uden ekstra ansatte.\n\n"
                f"Har I 15 min til et hurtigt kald denne uge?\n\nBedste hilsner"
            ),
        },
        {
            "subject": f"Så I {company} online",
            "body": (
                f"{greeting}\n\n"
                f"Fandt {company} og tænkte der kunne være en oplagt mulighed.\n\n"
                f"Mange {niche}-firmaer kæmper med at skaffe nye kunder konsekvent. "
                f"Vi har en metode der typisk fungerer inden for 30 dage.\n\n"
                f"Åben for et kort kald?\n\nBedste hilsner"
            ),
        },
        {
            "subject": f"Til ejeren af {company}",
            "body": (
                f"{greeting}\n\n"
                f"Jeg kontakter jer fordi vi har arbejdet med virksomheder som {company} "
                f"og set konkrete resultater inden for {niche}.\n\n"
                f"Kort spørgsmål: Hvad er jeres største udfordring med kundetilgang lige nu?\n\n"
                f"Bedste hilsner"
            ),
        },
        {
            "subject": f"Kan vi hjælpe {company}?",
            "body": (
                f"{greeting}\n\n"
                f"Et hurtigt spørgsmål: Er {company} åbne for nye kunder i øjeblikket?\n\n"
                f"Vi hjælper {niche}-virksomheder med at fylde kalenderen automatisk "
                f"– uden dyre annoncer.\n\n"
                f"Svar gerne hvis I er interesserede.\n\nBedste hilsner"
            ),
        },
    ]
    idx = int(hashlib.md5(company.encode()).hexdigest(), 16) % len(templates)
    return templates[idx]


class OutreachAgent(BaseAgent):
    name = "outreach"

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        campaign_id: int = task.get("campaign_id")
        lead_ids = task.get("lead_ids", [])

        await self.emit("running", f"Skriver emails til {len(lead_ids)} leads via {settings.ai_provider.upper()}")

        written = 0
        async with SessionLocal() as db:
            campaign = await db.get(Campaign, campaign_id)
            if not campaign:
                return {"score": 0.0, "error": "Campaign not found"}

            for lead_id in lead_ids:
                lead = await db.get(Lead, lead_id)
                if lead and lead.email:
                    written += 1

        score = min(1.0, written / max(len(lead_ids), 1))
        return {"score": score, "emails_prepared": written, "provider": settings.ai_provider}

    async def write_email_for_lead(self, lead: Lead, campaign: Campaign, context: str) -> Dict:
        company = lead.company or campaign.name
        niche = lead.niche or campaign.niche or "din branche"
        name = (lead.name or "").split()[0] if lead.name else ""

        prompt = (
            f"Skriv en cold email til denne lead:\n"
            f"Firma: {company}\n"
            f"Niche: {niche}\n"
            f"Kontakt: {name or 'ejeren'}\n"
            f"Website: {lead.website or 'ukendt'}\n"
            f"Om os: {context}\n\n"
            f"Gør det personligt og relevant for netop dette firma."
        )

        result = None

        if settings.ai_provider == "groq":
            await self.emit("running", f"Groq AI skriver email til {company}...")
            result = await _groq_write(prompt)

        elif settings.ai_provider == "ollama":
            await self.emit("running", f"Ollama skriver email til {company}...")
            result = await _ollama_write(prompt)

        if not result:
            result = _smart_template(lead, campaign)

        return result
