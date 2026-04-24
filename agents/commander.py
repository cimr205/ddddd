"""
Naturlig sprog → agent-handling.
Bruger Groq → Ollama → regex fallback.
"""
import re
import json
from typing import Dict, Any, Optional
from core.config import settings

PARSE_SYSTEM = """Du er en kommando-parser for et lead generation system.
Konverter brugerens besked til præcis ét JSON action-objekt.

TILGÆNGELIGE ACTIONS:

scrape – find leads via Google Maps:
{"action":"scrape","query":"firmatype","location":"by","count":50,"niche":"label"}

create_campaign – opret email-kampagne:
{"action":"create_campaign","name":"navn","niche":"niche"}

launch_campaign – send emails til leads:
{"action":"launch_campaign","campaign_id":null,"context":"om din service","from_name":"dit navn"}

status – vis systemstatus:
{"action":"status"}

leads – vis leads:
{"action":"leads","filter":""}

help – vis hjælp:
{"action":"help"}

REGLER:
- Output KUN valid JSON
- Ingen forklaring, ingen markdown
- Gæt rimelige defaults (count=50 hvis ikke nævnt)
- Hvis besked er på dansk, svar stadig kun med JSON"""

HELP_TEXT = """**Tilgængelige kommandoer:**

**Scraping:**
`find 50 rengøringsfirmaer i København`
`scrape 100 tandlæger i Aarhus`
`søg efter webshops i Danmark`

**Kampagner:**
`opret kampagne 'Rengøring DK'`
`send emails til alle nye leads`
`launch kampagne med kontekst: vi laver hjemmesider`

**Info:**
`status` – systemstatus
`leads` – vis leads
`hjælp` – denne liste"""


def _regex_parse(text: str) -> Optional[Dict]:
    t = text.lower().strip()

    # Scrape patterns – "alle" / "so many as possible" → 9999
    alle = bool(re.search(r'\balle\b|\bso many\b|\bmax\b|\balt\b', t))
    m = re.search(r'(\d+)\s+(.+?)\s+i\s+(.+)', t)
    if m or alle or any(w in t for w in ["find", "scrape", "søg", "hent", "leads fra"]):
        count = 9999 if alle else (int(m.group(1)) if m else 50)
        query_raw = m.group(2) if m else re.sub(r'\b(find|scrape|søg|hent|leads|alle)\b', '', t).strip()
        location = m.group(3) if m else "Danmark"
        return {"action": "scrape", "query": query_raw.strip(), "location": location.strip(), "count": count, "niche": query_raw.strip()}

    if any(w in t for w in ["opret kampagne", "ny kampagne", "create campaign"]):
        name_m = re.search(r"['\"](.+?)['\"]", text)
        name = name_m.group(1) if name_m else "Ny kampagne"
        return {"action": "create_campaign", "name": name, "niche": ""}

    if any(w in t for w in ["send emails", "launch", "kør kampagne"]):
        return {"action": "launch_campaign", "campaign_id": None, "context": text, "from_name": "Lead System"}

    if any(w in t for w in ["status", "hvad sker", "oversigt"]):
        return {"action": "status"}

    if any(w in t for w in ["leads", "vis leads", "show leads"]):
        return {"action": "leads", "filter": ""}

    if any(w in t for w in ["hjælp", "help", "kommandoer", "hvad kan"]):
        return {"action": "help"}

    return None


async def _groq_parse(text: str) -> Optional[Dict]:
    if not settings.groq_api_key:
        return None
    try:
        from groq import Groq
        client = Groq(api_key=settings.groq_api_key)
        resp = client.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {"role": "system", "content": PARSE_SYSTEM},
                {"role": "user", "content": text},
            ],
            max_tokens=200,
            temperature=0.1,
        )
        raw = resp.choices[0].message.content.strip()
        return json.loads(raw)
    except Exception:
        return None


async def _ollama_parse(text: str) -> Optional[Dict]:
    if not settings.ollama_enabled:
        return None
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                f"{settings.ollama_url}/api/chat",
                json={
                    "model": settings.ollama_model,
                    "messages": [
                        {"role": "system", "content": PARSE_SYSTEM},
                        {"role": "user", "content": text},
                    ],
                    "stream": False,
                },
            )
            content = r.json().get("message", {}).get("content", "")
            m = re.search(r'\{.*\}', content, re.DOTALL)
            if m:
                return json.loads(m.group())
    except Exception:
        pass
    return None


async def parse_command(text: str) -> Dict[str, Any]:
    # Try AI parsers first for best accuracy
    result = await _groq_parse(text) or await _ollama_parse(text) or _regex_parse(text)

    if not result:
        return {"action": "unknown", "raw": text}

    return result
