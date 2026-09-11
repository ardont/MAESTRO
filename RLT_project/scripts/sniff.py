import asyncio
import json
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        async def handle_response(response):
            if 'Article' in response.url or 'graphql' in response.url:
                try:
                    body = await response.json()
                    print(f"\\n=== API RESPONSE: {response.url} ===")
                    print(json.dumps(body, ensure_ascii=False, indent=2)[:2000]) # Print first 2000 chars
                except:
                    pass
                    
        page.on('response', handle_response)
        print("Go")
        await page.goto('https://zakupki.mos.ru/knowledgebase/article/details/ais/218960', wait_until='domcontentloaded')
        await page.wait_for_timeout(10000)
        await browser.close()

asyncio.run(run())
