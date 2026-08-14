import re
import uuid
from langchain_text_splitters import RecursiveCharacterTextSplitter
from .config import CHUNK_SIZE, CHUNK_OVERLAP
from .image_extractor import extract_images_from_markdown

# Инициализируем текстовый сплиттер
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n\n", "\n", ". ", "; ", ", ", " "]
)

def chunk_legislation_document(doc: dict) -> list:
    """
    Умный чанкинг для законов и кодексов по Статьям и Пунктам
    """
    text = doc["text"]
    title = doc["title"]
    url = doc["url"]
    category = doc["category"]
    doc_type = doc["doc_type"]
    file_name = doc["file_name"]
    
    # Паттерн для поиска статей
    article_pattern = re.compile(r"(^|\n)(Статья\s+\d+(?:\.\d+)?\.?[^\n]*)", re.IGNORECASE)
    
    # Находим все позиции статей
    matches = list(article_pattern.finditer(text))
    chunks = []
    
    if not matches:
        raw_chunks = text_splitter.split_text(text)
        for idx, ch_text in enumerate(raw_chunks):
            chunk_body = f"[Документ: {title} | Общие положения]\n\n{ch_text.strip()}"
            chunks.append({
                "chunk_id": str(uuid.uuid4()),
                "doc_id": file_name,
                "title": title,
                "url": url,
                "category": category,
                "doc_type": doc_type,
                "section_header": "Общие положения",
                "images": [],
                "text": chunk_body
            })
        return chunks

    for i in range(len(matches)):
        start = matches[i].start()
        end = matches[i+1].start() if i + 1 < len(matches) else len(text)
        
        article_header = matches[i].group(2).strip()
        article_body = text[start:end].strip()
        
        # Если статья слишком длинная, делим её на части
        if len(article_body) > CHUNK_SIZE + CHUNK_OVERLAP:
            sub_chunks = text_splitter.split_text(article_body)
            for sub_idx, sub_text in enumerate(sub_chunks):
                sec_header = f"{article_header} (Часть {sub_idx+1})"
                chunk_body = f"[Документ: {title} | {sec_header}]\n\n{sub_text.strip()}"
                chunks.append({
                    "chunk_id": str(uuid.uuid4()),
                    "doc_id": file_name,
                    "title": title,
                    "url": url,
                    "category": category,
                    "doc_type": doc_type,
                    "section_header": article_header,
                    "images": [],
                    "text": chunk_body
                })
        else:
            chunk_body = f"[Документ: {title} | {article_header}]\n\n{article_body}"
            chunks.append({
                "chunk_id": str(uuid.uuid4()),
                "doc_id": file_name,
                "title": title,
                "url": url,
                "category": category,
                "doc_type": doc_type,
                "section_header": article_header,
                "images": [],
                "text": chunk_body
            })
            
    return chunks

def chunk_markdown_article(doc: dict) -> list:
    """
    Умный чанкинг для статей базы знаний с привязкой к Markdown заголовкам (##, ###)
    и извлечением скриншотов/иллюстраций
    """
    text = doc["text"]
    title = doc["title"]
    url = doc["url"]
    category = doc["category"]
    doc_type = doc["doc_type"]
    file_name = doc["file_name"]
    
    # 1. Извлекаем глобальные изображения документа
    doc_images = extract_images_from_markdown(text)
    
    # 2. Разбиваем текст на секции по заголовкам ## или ###
    header_pattern = re.compile(r"(^|\n)(#{1,3}\s+[^\n]+)")
    matches = list(header_pattern.finditer(text))
    
    sections = []
    if not matches:
        sections.append(("Основная информация", text))
    else:
        # Текст до первого заголовка
        if matches[0].start() > 0:
            intro_text = text[:matches[0].start()].strip()
            if len(intro_text) > 20:
                sections.append(("Введение", intro_text))
                
        for i in range(len(matches)):
            start = matches[i].start()
            end = matches[i+1].start() if i + 1 < len(matches) else len(text)
            
            raw_header = matches[i].group(2).strip()
            clean_header = re.sub(r"^#{1,3}\s+", "", raw_header).strip()
            section_body = text[start:end].strip()
            sections.append((clean_header, section_body))

    # 3. Делим каждую секцию на чанки
    chunks = []
    for sec_header, sec_body in sections:
        sec_images = extract_images_from_markdown(sec_body)
        # Если в секции нет прямых ссылок, но в документе есть картинки
        if not sec_images and doc_images:
            if any(w in sec_header.lower() for w in ["установка", "настройка", "подача", "интерфейс", "вход", "шаг", "окно", "кнопк", "личный"]):
                sec_images = doc_images[:2]

        if len(sec_body) > CHUNK_SIZE + CHUNK_OVERLAP:
            sub_chunks = text_splitter.split_text(sec_body)
            for sub_idx, sub_text in enumerate(sub_chunks):
                context_prefix = f"[Документ: {title} | Раздел: {sec_header}]"
                chunk_body = f"{context_prefix}\n\n{sub_text.strip()}"
                chunks.append({
                    "chunk_id": str(uuid.uuid4()),
                    "doc_id": file_name,
                    "title": title,
                    "url": url,
                    "category": category,
                    "doc_type": doc_type,
                    "section_header": sec_header,
                    "images": sec_images,
                    "text": chunk_body
                })
        else:
            context_prefix = f"[Документ: {title} | Раздел: {sec_header}]"
            chunk_body = f"{context_prefix}\n\n{sec_body.strip()}"
            chunks.append({
                "chunk_id": str(uuid.uuid4()),
                "doc_id": file_name,
                "title": title,
                "url": url,
                "category": category,
                "doc_type": doc_type,
                "section_header": sec_header,
                "images": sec_images,
                "text": chunk_body
            })
            
    return chunks

def process_document_to_chunks(doc: dict) -> list:
    """
    Универсальная функция чанкинга документа
    """
    if doc.get("doc_type") == "legislation":
        return chunk_legislation_document(doc)
    else:
        return chunk_markdown_article(doc)
