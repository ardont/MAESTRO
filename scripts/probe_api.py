import asyncio
import json
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # Перехватываем GraphQL запросы
        async def handle_request(request):
            if "graphql" in request.url and request.method == "POST":
                print(f"\n[GRAPHQL REQUEST]")
                print(f"URL: {request.url}")
                print(f"Headers: {request.headers}")
                print(f"Post Data: {request.post_data}")
                
        async def handle_response(response):
            if "graphql" in response.url and response.request.method == "POST":
                print(f"\n[GRAPHQL RESPONSE]")
                try:
                    text = await response.text()
                    print(f"Body: {text[:1000]}")
                except Exception as e:
                    print(f"Error reading response: {e}")

        page.on("request", handle_request)
        page.on("response", handle_response)
        
        url = "https://zakupki.mos.ru/knowledgebase/article/details/cms/472g7hmnnf0xc46hb5x2pse2mr"
        print(f"Navigating to {url}")
        
        await page.goto(url, wait_until="networkidle", timeout=30000)
        
        await asyncio.sleep(5)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
