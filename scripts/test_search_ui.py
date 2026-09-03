import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import asyncio
from playwright.async_api import async_playwright
import json

async def test_search():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})

        network_requests = []
        async def on_request(req):
            url = req.url
            if any(k in url.lower() for k in ["api", "graphql", "search", "article", "knowledge"]):
                network_requests.append({"method": req.method, "url": url, "post_data": req.post_data})

        page.on("request", on_request)

        print("Navigating to https://zakupki.mos.ru/knowledgebase/main ...")
        await page.goto("https://zakupki.mos.ru/knowledgebase/main", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)

        # Look for search input
        inputs = await page.locator("input").all()
        print(f"Found {len(inputs)} input fields.")
        for idx, inp in enumerate(inputs):
            placeholder = await inp.get_attribute("placeholder")
            name = await inp.get_attribute("name")
            inp_type = await inp.get_attribute("type")
            print(f"Input #{idx}: type={inp_type}, placeholder={placeholder}, name={name}")

        # If there's an input with search/поиск
        search_input = None
        for inp in inputs:
            ph = (await inp.get_attribute("placeholder") or "").lower()
            if "поиск" in ph or "вопрос" in ph or "искать" in ph or "найти" in ph:
                search_input = inp
                break

        if not search_input and inputs:
            search_input = inputs[0]

        if search_input:
            print("Typing search query: 'котировочная сессия'...")
            await search_input.fill("котировочная сессия")
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(4000)

            # Check rendered search results
            body_text = await page.inner_text("body")
            print("Body text preview after search:\n", body_text[:800])

            # Check links
            links = await page.locator("a").all()
            print(f"Found {len(links)} links after search.")
            article_links = []
            for link in links:
                href = await link.get_attribute("href")
                text = (await link.inner_text()).strip()
                if href and ("article" in href or "knowledge" in href or "details" in href):
                    article_links.append({"text": text, "href": href})
            print(f"Matching article links ({len(article_links)}):")
            for al in article_links[:10]:
                print(f"  {al['text'][:50]} -> {al['href']}")

        print("\nCaptured network requests:")
        for nr in network_requests:
            print(f"  {nr['method']} {nr['url']}")
            if nr['post_data']:
                print(f"     payload: {nr['post_data'][:150]}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_search())
