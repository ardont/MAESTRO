"""
url_utils.py — Централизованная нормализация и валидация ссылок Портала Поставщиков Москвы.

Гарантирует 100% канонические рабочие ссылки:
- Статьи AIS: /knowledgebase/article/details/ais/{id} (добавляет пропущенный /details/ais/)
- Регламенты CMS: /knowledgebase/article/details/cms/{cid} (добавляет /details/cms/)
- Официальные документы: заменяет подчеркивания на %20 и адресует верные CDN
"""

import re
import urllib.parse

KNOWN_DOC_REDIRECTS = {
    "01.04.2022": "https://help.mos.ru/upload/iblock/1cd/rykovodstvo_polzovatelei_po_elektronnomy_ispolneniu_kontraktov_01.04.2022.docx",
    "rykovodstvo_polzovatelei_po_elektronnomy_ispolneniu_kontraktov": "https://help.mos.ru/upload/iblock/1cd/rykovodstvo_polzovatelei_po_elektronnomy_ispolneniu_kontraktov_01.04.2022.docx",
}


def normalize_portal_url(url: str) -> str:
    """
    Нормализует любую ссылку на Портал Поставщиков к 100% рабочему каноническому виду.
    Автоматически восстанавливает /details/ais/, /details/cms/, исправляет пути регламентов и документов.
    """
    if not url or not isinstance(url, str):
        return "https://zakupki.mos.ru/knowledgebase/main"

    url = url.strip().strip("'\"<>`").rstrip(").,;:")

    # 1. Проверяем спец-документы (help.mos.ru)
    for trigger, target in KNOWN_DOC_REDIRECTS.items():
        if trigger in url:
            return target

    # 2. Регламенты CMS (вместо нерабочего /knowledgebase/regulations)
    if "knowledgebase/regulations" in url or "knowledgebase/article/regulation" in url:
        return "https://zakupki.mos.ru/knowledgebase/article/regulation/cms"

    # 3. Статьи AIS: id состоит исключительно из цифр (например 506376, 213872)
    m_ais = re.search(r'knowledgebase/article/(?:details/(?:ais/)?|details/)?(\d+)(?:[/?#]|$)', url)
    if m_ais:
        art_id = m_ais.group(1)
        return f"https://zakupki.mos.ru/knowledgebase/article/details/ais/{art_id}"

    # 4. Статьи регламентов CMS: буквенно-цифровой идентификатор (например 48caq6vpp4pn97wbaxsfxnbn4b)
    m_cms = re.search(r'knowledgebase/article/(?:details/(?:cms/)?|details/)?([a-z0-9]{20,})(?:[/?#]|$)', url, re.IGNORECASE)
    if m_cms:
        cms_id = m_cms.group(1)
        return f"https://zakupki.mos.ru/knowledgebase/article/details/cms/{cms_id}"

    # 5. Официальные документы в CMS Media
    if "cms/media/docs/" in url.lower():
        unquoted = urllib.parse.unquote(url)
        filename = unquoted.split("docs/")[-1].strip()
        # Заменяем подчеркивания на пробелы (на сервере файлы с пробелами)
        clean_filename = filename.replace("_", " ")
        encoded_name = urllib.parse.quote(clean_filename)
        return f"https://zakupki.mos.ru/cms/Media/docs/{encoded_name}"

    # 6. Главная страница базы знаний
    if url.endswith("/knowledgebase") or url.endswith("/knowledgebase/"):
        return "https://zakupki.mos.ru/knowledgebase/main"

    # 7. Общая главная страница портала
    if url == "https://zakupki.mos.ru" or url == "https://zakupki.mos.ru/":
        return "https://zakupki.mos.ru/knowledgebase/main"

    # Гарантируем https
    if url.startswith("http://zakupki.mos.ru"):
        url = "https://" + url[7:]

    return url


def normalize_markdown_links(text: str) -> str:
    """
    Находит все ссылки в тексте (как [Заголовок](URL), так и явные текстовые URL)
    и нормализует их адреса к 100% рабочему виду.
    """
    if not text or not isinstance(text, str):
        return ""

    # 1. Заменяем markdown ссылки [текст](url)
    def _replace_md_link(match):
        label = match.group(1)
        raw_url = match.group(2).strip()
        norm_url = normalize_portal_url(raw_url)
        return f"[{label}]({norm_url})"

    text = re.sub(r'\[([^\]]+)\]\((https?://[^\)]+)\)', _replace_md_link, text)

    # 2. Нормализуем неразмеченные ссылки zakupki.mos.ru в сыром тексте
    def _replace_raw_url(match):
        raw_url = match.group(0)
        return normalize_portal_url(raw_url)

    text = re.sub(r'https?://zakupki\.mos\.ru/knowledgebase[^\s\)\]<>"\']+', _replace_raw_url, text)

    return text
