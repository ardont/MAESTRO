import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import asyncio
from playwright.async_api import async_playwright

async def inspect_ui():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})

        print("Opening supplier page...")
        await page.goto("https://zakupki.mos.ru/knowledgebase/main/supplier", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)

        # Print all headers and buttons
        elements = await page.locator("h1, h2, h3, h4, h5, button, [role='button']").all()
        print(f"Found {len(elements)} header/button elements:")
        for el in elements[:30]:
            tag = await el.evaluate("e => e.tagName")
            txt = (await el.inner_text()).strip()
            if txt:
                print(f"  <{tag}>: {txt[:60]}")

        # Let's inspect the main container text
        content = await page.inner_text("main, #root, #app, body")
        print("\nPage text snippet (first 1000 chars):\n", content[:1000])

        await browser.close()

if __name__ == "__main__":
    asyncio.run(inspect_ui())
