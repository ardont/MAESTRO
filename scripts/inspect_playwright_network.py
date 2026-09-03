import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import asyncio
from playwright.async_api import async_playwright
import json

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        api_calls = []

        async def on_response(response):
            url = response.url
            if any(k in url.lower() for k in ["api", "graphql", "knowledge", "article", "article/"]):
                if not any(ext in url.lower() for ext in [".js", ".css", ".png", ".jpg", ".svg", ".woff"]):
                    try:
                        ct = response.headers.get("content-type", "")
                        if "json" in ct:
                            body = await response.text()
                            api_calls.append({"url": url, "status": response.status, "body": body[:500]})
                        else:
                            api_calls.append({"url": url, "status": response.status, "content_type": ct})
                    except Exception as e:
                        api_calls.append({"url": url, "status": response.status, "error": str(e)})

        page.on("response", on_response)

        test_url = "https://zakupki.mos.ru/knowledgebase/article/171501"
        print(f"Navigating to {test_url}...")
        try:
            await page.goto(test_url, wait_until="networkidle", timeout=30000)
        except Exception as e:
            print(f"Goto error / timeout: {e}")

        await page.wait_for_timeout(3000)

        title = await page.title()
        content = await page.content()
        text = await page.inner_text("body")

        print("=== PAGE INFO ===")
        print("Title:", title)
        print("Text length:", len(text))
        print("Text preview:\n", text[:600])

        print("\n=== RELEVANT API CALLS ===")
        for call in api_calls:
            print(f"-> {call['status']} | {call['url']}")
            if "body" in call:
                print(f"   Response: {call['body'][:200]}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(test())
