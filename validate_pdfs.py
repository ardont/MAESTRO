import os
from pathlib import Path

# Попробуем импортировать библиотеку для чтения PDF
try:
    import PyPDF2
    HAS_PYPDF2 = True
except ImportError:
    HAS_PYPDF2 = False

DOCS_DIR = Path("/home/rama/ardont/knowledgebase_mos_ru/docs")

def main():
    if not DOCS_DIR.exists():
        print(f"Папка {DOCS_DIR} не найдена. Убедитесь, что путь верный.")
        return

    files = list(DOCS_DIR.glob("*"))
    if not files:
        print(f"Папка {DOCS_DIR} пуста.")
        return

    print(f"Всего файлов в папке docs/: {len(files)}")
    
    # Статистика по расширениям
    extensions = {}
    total_size_mb = 0
    pdf_files = []
    other_files = []

    for f in files:
        if f.is_file():
            ext = f.suffix.lower()
            extensions[ext] = extensions.get(ext, 0) + 1
            size_mb = f.stat().st_size / (1024 * 1024)
            total_size_mb += size_mb
            
            if ext == '.pdf':
                pdf_files.append((f, size_mb))
            else:
                other_files.append((f, size_mb))

    print(f"Общий объем: {total_size_mb:.2f} Мб")
    print("\n--- СТАТИСТИКА ПО ФОРМАТАМ ---")
    for ext, count in extensions.items():
        print(f"  {ext if ext else 'Без расширения'}: {count} шт.")

    print("\n--- ПРОВЕРКА PDF ФАЙЛОВ ---")
    if not HAS_PYPDF2:
        print("Библиотека PyPDF2 не установлена.")
        print("Для глубокого анализа текста внутри PDF выполните: pip install PyPDF2")
        print("Вывожу только список файлов:")
        for f, size in sorted(pdf_files, key=lambda x: x[1], reverse=True)[:5]:
            print(f"  - {f.name} ({size:.1f} Мб)")
    else:
        scanned_pdfs = []
        corrupted_pdfs = []
        valid_text_pdfs = []
        total_pages = 0

        for f, size in pdf_files:
            try:
                with open(f, "rb") as pdf_file:
                    reader = PyPDF2.PdfReader(pdf_file)
                    num_pages = len(reader.pages)
                    total_pages += num_pages
                    
                    # Проверяем первые 3 страницы на наличие текстового слоя
                    text_found = False
                    pages_to_check = min(3, num_pages)
                    for i in range(pages_to_check):
                        page = reader.pages[i]
                        text = page.extract_text()
                        if text and len(text.strip()) > 50:
                            text_found = True
                            break
                    
                    if text_found:
                        valid_text_pdfs.append((f.name, num_pages, size))
                    else:
                        scanned_pdfs.append((f.name, num_pages, size))
            except Exception as e:
                corrupted_pdfs.append((f.name, str(e)))

        print(f"Успешно прочитано PDF: {len(valid_text_pdfs)} шт.")
        print(f"Всего страниц во всех валидных PDF: {total_pages}")
        
        if valid_text_pdfs:
            print("\nТоп-3 самых больших текстовых PDF:")
            valid_text_pdfs.sort(key=lambda x: x[2], reverse=True)
            for name, pages, size in valid_text_pdfs[:3]:
                print(f"  - {name} ({pages} стр., {size:.1f} Мб)")

        if scanned_pdfs:
            print(f"\nВНИМАНИЕ: Найдено {len(scanned_pdfs)} PDF-файлов без текстового слоя (сканы/картинки).")
            print("Они потребуют OCR (Tesseract / EasyOCR) для извлечения текста:")
            for name, pages, size in scanned_pdfs:
                print(f"  - {name} ({pages} стр., {size:.1f} Мб)")
                
        if corrupted_pdfs:
            print(f"\nОШИБКА: Не удалось прочитать {len(corrupted_pdfs)} PDF-файлов:")
            for name, err in corrupted_pdfs:
                print(f"  - {name}: {err}")

    if other_files:
        print("\n--- ДРУГИЕ ДОКУМЕНТЫ (DOCX, PPTX и др.) ---")
        print("Для их обработки в RAG потребуются отдельные библиотеки (python-docx, python-pptx).")
        other_files.sort(key=lambda x: x[1], reverse=True)
        for f, size in other_files[:5]:
            print(f"  - {f.name} ({size:.1f} Мб)")

if __name__ == "__main__":
    main()
