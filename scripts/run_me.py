import asyncio
from playwright.async_api import async_playwright
import json
import os

CATEGORY_URLS = [
    "https://zakupki.mos.ru/knowledgebase/main/supplier",
    "https://zakupki.mos.ru/knowledgebase/main/customer",
    "https://zakupki.mos.ru/knowledgebase/main/instruction",
    "https://zakupki.mos.ru/knowledgebase/main/general"
]

async def auto_scroll(page):
    await page.evaluate("""async () => {
        await new Promise((resolve) => {
            let totalHeight = 0;
            let distance = 300;
            let timer = setInterval(() => {
                let scrollHeight = document.body.scrollHeight;
                window.scrollBy(0, distance);
                totalHeight += distance;
                if (totalHeight >= scrollHeight - window.innerHeight) {
                    clearInterval(timer);
                    resolve();
                }
            }, 200);
        });
    }""")

async def main():
    print("Открываю видимый браузер...")
    all_links = set()
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=['--start-maximized'])
        context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = await context.new_page()
        
        for url in CATEGORY_URLS:
            print(f"\nПерехожу по ссылке: {url}")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(4000)
                
                # Закрываем окно региона, если оно есть
                region_btn = page.locator("text=Да, верно").first
                if await region_btn.count() > 0:
                    await region_btn.click(force=True)
                    await page.wait_for_timeout(1000)
                
                # Пытаемся кликать 'Показать еще'
                print("Прокручиваю список и ищу новые статьи...")
                while True:
                    more_btn = page.locator("text=Показать еще").first
                    if await more_btn.count() > 0 and await more_btn.is_visible():
                        await more_btn.click(force=True)
                        await page.wait_for_timeout(2000)
                    else:
                        break
                
                await auto_scroll(page)
                await page.wait_for_timeout(2000)
                
                # Собираем ссылки
                links = await page.locator('a[href*="/knowledgebase/article/"]').all()
                count_before = len(all_links)
                for link in links:
                    href = await link.get_attribute('href')
                    if href and ('/cms/' in href or '/details/' in href):
                        full_url = "https://zakupki.mos.ru" + href if href.startswith('/') else href
                        all_links.add(full_url)
                
                print(f"Найдено {len(all_links) - count_before} новых ссылок в этой категории.")
                
            except Exception as e:
                print(f"Ошибка на {url}: {e}")
                
        await browser.close()
        
    out_path = os.path.join(os.path.dirname(__file__), '..', 'dataset', 'all_516_links.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(list(all_links), f, ensure_ascii=False, indent=2)
        
    print(f"\nГОТОВО! Собрано {len(all_links)} уникальных ссылок.")
    print(f"Ссылки сохранены в {out_path}")

if __name__ == "__main__":
    asyncio.run(main())
