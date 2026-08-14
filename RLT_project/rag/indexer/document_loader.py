import os
import re
from pathlib import Path
from .config import (
    DATASET_DIR, LEG_DIR, INST_DIR, INST_KB_DIR, INST_OFFICIAL_DIR, 
    CATEGORY_KEYWORDS
)

def classify_content_by_keywords(text: str, current_category: str) -> str:
    """
    Вторичная классификация: проверяет частоту ключевых слов в тексте
    """
    text_lower = text.lower()
    scores = {cat: 0 for cat in CATEGORY_KEYWORDS}
    
    for cat, kw_list in CATEGORY_KEYWORDS.items():
        for kw in kw_list:
            # Учитываем вхождения ключевого слова
            count = text_lower.count(kw)
            scores[cat] += count
            
    best_cat = max(scores, key=scores.get)
    # Если набралось больше 3 ключевых совпадений, используем лучшую категорию
    if scores[best_cat] >= 3 and best_cat != current_category:
        return best_cat
        
    return current_category

def parse_single_document(file_path: Path) -> dict:
    """
    Считывает файл и извлекает структурированные метаданные и чистый текст
    """
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as e:
        print(f"[ERROR] Failed to read {file_path}: {e}")
        return None

    fname = file_path.name.lower()
    
    # 1. Извлечение заголовка, URL и тегов
    source_url = ""
    title = ""
    tags = []
    
    url_match = re.search(r"^(?:SOURCE URL|SOURCE DOCUMENT):\s*(.+)$", content, re.MULTILINE | re.IGNORECASE)
    if url_match:
        source_url = url_match.group(1).strip()
        
    title_match = re.search(r"^TITLE:\s*(.+)$", content, re.MULTILINE | re.IGNORECASE)
    if title_match:
        title = title_match.group(1).strip()
    else:
        # Извлекаем из первого заголовка # или имени файла
        h1_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if h1_match:
            title = h1_match.group(1).strip()
        else:
            title = file_path.stem.replace("_", " ").replace("-", " ").capitalize()

    tags_match = re.search(r"^TAGS:\s*(.+)$", content, re.MULTILINE | re.IGNORECASE)
    if tags_match:
        tags = [t.strip() for t in tags_match.group(1).split(",") if t.strip()]

    # 2. Очистка текста от служебных заголовков
    clean_lines = []
    in_header = True
    for line in content.splitlines():
        if in_header:
            if line.startswith("SOURCE URL:") or line.startswith("SOURCE DOCUMENT:") or \
               line.startswith("TITLE:") or line.startswith("TAGS:") or \
               line.startswith("===") or line.startswith("--- Page"):
                continue
            if line.strip():
                in_header = False
                clean_lines.append(line)
        else:
            clean_lines.append(line)
            
    clean_text = "\n".join(clean_lines).strip()
    if not clean_text or len(clean_text) < 30:
        return None

    # 3. Первичная классификация по папкам и имени файла
    doc_type = "general"
    category = "general"
    
    if "1_legislation" in str(file_path) or any(w in fname for w in ["zakon", "kodex", "fz", "фз", "гк"]):
        doc_type = "legislation"
        category = "44fz" if "44" in fname else ("223fz" if "223" in fname else "legislation")
    elif "roseltorg_official_docs" in str(file_path):
        doc_type = "official_regulation"
        category = "223fz" if any(w in fname for w in ["223", "corp", "rosatom", "interrao"]) else \
                   ("44fz" if "44" in fname or "gos" in fname else "general")
    else:
        doc_type = "instruction"
        if "44fz" in fname or "44-fz" in fname:
            category = "44fz"
        elif "223fz" in fname or "223-fz" in fname:
            category = "223fz"
        elif "ecp" in fname or "crypto" in fname or "mchd" in fname:
            category = "ecp_mchd"
        elif "registration" in fname or "buyer" in fname or "seller" in fname or "supplier" in fname:
            category = "registration"
        elif "services" in fname or "credit" in fname or "garant" in fname:
            category = "services"
        elif "kim" in fname or "agro" in fname or "sales" in fname:
            category = "trading_sections"
        elif "video" in fname:
            doc_type = "video_transcript"
        elif "notes" in fname or "reply" in fname:
            doc_type = "faq_note"

    # 4. Вторичная классификация по содержанию
    category = classify_content_by_keywords(clean_text, category)

    return {
        "file_path": str(file_path),
        "file_name": file_path.name,
        "title": title,
        "url": source_url if source_url else "https://www.roseltorg.ru/knowledge_db",
        "tags": tags,
        "category": category,
        "doc_type": doc_type,
        "text": clean_text
    }

def load_all_documents() -> list:
    """
    Загружает и парсит все документы из директорий базы знаний
    """
    documents = []
    seen_files = set()
    
    # 1. Статьи базы знаний Росэлторга
    if INST_KB_DIR.exists():
        for p in INST_KB_DIR.glob("*.txt"):
            if p.is_file() and p.name not in seen_files:
                doc = parse_single_document(p)
                if doc:
                    documents.append(doc)
                    seen_files.add(p.name)

    # 2. Официальные регламенты Росэлторга
    if INST_OFFICIAL_DIR.exists():
        for p in INST_OFFICIAL_DIR.glob("*.txt"):
            if p.is_file() and p.name not in seen_files:
                doc = parse_single_document(p)
                if doc:
                    documents.append(doc)
                    seen_files.add(p.name)

    # 3. Законодательство (44-ФЗ, 223-ФЗ, 135-ФЗ, 63-ФЗ, 294-ФЗ, ГК РФ)
    if LEG_DIR.exists():
        for p in LEG_DIR.glob("*.txt"):
            if p.is_file() and p.name not in seen_files:
                doc = parse_single_document(p)
                if doc:
                    documents.append(doc)
                    seen_files.add(p.name)

    # 4. Общие инструкции из корня 2_instructions
    if INST_DIR.exists():
        for p in INST_DIR.glob("*.txt"):
            if p.is_file() and p.name not in seen_files:
                doc = parse_single_document(p)
                if doc:
                    documents.append(doc)
                    seen_files.add(p.name)

    print(f"[DOCUMENT LOADER] Loaded and categorized {len(documents)} unique documents.")
    return documents
