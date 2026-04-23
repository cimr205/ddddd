import asyncio
import re
from typing import List, Dict, Optional
from playwright.async_api import async_playwright, Page


async def _scroll_feed(page: Page, target: int, seen: set) -> List[Dict]:
    results = []
    stall = 0

    while len(results) < target and stall < 5:
        cards = await page.query_selector_all('[role="feed"] > div[jsaction]')
        before = len(results)

        for card in cards:
            try:
                name_el = await card.query_selector(".fontHeadlineSmall, .qBF1Pd")
                if not name_el:
                    continue
                name = (await name_el.inner_text()).strip()
                if not name or name in seen:
                    continue
                seen.add(name)

                rating_el = await card.query_selector(".MW4etd")
                rating = (await rating_el.inner_text()).strip() if rating_el else ""

                address_el = await card.query_selector(".W4Efsd:last-child .W4Efsd:last-child span:last-child")
                address = (await address_el.inner_text()).strip() if address_el else ""

                results.append({"name": name, "rating": rating, "address": address})

                if len(results) >= target:
                    break
            except Exception:
                continue

        if len(results) == before:
            stall += 1
        else:
            stall = 0

        if len(results) < target:
            feed = await page.query_selector('[role="feed"]')
            if feed:
                await feed.evaluate("el => el.scrollBy(0, 1200)")
            await asyncio.sleep(1.2)

    return results


async def _enrich_listing(page: Page, result: Dict) -> Dict:
    try:
        name_els = await page.query_selector_all(f'[aria-label="{result["name"]}"]')
        for el in name_els:
            try:
                await el.click(timeout=3000)
                break
            except Exception:
                continue

        await asyncio.sleep(1.5)

        # Phone
        phone_el = await page.query_selector('[data-tooltip="Copy phone number"], [aria-label*="phone"]')
        if phone_el:
            result["phone"] = (await phone_el.get_attribute("aria-label") or "").replace("Phone:", "").strip()

        # Website
        website_el = await page.query_selector('a[data-tooltip="Open website"], a[aria-label*="website"]')
        if website_el:
            result["website"] = await website_el.get_attribute("href") or ""
    except Exception:
        pass
    return result


async def scrape_google_maps(query: str, location: str, count: int = 50) -> List[Dict]:
    leads = []
    seen: set = set()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        page = await ctx.new_page()

        search = f"{query} {location}".replace(" ", "+")
        url = f"https://www.google.com/maps/search/{search}"
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)

        try:
            await page.wait_for_selector('[role="feed"]', timeout=15000)
        except Exception:
            await browser.close()
            return []

        leads = await _scroll_feed(page, count, seen)
        await browser.close()

    return leads
