"""
Naturlig sprog → agent-handling.
Bruger Groq → Ollama → regex fallback.
"""
import re
import json
from typing import Dict, Any, Optional
from core.config import settings

PARSE_SYSTEM = """You are a command parser for a lead generation system.
Convert the user's message to exactly one JSON action object.

AVAILABLE ACTIONS:

scrape – find leads via Google Maps:
{"action":"scrape","query":"business type","location":"city or country","count":50,"niche":"label"}

create_campaign – create email campaign:
{"action":"create_campaign","name":"name","niche":"niche"}

launch_campaign – send emails to leads:
{"action":"launch_campaign","campaign_id":null,"context":"about your service","from_name":"your name"}

status – show system status:
{"action":"status"}

leads – show leads:
{"action":"leads","filter":""}

help – show help:
{"action":"help"}

RULES:
- Output ONLY valid JSON, no explanation
- Default count=50 if not specified
- "alle"/"all"/"max" means count=9999
- If no location mentioned, default to "Danmark"
- Interpret intent liberally – "marketing i usa" means scrape marketing companies in USA
- Single words like "tandlæger" or "lawyers" are business queries, default location=Danmark"""

HELP_TEXT = """**Tilgængelige kommandoer:**

**Scraping:**
`marketing i usa` – find marketing firmaer i USA
`50 tandlæger i Aarhus` – find 50 tandlæger
`alle rengøringsfirmaer i Danmark` – find alt
`webshops i Sverige` – find webshops

**Kampagner:**
`opret kampagne 'Navn'`
`send emails til alle leads`

**Info:**
`status` · `leads` · `hjælp`"""


# Lande der automatisk splittes på tværs af byer
LOCATION_ALIASES: Dict[str, str] = {
    "usa": "United States",
    "us": "United States",
    "america": "United States",
    "uk": "United Kingdom",
    "england": "United Kingdom",
    "dk": "Danmark",
    "de": "Deutschland",
    "se": "Sverige",
    "no": "Norge",
}


def _normalize_location(loc: str) -> str:
    return LOCATION_ALIASES.get(loc.lower().strip(), loc.strip())


def _regex_parse(text: str) -> Optional[Dict]:
    t = text.lower().strip()

    # ── Hjælp ─────────────────────────────────────────────────────
    if any(w in t for w in ["hjælp", "help", "kommandoer", "hvad kan"]):
        return {"action": "help"}

    # ── Status ────────────────────────────────────────────────────
    if any(w in t for w in ["status", "hvad sker", "oversigt"]):
        return {"action": "status"}

    # ── Leads ─────────────────────────────────────────────────────
    if t in ("leads", "vis leads", "show leads"):
        return {"action": "leads", "filter": ""}

    # ── Kampagne opret ────────────────────────────────────────────
    if any(w in t for w in ["opret kampagne", "ny kampagne", "create campaign", "new campaign"]):
        name_m = re.search(r"['\"](.+?)['\"]", text)
        name = name_m.group(1) if name_m else "Ny kampagne"
        return {"action": "create_campaign", "name": name, "niche": ""}

    # ── Kampagne send ─────────────────────────────────────────────
    if any(w in t for w in ["send email", "launch", "kør kampagne", "send til", "send alle"]):
        return {"action": "launch_campaign", "campaign_id": None, "context": text, "from_name": "Lead System"}

    # ── Scrape ────────────────────────────────────────────────────
    # Ingen tal = ingen grænse (9999). Kun hvis bruger skriver et tal sættes et specifikt mål.
    alle = bool(re.search(r'\balle\b|\ball\b|\bmax\b|\balt\b|\beverything\b', t))
    count = 9999  # default: kør til Maps løber tør

    # Pattern 1: "500 tandlæger i Aarhus" eller "find 50 lawyers in New York"
    m = re.search(r'(\d+)\s+(.+?)\s+(?:i|in|på)\s+(.+)', t)
    if m:
        count = int(m.group(1))
        query = m.group(2).strip()
        location = _normalize_location(m.group(3).strip())
        query = re.sub(r'\b(find|scrape|søg|hent|get)\b', '', query).strip()
        return {"action": "scrape", "query": query, "location": location, "count": count, "niche": query}

    # Pattern 2: "marketing i usa" / "lawyers in New York" (uden tal)
    m2 = re.search(r'(.+?)\s+(?:i|in|på)\s+(.+)', t)
    if m2:
        query = m2.group(1).strip()
        location = _normalize_location(m2.group(2).strip())
        query = re.sub(r'\b(find|scrape|søg|hent|get|alle|all)\b', '', query).strip()
        if query and location:
            return {"action": "scrape", "query": query, "location": location, "count": count, "niche": query}

    # Pattern 3: eksplicitte søgeord uden location
    if any(w in t for w in ["find", "scrape", "søg", "hent", "leads"]):
        query = re.sub(r'\b(find|scrape|søg|hent|leads|alle|all|fra)\b', '', t).strip()
        return {"action": "scrape", "query": query or text, "location": "Danmark", "count": 9999, "niche": query or text}

    # Pattern 4: enkelt ord eller sætning uden location → fortolk som scrape i Danmark
    words = t.split()
    if 1 <= len(words) <= 5 and not any(w in t for w in ["status", "lead", "kampagne", "send", "hjælp"]):
        query = re.sub(r'\b(alle|all|max)\b', '', t).strip()
        if query:
            return {"action": "scrape", "query": query, "location": "Danmark", "count": 9999, "niche": query}

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
        # Strip markdown if model wraps in code block
        if "```" in raw:
            raw = re.search(r'\{.*\}', raw, re.DOTALL)
            if raw:
                raw = raw.group()
            else:
                return None
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
    result = await _groq_parse(text) or await _ollama_parse(text) or _regex_parse(text)
    if not result:
        # Last resort: treat entire input as a scrape query in Denmark
        return {"action": "scrape", "query": text.strip(), "location": "Danmark", "count": 50, "niche": text.strip()}
    return result
