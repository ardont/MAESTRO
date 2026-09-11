import asyncio
import json
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        async def handle_request(request):
            if 'Article' in request.url or 'graphql' in request.url:
                print(f"\\n=== API REQUEST: {request.url} [{request.method}] ===")
                try:
                    print("Headers:", request.headers)
                    if request.post_data:
                        print("Post Data:", request.post_data)
                except Exception as e:
                    print("Err:", e)

        async def handle_response(response):
            if 'Article' in response.url or 'graphql' in response.url:
                print(f"\\n=== API RESPONSE: {response.url} [{response.status}] ===")
                try:
                    text = await response.text()
                    print("Body[:2000]:", text[:2000])
                except Exception as e:
                    print("Err:", e)
                    
        page.on('request', handle_request)
        page.on('response', handle_response)
        
        print("Go")
        await page.goto('https://zakupki.mos.ru/knowledgebase/article/details/ais/218960', wait_until='domcontentloaded')
        await page.wait_for_timeout(10000)
        await browser.close()

asyncio.run(run())
