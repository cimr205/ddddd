import re
import httpx
from typing import Optional, List
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse


EMAIL_REGEX = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
)

CONTACT_PATHS = ["/contact", "/contact-us", "/kontakt", "/om-os", "/about", "/about-us"]


def _is_junk_email(email: str) -> bool:
    junk = ["example.com", "domain.com", "sentry.io", "wixpress.com", "email.com", "yoursite."]
    return any(j in email.lower() for j in junk)


async def _fetch(client: httpx.AsyncClient, url: str) -> Optional[str]:
    try:
        r = await client.get(url, timeout=10, follow_redirects=True)
        if r.status_code == 200 and "text/html" in r.headers.get("content-type", ""):
            return r.text
    except Exception:
        pass
    return None


def _extract_emails(html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    # mailto links first (most reliable)
    found = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("mailto:"):
            email = href[7:].split("?")[0].strip()
            if email and not _is_junk_email(email):
                found.append(email.lower())

    # Regex fallback on visible text
    text = soup.get_text()
    for match in EMAIL_REGEX.findall(text):
        if not _is_junk_email(match) and match.lower() not in found:
            found.append(match.lower())

    return list(dict.fromkeys(found))  # deduplicate, preserve order


async def scrape_website_email(website_url: str) -> Optional[str]:
    if not website_url:
        return None

    base = website_url.rstrip("/")
    if not base.startswith("http"):
        base = "https://" + base

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    async with httpx.AsyncClient(headers=headers, verify=False) as client:
        # Try homepage first
        html = await _fetch(client, base)
        if html:
            emails = _extract_emails(html)
            if emails:
                return emails[0]

        # Try contact pages
        for path in CONTACT_PATHS:
            url = base + path
            html = await _fetch(client, url)
            if html:
                emails = _extract_emails(html)
                if emails:
                    return emails[0]

    return None


def guess_email(name: str, domain: str) -> str:
    if not name or not domain:
        return f"info@{domain}" if domain else ""

    parts = name.lower().split()
    if not parts:
        return f"info@{domain}"

    first = re.sub(r"[^a-z]", "", parts[0])
    last = re.sub(r"[^a-z]", "", parts[-1]) if len(parts) > 1 else ""

    patterns = []
    if first and last:
        patterns = [
            f"{first}.{last}@{domain}",
            f"{first[0]}{last}@{domain}",
            f"{first}@{domain}",
        ]
    elif first:
        patterns = [f"{first}@{domain}"]

    patterns.append(f"info@{domain}")
    return patterns[0]
