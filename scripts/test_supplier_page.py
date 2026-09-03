import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import asyncio
from playwright.async_api import async_playwright
import json

async def test_supplier_page():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})

        network_calls = []
        async def on_resp(resp):
            url = resp.url
            if any(k in url.lower() for k in ["api", "graphql", "knowledge"]):
                if not any(ext in url.lower() for ext in [".js", ".css", ".png", ".jpg", ".svg"]):
                    try:
                        ct = resp.headers.get("content-type", "")
                        if "json" in ct:
                            text = await resp.text()
                            network_calls.append({"url": url, "status": resp.status, "body": text[:300]})
                        else:
                            network_calls.append({"url": url, "status": resp.status, "content_type": ct})
                    except Exception:
                        pass

        page.on("response", on_resp)

        print("Navigating to https://zakupki.mos.ru/knowledgebase/main/supplier ...")
        await page.goto("https://zakupki.mos.ru/knowledgebase/main/supplier", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(4000)

        # Region popup
        try:
            region_btn = page.locator("text=Да, верно").first
            if await region_btn.count() > 0 and await region_btn.is_visible():
                await region_btn.click(force=True)
                await page.wait_for_timeout(1000)
        except Exception:
            pass

        # Check links
        links = await page.locator("a").all()
        article_links = []
        for l in links:
            href = await l.get_attribute("href")
            txt = (await l.inner_text()).strip()
            if href and ("article" in href or "details" in href):
                article_links.append((txt, href))

        print(f"Found {len(article_links)} article links on supplier page:")
        for txt, href in article_links[:15]:
            print(f"  {txt[:50]} -> {href}")

        print("\nCaptured API calls:")
        for call in network_calls:
            print(f"  {call['status']} | {call['url']}")
            if "body" in call:
                print(f"    Body snippet: {call['body'][:150]}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_supplier_page())
