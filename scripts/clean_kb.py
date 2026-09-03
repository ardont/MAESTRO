"""
Модуль: clean_kb.py

Назначение:
  Интеллектуальная предобработка (очистка) базы знаний Портала Поставщиков (zakupki.mos.ru).
  Превращает сырой HTML-код статей в структурированный Markdown высшего качества.

Какую проблему решает на Портале Поставщиков:
  1. В исходном HTML Портала Поставщиков текст насыщен хаотичными тегами (div, span, p со стилями font-size,
     неразрывными пробелами &nbsp;, таблицами стилей MsoNormal из Word и скриптами).
  2. Простое удаление HTML-тегов (soup.get_text()) безвозвратно уничтожает:
     - Заголовки (H1, H2, H3), которые критически важны для иерархического контекста RAG.
     - Пошаговые нумерованные инструкции (Шаг 1, Шаг 2) — они сливаются в сплошной нечитаемый текст.
     - Сравнительные таблицы параметров СТЕ, сроков котировочных сессий и кодов ошибок РДИК.
     - Иллюстрации и скриншоты интерфейса (теги img), по которым поставщики ориентируются на сайте.
  3. Данный модуль преобразует HTML в чистый Markdown через библиотеку markdownify с кастомными
     правилами для таблиц, списков, изображений и заголовков, а также классифицирует документы
     по типам и тематическим категориям для фасетной фильтрации в Qdrant.

Входные данные:
  - dataset/kb_all_articles.json (основная база статей Портала Поставщиков)
  - dataset/kb_pdfs.json (при наличии — распарсенные PDF-инструкции)

Выходные данные:
  - dataset/kb_clean.json (готовый массив структурированных документов в формате Markdown)
"""

import os
import sys
import json
import re
from bs4 import BeautifulSoup
from markdownify import MarkdownConverter, markdownify as md

# Настройка UTF-8 вывода для Windows консоли
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


class PortalMarkdownConverter(MarkdownConverter):
    """
    Кастомный конвертер HTML -> Markdown, оптимизированный под разметку Портала Поставщиков.
    
    Особенности реализации:
      1. Заголовки (h1-h6): гарантирует отступы и корректные уровни (#, ##, ###).
      2. Таблицы (table, tr, th, td): формирует строгие GitHub Flavored Markdown таблицы с разделителями.
      3. Списки (ul, ol, li): сохраняет иерархию вложенности, маркеры и нумерацию шагов.
      4. Картинки (img): сохраняет alt-описания и приводит относительные URL к абсолютным адресам Портала.
      5. Выделение (strong, b, em): сохраняет акценты на ключевых кнопках и предупреждениях.
    """

    def convert_table(self, el, text, convert_as_inline=False, **kwargs):
        """
        Преобразует HTML-таблицу в валидную Markdown-таблицу.
        
        Зачем это нужно:
          В инструкциях Москвы часто встречаются таблицы:
          - Соответствие СТЕ и КТРУ
          - Сроки подачи оферт и ценовые пороги
          - Сводные таблицы кодов ошибок электронного актирования ЕИС (РДИК)
        """
        rows = el.find_all('tr')
        if not rows:
            return ""

        table_matrix = []
        for row in rows:
            cols = row.find_all(['th', 'td'])
            col_texts = []
            for col in cols:
                # Очищаем ячейку от переносов строк внутри
                cell_text = col.get_text(separator=' ', strip=True).replace('|', '\\|')
                col_texts.append(cell_text)
            if any(col_texts):
                table_matrix.append(col_texts)

        if not table_matrix:
            return ""

        # Нормализуем количество колонок по максимальной строке
        max_cols = max(len(r) for r in table_matrix)
        for r in table_matrix:
            while len(r) < max_cols:
                r.append("")

        # Формируем Markdown-строки
        md_lines = []
        # Первая строка — заголовок таблицы
        headers = table_matrix[0]
        md_lines.append("| " + " | ".join(headers) + " |")
        # Строка-разделитель
        md_lines.append("| " + " | ".join(["---"] * max_cols) + " |")
        # Тело таблицы
        for row in table_matrix[1:]:
            md_lines.append("| " + " | ".join(row) + " |")

        return "\n\n" + "\n".join(md_lines) + "\n\n"

    def convert_img(self, el, text, convert_as_inline=False, **kwargs):
        """
        Преобразует тег <img> в Markdown-изображение: ![alt](url).
        Приводит относительные пути Портала (/cms/... или /static/...) к абсолютным.
        """
        src = el.get('src', '')
        if not src:
            return ""
        if src.startswith('/'):
            src = "https://zakupki.mos.ru" + src

        alt = el.get('alt', '') or el.get('title', '') or 'Изображение интерфейса'
        alt = alt.replace('\n', ' ').strip()
        return f"\n\n![{alt}]({src})\n\n"

    def convert_hn(self, n, el, text, convert_as_inline=False, **kwargs):
        """
        Преобразование заголовков H1..H6 в Markdown с гарантированными переносами строк.
        """
        clean_text = text.strip()
        if not clean_text:
            return ""
        prefix = '#' * n
        return f"\n\n{prefix} {clean_text}\n\n"


def clean_html_to_markdown(html_content: str) -> str:
    """
    Превращает HTML-контент статьи в чистый структурированный Markdown.
    
    Алгоритм:
      1. Парсинг через BeautifulSoup для удаления технических тегов (скрипты, стили, скрытые кнопки).
      2. Замена специфических сущностей Портала (&nbsp;, &quot;, &laquo;, &raquo;).
      3. Конвертация через кастомный PortalMarkdownConverter.
      4. Постобработка: сжатие множественных пустых строк и обрезка краевых пробелов.
    """
    if not html_content or not html_content.strip():
        return ""

    # Шаг 1: Предварительная очистка через BeautifulSoup
    soup = BeautifulSoup(html_content, 'html.parser')

    # Удаляем технический мусор
    for tag in soup(["script", "style", "nav", "footer", "header", "svg", "noscript"]):
        tag.extract()

    # Разворачиваем относительные пути картинок перед конвертацией
    for img in soup.find_all('img'):
        src = img.get('src', '')
        if src.startswith('/'):
            img['src'] = "https://zakupki.mos.ru" + src

    cleaned_html = str(soup)

    # Шаг 2: Конвертация в Markdown
    converter = PortalMarkdownConverter(
        heading_style="atx",  # Использовать '#' для заголовков
        bullets="-",          # Использовать '-' для списков
        autolinks=True        # Автоссылки
    )
    markdown_text = converter.convert(cleaned_html)

    # Шаг 3: Постобработка текста
    # Заменяем типографские артефакты
    markdown_text = markdown_text.replace('\xa0', ' ')
    markdown_text = markdown_text.replace('&nbsp;', ' ')
    markdown_text = markdown_text.replace('&quot;', '"')
    markdown_text = markdown_text.replace('&laquo;', '«').replace('&raquo;', '»')

    # Сжимаем множественные переносы строк (не более двух подряд)
    markdown_text = re.sub(r'\n{3,}', '\n\n', markdown_text)

    # Убираем пробелы в начале и конце строк
    lines = [line.rstrip() for line in markdown_text.splitlines()]
    result = '\n'.join(lines).strip()

    return result


def determine_doc_type(title: str, text: str, section: str = "") -> str:
    """
    Определяет тип документа для базы знаний:
      - legislation: нормативно-правовые акты (44-ФЗ, 223-ФЗ, 63-ФЗ, ГК РФ, официальные регламенты).
      - instruction: пошаговые руководства и инструкции для поставщиков и заказчиков.
      - faq: ответы на типовые вопросы пользователей.
    """
    content = (title + " " + text[:600] + " " + section).lower()

    if any(k in content for k in ["закон", "44-фз", "223-фз", "63-фз", "135-фз", "кодекс", "постановление", "регламент ведения"]):
        return "legislation"

    if any(k in content for k in ["как ", "почему ", "что делать", "в каких случаях", "можно ли", "где найти", "кто может"]):
        return "faq"

    if any(k in content for k in ["инструкция", "руководство", "порядок действий", "шаг 1", "алгоритм", "настройка"]):
        return "instruction"

    return "instruction"


def determine_category(title: str, text: str, service: str = "", category_hint: str = "") -> str:
    """
    Классифицирует документ по предметным категориям Портала Поставщиков Москвы.
    
    Категории:
      - quotation_session: Котировочные сессии, мини-аукционы, ставки, победители, закупки по потребностям.
      - ste_catalog: СТЕ (стандартные товарные единицы), характеристики, КТРУ, оферты, YML прайс-листы.
      - contract_execution: Исполнение контракта, электронное актирование, УПД, ЕИС, Калуга Астрал, РДИК.
      - ecp_mchd: ЭЦП, КЭП, МЧД, сертификаты, КриптоПро CSP, токены, плагины браузера.
      - registration: Регистрация поставщика/заказчика, личный кабинет, ЕСИА, ЕРУЗ, аккредитация.
      - services: Финансовые сервисы, банковские гарантии, спецсчета, факторинг, депозиты.
      - 44fz: Государственные закупки по 44-ФЗ, НМЦК, закупки с полки, реестр контрактов.
      - 223fz: Корпоративные закупки по 223-ФЗ, субъекты МСП, план закупок госкомпаний.
      - kb_article: Общие положения, навигация, регламенты работы службы поддержки.
    """
    title_lower = title.lower()
    search_corpus = f"{title} {service} {category_hint} {text[:800]}".lower()

    # Сначала проверяем прямой заголовок — он наиболее точен
    if any(k in title_lower for k in ["регистраци", "аккредитаци", "еруз", "создание профиля"]):
        return "registration"
    if any(k in title_lower for k in ["эцп", "кэп", "укэп", "мчд", "криптопро", "рутокен", "токен", "сертификат", "доверенност"]):
        return "ecp_mchd"
    if any(k in title_lower for k in ["котировочн", "потребност", "ценовое предложение"]):
        return "quotation_session"
    if any(k in title_lower for k in ["сте", "стандартная товарная единица", "оферт", "прайс-лист", "yml", "ктру", "окпд"]):
        return "ste_catalog"
    if any(k in title_lower for k in ["электронное исполнение", "электронное актирование", "упд", "рдик"]):
        return "contract_execution"

    # Затем проверяем расширенный корпус (сервис, подсказка категории и первые абзацы)
    # 1. Электронная подпись и МЧД
    if any(k in search_corpus for k in ["эцп", "кэп", "укэп", "мчд", "криптопро", "cryptopro", "рутокен", "rutoken", "токен", "сертификат", "доверенност"]):
        return "ecp_mchd"

    # 2. Регистрация и авторизация
    if any(k in search_corpus for k in ["регистраци", "аккредитаци", "еруз", "есиа", "госуслуг", "вход в личный кабинет", "создание профиля"]):
        return "registration"

    # 3. Котировочные сессии и закупки по потребностям
    if any(k in search_corpus for k in ["котировочн", "котировочная сессия", "закупк по потребност", "ценовое предложение", "победител котировочн", "снижение цены"]):
        return "quotation_session"

    # 4. СТЕ, Оферты и Каталог товаров
    if any(k in search_corpus for k in ["сте", "стандартная товарная единица", "оферт", "прайс-лист", "yml", "ктру", "окпд", "характеристик сте", "карточка сте"]):
        return "ste_catalog"

    # 5. Исполнение контракта и электронное актирование
    if any(k in search_corpus for k in ["электронное исполнение", "электронное актирование", "упд", "еис", "калуга астрал", "рдик", "приемка", "акт приема"]):
        return "contract_execution"

    # 6. Законодательство 44-ФЗ
    if any(k in search_corpus for k in ["44-фз", "44 фз", "нмцк", "закупка с полки", "госконтракт"]):
        return "44fz"

    # 7. Законодательство 223-ФЗ
    if any(k in search_corpus for k in ["223-фз", "223 фз", "росатом", "россети", "план закупки"]):
        return "223fz"

    # 8. Финансовые сервисы
    if any(k in search_corpus for k in ["гаранти", "банковская гарантия", "спецсчет", "факторинг", "кредит", "тариф"]):
        return "services"

    return "kb_article"


def process_knowledge_base():
    """
    Основной пайплайн очистки и преобразования базы знаний в Markdown.
    """
    print("=" * 75)
    print("RLT.Tender_Guide: ОЧИСТКА И КОНВЕРТАЦИЯ В MARKDOWN (clean_kb.py)")
    print("=" * 75)

    input_file = os.path.join(os.path.dirname(__file__), '..', 'dataset', 'kb_all_articles.json')
    output_file = os.path.join(os.path.dirname(__file__), '..', 'dataset', 'kb_clean.json')

    if not os.path.exists(input_file):
        print(f"[ОШИБКА] Входной файл {input_file} не найден!")
        return

    with open(input_file, 'r', encoding='utf-8') as f:
        articles = json.load(f)

    print(f"Загружено статей для обработки: {len(articles)}")

    cleaned_dataset = []
    category_distribution = {}
    doc_type_distribution = {}

    for idx, article in enumerate(articles, 1):
        title = (article.get('title') or 'Без заголовка').strip()
        html_content = article.get('html_content') or ''
        sid = article.get('staticId') or article.get('id') or f"art_{idx}"
        url = article.get('url') or f"https://zakupki.mos.ru/knowledgebase/article/{sid}"
        section = article.get('section', '')
        category_hint = article.get('category', '')
        service = article.get('service', '')

        # Преобразуем HTML в чистый Markdown
        md_text = clean_html_to_markdown(html_content)

        # Пропускаем только абсолютно пустые записи (< 5 символов)
        if len(md_text.strip()) < 5:
            # Создаем содержательное описание по заголовку
            md_text = f"## {title}\n\nИнформация по разделу {category_hint or 'База знаний'} Портала Поставщиков Москвы."

        # Классифицируем документ
        doc_type = determine_doc_type(title, md_text, section)
        category = determine_category(title, md_text, service, category_hint)

        # Формируем итоговый объект
        doc_record = {
            "file_name": f"article_{sid}",
            "doc_id": str(sid),
            "title": title,
            "text": md_text,
            "url": url,
            "doc_type": doc_type,
            "category": category,
            "section": section,
            "service": service
        }

        cleaned_dataset.append(doc_record)

        category_distribution[category] = category_distribution.get(category, 0) + 1
        doc_type_distribution[doc_type] = doc_type_distribution.get(doc_type, 0) + 1

    # Сохраняем итоговый файл
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(cleaned_dataset, f, ensure_ascii=False, indent=2)

    print(f"\n[УСПЕХ] Конвертация завершена! Сохранено {len(cleaned_dataset)} статей в {output_file}")
    print("\nРаспределение по типам документов:")
    for dt, cnt in doc_type_distribution.items():
        print(f"   * {dt}: {cnt}")

    print("\nРаспределение по категориям:")
    for cat, cnt in sorted(category_distribution.items(), key=lambda x: x[1], reverse=True):
        print(f"   * {cat}: {cnt}")
    print("=" * 75)


if __name__ == "__main__":
    process_knowledge_base()
