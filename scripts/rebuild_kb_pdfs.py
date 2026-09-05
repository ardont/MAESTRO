"""
Скрипт: rebuild_kb_pdfs.py

Назначение:
  Генерация идеального реестра официальных инструкций (PDF и DOCX) в dataset/kb_pdfs.json.
  Включает:
    - Инструкция по созданию оферты и СТЕ (PDF)
    - Инструкция по формированию YML (PDF)
    - Инструкция по регистрации на Портале (PDF)
    - Руководство пользователей по электронному исполнению контрактов (DOCX)
    - Руководство пользователя: Производитель (DOCX)
"""

import os
import sys
import json
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import fitz  # PyMuPDF
import docx

BASE_DIR = Path(__file__).resolve().parent.parent
PDF_DIR = BASE_DIR / "dataset" / "pdfs"
OUT_FILE = BASE_DIR / "dataset" / "kb_pdfs.json"

DOCS_META = [
    {
        "file": "Инструкция по созданию оферты и СТЕ.pdf",
        "title": "Официальная инструкция: Создание и ведение оферт и СТЕ на Портале Поставщиков",
        "category": "ste_catalog",
        "doc_type": "instruction",
        "url": "https://zakupki.mos.ru/cms/Media/docs/Инструкция по созданию оферты и СТЕ.pdf"
    },
    {
        "file": "Инструкция_по_формированию_YML.pdf",
        "title": "Официальная инструкция по формированию YML прайс-листа и массовой загрузке оферт",
        "category": "ste_catalog",
        "doc_type": "instruction",
        "url": "https://zakupki.mos.ru/cms/Media/docs/Инструкция по формированию YML.pdf"
    },
    {
        "file": "Инструкция по регистрации на Портале.pdf",
        "title": "Официальная инструкция по регистрации организации и пользователей на Портале Поставщиков",
        "category": "registration",
        "doc_type": "instruction",
        "url": "https://zakupki.mos.ru/cms/Media/docs/Инструкция по регистрации на Портале.pdf"
    },
    {
        "file": "rykovodstvo_polzovatelei_po_elektronnomy_ispolneniu_kontraktov_01.04.2022.docx",
        "title": "Официальное руководство пользователей по электронному исполнению контрактов (УПД, ЕИС)",
        "category": "contract_execution",
        "doc_type": "instruction",
        "url": "https://zakupki.mos.ru/newapi/api/FileStorage/Download?id=2118416529"
    },
    {
        "file": "руководство_пользователя_производитель_v41.docx",
        "title": "Официальное руководство пользователя для производителей продукции на Портале Поставщиков",
        "category": "ste_catalog",
        "doc_type": "instruction",
        "url": "https://zakupki.mos.ru/cms/media/docs/руководство_пользователя_производитель_v41_03_05_23.docx"
    }
]

def main():
    print("=" * 70)
    print("ПЕРЕСБОРКА dataset/kb_pdfs.json")
    print("=" * 70)

    records = []
    for meta in DOCS_META:
        p = PDF_DIR / meta["file"]
        if not p.exists():
            print(f"[ПРОПУСК] Файл не найден: {p.name}")
            continue

        text = ""
        if p.suffix.lower() == ".pdf":
            doc = fitz.open(p)
            text = "\n\n".join([page.get_text() for page in doc]).strip()
        elif p.suffix.lower() == ".docx":
            d = docx.Document(p)
            text = "\n\n".join([para.text for para in d.paragraphs if para.text.strip()]).strip()

        print(f"[OK] {meta['file']}: извлечено {len(text):,} символов")
        records.append({
            "file_name": meta["file"],
            "title": meta["title"],
            "category": meta["category"],
            "doc_type": meta["doc_type"],
            "url": meta["url"],
            "content": text,
            "char_count": len(text)
        })

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"\n[УСПЕХ] Сохранен {OUT_FILE} ({len(records)} официальных руководств)!")

if __name__ == "__main__":
    main()
