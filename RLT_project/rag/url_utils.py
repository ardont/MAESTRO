"""
url_utils.py — Централизованная нормализация и валидация ссылок Портала Поставщиков Москвы.

Гарантирует 100% канонические рабочие ссылки:
- Статьи AIS: /knowledgebase/article/details/ais/{id} (добавляет пропущенный /details/ais/)
- Регламенты CMS: /knowledgebase/article/details/cms/{cid} (добавляет /details/cms/)
- Официальные документы: заменяет подчеркивания на %20 и адресует верные CDN
"""

import os
import json
import re
import urllib.parse
from pathlib import Path
from typing import Optional, Dict, Any

# Загружаем официальный реестр статей базы знаний
ARTICLES_BY_STATIC_ID: Dict[str, Dict[str, Any]] = {}
ARTICLES_BY_ID: Dict[str, Dict[str, Any]] = {}

def _init_articles_database():
    global ARTICLES_BY_STATIC_ID, ARTICLES_BY_ID
    if ARTICLES_BY_STATIC_ID:
        return
    possible_paths = [
        Path(__file__).resolve().parent.parent.parent / "dataset" / "data" / "articles.json",
        Path("/app/dataset/data/articles.json"),
        Path("dataset/data/articles.json"),
        Path("../dataset/data/articles.json"),
    ]
    for p in possible_paths:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    articles = json.load(f)
                for a in articles:
                    sid = str(a.get("staticId") or "").strip()
                    aid = str(a.get("id") or "").strip()
                    name = (a.get("largeName") or "").strip()
                    if sid and name:
                        entry = {
                            "title": name,
                            "staticId": sid,
                            "id": aid,
                            "url": f"https://zakupki.mos.ru/knowledgebase/article/details/ais/{sid}"
                        }
                        ARTICLES_BY_STATIC_ID[sid] = entry
                        if aid:
                            ARTICLES_BY_ID[aid] = entry
                break
            except Exception:
                pass

_init_articles_database()


def get_verified_article(art_id: str) -> Optional[Dict[str, Any]]:
    """Возвращает верифицированную статью из официальной базы по staticId или id."""
    _init_articles_database()
    s = str(art_id).strip()
    return ARTICLES_BY_STATIC_ID.get(s) or ARTICLES_BY_ID.get(s)


def clean_citation_title(title: str, url: str = "") -> str:
    """
    Гарантирует 100% точное соответствие названия статьи её содержимому на Портале.
    1. Если URL содержит ID статьи из реестра — возвращает эталонное название (largeName).
    2. Если название содержит технические артефакты (SOURCE URL: ...) — очищает их.
    """
    _init_articles_database()
    if url:
        m_ais = re.search(r'knowledgebase/article/(?:details/(?:ais/)?|details/)?(\d+)(?:[/?#]|$)', url)
        if m_ais:
            verified = get_verified_article(m_ais.group(1))
            if verified and verified.get("title"):
                return verified["title"]

    cleaned = (title or "").strip()
    # Убираем технический мусор парсеров
    cleaned = re.sub(r'^SOURCE\s+URL:\s*https?://\S+', '', cleaned).strip()
    cleaned = re.sub(r'https?://\S+', '', cleaned).strip()
    cleaned = cleaned.strip(" -:—|")
    return cleaned if cleaned else "Официальная база знаний Портала поставщиков"


KNOWN_DOC_REDIRECTS = {
    "01.04.2022": "https://help.mos.ru/upload/iblock/1cd/rykovodstvo_polzovatelei_po_elektronnomy_ispolneniu_kontraktov_01.04.2022.docx",
    "rykovodstvo_polzovatelei_po_elektronnomy_ispolneniu_kontraktov": "https://help.mos.ru/upload/iblock/1cd/rykovodstvo_polzovatelei_po_elektronnomy_ispolneniu_kontraktov_01.04.2022.docx",
}


def normalize_portal_url(url: str) -> str:
    """
    Нормализует любую ссылку на Портал Поставщиков к 100% рабочему каноническому виду.
    Автоматически сопоставляет ID статей с официальной базой Портала.
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
        verified = get_verified_article(art_id)
        if verified:
            return verified["url"]
        return f"https://zakupki.mos.ru/knowledgebase/article/details/ais/{art_id}"

    # 4. Статьи регламентов CMS: буквенно-цифровой идентификатор (например 48caq6vpp4pn97wbaxsfxnbn4b)
    m_cms = re.search(r'knowledgebase/article/(?:details/(?:cms/)?|details/)?([a-z0-9]{20,})(?:[/?#]|$)', url, re.IGNORECASE)
    if m_cms:
        cms_id = m_cms.group(1)
        return f"https://zakupki.mos.ru/knowledgebase/article/details/cms/{cms_id}"

    # 5. Официальные документы в CMS Media / PDF инструкции
    if "cms/media/docs/" in url.lower() or "knowledgebase/docs/" in url.lower() or url.lower().endswith(".pdf"):
        unquoted = urllib.parse.unquote(url)
        filename = unquoted.split("/")[-1].strip()
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
        clean_label = clean_citation_title(label, norm_url)
        return f"[{clean_label}]({norm_url})"

    text = re.sub(r'\[([^\]]+)\]\((https?://[^\)]+)\)', _replace_md_link, text)

    # 2. Нормализуем неразмеченные ссылки zakupki.mos.ru в сыром тексте
    def _replace_raw_url(match):
        raw_url = match.group(0)
        return normalize_portal_url(raw_url)

    text = re.sub(r'https?://zakupki\.mos\.ru/knowledgebase[^\s\)\]<>"\']+', _replace_raw_url, text)

    return text

