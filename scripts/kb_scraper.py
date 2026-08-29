import asyncio
import json
import os
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# Список стартовых ссылок (из задания)
START_URLS = [
    "https://zakupki.mos.ru/knowledgebase/article/regulation/cms",
    "https://zakupki.mos.ru/knowledgebase/article/details/cms/472g7hmnnf0xc46hb5x2pse2mr",
    "https://zakupki.mos.ru/knowledgebase/article/details/cms/48caq6vpp4pn97wbaxsfxnbn4b",
    "https://zakupki.mos.ru/knowledgebase/article/details/cms/4wx0ezbebam39096dnqdz15v4s",
    "https://zakupki.mos.ru/knowledgebase/article/details/cms/4zmpebqdkyq9dzzpdhr538qxn7",
    "https://zakupki.mos.ru/knowledgebase/article/details/cms/46ac0zd3ewy0tt5ffx1h9zd5mx",
    "https://zakupki.mos.ru/knowledgebase/article/details/cms/4kh3hws0e8wknzdkd59xr15qwz",
    "https://zakupki.mos.ru/knowledgebase/article/details/cms/490f7bzfmrfvs2sebfb95t9rwg",
    "https://zakupki.mos.ru/knowledgebase/article/details/cms/4jx54dvpmthnr0w1e0xb7cvxx0",
    "https://zakupki.mos.ru/knowledgebase/article/details/cms/4d8rc6m7hewj5yxgs2dj0fc15g",
    "https://zakupki.mos.ru/knowledgebase/article/details/cms/4p59tn72h3z2c3d3rfcz3jmtmp",
    "https://zakupki.mos.ru/knowledgebase/article/details/cms/4nsazjshjxssn1wm105z3p5hm3",
    "https://zakupki.mos.ru/knowledgebase/article/details/cms/465ybcpkg8x0d0acg2qg3hb05w",
    "https://zakupki.mos.ru/knowledgebase/article/details/cms/4jhye2315cmgd7c0b77s4d9cnn",
    "https://zakupki.mos.ru/knowledgebase/article/details/cms/4cqhkb45zqcscws8d9wbzg0qxq",
    "https://zakupki.mos.ru/knowledgebase/article/details/cms/476pxvm6xjaw8r4fyfw20hxc4a"
]

DATASET_PATH = os.path.join(os.path.dirname(__file__), '..', 'dataset', 'kb_articles.json')

async def scrape_article(page, url):
    print(f"Парсинг: {url}")
    try:
        # Переходим на страницу, ждем пока сеть успокоится (чтобы React успел отрендерить страницу)
        await page.goto(url, wait_until="networkidle")
        
        # Можно добавить ожидание специфичного селектора, где лежит статья (зависит от верстки)
        # await page.wait_for_selector('.article-content', timeout=5000)
        
        html = await page.content()
        soup = BeautifulSoup(html, 'html.parser')
        
        # TODO: Уточнить селекторы, когда посмотрим на реальную верстку в браузере.
        # Пока просто собираем весь текст (убрав скрипты и стили)
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.extract()
            
        title = soup.title.string if soup.title else url.split("/")[-1]
        
        # Получаем чистый текст
        text = soup.get_text(separator='\n', strip=True)
        
        return {
            "url": url,
            "title": title.strip(),
            "content": text
        }
    except Exception as e:
        print(f"Ошибка при парсинге {url}: {e}")
        return None

async def main():
    os.makedirs(os.path.dirname(DATASET_PATH), exist_ok=True)
    results = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        for url in START_URLS:
            data = await scrape_article(page, url)
            if data:
                results.append(data)
                
            # Небольшая пауза, чтобы не забанили
            await asyncio.sleep(2)
            
        await browser.close()
        
    # Сохраняем в JSON (как договорились)
    with open(DATASET_PATH, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=4)
        
    print(f"Парсинг завершен. Сохранено {len(results)} статей в {DATASET_PATH}")

if __name__ == "__main__":
    asyncio.run(main())
