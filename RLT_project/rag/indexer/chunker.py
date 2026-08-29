"""
chunker.py — Модуль умного чанкинга (разбивки документов на фрагменты).

Зачем нужен чанкинг?
  Документы (законы, инструкции) слишком длинные для прямой векторизации.
  BERT-модель принимает максимум ~512 токенов (~750 символов).
  Поэтому каждый документ нарезается на «чанки» — короткие фрагменты
  с метаданными (заголовок, URL, категория, скриншоты).

Два режима чанкинга:
  1. chunk_legislation_document() — для законов (режет по "Статья N")
  2. chunk_markdown_article()     — для статей базы знаний (режет по заголовкам ##)

Каждый чанк — это словарь с полями:
  chunk_id, doc_id, title, url, category, doc_type, section_header, images, text
"""

import re       # Регулярные выражения — для поиска заголовков и статей в тексте
import uuid     # Генератор уникальных идентификаторов (UUID4) для каждого чанка

# Пытаемся импортировать профессиональный сплиттер из LangChain.
# Если библиотека не установлена — используем собственную упрощённую реализацию.
try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError:
    # === FALLBACK: Собственная реализация RecursiveCharacterTextSplitter ===
    # Работает так же, как LangChain-версия: делит текст на части
    # по списку разделителей (от крупных к мелким), стараясь
    # не разрывать предложения.
    class RecursiveCharacterTextSplitter:
        def __init__(self, chunk_size=750, chunk_overlap=120, separators=None):
            self.chunk_size = chunk_size        # Максимум символов в одном чанке
            self.chunk_overlap = chunk_overlap    # Перекрытие между чанками
            # Приоритет разделителей: абзац > строка > точка > точка с запятой > запятая > пробел
            self.separators = separators or ["\n\n", "\n", ". ", "; ", ", ", " "]

        def split_text(self, text: str) -> list:
            """Разбивает текст на чанки заданного размера."""
            # Если текст и так короче лимита — возвращаем как есть
            if len(text) <= self.chunk_size:
                return [text]

            chunks = []
            start = 0  # Позиция начала текущего чанка

            while start < len(text):
                # Определяем конец чанка (не дальше chunk_size от начала)
                end = min(start + self.chunk_size, len(text))

                if end < len(text):
                    # Ищем ближайший «удобный» разделитель перед концом чанка,
                    # чтобы не обрезать текст посреди слова или предложения.
                    # rfind() ищет ПОСЛЕДНЕЕ вхождение разделителя в диапазоне [start, end]
                    for sep in self.separators:
                        last_sep = text.rfind(sep, start, end)
                        if last_sep != -1 and last_sep > start:
                            end = last_sep + len(sep)  # Сдвигаем конец к разделителю
                            break

                # Обрезаем пробелы по краям и добавляем непустой чанк
                chunk = text[start:end].strip()
                if chunk:
                    chunks.append(chunk)

                # Следующий чанк начинается с перекрытием (overlap),
                # чтобы контекст на границе не терялся
                start = max(start + 1, end - self.chunk_overlap)

            return chunks

# Импортируем параметры чанкинга из центрального конфига
from .config import CHUNK_SIZE, CHUNK_OVERLAP
# Функция для извлечения ссылок на картинки из markdown-текста
from .image_extractor import extract_images_from_markdown

# Создаём глобальный экземпляр сплиттера (один на весь модуль).
# Параметры берутся из config.py: CHUNK_SIZE=750, CHUNK_OVERLAP=120.
# Разделители упорядочены от «крупных» к «мелким»:
#   \n\n — двойной перевод строки (между абзацами)
#   \n   — одинарный перевод строки
#   ". " — конец предложения
#   "; " — точка с запятой (в перечислениях)
#   ", " — запятая
#   " "  — пробел (крайний случай — разрыв по словам)
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n\n", "\n", ". ", "; ", ", ", " "]
)

def chunk_legislation_document(doc: dict) -> list:
    """
    Умный чанкинг для ЗАКОНОДАТЕЛЬНЫХ документов (44-ФЗ, 223-ФЗ и т.д.).

    Логика:
      1. Ищем в тексте все заголовки вида "Статья 93. Закупка у единственного поставщика"
      2. Каждую статью оформляем как отдельный чанк
      3. Если статья слишком длинная (> CHUNK_SIZE) — дополнительно делим на части
      4. К каждому чанку прикрепляем метаданные: заголовок, URL, категория

    Аргумент:
      doc — словарь с полями: text, title, url, category, doc_type, file_name

    Возвращает:
      Список чанков (каждый — словарь с text, chunk_id, title, url и пр.)
    """
    # Извлекаем метаданные документа
    text = doc["text"]           # Полный текст закона
    title = doc["title"]         # Название (напр. "Федеральный закон №44-ФЗ")
    url = doc["url"]             # Ссылка на источник
    category = doc["category"]   # Категория (напр. "44fz")
    doc_type = doc["doc_type"]   # Тип документа ("legislation")
    file_name = doc["file_name"] # Имя исходного файла

    # Регулярное выражение для поиска заголовков статей:
    # Ищет строки вида "Статья 93", "Статья 44.1", "Статья 7.2. Название" и т.п.
    # (^|\n) — начало строки или перевод строки перед статьёй
    article_pattern = re.compile(r"(^|\n)(Статья\s+\d+(?:\.\d+)?\.?[^\n]*)", re.IGNORECASE)
    
    # Находим все позиции заголовков статей в тексте
    matches = list(article_pattern.finditer(text))
    chunks = []  # Сюда будем складывать готовые чанки

    # Если в тексте НЕ найдено ни одной "Статья N" — значит это
    # вводная часть или документ без статейной структуры.
    # Просто разбиваем весь текст обычным сплиттером.
    if not matches:
        raw_chunks = text_splitter.split_text(text)
        for idx, ch_text in enumerate(raw_chunks):
            # Добавляем контекстную метку перед текстом чанка,
            # чтобы при поиске модель «знала», откуда этот фрагмент
            chunk_body = f"[Документ: {title} | Общие положения]\n\n{ch_text.strip()}"
            chunks.append({
                "chunk_id": str(uuid.uuid4()),  # Уникальный ID чанка (UUID4)
                "doc_id": file_name,             # Из какого файла
                "title": title,                  # Название документа
                "url": url,                      # Ссылка на источник
                "category": category,            # Категория для фильтрации
                "doc_type": doc_type,            # Тип документа
                "section_header": "Общие положения",  # Название раздела
                "images": [],                    # У законов обычно нет картинок
                "text": chunk_body               # Текст чанка с контекстной меткой
            })
        return chunks

    # Проходим по каждой найденной статье.
    # Текст статьи = от её заголовка до начала следующей статьи.
    for i in range(len(matches)):
        start = matches[i].start()  # Позиция начала текущей статьи
        # Конец текущей статьи = начало следующей (или конец текста, если это последняя)
        end = matches[i+1].start() if i + 1 < len(matches) else len(text)

        article_header = matches[i].group(2).strip()  # Заголовок: "Статья 93. Закупка..."
        article_body = text[start:end].strip()         # Полный текст этой статьи

        # Если статья слишком длинная для одного чанка — дробим её на подчанки
        if len(article_body) > CHUNK_SIZE + CHUNK_OVERLAP:
            sub_chunks = text_splitter.split_text(article_body)
            for sub_idx, sub_text in enumerate(sub_chunks):
                # Помечаем каждый подчанк номером части: "Статья 93 (Часть 1)", "(Часть 2)"...
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
            # Статья помещается целиком в один чанк — отлично
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
    Умный чанкинг для СТАТЕЙ БАЗЫ ЗНАНИЙ (инструкции, FAQ).

    Логика:
      1. Извлекаем все картинки/скриншоты из markdown-текста
      2. Разбиваем текст на секции по заголовкам (## и ###)
      3. Каждую секцию оформляем как чанк (или несколько, если секция длинная)
      4. К чанкам прикрепляем найденные скриншоты

    Аргумент:
      doc — словарь с полями: text, title, url, category, doc_type, file_name

    Возвращает:
      Список чанков (каждый — словарь с text, chunk_id, images и пр.)
    """
    # Извлекаем метаданные документа
    text = doc["text"]           # Полный markdown-текст статьи
    title = doc["title"]         # Заголовок статьи
    url = doc["url"]             # URL-источник
    category = doc["category"]   # Категория (ecp_mchd, 44fz, ...)
    doc_type = doc["doc_type"]   # Тип ("instruction", "kb_article")
    file_name = doc["file_name"] # Имя файла-источника

    # ШАГ 1: Извлекаем ВСЕ ссылки на изображения из всего текста документа.
    # Они пригодятся как fallback, если в конкретной секции картинок нет.
    doc_images = extract_images_from_markdown(text)
    
    # ШАГ 2: Разбиваем текст на секции по markdown-заголовкам (# / ## / ###).
    # Регулярка ищет строки, начинающиеся с 1-3 символов "#" и пробела.
    header_pattern = re.compile(r"(^|\n)(#{1,3}\s+[^\n]+)")
    matches = list(header_pattern.finditer(text))

    sections = []  # Список пар: (заголовок_секции, текст_секции)

    if not matches:
        # Если заголовков нет — весь текст считаем одной секцией
        sections.append(("Основная информация", text))
    else:
        # Если перед первым заголовком есть текст (вводная часть) — берём его отдельно
        if matches[0].start() > 0:
            intro_text = text[:matches[0].start()].strip()
            # Игнорируем слишком короткие обрывки (< 20 символов)
            if len(intro_text) > 20:
                sections.append(("Введение", intro_text))

        # Проходим по каждому заголовку: текст секции = от заголовка до следующего
        for i in range(len(matches)):
            start = matches[i].start()
            end = matches[i+1].start() if i + 1 < len(matches) else len(text)

            raw_header = matches[i].group(2).strip()  # Сырой заголовок: "## Настройка ЭЦП"
            # Убираем символы "#" из заголовка → "Настройка ЭЦП"
            clean_header = re.sub(r"^#{1,3}\s+", "", raw_header).strip()
            section_body = text[start:end].strip()     # Полный текст секции
            sections.append((clean_header, section_body))

    # ШАГ 3: Каждую секцию превращаем в один или несколько чанков
    chunks = []
    for sec_header, sec_body in sections:
        # Ищем картинки, упомянутые непосредственно в этой секции
        sec_images = extract_images_from_markdown(sec_body)

        # Если в секции нет картинок, но в документе целиком они есть —
        # привязываем первые 2 картинки к «визуальным» секциям
        # (те, что описывают UI, кнопки, шаги, окна интерфейса)
        if not sec_images and doc_images:
            visual_keywords = ["установка", "настройка", "подача", "интерфейс",
                               "вход", "шаг", "окно", "кнопк", "личный"]
            if any(w in sec_header.lower() for w in visual_keywords):
                sec_images = doc_images[:2]  # Берём максимум 2 картинки

        # Если секция слишком длинная — дробим на подчанки
        if len(sec_body) > CHUNK_SIZE + CHUNK_OVERLAP:
            sub_chunks = text_splitter.split_text(sec_body)
            for sub_idx, sub_text in enumerate(sub_chunks):
                # Контекстный префикс помогает модели при поиске «знать»,
                # из какого документа и раздела этот фрагмент
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
                    "images": sec_images,  # Все подчанки секции делят одни картинки
                    "text": chunk_body
                })
        else:
            # Секция помещается в один чанк целиком
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
    Точка входа для чанкинга: выбирает стратегию в зависимости от типа документа.

    - legislation (закон/кодекс)  → chunk_legislation_document() — режет по статьям
    - всё остальное (инструкция)  → chunk_markdown_article()     — режет по заголовкам ##

    Вызывается из index_knowledge_base.py при индексации всей базы знаний.
    """
    if doc.get("doc_type") == "legislation":
        return chunk_legislation_document(doc)
    else:
        return chunk_markdown_article(doc)
