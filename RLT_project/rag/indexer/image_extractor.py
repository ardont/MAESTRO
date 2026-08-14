import os
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from pathlib import Path
from .config import MEDIA_DIR

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# Кэш извлеченных изображений по URL статьи
_URL_IMAGES_CACHE = {}

def extract_images_from_markdown(text: str) -> list:
    """
    Извлекает ссылки на изображения из markdown текста (![alt](url) и <img src="...">)
    """
    images = []
    # Markdown format ![alt](url)
    md_matches = re.findall(r'!\[.*?\]\((https?://[^\s\)]+|\/[^\s\)]+)\)', text)
    for img_url in md_matches:
        if img_url not in images:
            images.append(img_url)
            
    # HTML format <img ... src="url" ...>
    html_matches = re.findall(r'<img[^>]+src=["\'](https?://[^"\']+|\/[^"\']+)["\']', text, re.IGNORECASE)
    for img_url in html_matches:
        if img_url not in images:
            images.append(img_url)
            
    return images

def fetch_page_images(url: str, timeout: int = 5) -> list:
    """
    Парсит страницу по URL и извлекает ссылки на скриншоты/иллюстрации из основного контента
    """
    if not url or not url.startswith("http"):
        return []
        
    if url in _URL_IMAGES_CACHE:
        return _URL_IMAGES_CACHE[url]
        
    images = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            main_el = soup.find('main') or soup.find('article') or soup.find(class_='content') or soup.find(class_='region-content')
            container = main_el if main_el else soup
            
            for img in container.find_all('img'):
                src = img.get('src') or img.get('data-src')
                if not src:
                    continue
                # Игнорируем мелкие иконки/логотипы
                if any(ignored in src.lower() for ignored in ['icon', 'logo', 'badge', 'avatar', 'pixel', 'counter', 'svg']):
                    continue
                    
                full_src = urljoin(url, src)
                if full_src not in images:
                    images.append(full_src)
    except Exception:
        pass
        
    _URL_IMAGES_CACHE[url] = images
    return images

def extract_pdf_images(pdf_path: str, max_images: int = 5) -> list:
    """
    Извлекает встроенные картинки из PDF-файла с помощью PyMuPDF (fitz)
    """
    saved_images = []
    try:
        import fitz
        doc = fitz.open(pdf_path)
        pdf_name = Path(pdf_path).stem
        
        img_count = 0
        for page_idx, page in enumerate(doc):
            for img_index, img in enumerate(page.get_images(full=True)):
                if img_count >= max_images:
                    break
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]
                
                # Фильтруем слишком маленькие изображения (иконки/линии < 5KB)
                if len(image_bytes) < 5000:
                    continue
                    
                img_filename = f"{pdf_name}_p{page_idx+1}_{img_index}.{image_ext}"
                out_path = MEDIA_DIR / img_filename
                
                if not out_path.exists():
                    with open(out_path, "wb") as f:
                        f.write(image_bytes)
                        
                saved_images.append(f"/media/kb_images/{img_filename}")
                img_count += 1
                
            if img_count >= max_images:
                break
    except Exception:
        pass
        
    return saved_images
