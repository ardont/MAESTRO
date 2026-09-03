"""
Модуль: chunker.py (ЯДРО ИНТЕЛЛЕКТУАЛЬНОГО ЧАНКИНГА)

Назначение:
  Разбиение структурированных Markdown-документов (инструкций, регламентов, законов)
  на оптимизированные семантические фрагменты (чанки) с сохранением полного контекста
  и метаданных для RAG-пайплайна Портала Поставщиков Москвы (zakupki.mos.ru).

Какую проблему решает на Портале Поставщиков:
  1. Документы Портала (инструкции по котировочным сессиям, регламенты ведения СТЕ,
     законы 44-ФЗ и 223-ФЗ) объемны (до 50-100 страниц). Модели эмбеддингов
     (ru-en-RoSBERTa) принимают максимум 512 токенов (~1500 символов).
  2. Примитивный сплиттер (по фиксированному числу символов):
     - Разрывает таблицы характеристик СТЕ и кодов ошибок РДИК прямо посередине строки.
     - Отрывает номера шагов ("Шаг 3. Нажмите Подписать") от поясняющего текста и скриншота.
     - Разрывает юридические статьи законов, лишая норму обязательных условий (диспозиции/санкции).
     - Теряет контекст: найденный чанк содержит "Нажмите кнопку Отправить", но неизвестно,
       в каком разделе и для какого действия (подача оферты или отклонение протокола).
  3. Настоящий модуль реализует ИЕРАРХИЧЕСКИЙ СТРУКТУРНЫЙ ЧАНКИНГ:
     - Отслеживает дерево заголовков (H1 -> H2 -> H3) и добавляет в каждый чанк
       контекстный префикс вида: [Документ: ... | Раздел: ... | Категория: ...].
     - Сохраняет таблицы целиком, а при превышении лимита делит строго по строкам,
       дублируя заголовок таблицы в каждом подчанке.
     - Сохраняет пошаговые алгоритмы (Шаг 1, Шаг 2) и привязывает локальные скриншоты.
     - Юридический чанкинг для нормативных актов делит строго по Статьям и Пунктам.
     - Поддерживает специфику Москвы: Котировочные сессии, СТЕ, Оферты, ЭДО ЕИС.

Контракт чанка (выходные поля каждого словаря):
  - chunk_id: Уникальный UUID4
  - doc_id: Идентификатор исходного документа
  - title: Полное название документа/статьи
  - url: Прямая ссылка на первоисточник Портала
  - category: Тематическая категория (quotation_session, ste_catalog, ecp_mchd и др.)
  - doc_type: Тип документа (instruction, legislation, faq)
  - section_header: Полный путь заголовков (H1 > H2 > H3)
  - step_number: Номер шага (если применимо, например "Шаг 2")
  - images: Список локальных путей к скриншотам (например ["images/art_123_btn.png"])
  - text: Готовый текст фрагмента с контекстным префиксом для векторизации
"""

import re
import uuid
from typing import List, Dict, Any, Optional, Tuple

# Импортируем конфигурационные константы RAG
from .config import CHUNK_SIZE, CHUNK_OVERLAP
from .image_extractor import extract_images_from_markdown


# =====================================================================
# 1. ТЕКСТОВЫЙ СПЛИТТЕР С ПРИОРИТЕТОМ РАЗДЕЛИТЕЛЕЙ (FALLBACK / CORE)
# =====================================================================

class SmartTextSplitter:
    """
    Интеллектуальный рекурсивный сплиттер текста.
    
    В отличие от наивной нарезки, учитывает естественные границы русского языка
    и структуры Markdown: абзацы -> строки списков -> предложения -> точки с запятой -> пробелы.
    """

    def __init__(
        self,
        chunk_size: int = CHUNK_SIZE,
        chunk_overlap: int = CHUNK_OVERLAP,
        separators: Optional[List[str]] = None
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        # Приоритет разделителей от крупных смысловых блоков к мелким
        self.separators = separators or [
            "\n\n",          # Граница между абзацами
            "\n- ",          # Элемент ненумерованного списка
            "\n* ",          # Элемент списка со звездочкой
            "\n1. ", "\n2. ", "\n3. ", "\n4. ", "\n5. ",  # Нумерованные шаги
            "\n",            # Одиночный перевод строки
            ". ",            # Конец предложения
            ";\n", "; ",     # Точка с запятой (перечисления в нормативных актах)
            ", ",            # Запятая
            " "              # Разрыв по словам (крайний случай)
        ]

    def split_text(self, text: str) -> List[str]:
        """
        Разбивает длинный текст на связные фрагменты с заданным перекрытием (overlap).
        """
        text = text.strip()
        if len(text) <= self.chunk_size:
            return [text] if text else []

        chunks = []
        start = 0

        while start < len(text):
            end = min(start + self.chunk_size, len(text))

            # Если мы не дошли до конца текста — ищем ближайший удобный разделитель
            if end < len(text):
                found_split = False
                for sep in self.separators:
                    last_pos = text.rfind(sep, start, end)
                    # Разделитель должен быть глубже трети чанка, чтобы не делать микрочанки
                    if last_pos != -1 and last_pos > start + (self.chunk_size // 3):
                        end = last_pos + len(sep)
                        found_split = True
                        break

                # Если разделитель не найден в окне — ищем пробел назад
                if not found_split:
                    space_pos = text.rfind(" ", start, end)
                    if space_pos != -1 and space_pos > start:
                        end = space_pos + 1

            chunk_content = text[start:end].strip()
            if chunk_content:
                chunks.append(chunk_content)

            # Сдвигаем окно с учетом overlap
            if end >= len(text):
                break
            start = max(start + 1, end - self.chunk_overlap)

        return chunks


# Глобальный экземпляр сплиттера
text_splitter = SmartTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)


# =====================================================================
# 2. ОБРАБОТКА И СОХРАНЕНИЕ ТАБЛИЦ (TABLE CHUNKING)
# =====================================================================

def split_markdown_table_if_needed(table_text: str, max_size: int = CHUNK_SIZE) -> List[str]:
    """
    Разрезает слишком большую Markdown-таблицу строго по строкам данных,
    при этом ДУБЛИРУЕТ строку заголовков и разделителей в начале каждого подчанка.
    
    Зачем это нужно:
      Если таблица характеристик СТЕ на 40 параметров разрежется посередине,
      без заголовка колонки модель не поймет, что означает число '12' (вольт, штук или дней).
    """
    lines = [line.strip() for line in table_text.strip().splitlines() if line.strip()]
    if len(lines) < 3:
        return [table_text]

    header_line = lines[0]
    separator_line = lines[1]
    data_rows = lines[2:]

    # Если таблица помещается целиком — возвращаем как есть
    if len(table_text) <= max_size:
        return [table_text]

    table_chunks = []
    current_rows = []
    current_len = len(header_line) + len(separator_line) + 4

    for row in data_rows:
        row_len = len(row) + 1
        if current_len + row_len > max_size and current_rows:
            # Формируем законченный подчанк с заголовком таблицы
            chunk_body = f"{header_line}\n{separator_line}\n" + "\n".join(current_rows)
            table_chunks.append(chunk_body)
            current_rows = [row]
            current_len = len(header_line) + len(separator_line) + 4 + row_len
        else:
            current_rows.append(row)
            current_len += row_len

    if current_rows:
        chunk_body = f"{header_line}\n{separator_line}\n" + "\n".join(current_rows)
        table_chunks.append(chunk_body)

    return table_chunks


# =====================================================================
# 3. ИЕРАРХИЧЕСКИЙ ЧАНКИНГ ИНСТРУКЦИЙ И FAQ (MARKDOWN)
# =====================================================================

def extract_step_number(text: str) -> Optional[str]:
    """
    Извлекает номер шага из текста (например: 'Шаг 1', 'Шаг 2.1', 'Этап 3').
    """
    match = re.search(r'(?:^|\n|\b)(Шаг\s+\d+(?:\.\d+)?|Этап\s+\d+)', text, re.IGNORECASE)
    if match:
        return match.group(1).capitalize()
    return None


def chunk_markdown_article(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Умный чанкинг для статей базы знаний, регламентов и пошаговых инструкций Москвы.
    
    Алгоритм:
      1. Парсит дерево заголовков (# H1, ## H2, ### H3, #### H4).
      2. Отслеживает иерархию разделов (Breadcrumbs), чтобы дочерние чанки
         наследовали контекст родительских разделов.
      3. Анализирует блоки внутри разделов (абзацы, списки, таблицы).
      4. Привязывает иллюстрации и скриншоты интерфейса к соответствующему шагу.
      5. Добавляет метаданные: doc_id, category, doc_type, step_number, images, url.
    """
    text = doc.get("text", "")
    title = doc.get("title", "Без названия").strip()
    url = doc.get("url", "")
    category = doc.get("category", "kb_article")
    doc_type = doc.get("doc_type", "instruction")
    doc_id = str(doc.get("doc_id") or doc.get("file_name") or uuid.uuid4())

    # Все картинки статьи (для fallback-привязки при необходимости)
    all_doc_images = extract_images_from_markdown(text)

    # Регулярка для поиска Markdown-заголовков (#..####)
    header_regex = re.compile(r'(^|\n)(#{1,4}\s+[^\n]+)')
    matches = list(header_regex.finditer(text))

    sections: List[Tuple[str, str, int]] = []  # (заголовок, тело_секции, уровень_H)

    if not matches:
        # Если явных заголовков нет — считаем весь документ одной секцией
        sections.append((title, text, 1))
    else:
        # Если есть текст до первого заголовка (введение/преамбула)
        if matches[0].start() > 0:
            intro_text = text[:matches[0].start()].strip()
            if len(intro_text) > 20:
                sections.append(("Введение", intro_text, 2))

        # Собираем секции по границам заголовков
        for i in range(len(matches)):
            start_pos = matches[i].start()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(text)

            raw_header_match = matches[i].group(2).strip()
            # Определяем уровень заголовка по количеству '#'
            level = len(raw_header_match) - len(raw_header_match.lstrip('#'))
            clean_header = raw_header_match.lstrip('#').strip()
            section_body = text[start_pos:end_pos].strip()

            sections.append((clean_header, section_body, level))

    chunks: List[Dict[str, Any]] = []
    active_breadcrumb_stack: List[Tuple[int, str]] = []

    for header_title, body_text, level in sections:
        # Обновляем стек хлебных крошек (breadcrumb stack)
        while active_breadcrumb_stack and active_breadcrumb_stack[-1][0] >= level:
            active_breadcrumb_stack.pop()
        active_breadcrumb_stack.append((level, header_title))

        breadcrumb_path = " > ".join([h[1] for h in active_breadcrumb_stack])
        if not breadcrumb_path:
            breadcrumb_path = title

        # Извлекаем картинки, присутствующие именно в этой секции
        section_images = extract_images_from_markdown(body_text)

        # Если в секции нет картинок, но документ содержит скриншоты —
        # привязываем первые картинки к ключевым интерактивным разделам
        if not section_images and all_doc_images:
            interactive_keywords = ["кнопк", "нажат", "вход", "окно", "шаг", "подать", "загруз", "интерфейс"]
            if any(k in header_title.lower() for k in interactive_keywords):
                section_images = all_doc_images[:2]

        # Проверяем наличие Markdown-таблицы в секции
        if "|" in body_text and "---" in body_text:
            # Выделяем таблицу из секции
            table_match = re.search(r'(\|[^\n]+\|\n\|[\s\-:|]+\|\n(?:\|[^\n]+\|\n?)+)', body_text)
            if table_match:
                table_str = table_match.group(1)
                before_table = body_text[:table_match.start()].strip()
                after_table = body_text[table_match.end():].strip()

                sub_tables = split_markdown_table_if_needed(table_str, CHUNK_SIZE)
                # Обрабатываем текст до таблицы
                if before_table:
                    for sub_t in text_splitter.split_text(before_table):
                        chunks.append(_create_chunk(
                            doc_id=doc_id, title=title, url=url, category=category,
                            doc_type=doc_type, breadcrumb=breadcrumb_path,
                            body=sub_t, images=section_images
                        ))
                # Добавляем чанки таблицы
                for tbl_chunk in sub_tables:
                    chunks.append(_create_chunk(
                        doc_id=doc_id, title=title, url=url, category=category,
                        doc_type=doc_type, breadcrumb=f"{breadcrumb_path} (Таблица)",
                        body=tbl_chunk, images=section_images
                    ))
                # Обрабатываем текст после таблицы
                if after_table:
                    for sub_t in text_splitter.split_text(after_table):
                        chunks.append(_create_chunk(
                            doc_id=doc_id, title=title, url=url, category=category,
                            doc_type=doc_type, breadcrumb=breadcrumb_path,
                            body=sub_t, images=section_images
                        ))
                continue

        # Обычная секция: если помещается в лимит — один чанк
        if len(body_text) <= CHUNK_SIZE + CHUNK_OVERLAP:
            chunks.append(_create_chunk(
                doc_id=doc_id, title=title, url=url, category=category,
                doc_type=doc_type, breadcrumb=breadcrumb_path,
                body=body_text, images=section_images
            ))
        else:
            # Секция слишком длинная — дробим через SmartTextSplitter
            sub_parts = text_splitter.split_text(body_text)
            for part_idx, part in enumerate(sub_parts, 1):
                part_header = f"{breadcrumb_path} (Часть {part_idx})"
                # Ищем картинки именно в этом подчанке
                part_images = extract_images_from_markdown(part) or section_images
                chunks.append(_create_chunk(
                    doc_id=doc_id, title=title, url=url, category=category,
                    doc_type=doc_type, breadcrumb=part_header,
                    body=part, images=part_images
                ))

    return chunks


# =====================================================================
# 4. ЮРИДИЧЕСКИЙ ЧАНКИНГ НОРМАТИВНЫХ АКТОВ (44-ФЗ, 223-ФЗ, 63-ФЗ)
# =====================================================================

def chunk_legislation_document(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Специализированный юридический чанкинг для законов и кодексов РФ:
      - Федеральный закон №44-ФЗ (О контрактной системе в сфере госзакупок)
      - Федеральный закон №223-ФЗ (О закупках отдельными видами юрлиц)
      - Федеральный закон №63-ФЗ (Об электронной подписи)
      - Федеральный закон №135-ФЗ (О защите конкуренции)
      - Гражданский кодекс РФ (Часть первая)
    
    Принцип:
      1. Резка строго по границам «Статья N. Название статьи».
      2. Если статья длинная — деление строго по частям / пунктам (1., 2., 3.).
      3. Ни в коем случае не разрывать условие нормы и её санкцию.
      4. Префикс каждого чанка явно указывает закон и номер статьи:
         [Закон: 44-ФЗ | Статья 93. Закупка у единственного поставщика (Часть 1)]
    """
    text = doc.get("text", "")
    title = doc.get("title", "Нормативный документ").strip()
    url = doc.get("url", "")
    category = doc.get("category", "legislation")
    doc_type = "legislation"
    doc_id = str(doc.get("doc_id") or doc.get("file_name") or uuid.uuid4())

    # Паттерн поиска статей: "Статья 93.", "Статья 3.1.", "Статья 4."
    article_pattern = re.compile(r'(^|\n)(Статья\s+\d+(?:\.\d+)?\.?[^\n]*)', re.IGNORECASE)
    matches = list(article_pattern.finditer(text))

    if not matches:
        # Если в документе нет деления на статьи (регламент/положение)
        raw_parts = text_splitter.split_text(text)
        chunks = []
        for p_idx, part in enumerate(raw_parts, 1):
            chunks.append(_create_chunk(
                doc_id=doc_id, title=title, url=url, category=category,
                doc_type=doc_type, breadcrumb=f"{title} | Часть {p_idx}",
                body=part, images=[]
            ))
        return chunks

    chunks: List[Dict[str, Any]] = []

    for i in range(len(matches)):
        start = matches[i].start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)

        article_header = matches[i].group(2).strip()
        article_body = text[start:end].strip()

        # Если статья помещается в чанк целиком — сохраняем неделимо
        if len(article_body) <= CHUNK_SIZE + CHUNK_OVERLAP:
            chunks.append(_create_chunk(
                doc_id=doc_id, title=title, url=url, category=category,
                doc_type=doc_type, breadcrumb=article_header,
                body=article_body, images=[]
            ))
        else:
            # Статья длинная — делим по частям статьи (1., 2., 3.)
            part_pattern = re.compile(r'(^|\n)(\d+\.\s+[^\n]+)')
            part_matches = list(part_pattern.finditer(article_body))

            if part_matches:
                for p_i in range(len(part_matches)):
                    p_start = part_matches[p_i].start()
                    p_end = part_matches[p_i + 1].start() if p_i + 1 < len(part_matches) else len(article_body)
                    part_num = part_matches[p_i].group(2)[:15].strip()
                    part_text = article_body[p_start:p_end].strip()

                    # Если даже одна часть статьи слишком велика — делим сплиттером
                    if len(part_text) > CHUNK_SIZE + CHUNK_OVERLAP:
                        sub_splits = text_splitter.split_text(part_text)
                        for s_idx, s_text in enumerate(sub_splits, 1):
                            chunks.append(_create_chunk(
                                doc_id=doc_id, title=title, url=url, category=category,
                                doc_type=doc_type,
                                breadcrumb=f"{article_header} | Пункт {part_num} (п.{s_idx})",
                                body=s_text, images=[]
                            ))
                    else:
                        chunks.append(_create_chunk(
                            doc_id=doc_id, title=title, url=url, category=category,
                            doc_type=doc_type, breadcrumb=f"{article_header} | Пункт {part_num}",
                            body=part_text, images=[]
                        ))
            else:
                # Если нумерованных частей нет — делим SmartTextSplitter
                sub_splits = text_splitter.split_text(article_body)
                for s_idx, s_text in enumerate(sub_splits, 1):
                    chunks.append(_create_chunk(
                        doc_id=doc_id, title=title, url=url, category=category,
                        doc_type=doc_type, breadcrumb=f"{article_header} (Часть {s_idx})",
                        body=s_text, images=[]
                    ))

    return chunks


# =====================================================================
# 5. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ И ТОЧКА ВХОДА
# =====================================================================

def _create_chunk(
    doc_id: str,
    title: str,
    url: str,
    category: str,
    doc_type: str,
    breadcrumb: str,
    body: str,
    images: List[str]
) -> Dict[str, Any]:
    """
    Фабрика создания чанка с контекстным заголовком и валидными метаданными.
    """
    # Определяем номер шага, если он есть в тексте
    step_num = extract_step_number(breadcrumb) or extract_step_number(body)

    # Формируем семантический контекстный префикс
    # Модель при векторизации видит метаданные прямо в начале текста
    context_prefix = f"[Документ: {title} | Раздел: {breadcrumb} | Категория: {category}]"
    final_text = f"{context_prefix}\n\n{body.strip()}"

    return {
        "chunk_id": str(uuid.uuid4()),
        "doc_id": doc_id,
        "title": title,
        "url": url,
        "category": category,
        "doc_type": doc_type,
        "section_header": breadcrumb,
        "step_number": step_num,
        "images": images or [],
        "text": final_text
    }


def process_document_to_chunks(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Главная точка входа для чанкинга любого документа в RAG-системе.
    
    Автоматически определяет стратегию:
      - legislation (законы, кодексы) -> chunk_legislation_document()
      - instruction, faq, articles     -> chunk_markdown_article()
    """
    doc_type = doc.get("doc_type", "instruction")
    if doc_type == "legislation":
        return chunk_legislation_document(doc)
    else:
        return chunk_markdown_article(doc)
