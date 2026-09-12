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
import urllib.parse

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

try:
    import PyPDF2
except ImportError:
    try:
        import pypdf as PyPDF2
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

            # Используем точный сохраненный канонический URL из датасета
            art_url = art.get("url") or f"https://zakupki.mos.ru/knowledgebase/article/details/ais/{art_id}"

            documents.append({
                "text": clean_text,
                "title": title,
                "url": art_url,
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
KNOWN_DOC_URLS = {
    "руководство_пользователей_по_электронному_исполнению_контрактов_01.04.2022.docx": "https://help.mos.ru/upload/iblock/1cd/rykovodstvo_polzovatelei_po_elektronnomy_ispolneniu_kontraktov_01.04.2022.docx",
    "руководство пользователей по электронному исполнению контрактов 01.04.2022.docx": "https://help.mos.ru/upload/iblock/1cd/rykovodstvo_polzovatelei_po_elektronnomy_ispolneniu_kontraktov_01.04.2022.docx",
}


def get_canonical_doc_url(filename: str) -> str:
    """Возвращает 100% проверенную рабочую ссылку для официального документа"""
    fn_lower = filename.lower()
    if fn_lower in KNOWN_DOC_URLS:
        return KNOWN_DOC_URLS[fn_lower]
    # На портале zakupki.mos.ru/cms/Media/docs/ документы размещаются с пробелами
    clean_name = filename.replace("_", " ")
    return f"https://zakupki.mos.ru/cms/Media/docs/{urllib.parse.quote(clean_name)}"


def load_pdf(kb_path: Path) -> List[Dict[str, Any]]:
    """Извлекает текст из официальных PDF-инструкций с дедупликацией по хешу"""
    import hashlib
    docs_dir = kb_path / "docs"
    documents = []

    if not docs_dir.exists():
        return documents

    if not PyPDF2:
        print("[LOADER] PyPDF2/pypdf не установлен. Пропуск загрузки PDF.")
        return documents

    seen_hashes = set()
    pdf_count = 0

    for pdf_file in sorted(docs_dir.glob("*.pdf")):
        try:
            content = pdf_file.read_bytes()
            file_hash = hashlib.sha256(content).hexdigest()
            if file_hash in seen_hashes:
                print(f"[LOADER] Пропуск дубликата PDF: {pdf_file.name}")
                continue
            seen_hashes.add(file_hash)

            text_blocks = []
            reader = PyPDF2.PdfReader(pdf_file)
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text_blocks.append(extracted)
            
            full_text = "\n".join(text_blocks).strip()
            if len(full_text) > 100:
                title = pdf_file.stem.replace("_", " ")
                doc_type = "legislation" if "регламент" in title.lower() or "фз" in title.lower() else "instruction"
                doc_url = get_canonical_doc_url(pdf_file.name)
                
                documents.append({
                    "text": full_text,
                    "title": title,
                    "url": doc_url,
                    "category": "official_docs",
                    "doc_type": doc_type,
                    "file_name": pdf_file.name,
                    "doc_id": f"pdf_{pdf_file.stem}"
                })
                pdf_count += 1
        except Exception as e:
            print(f"[LOADER] Ошибка чтения PDF {pdf_file.name}: {e}")

    if pdf_count > 0:
        print(f"[LOADER] Успешно загружено {pdf_count} уникальных PDF-инструкций")

    return documents


def load_docx(kb_path: Path) -> List[Dict[str, Any]]:
    """Извлекает текст из официальных DOCX-инструкций с дедупликацией по хешу"""
    import hashlib
    docs_dir = kb_path / "docs"
    documents = []

    if not docs_dir.exists():
        return documents

    if not docx:
        print("[LOADER] python-docx не установлен. Пропуск загрузки DOCX.")
        return documents

    seen_hashes = set()
    docx_count = 0

    for docx_file in sorted(docs_dir.glob("*.docx")):
        try:
            content = docx_file.read_bytes()
            file_hash = hashlib.sha256(content).hexdigest()
            if file_hash in seen_hashes:
                print(f"[LOADER] Пропуск дубликата DOCX: {docx_file.name}")
                continue
            seen_hashes.add(file_hash)

            doc = docx.Document(docx_file)
            full_text = "\n".join([para.text for para in doc.paragraphs if para.text]).strip()
            
            if len(full_text) > 100:
                title = docx_file.stem.replace("_", " ")
                doc_url = get_canonical_doc_url(docx_file.name)
                
                documents.append({
                    "text": full_text,
                    "title": title,
                    "url": doc_url,
                    "category": "official_docs",
                    "doc_type": "instruction",
                    "file_name": docx_file.name,
                    "doc_id": f"docx_{docx_file.stem}"
                })
                docx_count += 1
        except Exception as e:
            print(f"[LOADER] Ошибка чтения DOCX {docx_file.name}: {e}")

    if docx_count > 0:
        print(f"[LOADER] Успешно загружено {docx_count} уникальных DOCX-инструкций")

    return documents


def load_regulations_json(kb_path: Path) -> List[Dict[str, Any]]:
    """Загружает разделы Регламента ведения портала из regulations.json"""
    reg_file = kb_path / "data" / "regulations.json"
    documents = []

    if not reg_file.exists():
        return documents

    try:
        with open(reg_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        for page in data.get("pages", []):
            cid = page.get("contentItemId")
            if not cid:
                continue

            html = page.get("content", {}).get("html", "")
            clean_text = _clean_html(html)
            if len(clean_text) < 50:
                continue

            title = page.get("displayText", "Регламент ведения портала").strip()
            url = page.get("url") or f"https://zakupki.mos.ru/knowledgebase/article/details/cms/{cid}"

            documents.append({
                "text": clean_text,
                "title": title,
                "url": url,
                "category": "regulations",
                "doc_type": "legislation",
                "file_name": f"{cid}.html",
                "doc_id": f"reg_{cid}"
            })

        if documents:
            print(f"[LOADER] Загружено {len(documents)} разделов Регламента из regulations.json")
    except Exception as e:
        print(f"[LOADER] Ошибка чтения {reg_file}: {e}")

    return documents


def load_all_documents(kb_path: str = DEFAULT_KB_PATH) -> List[Dict[str, Any]]:
    """
    Загружает полный массив документов из нового датасета (JSON + PDF + DOCX + Регламент).
    """
    path_obj = Path(kb_path)
    print(f"[LOADER] Начинаю загрузку базы знаний из: {path_obj}")
    
    documents = []
    
    # 1. Текстовые статьи
    documents.extend(load_articles_json(path_obj))
    
    # 2. Регламент портала (CMS)
    documents.extend(load_regulations_json(path_obj))
    
    # 3. PDF инструкции
    documents.extend(load_pdfs(path_obj))
    
    # 4. DOCX инструкции
    documents.extend(load_docx(path_obj))
    
    print(f"[LOADER] Итого подготовлено {len(documents)} документов для индексатора.")
    return documents


if __name__ == "__main__":
    docs = load_all_documents()
    if docs:
        print(f"\nПример первого документа: {docs[0]['title']} (Категория: {docs[0]['category']})")
