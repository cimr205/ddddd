"""
Google Maps scraper via Playwright (headless Chromium).
Playwright downloader selv browseren – ingen key eller betaling krævet.
Internet-adgang: systemets normale netværksforbindelse bruges direkte.
"""
import asyncio
import random
from typing import List, Dict
from playwright.async_api import async_playwright, Page, BrowserContext

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


async def _human_scroll(page: Page, selector: str, times: int = 3):
    for _ in range(times):
        el = await page.query_selector(selector)
        if el:
            await el.evaluate("el => el.scrollBy(0, 800 + Math.random()*400)")
        await asyncio.sleep(random.uniform(0.8, 1.6))


async def _collect_listings(page: Page, target: int) -> List[Dict]:
    results = []
    seen = set()
    stall = 0

    while len(results) < target and stall < 6:
        # Google Maps feed selector – fallback to multiple possible selectors
        cards = await page.query_selector_all('[role="feed"] > div[jsaction], [role="feed"] > div > div[jsaction]')
        before = len(results)

        for card in cards:
            try:
                name_el = await card.query_selector(
                    '.fontHeadlineSmall, .qBF1Pd, [class*="fontHeadline"]'
                )
                if not name_el:
                    continue
                name = (await name_el.inner_text()).strip()
                if not name or name in seen or len(name) < 2:
                    continue
                seen.add(name)

                # Rating
                rating_el = await card.query_selector('.MW4etd')
                rating = (await rating_el.inner_text()).strip() if rating_el else ""

                # Category / type
                cat_el = await card.query_selector('.W4Efsd span[aria-label], .DkEaL')
                category = (await cat_el.inner_text()).strip() if cat_el else ""

                results.append({
                    "name": name,
                    "rating": rating,
                    "category": category,
                    "phone": "",
                    "website": "",
                    "address": "",
                })

                if len(results) >= target:
                    break

            except Exception:
                continue

        if len(results) == before:
            stall += 1
        else:
            stall = 0

        if len(results) < target:
            await _human_scroll(page, '[role="feed"]')

    return results


async def _enrich_listing(page: Page, name: str) -> Dict:
    extra = {"phone": "", "website": "", "address": ""}
    try:
        # Click on the listing to open detail panel
        els = await page.query_selector_all(f'[aria-label="{name}"]')
        clicked = False
        for el in els:
            try:
                await el.click(timeout=2000)
                clicked = True
                break
            except Exception:
                continue

        if not clicked:
            return extra

        await asyncio.sleep(random.uniform(1.2, 2.0))

        # Phone
        phone_el = await page.query_selector(
            'button[data-tooltip*="phone"] [class*="Io6YTe"], '
            '[aria-label*="Phone"] [class*="Io6YTe"], '
            '[data-item-id*="phone"] [class*="Io6YTe"]'
        )
        if phone_el:
            extra["phone"] = (await phone_el.inner_text()).strip()

        # Website
        website_el = await page.query_selector(
            'a[data-tooltip="Open website"], a[aria-label*="website"], a[href*="http"][data-item-id*="authority"]'
        )
        if website_el:
            extra["website"] = await website_el.get_attribute("href") or ""

        # Address
        addr_el = await page.query_selector(
            '[data-item-id*="address"] [class*="Io6YTe"], button[aria-label*="Address"]'
        )
        if addr_el:
            extra["address"] = (await addr_el.inner_text()).strip()

    except Exception:
        pass

    return extra


async def scrape_google_maps(query: str, location: str, count: int = 50) -> List[Dict]:
    """
    Bruger Playwright Chromium (headless) til at tilgå Google Maps via internet.
    Chromium er installeret lokalt af `playwright install chromium`.
    """
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        )

        ctx: BrowserContext = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1280, "height": 800},
            locale="da-DK",
            timezone_id="Europe/Copenhagen",
        )

        # Remove automation fingerprint
        await ctx.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
        """)

        page = await ctx.new_page()

        search = f"{query} {location}".replace(" ", "+")
        url = f"https://www.google.com/maps/search/{search}"

        await page.goto(url, wait_until="domcontentloaded", timeout=30000)

        # Accept cookies if prompted
        try:
            cookie_btn = await page.wait_for_selector(
                'button[aria-label*="Accept"], button[jsname="b3VHJd"]',
                timeout=4000,
            )
            if cookie_btn:
                await cookie_btn.click()
                await asyncio.sleep(1)
        except Exception:
            pass

        try:
            await page.wait_for_selector('[role="feed"]', timeout=15000)
        except Exception:
            await browser.close()
            return []

        # Collect listings without enrichment (fast)
        listings = await _collect_listings(page, count)

        # Enrich top results with phone + website (slower but more data)
        enrich_count = min(len(listings), count)
        for i in range(enrich_count):
            extra = await _enrich_listing(page, listings[i]["name"])
            listings[i].update(extra)
            if i < enrich_count - 1:
                await asyncio.sleep(random.uniform(0.5, 1.0))

        await browser.close()

    return listings
