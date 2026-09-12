import json
import re
from pathlib import Path
from bs4 import BeautifulSoup
from collections import Counter

DATASET_PATH = Path("dataset/articles.json")

def clean_html(html_text: str) -> str:
    """Очищает HTML-теги для подачи чистого текста в LLM/эмбеддинги."""
    if not html_text:
        return ""
    soup = BeautifulSoup(html_text, "html.parser")
    text = soup.get_text(separator="\n")
    return re.sub(r'\n+', '\n', text).strip()

def main():
    if not DATASET_PATH.exists():
        print(f"Файл {DATASET_PATH} не найден. Проверьте путь.")
        # Для тестирования локально можно подсунуть заглушку, 
        # но скрипт расчитан на запуск на сервере.
        return

    try:
        with open(DATASET_PATH, "r", encoding="utf-8") as f:
            articles = json.load(f)
    except Exception as e:
        print(f"Ошибка загрузки датасета: {e}")
        return

    print(f"Всего статей в датасете: {len(articles)}")
    
    issues = {
        "no_id": [],
        "no_title": [],
        "no_text": [],
        "short_text": [],  # Текст < 50 символов (возможно заглушка)
        "only_pdf_link": [], # Статьи, где есть только ссылка на PDF
    }
    
    categories = Counter()
    section_types = Counter()
    
    valid_articles = 0
    total_length = 0
    
    for art in articles:
        raw_content = art.get("selfServicePortal") or art.get("detailText") or art.get("previewText") or ""
        clean_text = clean_html(raw_content)
        
        art_id = art.get("staticId") or art.get("id") or "UNKNOWN"
        title = art.get("largeName", "").strip()
        category = art.get("serviceName", "unknown_category")
        sec_types = art.get("sectionTypes", [])
        
        # Сбор статистики по категориям
        if isinstance(sec_types, list):
            for st in sec_types:
                section_types[st] += 1
        elif isinstance(sec_types, str):
            section_types[sec_types] += 1
            
        categories[category] += 1
        
        # Проверка на то, что это просто ссылка на PDF
        if ".pdf" in raw_content.lower() and len(clean_text) < 200:
            issues["only_pdf_link"].append(str(art_id))
            continue # Пропускаем PDF файлы, как вы и просили
            
        has_issue = False
        if art_id == "UNKNOWN":
            issues["no_id"].append(title or "Unknown")
            has_issue = True
        if not title:
            issues["no_title"].append(str(art_id))
            has_issue = True
        if not clean_text:
            issues["no_text"].append(str(art_id))
            has_issue = True
        elif len(clean_text) < 50:
            issues["short_text"].append(str(art_id))
            # Может быть валидно, но подозрительно коротко
            
        if not has_issue and clean_text:
            valid_articles += 1
            total_length += len(clean_text)

    print("\n--- СТАТИСТИКА ПО КАТЕГОРИЯМ (Топ-10) ---")
    for cat, count in categories.most_common(10):
        print(f"  {cat}: {count}")

    print("\n--- СТАТИСТИКА ПО РАЗДЕЛАМ (sectionTypes) ---")
    for sec, count in section_types.most_common():
        print(f"  {sec}: {count}")

    print("\n--- ОТЧЕТ ПО ПРОБЛЕМНЫМ/ПУСТЫМ СТАТЬЯМ ---")
    print(f"Без ID: {len(issues['no_id'])}")
    print(f"Без заголовка: {len(issues['no_title'])}")
    print(f"Пустой текст: {len(issues['no_text'])}")
    print(f"Очень короткий текст (<50 символов): {len(issues['short_text'])}")
    print(f"Исключено статей-ссылок на PDF: {len(issues['only_pdf_link'])}")
    
    if issues["no_text"]:
        print(f"Примеры ID с пустым текстом: {issues['no_text'][:5]}")
    if issues["short_text"]:
        print(f"Примеры ID с коротким текстом: {issues['short_text'][:5]}")

    if valid_articles > 0:
        avg_len = total_length / valid_articles
        print(f"\n--- ИТОГ (Обыкновенные инструкции) ---")
        print(f"Валидных текстовых инструкций: {valid_articles} из {len(articles)}")
        print(f"Средняя длина текста валидной статьи: {avg_len:.0f} символов")
        
        if valid_articles > 0:
            print("\nВсё выглядит отлично! Датасет готов к загрузке в RAG.")
    else:
        print("\nВНИМАНИЕ: Не найдено валидных текстовых инструкций.")

if __name__ == "__main__":
    main()
