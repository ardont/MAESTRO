import os
import json
from bs4 import BeautifulSoup
from urllib.parse import urljoin

def parse_local_article(html_file_path):
    with open(html_file_path, 'r', encoding='utf-8') as f:
        html = f.read()
        
    soup = BeautifulSoup(html, 'html.parser')
    
    # 1. Заголовок
    title_el = soup.find('h1')
    if not title_el:
        # Иногда заголовок может быть в классе
        title_el = soup.find(class_=lambda x: x and 'title' in x.lower() and 'article' in x.lower())
    title = title_el.get_text(strip=True) if title_el else "Заголовок не найден"
    
    # 2. Хлебные крошки
    breadcrumbs = []
    # На скрине видно: Главная / Центр поддержки пользователей / Общее / Личный кабинет компании
    # Ищем элементы, содержащие разделитель '/' или ссылки в ряд перед заголовком
    nav = soup.find('nav')
    if nav:
        breadcrumbs = [a.get_text(strip=True) for a in nav.find_all('a')]
    
    # Если nav нет, попробуем найти класс breadcrumb
    if not breadcrumbs:
        bc_container = soup.find(class_=lambda x: x and 'breadcrumb' in x.lower())
        if bc_container:
            breadcrumbs = [el.get_text(strip=True) for el in bc_container.find_all(True) if el.get_text(strip=True)]
    
    # 3. Контент
    # Ищем контейнер с текстом. Обычно это article или div с определенным классом
    content_text = ""
    article = soup.find('article')
    if not article:
        # Эвристика: ищем блок после H1
        if title_el and title_el.parent:
            article = title_el.parent
        else:
            article = soup.body
            
    if article:
        # Убираем скрипты и стили
        for script in article(["script", "style", "nav", "header", "footer"]):
            script.decompose()
        content_text = article.get_text(separator='\n', strip=True)
    
    # 4. Картинки
    images = []
    if article:
        for img in article.find_all('img'):
            src = img.get('src')
            if src:
                images.append(src)
                
    # 5. Документы (PDF)
    documents = []
    if article:
        for a in article.find_all('a', href=True):
            href = a['href']
            if href.lower().endswith('.pdf') or 'download' in href.lower():
                documents.append({
                    "text": a.get_text(strip=True),
                    "url": href
                })
                
    return {
        "file": os.path.basename(html_file_path),
        "title": title,
        "breadcrumbs": breadcrumbs,
        "content_length": len(content_text),
        "content": content_text[:1000] + "..." if len(content_text) > 1000 else content_text,
        "images": images,
        "documents": documents
    }

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    
    # Указывайте путь к вашему сохраненному HTML-файлу
    test_file = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\Maxim\Desktop\фокусы\хакатоны\рлт\агентная система поддержки\dataset\sample.html"
    
    if os.path.exists(test_file):
        result = parse_local_article(test_file)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Файл не найден: {test_file}")
