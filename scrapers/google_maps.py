"""
Google Maps scraper med live screenshot + cursor streaming til dashboard.
Playwright kører en usynlig Chromium browser lokalt – ingen API key krævet.
"""
import asyncio
import base64
import random
from typing import List, Dict, Optional, TYPE_CHECKING

from playwright.async_api import async_playwright, Page, BrowserContext

if TYPE_CHECKING:
    from core.monitor import Monitor

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


async def _screenshot(page: Page, mon: Optional["Monitor"], label: str = "", cx: int = 0, cy: int = 0):
    if mon is None:
        return
    try:
        img = await page.screenshot(type="jpeg", quality=55, full_page=False)
        b64 = base64.b64encode(img).decode()
        url = page.url
        await mon.emit_browser_frame(b64, cx, cy, url, label)
    except Exception:
        pass


async def _click_with_track(page: Page, el, mon: Optional["Monitor"], label: str = ""):
    try:
        box = await el.bounding_box()
        if box:
            cx = int(box["x"] + box["width"] / 2)
            cy = int(box["y"] + box["height"] / 2)
            await page.mouse.move(cx, cy)
            await _screenshot(page, mon, f"Moving to: {label}", cx, cy)
            await asyncio.sleep(random.uniform(0.3, 0.6))
            await el.click(timeout=3000)
            await asyncio.sleep(random.uniform(0.4, 0.8))
            await _screenshot(page, mon, f"Clicked: {label}", cx, cy)
    except Exception:
        pass


async def _human_scroll(page: Page, selector: str, mon: Optional["Monitor"]):
    el = await page.query_selector(selector)
    if el:
        scroll_y = random.randint(700, 1100)
        await el.evaluate(f"el => el.scrollBy(0, {scroll_y})")
        await asyncio.sleep(random.uniform(0.9, 1.5))
        await _screenshot(page, mon, "Scrolling results list...")


async def _collect_listings(page: Page, target: int, mon: Optional["Monitor"]) -> List[Dict]:
    results = []
    seen: set = set()
    stall = 0
    # stall: antal scrolls uden nye resultater – stopper kun når Google Maps
    # ikke har flere at vise (typisk ~120 per søgning på Maps)
    max_stall = 12

    while len(results) < target and stall < max_stall:
        cards = await page.query_selector_all(
            '[role="feed"] > div[jsaction], [role="feed"] > div > div[jsaction]'
        )
        before = len(results)

        for card in cards:
            try:
                name_el = await card.query_selector('.fontHeadlineSmall, .qBF1Pd, [class*="fontHeadline"]')
                if not name_el:
                    continue
                name = (await name_el.inner_text()).strip()
                if not name or name in seen or len(name) < 2:
                    continue
                seen.add(name)

                rating_el = await card.query_selector('.MW4etd')
                rating = (await rating_el.inner_text()).strip() if rating_el else ""

                cat_el = await card.query_selector('.W4Efsd span[aria-label], .DkEaL')
                category = (await cat_el.inner_text()).strip() if cat_el else ""

                results.append({"name": name, "rating": rating, "category": category, "phone": "", "website": "", "address": ""})

                if len(results) >= target:
                    break
            except Exception:
                continue

        if len(results) == before:
            stall += 1
        else:
            stall = 0  # reset – nye resultater fundet
            label = f"Indsamler... {len(results)}" + (f"/{target}" if target < 9999 else "") + " firmaer"
            await _screenshot(page, mon, label)

        if len(results) < target:
            await _human_scroll(page, '[role="feed"]', mon)

    return results


async def _enrich_listing(page: Page, name: str, mon: Optional["Monitor"]) -> Dict:
    extra = {"phone": "", "website": "", "address": ""}
    try:
        els = await page.query_selector_all(f'[aria-label="{name}"], [data-value="{name}"]')
        clicked = False
        for el in els:
            try:
                await _click_with_track(page, el, mon, name)
                clicked = True
                break
            except Exception:
                continue

        if not clicked:
            return extra

        await asyncio.sleep(random.uniform(1.0, 1.8))
        await _screenshot(page, mon, f"Reading details: {name}")

        phone_el = await page.query_selector(
            'button[data-tooltip*="phone"] [class*="Io6YTe"], '
            '[aria-label*="Phone"] [class*="Io6YTe"], '
            '[data-item-id*="phone"] [class*="Io6YTe"]'
        )
        if phone_el:
            extra["phone"] = (await phone_el.inner_text()).strip()

        website_el = await page.query_selector(
            'a[data-tooltip="Open website"], a[aria-label*="website"], '
            'a[href*="http"][data-item-id*="authority"]'
        )
        if website_el:
            extra["website"] = await website_el.get_attribute("href") or ""

        addr_el = await page.query_selector('[data-item-id*="address"] [class*="Io6YTe"]')
        if addr_el:
            extra["address"] = (await addr_el.inner_text()).strip()

    except Exception:
        pass
    return extra


async def scrape_google_maps(
    query: str,
    location: str,
    count: int = 50,
    mon: Optional["Monitor"] = None,
) -> List[Dict]:
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
        await ctx.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
        """)

        page = await ctx.new_page()
        search = f"{query} {location}".replace(" ", "+")
        url = f"https://www.google.com/maps/search/{search}"

        if mon:
            await mon.emit("scraper", "Browser Agent", f"Opening Google Maps: {query} in {location}", "running")

        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await _screenshot(page, mon, f"Google Maps: {query} in {location}")

        # Accept cookies
        try:
            btn = await page.wait_for_selector('button[aria-label*="Accept"], button[jsname="b3VHJd"]', timeout=4000)
            if btn:
                await _click_with_track(page, btn, mon, "Accept cookies")
        except Exception:
            pass

        try:
            await page.wait_for_selector('[role="feed"]', timeout=15000)
        except Exception:
            await browser.close()
            return []

        await _screenshot(page, mon, f"Search results loaded – collecting firms...")

        listings = await _collect_listings(page, count, mon)

        if mon:
            await mon.emit("scraper", "Browser Agent", f"Enriching {len(listings)} firms with details...", "running")

        for i, listing in enumerate(listings):
            extra = await _enrich_listing(page, listing["name"], mon)
            listings[i].update(extra)
            if i < len(listings) - 1:
                await asyncio.sleep(random.uniform(0.4, 0.9))

        await _screenshot(page, mon, f"Done – {len(listings)} firms collected")
        await browser.close()

    return listings
