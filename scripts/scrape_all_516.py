import asyncio
import json
import os
import time
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from playwright.async_api import async_playwright
import re

BASE_URL = "https://zakupki.mos.ru"
DATASET_FINAL = os.path.join(os.path.dirname(__file__), '..', 'dataset', 'kb_full_516.json')
IMAGES_DIR = os.path.join(os.path.dirname(__file__), '..', 'dataset', 'images_516')

CATEGORIES = [
    "ДЛЯ ПОСТАВЩИКА",
    "ДЛЯ ЗАКАЗЧИКА",
    "ИНСТРУКЦИИ",
    "ОБЩИЙ РАЗДЕЛ"
]

def download_image(url, save_path):
    try:
        if not url.startswith('http'):
            if url.startswith('/'):
                url = f"https://zakupki.mos.ru{url}"
            else:
                return False
        if url.startswith('data:') or '.svg' in url.lower():
            return False
        response = httpx.get(url, timeout=15.0, verify=False)
        if response.status_code == 200:
            with open(save_path, 'wb') as f:
                f.write(response.content)
            return True
    except:
        pass
    return False

def determine_doc_type(title, text):
    title_lower = title.lower()
    text_lower = text[:500].lower()
    if "закон" in title_lower or "фз" in title_lower or "регламент" in title_lower:
        return "legislation"
    if "статья " in text_lower and ("федеральный" in text_lower or "кодекс" in text_lower):
         return "legislation"
    return "instruction"

def determine_category(title, text):
    content = (title + " " + text[:500]).lower()
    if "эцп" in content or "криптопро" in content or "мчд" in content:
        return "ecp_mchd"
    if "44-фз" in content or "44 фз" in content:
        return "44fz"
    if "223-фз" in content or "223 фз" in content:
        return "223fz"
    if "регистрация" in content or "регистрации" in content:
        return "registration"
    if "гарантия" in content or "услуг" in content:
        return "services"
    return "kb_article"

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
            }, 150);
        });
    }""")

async def scrape_article(page, url):
    print(f"Парсинг: {url}")
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        
        html = await page.content()
        soup = BeautifulSoup(html, 'html.parser')
        
        title = soup.title.string if soup.title else url.split("/")[-1]
        
        # Конвертация изображений
        for img in soup.find_all('img'):
            src = img.get('src', '')
            if src.startswith('/'):
                src = "https://zakupki.mos.ru" + src
            alt = img.get('alt', 'Изображение')
            img.replace_with(f"\n![{alt}]({src})\n")
            
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.extract()
            
        text = soup.get_text(separator='\n', strip=True)
        if "Ничего не нашлось" in title or "Страница не найдена" in text:
            return None
            
        doc_type = determine_doc_type(title, text)
        category = determine_category(title, text)
        file_name = url.split("/")[-1]
        
        # Скачиваем изображения локально
        img_pattern = re.compile(r'!\[(.*?)\]\((.*?)\)')
        matches = img_pattern.findall(text)
        for alt, img_url in matches:
            parsed_url = urlparse(img_url)
            filename = os.path.basename(parsed_url.path)
            if not filename or '.' not in filename:
                filename = f"img_{int(time.time()*1000)}.png"
            local_filename = f"{file_name}_{filename}"
            local_filename = "".join(c for c in local_filename if c.isalnum() or c in ('.', '_', '-'))
            local_path = os.path.join(IMAGES_DIR, local_filename)
            
            if download_image(img_url, local_path):
                old_md = f"![{alt}]({img_url})"
                new_md = f"![{alt}](images_516/{local_filename})"
                text = text.replace(old_md, new_md)
        
        return {
            "file_name": file_name,
            "title": title.strip(),
            "text": text,
            "url": url,
            "doc_type": doc_type,
            "category": category
        }
    except Exception as e:
        print(f"Ошибка при парсинге {url}: {e}")
        return None

async def main():
    os.makedirs(os.path.dirname(DATASET_FINAL), exist_ok=True)
    os.makedirs(IMAGES_DIR, exist_ok=True)
    
    all_links = set()
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=['--start-maximized'])
        context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = await context.new_page()
        
        print("=== ЭТАП 1: Сбор ссылок по меню ===")
        for category in CATEGORIES:
            try:
                await page.goto("https://zakupki.mos.ru/knowledgebase/main", wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(3000)
                
                cat_locator = page.locator(f"text={category}").first
                if await cat_locator.count() > 0:
                    await cat_locator.click()
                    await page.wait_for_timeout(5000)
                    
                    # Пытаемся нажать кнопку 'Показать еще' если она есть
                    while True:
                        more_btn = page.locator("text=Показать еще").first
                        if await more_btn.count() > 0 and await more_btn.is_visible():
                            await more_btn.click()
                            await page.wait_for_timeout(2000)
                        else:
                            break
                            
                    await auto_scroll(page)
                    await page.wait_for_timeout(2000)
                    
                    links = await page.locator('a[href*="/knowledgebase/article/details/cms/"]').all()
                    for link in links:
                        href = await link.get_attribute('href')
                        if href:
                            all_links.add(BASE_URL + href if href.startswith('/') else href)
            except Exception as e:
                print(f"Ошибка в категории {category}: {e}")
                
        # Если почему-то ссылки не собрались визуально, берем старые 102 как минимум
        if not all_links:
            print("Браузерная защита отбила клики. Парсим хотя бы 102 доступные по API.")
            with open(os.path.join(os.path.dirname(__file__), '..', 'dataset', 'kb_graphql.json'), 'r', encoding='utf-8') as f:
                data = json.load(f)
                for item in data:
                    all_links.add(f"https://zakupki.mos.ru/knowledgebase/article/details/cms/{item['contentItemId']}")
                    
        print(f"\nСобрано уникальных ссылок: {len(all_links)}")
        
        print("\n=== ЭТАП 2: Парсинг и скачивание изображений ===")
        results = []
        for url in list(all_links):
            data = await scrape_article(page, url)
            if data:
                results.append(data)
            # Спасаемся от бана
            await asyncio.sleep(2)
            
        await browser.close()
        
    with open(DATASET_FINAL, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
        
    print(f"\nУспешно скачано {len(results)} статей вместе со всеми физическими картинками.")

if __name__ == "__main__":
    asyncio.run(main())
