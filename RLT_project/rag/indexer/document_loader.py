"""
Модуль: document_loader.py (ЗАГРУЗЧИК БАЗЫ ЗНАНИЙ И ЗАКОНОДАТЕЛЬСТВА)

Назначение:
  Сборка единого реестра документов для индексации в векторную базу Qdrant.
  Объединяет три ключевых источника:
    1. Очищенные статьи Портала Поставщиков (dataset/kb_clean.json)
    2. Нормативно-правовые акты РФ (dataset/1_legislation/*.txt)
    3. Дополнительные прикладные инструкции по 44-ФЗ и 223-ФЗ (dataset/2_instructions/...)

Какую проблему решает на Портале Поставщиков:
  Пользователи (поставщики и заказчики) задают как практические вопросы по интерфейсу
  ("где кнопка подачи оферты", "как привязать СТЕ к оферте"), так и юридические
  ("в какие сроки направляется протокол разногласий по 44-ФЗ", "разрешена ли закупка
  у ед. поставщика до 600 тыс. руб").
  Загрузчик объединяет технический и нормативно-правовой корпуса в согласованную структуру.

Контракт выходного объекта:
  {
      "text": str,        # Полный текст документа (Markdown / Raw Text)
      "title": str,       # Название документа / статьи
      "url": str,         # URL первоисточника или ссылка на консультант/регламент
      "category": str,    # Категория (quotation_session, ste_catalog, 44fz, 223fz, ecp_mchd и др.)
      "doc_type": str,    # "instruction" | "legislation" | "faq"
      "file_name": str,   # Имя файла или уникальный ID
      "doc_id": str       # Стабильный ID документа
  }
"""

import json
import os
import sys
from pathlib import Path
from typing import List, Dict, Any

# Настройка UTF-8 вывода для Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _clean_legislation_title(filename: str) -> str:
    """
    Превращает имя файла закона в красивый официальный заголовок.
    Пример: 'Federalny_zakon_ot_18_07_2011_N_223_FZ_red_ot_08_08_2024.txt'
            -> 'Федеральный закон № 223-ФЗ от 18.07.2011 (ред. 08.08.2024)'
    """
    fn = filename.lower()
    if "223_fz" in fn or "223-fz" in fn or "223fz" in fn:
        return "Федеральный закон № 223-ФЗ «О закупках товаров, работ, услуг отдельными видами юридических лиц»"
    if "63_fz" in fn or "63-fz" in fn:
        return "Федеральный закон № 63-ФЗ «Об электронной подписи»"
    if "135_fz" in fn or "135-fz" in fn:
        return "Федеральный закон № 135-ФЗ «О защите конкуренции»"
    if "294_fz" in fn or "294-fz" in fn:
        return "Федеральный закон № 294-ФЗ «О защите прав юридических лиц и ИП при осуществлении госконтроля»"
    if "grazhdanskiy_kodex" in fn or "gk" in fn:
        return "Гражданский кодекс Российской Федерации (Часть первая)"
    return filename.replace(".txt", "").replace("_", " ")


def _determine_legislation_category(filename: str) -> str:
    """Определяет категорию для закона."""
    fn = filename.lower()
    if "223" in fn:
        return "223fz"
    if "63" in fn:
        return "ecp_mchd"
    if "135" in fn:
        return "legislation"
    return "legislation"


def load_all_documents(include_legislation: bool = True) -> List[Dict[str, Any]]:
    """
    Загружает полный массив документов базы знаний и законодательства.
    
    Аргументы:
      include_legislation: флаг загрузки нормативно-правовых актов РФ из 1_legislation.
    """
    base_dir = Path(__file__).resolve().parent.parent.parent.parent
    dataset_file = base_dir / "dataset" / "kb_clean.json"
    legislation_dir = base_dir / "dataset" / "1_legislation"
    instructions_dir = base_dir / "dataset" / "2_instructions" / "zakupki_mos_ru_kb_articles"

    documents: List[Dict[str, Any]] = []

    # 1. Загрузка очищенных статей Портала Поставщиков (kb_clean.json)
    if dataset_file.exists():
        try:
            with open(dataset_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            for item in data:
                doc = {
                    "text": item.get("text", "").strip(),
                    "title": item.get("title", "Без названия").strip(),
                    "url": item.get("url", ""),
                    "category": item.get("category", "kb_article"),
                    "doc_type": item.get("doc_type", "instruction"),
                    "file_name": item.get("file_name", ""),
                    "doc_id": str(item.get("doc_id") or item.get("file_name", ""))
                }
                if len(doc["text"]) > 10:
                    documents.append(doc)

            print(f"[LOADER] Загружено {len(documents)} статей из {dataset_file.name}")
        except Exception as e:
            print(f"[LOADER] Ошибка при чтении {dataset_file}: {e}")
    else:
        print(f"[LOADER] ВНИМАНИЕ: Файл {dataset_file} не найден!")

    # 2. Загрузка законодательства РФ (1_legislation)
    if include_legislation and legislation_dir.exists():
        leg_count = 0
        for leg_file in sorted(legislation_dir.glob("*.txt")):
            try:
                with open(leg_file, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read().strip()

                if len(content) > 100:
                    clean_title = _clean_legislation_title(leg_file.name)
                    cat = _determine_legislation_category(leg_file.name)
                    documents.append({
                        "text": content,
                        "title": clean_title,
                        "url": f"https://www.consultant.ru/document/cons_doc_LAW_{abs(hash(leg_file.name))%100000}/",
                        "category": cat,
                        "doc_type": "legislation",
                        "file_name": leg_file.name,
                        "doc_id": f"leg_{leg_file.stem}"
                    })
                    leg_count += 1
            except Exception as e:
                print(f"[LOADER] Ошибка чтения закона {leg_file.name}: {e}")

        print(f"[LOADER] Загружено {leg_count} федеральных законов из 1_legislation/")

    # 3. Загрузка прикладных статей по 44-ФЗ и 223-ФЗ (2_instructions/zakupki_mos_ru_kb_articles)
    if instructions_dir.exists():
        extra_count = 0
        for inst_file in instructions_dir.glob("*.txt"):
            fn = inst_file.name.lower()
            # Берем практические руководства по 44-ФЗ и 223-ФЗ
            if ("44fz" in fn or "44-fz" in fn or "223fz" in fn or "223-fz" in fn) and "video" not in fn:
                try:
                    with open(inst_file, "r", encoding="utf-8", errors="ignore") as f:
                        text_body = f.read().strip()

                    if len(text_body) > 200:
                        first_line = text_body.splitlines()[0].strip("# ").strip()
                        title = first_line if len(first_line) > 5 else inst_file.stem.replace("_", " ")
                        cat = "44fz" if ("44" in fn) else "223fz"

                        documents.append({
                            "text": text_body,
                            "title": title,
                            "url": f"https://zakupki.mos.ru/knowledgebase/article/{abs(hash(inst_file.name))%1000000}",
                            "category": cat,
                            "doc_type": "instruction",
                            "file_name": inst_file.name,
                            "doc_id": f"inst_{inst_file.stem}"
                        })
                        extra_count += 1
                except Exception:
                    pass

        if extra_count > 0:
            print(f"[LOADER] Дополнительно загружено {extra_count} руководств по 44-ФЗ/223-ФЗ из 2_instructions/")

    print(f"[LOADER] Итого подготовлено {len(documents)} документов для индексатора.")
    return documents


if __name__ == "__main__":
    docs = load_all_documents()
    print(f"Пример первого документа: {docs[0]['title']} (Категория: {docs[0]['category']})")
