"""
Модуль: download_images.py

Назначение:
  Автоматическое скачивание и локализация всех графических иллюстраций и скриншотов
  интерфейса Портала Поставщиков Москвы (zakupki.mos.ru).

Какую проблему решает на Портале Поставщиков:
  1. В статьях и регламентах Портала содержится множество критически важных скриншотов:
     - Где находится кнопка «Подать оферту» в котировочной сессии.
     - Как выглядит форма заполнения характеристик СТЕ.
     - Окно выбора сертификата ЭЦП и настройки плагина КриптоПро.
  2. Если использовать прямые ссылки на внешний сервер (zakupki.mos.ru/cms/...), то:
     - При недоступности сайта или изменениях в CMS картинки перестанут отображаться.
     - Пользовательский интерфейс поддержки не сможет надежно отображать скриншоты в чате.
  3. Модуль находит все ссылки вида `![alt](url)` в Markdown-тексте статей,
     скачивает реальные изображения в папку `dataset/images/` и заменяет внешние веб-ссылки
     на локальные относительные пути вида `images/<file_name>_<image_name>.png`.

Входные данные:
  - dataset/kb_clean.json (очищенный датасет в формате Markdown)

Выходные данные:
  - dataset/images/* (скачанные физические файлы картинок)
  - dataset/kb_clean.json и dataset/kb_final.json (датасет с обновленными локальными путями)
"""

import json
import os
import sys
import httpx
from urllib.parse import urlparse, unquote
import time
import re

# Настройка кодировки UTF-8 для Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_CLEAN = os.path.join(BASE_DIR, 'dataset', 'kb_clean.json')
IMAGES_DIR = os.path.join(BASE_DIR, 'dataset', 'images')
DATASET_FINAL = os.path.join(BASE_DIR, 'dataset', 'kb_final.json')

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
}


def download_image(url: str, save_path: str) -> bool:
    """
    Скачивает изображение по указанному URL и сохраняет по локальному пути.
    
    Особенности и граничные случаи:
      - Если файл уже существует и не пустой — пропускает скачивание (кэш).
      - Игнорирует data:base64 и служебные .svg-иконки.
      - Автоматически дополняет относительные пути (начинающиеся с /) базовым доменом Портала.
      - Обрабатывает таймауты и сетевые сбои без остановки всего пайплайна.
    """
    if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
        return True  # Уже скачано ранее

    try:
        if not url.startswith('http'):
            if url.startswith('/'):
                url = f"https://zakupki.mos.ru{url}"
            else:
                return False

        # Не сохраняем inline data-uri и служебные векторные иконки интерфейса
        if url.startswith('data:') or '.svg' in url.lower():
            return False

        with httpx.Client(headers=HEADERS, timeout=20.0, verify=False, follow_redirects=True) as client:
            response = client.get(url)
            if response.status_code == 200:
                # Проверяем, что получен не HTML с ошибкой 404
                content_type = response.headers.get('content-type', '')
                if 'html' in content_type and len(response.content) < 5000:
                    return False
                with open(save_path, 'wb') as f:
                    f.write(response.content)
                return True
            else:
                return False
    except Exception as e:
        return False


def process_images():
    """
    Основная процедура скачивания и обновления ссылок в датасете.
    """
    os.makedirs(IMAGES_DIR, exist_ok=True)

    print("=" * 75)
    print("RLT.Tender_Guide: ЛОКАЛИЗАЦИЯ ИЗОБРАЖЕНИЙ И СКРИНШОТОВ (download_images.py)")
    print("=" * 75)

    if not os.path.exists(DATASET_CLEAN):
        print(f"[ОШИБКА] Файл не найден: {DATASET_CLEAN}")
        return

    print(f"Загрузка очищенного датасета: {DATASET_CLEAN}...")
    with open(DATASET_CLEAN, 'r', encoding='utf-8') as f:
        articles = json.load(f)

    print(f"Всего статей в датасете: {len(articles)}")

    img_pattern = re.compile(r'!\[(.*?)\]\((.*?)\)')
    downloaded_count = 0
    cached_count = 0
    total_images = 0

    for idx, article in enumerate(articles):
        text = article.get('text', '')
        matches = img_pattern.findall(text)
        if not matches:
            continue

        total_images += len(matches)
        doc_key = article.get('file_name') or article.get('doc_id') or f"art_{idx}"

        for alt, img_url in matches:
            # Если путь уже локальный (начинается с images/) — пропускаем
            if img_url.startswith('images/'):
                continue

            parsed_url = urlparse(img_url)
            filename = os.path.basename(parsed_url.path)
            if not filename or '.' not in filename:
                filename = f"img_{abs(hash(img_url)) % 1000000}.png"

            # Убираем спецсимволы из имени файла
            filename = unquote(filename)
            safe_filename = "".join(c for c in f"{doc_key}_{filename}" if c.isalnum() or c in ('.', '_', '-'))
            local_path = os.path.join(IMAGES_DIR, safe_filename)

            if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
                cached_count += 1
                local_markdown_path = f"images/{safe_filename}"
                text = text.replace(f"![{alt}]({img_url})", f"![{alt}]({local_markdown_path})")
            elif download_image(img_url, local_path):
                downloaded_count += 1
                local_markdown_path = f"images/{safe_filename}"
                text = text.replace(f"![{alt}]({img_url})", f"![{alt}]({local_markdown_path})")

        article['text'] = text

    # Сохраняем обновленный датасет в оба файла (kb_clean.json и kb_final.json)
    with open(DATASET_CLEAN, 'w', encoding='utf-8') as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

    with open(DATASET_FINAL, 'w', encoding='utf-8') as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 75)
    print("ИТОГИ ОБРАБОТКИ ИЗОБРАЖЕНИЙ:")
    print("=" * 75)
    print(f"Всего ссылок на изображения:  {total_images}")
    print(f"Успешно скачано новых файлов: {downloaded_count}")
    print(f"Использовано из кэша:        {cached_count}")
    print(f"Всего файлов в dataset/images: {len(os.listdir(IMAGES_DIR))}")
    print(f"Обновлен файл:                 {DATASET_CLEAN}")
    print(f"Обновлен файл:                 {DATASET_FINAL}")
    print("=" * 75)


if __name__ == "__main__":
    process_images()
