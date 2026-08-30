import json
import os
import httpx
from urllib.parse import urlparse
import time
import re

DATASET_CLEAN = os.path.join(os.path.dirname(__file__), '..', 'dataset', 'kb_clean.json')
IMAGES_DIR = os.path.join(os.path.dirname(__file__), '..', 'dataset', 'images')
DATASET_FINAL = os.path.join(os.path.dirname(__file__), '..', 'dataset', 'kb_final.json')

def download_image(url, save_path):
    try:
        if not url.startswith('http'):
            if url.startswith('/'):
                url = f"https://zakupki.mos.ru{url}"
            else:
                return False
                
        # Не скачиваем base64 и svg-иконки
        if url.startswith('data:') or '.svg' in url.lower():
            return False
            
        response = httpx.get(url, timeout=15.0, verify=False)
        if response.status_code == 200:
            with open(save_path, 'wb') as f:
                f.write(response.content)
            return True
        else:
            print(f"Ошибка {response.status_code} при скачивании {url}")
            return False
    except Exception as e:
        print(f"Ошибка при скачивании {url}: {e}")
        return False

def main():
    os.makedirs(IMAGES_DIR, exist_ok=True)
    
    print(f"Читаем файл {DATASET_CLEAN}...")
    with open(DATASET_CLEAN, 'r', encoding='utf-8') as f:
        articles = json.load(f)
        
    print(f"Всего статей для обработки: {len(articles)}")
    
    img_pattern = re.compile(r'!\[(.*?)\]\((.*?)\)')
    
    downloaded_count = 0
    total_images = 0
    
    for i, article in enumerate(articles):
        text = article.get('text', '')
        
        # Ищем все markdown-картинки в тексте
        matches = img_pattern.findall(text)
        total_images += len(matches)
        
        for alt, img_url in matches:
            # Формируем локальное имя файла
            parsed_url = urlparse(img_url)
            filename = os.path.basename(parsed_url.path)
            if not filename or '.' not in filename:
                filename = f"img_{int(time.time()*1000)}.png"
                
            local_filename = f"{article['file_name']}_{filename}"
            # Убираем недопустимые символы
            local_filename = "".join(c for c in local_filename if c.isalnum() or c in ('.', '_', '-'))
            local_path = os.path.join(IMAGES_DIR, local_filename)
            
            # Скачиваем файл
            print(f"Скачиваем {img_url} -> {local_filename}")
            if download_image(img_url, local_path):
                downloaded_count += 1
                # Заменяем URL в тексте на локальный путь
                local_markdown_path = f"images/{local_filename}"
                old_md = f"![{alt}]({img_url})"
                new_md = f"![{alt}]({local_markdown_path})"
                text = text.replace(old_md, new_md)
                
        # Обновляем текст статьи
        article['text'] = text
        
    print(f"\nСохраняем итоговый датасет в {DATASET_FINAL}...")
    with open(DATASET_FINAL, 'w', encoding='utf-8') as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
        
    print(f"Готово! Скачано изображений: {downloaded_count} из {total_images}.")

if __name__ == "__main__":
    main()
