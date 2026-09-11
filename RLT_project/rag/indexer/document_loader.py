"""
Модуль: document_loader.py (НОВЫЙ ЗАГРУЗЧИК БАЗЫ ЗНАНИЙ И ДОКУМЕНТОВ)

Назначение:
  Сборка единого реестра документов для индексации в векторную базу Qdrant
  из нового чистого датасета (articles.json, PDF и DOCX).

Контракт выходного объекта:
  {
      "text": str,        # Полный текст документа (чистый текст)
      "title": str,       # Название документа / статьи
      "url": str,         # URL первоисточника на портале
      "category": str,    # Категория (serviceName или sectionType)
      "doc_type": str,    # "instruction" | "legislation"
      "file_name": str,   # Имя файла или ID статьи
      "doc_id": str       # Стабильный ID документа
  }
"""

import json
import os
import re
from pathlib import Path
from typing import List, Dict, Any

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

try:
    import PyPDF2
except ImportError:
    PyPDF2 = None

try:
    import docx
except ImportError:
    docx = None


from .config import DATASET_DIR

# По умолчанию ищем новую базу в папке dataset внутри проекта
DEFAULT_KB_PATH = os.environ.get("KB_PATH", str(DATASET_DIR))


def _clean_html(html_text: str) -> str:
    """Очищает HTML-теги для подачи чистого текста в RAG."""
    if not html_text:
        return ""
    if BeautifulSoup:
        soup = BeautifulSoup(html_text, "html.parser")
        text = soup.get_text(separator="\n")
    else:
        # Fallback if BeautifulSoup is not installed
        text = re.sub(r'<[^>]+>', '\n', html_text)
    return re.sub(r'\n+', '\n', text).strip()


def load_articles_json(kb_path: Path) -> List[Dict[str, Any]]:
    """Загружает текстовые инструкции из articles.json"""
    articles_file = kb_path / "data" / "articles.json"
    documents = []

    if not articles_file.exists():
        print(f"[LOADER] ВНИМАНИЕ: Файл {articles_file} не найден!")
        return documents

    try:
        with open(articles_file, "r", encoding="utf-8") as f:
            articles = json.load(f)

        for art in articles:
            raw_content = art.get("selfServicePortal") or art.get("detailText") or art.get("previewText") or ""
            clean_text = _clean_html(raw_content)

            # Игнорируем статьи-пустышки (ссылки на скачивание PDF)
            if ".pdf" in raw_content.lower() and len(clean_text) < 200:
                continue
            
            if len(clean_text) < 50:
                continue

            art_id = str(art.get("staticId") or art.get("id") or "unknown")
            title = art.get("largeName", "Без названия").strip()
            category = art.get("serviceName", "kb_article").strip()
            
            # Определяем doc_type (нормативка или обычная инструкция)
            doc_type = "instruction"
            if "закон" in title.lower() or "регламент" in title.lower() or "фз" in title.lower():
                doc_type = "legislation"

            documents.append({
                "text": clean_text,
                "title": title,
                "url": f"https://zakupki.mos.ru/knowledgebase/article/{art_id}",
                "category": category,
                "doc_type": doc_type,
                "file_name": f"{art_id}.html",
                "doc_id": f"art_{art_id}"
            })

        print(f"[LOADER] Загружено {len(documents)} текстовых статей из articles.json")
    except Exception as e:
        print(f"[LOADER] Ошибка при чтении {articles_file}: {e}")

    return documents


def load_pdfs(kb_path: Path) -> List[Dict[str, Any]]:
    """Извлекает текст из официальных PDF-инструкций"""
    docs_dir = kb_path / "docs"
    documents = []

    if not docs_dir.exists():
        return documents

    if not PyPDF2:
        print("[LOADER] PyPDF2 не установлен. Пропуск загрузки PDF (выполните pip install PyPDF2).")
        return documents

    pdf_count = 0
    for pdf_file in docs_dir.glob("*.pdf"):
        try:
            text_blocks = []
            with open(pdf_file, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text_blocks.append(extracted)
            
            full_text = "\n".join(text_blocks).strip()
            if len(full_text) > 100:
                title = pdf_file.stem.replace("_", " ")
                doc_type = "legislation" if "регламент" in title.lower() or "фз" in title.lower() else "instruction"
                
                documents.append({
                    "text": full_text,
                    "title": title,
                    "url": f"https://zakupki.mos.ru/knowledgebase/docs/{pdf_file.name}",
                    "category": "official_docs",
                    "doc_type": doc_type,
                    "file_name": pdf_file.name,
                    "doc_id": f"pdf_{pdf_file.stem}"
                })
                pdf_count += 1
        except Exception as e:
            print(f"[LOADER] Ошибка чтения PDF {pdf_file.name}: {e}")

    if pdf_count > 0:
        print(f"[LOADER] Успешно загружено {pdf_count} PDF-инструкций")

    return documents


def load_docx(kb_path: Path) -> List[Dict[str, Any]]:
    """Извлекает текст из официальных DOCX-инструкций"""
    docs_dir = kb_path / "docs"
    documents = []

    if not docs_dir.exists():
        return documents

    if not docx:
        print("[LOADER] python-docx не установлен. Пропуск загрузки DOCX (выполните pip install python-docx).")
        return documents

    docx_count = 0
    for docx_file in docs_dir.glob("*.docx"):
        try:
            doc = docx.Document(docx_file)
            full_text = "\n".join([para.text for para in doc.paragraphs if para.text]).strip()
            
            if len(full_text) > 100:
                title = docx_file.stem.replace("_", " ")
                
                documents.append({
                    "text": full_text,
                    "title": title,
                    "url": f"https://zakupki.mos.ru/knowledgebase/docs/{docx_file.name}",
                    "category": "official_docs",
                    "doc_type": "instruction",
                    "file_name": docx_file.name,
                    "doc_id": f"docx_{docx_file.stem}"
                })
                docx_count += 1
        except Exception as e:
            print(f"[LOADER] Ошибка чтения DOCX {docx_file.name}: {e}")

    if docx_count > 0:
        print(f"[LOADER] Успешно загружено {docx_count} DOCX-инструкций")

    return documents


def load_all_documents(kb_path: str = DEFAULT_KB_PATH) -> List[Dict[str, Any]]:
    """
    Загружает полный массив документов из нового датасета (JSON + PDF + DOCX).
    """
    path_obj = Path(kb_path)
    print(f"[LOADER] Начинаю загрузку базы знаний из: {path_obj}")
    
    documents = []
    
    # 1. Текстовые статьи
    documents.extend(load_articles_json(path_obj))
    
    # 2. PDF инструкции
    documents.extend(load_pdfs(path_obj))
    
    # 3. DOCX инструкции
    documents.extend(load_docx(path_obj))
    
    print(f"[LOADER] Итого подготовлено {len(documents)} документов для индексатора.")
    return documents


if __name__ == "__main__":
    docs = load_all_documents()
    if docs:
        print(f"\nПример первого документа: {docs[0]['title']} (Категория: {docs[0]['category']})")
