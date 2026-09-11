import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import json
from urllib.parse import urljoin

async def parse_article(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        print(f"Загрузка страницы: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        
        print("Ожидание отрисовки контента (ждем появления заголовка)...")
        try:
            await page.wait_for_selector('h1', timeout=30000)
            await page.wait_for_timeout(2000) # Даем еще пару секунд на подгрузку картинок
        except Exception as e:
            print(f"Не удалось дождаться H1: {e}")
        
        # Получаем полностью отрендеренный HTML
        html = await page.content()
        await browser.close()
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # 1. Парсинг заголовка (обычно H1)
        title_element = soup.find('h1')
        title = title_element.text.strip() if title_element else "Без заголовка"
        
        # 2. Парсинг хлебных крошек
        breadcrumbs = []
        # Пытаемся найти элементы хлебных крошек по типичным классам
        breadcrumb_container = soup.find(class_=lambda x: x and 'breadcrumb' in x.lower())
        if breadcrumb_container:
            for item in breadcrumb_container.find_all('a'):
                breadcrumbs.append(item.text.strip())
        
        if not breadcrumbs:
            # Альтернативный поиск по вложенным ссылкам перед H1
            # Это эвристика, если нет явного класса breadcrumb
            pass
            
        # 3. Парсинг контента статьи
        # Ищем основной контейнер статьи. 
        # На mos.ru это может быть 'article', класс 'content' и т.д.
        article_body = soup.find('article') or soup.find(class_=lambda x: x and ('content' in x.lower() or 'article' in x.lower()))
        content_text = article_body.get_text(separator='\n', strip=True) if article_body else soup.body.get_text(separator='\n', strip=True)
        
        # 4. Парсинг картинок
        images = []
        target_container = article_body if article_body else soup
        for img in target_container.find_all('img'):
            src = img.get('src')
            if src:
                # Преобразуем относительные ссылки в абсолютные
                absolute_url = urljoin(url, src)
                images.append(absolute_url)
                
        # 5. Парсинг PDF (и других документов)
        documents = []
        for a in target_container.find_all('a', href=True):
            href = a['href']
            if href.lower().endswith('.pdf') or 'download' in href.lower():
                absolute_url = urljoin(url, href)
                documents.append({
                    "text": a.text.strip(),
                    "url": absolute_url
                })
                
        result = {
            "url": url,
            "title": title,
            "breadcrumbs": breadcrumbs,
            "content": content_text[:1000] + "..." if len(content_text) > 1000 else content_text, # Обрезаем для вывода
            "images": images,
            "documents": documents
        }
        
        return result

if __name__ == "__main__":
    url_to_parse = "https://zakupki.mos.ru/knowledgebase/article/details/ais/218960"
    
    # Запуск асинхронной функции
    result = asyncio.run(parse_article(url_to_parse))
    
    # Красивый вывод результата
    print(json.dumps(result, ensure_ascii=False, indent=2))
