"""
Скрипт: extract_all_doc_media.py

Назначение:
  Извлечение встроенных скриншотов и графических схем из всех официальных PDF и DOCX инструкций:
  - Инструкция по регистрации на Портале.pdf
  - Инструкция по созданию оферты и СТЕ.pdf
  - Инструкция_по_формированию_YML.pdf
  - rykovodstvo_polzovatelei_po_elektronnomy_ispolneniu_kontraktov_01.04.2022.docx
  - руководство_пользователя_производитель_v41.docx

Сохраняет скриншоты в директории:
  - dataset/images/pdf_extracted/
  - dataset/images/docx_extracted/
"""

import os
import sys
import zipfile
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    import fitz  # PyMuPDF
    HAVE_PYMUPDF = True
except ImportError:
    HAVE_PYMUPDF = False

BASE_DIR = Path(__file__).resolve().parent.parent
PDF_DIR = BASE_DIR / "dataset" / "pdfs"
PDF_IMG_DIR = BASE_DIR / "dataset" / "images" / "pdf_extracted"
DOCX_IMG_DIR = BASE_DIR / "dataset" / "images" / "docx_extracted"

PDF_IMG_DIR.mkdir(parents=True, exist_ok=True)
DOCX_IMG_DIR.mkdir(parents=True, exist_ok=True)


def extract_images_from_pdfs():
    if not HAVE_PYMUPDF:
        print("[PDF] PyMuPDF (fitz) не установлен, пропуск.")
        return 0

    total_extracted = 0
    for pdf_file in PDF_DIR.glob("*.pdf"):
        if pdf_file.stat().st_size < 10000:
            continue  # Пропуск фиктивных файлов

        prefix = pdf_file.stem.replace(" ", "_")
        try:
            doc = fitz.open(pdf_file)
            pdf_count = 0
            for page_idx, page in enumerate(doc):
                img_list = page.get_images(full=True)
                for img_idx, img_info in enumerate(img_list):
                    xref = img_info[0]
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    image_ext = base_image["ext"]

                    # Игнорируем мелкие иконки/линейки (< 5 КБ)
                    if len(image_bytes) < 5000:
                        continue

                    out_name = f"{prefix}_p{page_idx+1}_{img_idx}.{image_ext}"
                    out_path = PDF_IMG_DIR / out_name
                    with open(out_path, "wb") as f:
                        f.write(image_bytes)

                    pdf_count += 1
                    total_extracted += 1

            print(f"[PDF] {pdf_file.name}: извлечено {pdf_count} скриншотов")
        except Exception as e:
            print(f"[PDF] Ошибка при обработке {pdf_file.name}: {e}")

    return total_extracted


def extract_images_from_docx():
    total_extracted = 0
    for docx_file in PDF_DIR.glob("*.docx"):
        prefix = docx_file.stem.replace(" ", "_")
        try:
            docx_count = 0
            with zipfile.ZipFile(docx_file, "r") as z:
                for item in z.namelist():
                    if item.startswith("word/media/"):
                        data = z.read(item)
                        # Игнорируем мелкие иконки (< 5 КБ)
                        if len(data) < 5000:
                            continue

                        ext = Path(item).suffix or ".png"
                        out_name = f"{prefix}_{Path(item).stem}{ext}"
                        out_path = DOCX_IMG_DIR / out_name
                        with open(out_path, "wb") as f:
                            f.write(data)

                        docx_count += 1
                        total_extracted += 1

            print(f"[DOCX] {docx_file.name}: извлечено {docx_count} скриншотов")
        except Exception as e:
            print(f"[DOCX] Ошибка при обработке {docx_file.name}: {e}")

    return total_extracted


def main():
    print("=" * 70)
    print("ИЗВЛЕЧЕНИЕ СКРИНШОТОВ ИЗ ОФИЦИАЛЬНЫХ РЕГЛАМЕНТОВ (PDF/DOCX)")
    print("=" * 70)

    pdf_total = extract_images_from_pdfs()
    docx_total = extract_images_from_docx()

    print("\n" + "=" * 70)
    print("ИТОГИ ИЗВЛЕЧЕНИЯ:")
    print(f"Скриншотов из PDF:  {pdf_total}")
    print(f"Скриншотов из DOCX: {docx_total}")
    print(f"Всего извлечено:    {pdf_total + docx_total}")
    print(f"Сохранено в: {PDF_IMG_DIR} и {DOCX_IMG_DIR}")
    print("=" * 70)


if __name__ == "__main__":
    main()
