"""
Google search scraper til at finde virksomhedsejere og LinkedIn-profiler.
Bruger Playwright til at søge på Google – ingen API key.
"""
import asyncio
import base64
import random
import re
from typing import List, Dict, Optional, TYPE_CHECKING

from playwright.async_api import async_playwright, Page

if TYPE_CHECKING:
    from core.monitor import Monitor

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
]


async def _screenshot(page: Page, mon: Optional["Monitor"], label: str = "", panel_id: str = "owner1"):
    if mon is None:
        return
    try:
        img = await page.screenshot(type="jpeg", quality=50, full_page=False)
        b64 = base64.b64encode(img).decode()
        await mon.emit_browser_frame(b64, 0, 0, page.url, label, panel_id=panel_id)
    except Exception:
        pass


async def google_search_text(query: str, mon: Optional["Monitor"] = None, panel_id: str = "owner1") -> str:
    """Returns the text content of the first page of Google search results."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        )
        ctx = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1280, "height": 800},
        )
        await ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )
        page = await ctx.new_page()
        try:
            url = f"https://www.google.com/search?q={query.replace(' ', '+')}&hl=da&num=10"
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(random.uniform(1.0, 2.0))
            await _screenshot(page, mon, f"Google: {query[:50]}", panel_id=panel_id)

            # Accept cookies if prompted
            try:
                btn = await page.wait_for_selector(
                    'button:has-text("Accept all"), button:has-text("Accepter alle")', timeout=3000
                )
                if btn:
                    await btn.click()
                    await asyncio.sleep(0.5)
            except Exception:
                pass

            text = await page.evaluate("document.body.innerText")
            await _screenshot(page, mon, f"Results: {query[:40]}", panel_id=panel_id)
            return text or ""
        except Exception:
            return ""
        finally:
            await browser.close()


async def find_company_owner(company: str, mon: Optional["Monitor"] = None, panel_id: str = "owner1") -> Dict:
    """Searches Google to find the owner/CEO/director of a company."""
    results = {"owner_name": "", "title": "", "linkedin_url": "", "email": ""}

    queries = [
        f'"{company}" CEO OR ejer OR direktør site:linkedin.com',
        f'"{company}" ejer OR CEO OR direktør',
    ]

    for query in queries:
        text = await google_search_text(query, mon, panel_id=panel_id)
        if not text:
            continue

        # Extract LinkedIn URLs
        linkedin_matches = re.findall(
            r'linkedin\.com/in/([a-zA-Z0-9\-_]+)', text
        )
        if linkedin_matches:
            results["linkedin_url"] = f"https://www.linkedin.com/in/{linkedin_matches[0]}"

        # Try to extract a person name near the company name
        name_patterns = [
            rf'{re.escape(company)}\s*[–\-·]\s*([A-ZÆØÅ][a-zæøå]+ [A-ZÆØÅ][a-zæøå]+)',
            r'(?:CEO|Ejer|Direktør|Founder|Partner)[:,]?\s*([A-ZÆØÅ][a-zæøå]+ [A-ZÆØÅ][a-zæøå]+)',
            r'([A-ZÆØÅ][a-zæøå]+ [A-ZÆØÅ][a-zæøå]+)\s*(?:is|er|,)\s*(?:CEO|ejer|direktør)',
        ]
        for pat in name_patterns:
            m = re.search(pat, text)
            if m:
                results["owner_name"] = m.group(1).strip()
                break

        if results["owner_name"] or results["linkedin_url"]:
            break

        await asyncio.sleep(random.uniform(2.0, 3.5))

    return results


async def find_linkedin_email(linkedin_url: str, owner_name: str, company: str,
                               mon: Optional["Monitor"] = None, panel_id: str = "linkedin") -> str:
    """Tries to find an email for a LinkedIn profile via search."""
    if not owner_name and not linkedin_url:
        return ""

    # Search for email using various patterns
    search_queries = []
    if owner_name:
        search_queries.append(f'"{owner_name}" "{company}" email')
        search_queries.append(f'"{owner_name}" kontakt email site:{_extract_domain_from_company(company)}')
    if linkedin_url:
        username = linkedin_url.split("/in/")[-1].rstrip("/")
        search_queries.append(f'"{username}" email contact')

    for query in search_queries:
        text = await google_search_text(query, mon, panel_id=panel_id)
        emails = re.findall(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', text)
        # Filter out generic/noise emails
        for email in emails:
            domain = email.split("@")[1].lower()
            if any(x in domain for x in ["google", "facebook", "example", "sentry", "schema"]):
                continue
            return email
        await asyncio.sleep(random.uniform(1.5, 2.5))

    return ""


def _extract_domain_from_company(company: str) -> str:
    """Rough guess at company domain."""
    clean = re.sub(r'[^a-zA-Z0-9æøåÆØÅ\s]', '', company).strip().lower()
    parts = clean.split()
    if parts:
        return f"{parts[0]}.dk"
    return ""
