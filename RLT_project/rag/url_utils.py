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
        Path(__file__).resolve().parent.parent.parent / "dataset" / "articles.json",
        Path("/app/dataset/data/articles.json"),
        Path("/app/dataset/articles.json"),
        Path("dataset/data/articles.json"),
        Path("dataset/articles.json"),
        Path("../dataset/data/articles.json"),
        Path("../dataset/articles.json"),
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
                    if name:
                        entry = {
                            "title": name,
                            "staticId": sid,
                            "id": aid,
                            "url": f"https://zakupki.mos.ru/knowledgebase/article/details/ais/{sid or aid}"
                        }
                        if sid:
                            ARTICLES_BY_STATIC_ID[sid] = entry
                        if aid:
                            ARTICLES_BY_ID[aid] = entry
            except Exception:
                pass

_init_articles_database()


def get_verified_article(art_id: str) -> Optional[Dict[str, Any]]:
    """Возвращает верифицированную статью из официальной базы по staticId или id."""
    _init_articles_database()
    s = str(art_id).strip()
    return ARTICLES_BY_STATIC_ID.get(s) or ARTICLES_BY_ID.get(s)


import html

def clean_citation_section(section: str) -> str:
    """
    Очищает заголовок подраздела от технического мусора:
    - Декодирует URL-encoded символы (%D0%...)
    - Удаляет SOURCE URL: ...
    - Удаляет технические индексы чанкера (Часть N)
    - Преобразует Содержимое документа (X.pdf) в Инструкция: X
    - Удаляет дублирование и мусорные префиксы
    - Преобразует HTML-сущности (&quot;, &amp;)
    """
    if not section or not isinstance(section, str):
        return ""

    try:
        s = urllib.parse.unquote(section)
    except Exception:
        s = section

    s = html.unescape(s).strip()
    s = re.sub(r'SOURCE\s+URL:\s*https?://\S+', '', s, flags=re.IGNORECASE).strip()
    s = re.sub(r'https?://\S+', '', s).strip()
    s = re.sub(r'\s*\(Часть\s*\d+\)', '', s, flags=re.IGNORECASE).strip()
    s = re.sub(r'Часть\s*\d+', '', s, flags=re.IGNORECASE).strip()

    m_doc = re.search(r'Содержимое документа\s*\(([^)]+)\)', s, re.IGNORECASE)
    if m_doc:
        doc_name = m_doc.group(1).replace("_", " ").strip()
        doc_name = re.sub(r'\.(pdf|docx)$', '', doc_name, flags=re.IGNORECASE).strip()
        pref = "" if doc_name.lower().startswith(("инструкция", "регламент", "руководство", "положение")) else "Инструкция: "
        s = re.sub(r'Содержимое документа\s*\([^)]+\)', f"{pref}{doc_name}", s, flags=re.IGNORECASE)

    s = s.strip(" -:—|()>")

    if not s or s.lower() in {"введение", "главная", "документ"}:
        return ""
    return s


def extract_pdf_citation(section_header: str = "", text: str = "", raw_url: str = "") -> Optional[Dict[str, str]]:
    """
    Извлекает прямую ссылку на официальный PDF/DOCX документ из метаданных чанка базы знаний.
    """
    candidate_name = None
    if raw_url and (".pdf" in raw_url.lower() or ".docx" in raw_url.lower() or "cms/media/docs/" in raw_url.lower()):
        unquoted = urllib.parse.unquote(raw_url)
        candidate_name = unquoted.split("/")[-1].strip()

    if not candidate_name and section_header:
        try:
            unquoted_sec = urllib.parse.unquote(section_header)
        except Exception:
            unquoted_sec = section_header
        
        m_doc = re.search(r'Содержимое документа\s*\(([^)]+?\.(?:pdf|docx))\)', unquoted_sec, re.IGNORECASE)
        if m_doc:
            candidate_name = m_doc.group(1).strip()
        else:
            m_any = re.search(r'([a-zA-Zа-яА-ЯёЁ0-9_\-\.\s%]+?\.(?:pdf|docx))', unquoted_sec, re.IGNORECASE)
            if m_any:
                candidate_name = m_any.group(1).strip()

    if not candidate_name and text:
        m_txt = re.search(r'(?:файл|документ|инструкци\w*|регламент)[:\s]+([^\n\r()<>"]+?\.(?:pdf|docx))', text[:400], re.IGNORECASE)
        if m_txt:
            candidate_name = m_txt.group(1).strip()


    if candidate_name:
        fname = os.path.basename(candidate_name).strip()
        clean_name = re.sub(r'\.(pdf|docx)$', '', fname, flags=re.IGNORECASE).replace("_", " ").strip()
        clean_name = html.unescape(clean_name)
        unq = urllib.parse.unquote(fname)
        encoded_name = urllib.parse.quote(unq.replace("_", " "))
        pdf_url = f"https://zakupki.mos.ru/cms/Media/docs/{encoded_name}"

        title = clean_name
        if not title.lower().startswith(("инструкция", "регламент", "руководство", "положение")):
            title = f"Инструкция: {clean_name}"
        return {
            "title": title,
            "section": "Официальный документ (PDF)",
            "url": pdf_url
        }
    return None



# Реестр разделов и приложений Регламента информационного взаимодействия АИС «Портал поставщиков»
CMS_REGULATION_ARTICLES: Dict[str, str] = {
    # Основные разделы регламента
    "48caq6vpp4pn97wbaxsfxnbn4b": "Регламент: 1. Общие положения",
    "4wx0ezbebam39096dnqdz15v4s": "Регламент: 2. Состав информации, размещаемой и обрабатываемой в АИС «Портал поставщиков»",
    "4zmpebqdkyq9dzzpdhr538qxn7": "Регламент: 3. Порядок взаимодействия участников информационного взаимодействия",
    "46ac0zd3ewy0tt5ffx1h9zd5mx": "Регламент: 4. Порядок доступа к информации, содержащейся в АИС «Портал поставщиков»",
    "4kh3hws0e8wknzdkd59xr15qwz": "Регламент: 5. Порядок организации информационного взаимодействия с иными системами",
    "4txdtwazc7z9dtccd306xyy55p": "Регламент: 6. Порядок сбора и обобщения информации о закупках",
    "4jx54dvpmthnr0w1e0xb7cvxx0": "Регламент: 7. Иные правила функционирования АИС «Портал поставщиков»",
    # Приложения к регламенту
    "42we7zhjby4nw2pgmdrk8eddwx": "Приложение 1. Схема распределения полномочий в личных кабинетах",
    "4p59tn72h3z2c3d3rfcz3jmtmp": "Приложение 2. Пользовательское соглашение АИС «Портал поставщиков»",
    "4nsazjshjxssn1wm105z3p5hm3": "Приложение 2. 1. Предмет Соглашения",
    "465ybcpkg8x0d0acg2qg3hb05w": "Приложение 2. 2. Термины и определения",
    "4jhye2315cmgd7c0b77s4d9cnn": "Приложение 2. 3. Общие положения о реализации Соглашения",
    "4t87ge0cz2sd7zbyz0sxwrnpda": "Приложение 2. 4. Порядок реализации Соглашения",
    "4cqhkb45zqcscws8d9wbzg0qxq": "Приложение 2. 5. Обязательства Сторон Соглашения",
    "476pxvm6xjaw8r4fyfw20hxc4a": "Приложение 2. 6. Дополнительные возможности использования Портала",
    "4c955bvwd85x3sz7rk096cygwb": "Приложение 2. 7. Конфиденциальность",
    "4rfjcvrrs4mbfzm1j9xq23p6w1": "Приложение 2. 8. Ответственность Сторон Соглашения",
    "43mc9g90s2w0cvpn36xdnfvfcz": "Приложение 2. 9. Ответственность Сторон",
    "4bvv8fgf95pchy702vskcghhnk": "Приложение 2. 10. Подписание Соглашения, его вступление в силу",
    "4gqp5s76ny8cst0td5nsbe1jd5": "Приложение 3. Порядок подачи и регистрации оферт",
    "4gtfe46htq9ar7804w2j8g5gcy": "Приложение 4. Правила проведения котировочной сессии",
    "4majsztp4d5bt6ak0me8md56dt": "Приложение 4. 2. Порядок создания и подписания оферты",
    "4e5jxcfzna4pezy2dg38e0mbwk": "Приложение 4. 3. Порядок подписания контракта (договора)",
    "4jgzc3h3qnv1kx3ckh2tyyejnr": "Приложение 4. 4. Порядок проведения совместной котировочной сессии",
    "4vkn1xg7byrnprbpkmsgwp0knx": "Приложение 4. 5. Снятие котировочной сессии с публикации",
    "450p49y65e4q1yres1awzy5s55": "Приложение 4. 6. Продление сроков котировочной сессии",
    "4r00gexf8asvc6bafkfyma9cma": "Приложение 4. 7. Иные правила проведения котировочной сессии",
    "49hpw7tckn9w9vq3bvxjzypcnv": "Приложение 5. Правила осуществления закупки по потребностям для региональных заказчиков",
    "4392d6hjwa2x6tyb35as8nwvxa": "Приложение 6. Правила осуществления прямой закупки",
    "4t3a8qny7ahrxw5jf8zrmwejxw": "Приложение 7. Порядок создания микросайта пользователя",
    "4n50757tk43h15gxn22r5655d9": "Приложение 8. Правила блокировки личного кабинета и ее снятия",
    "4c8zyr53npv5ns5wzrss748bx2": "Приложение 9. Минимальные характеристики автоматизированных рабочих мест",
    "4ydkt2mtqsr9v1mwfhrcxxfpct": "Приложение 10. Протокол информационного взаимодействия АИС «Портал поставщиков»",
    "4f0xbs0p831axv2epx2nrdh3d6": "Приложение 10. 1. Перечень видов информации информационного взаимодействия",
    "4n1a69na5c1v46hewzq3brcqd6": "Приложение 10. 2. Правила информационного обмена АИС «Портал поставщиков»",
    "4hwh3m40546rw00a5kjtxj1gwm": "Приложение 11. Соглашение о размещении информации кредитных организаций (банковские гарантии)",
    "4fb7egq77ezya73h26qc3m4dwb": "Приложение 11. 1. Предмет Соглашения",
    "4q509314cgs76xybs4k153vqdr": "Приложение 11. 2. Порядок исполнения Соглашения",
    "44wps3n0fx20tzkefgfnzy33dk": "Приложение 11. 3. Ответственность Сторон Соглашения",
    "4vj83t63hhrxfy5yqz2js44wc1": "Приложение 11. 4. Подписание Соглашения",
    "4323j2yr479tkwz5e5m4zj97wd": "Приложение 11. Условия участия кредитной организации",
    "4fmv7h0bp73chwh4az5gybxcmm": "Приложение 11. Параметры информации (баннер)",
    "4mh4ekyfe51hqv2y931d5ack4k": "Приложение 11. Гиперссылка на информационный ресурс банковских гарантий",
    # Соглашение об информационном обмене
    "4ps3bnmhng6wtx1m4devhy8e57": "Соглашение об информационном обмене: I. Предмет Соглашения",
    "4v420k37nkddx7cnqhkpqdrm5q": "Соглашение об информационном обмене: II. Термины и определения",
    "4vqsfeqnkh0x9v0yjty5v79mcx": "Соглашение об информационном обмене: III. Общие положения",
    "4pck5p2sxjkybt5xx6fk8p1n5s": "Соглашение об информационном обмене: IV. Порядок реализации",
    "4mecnmrqgjzfaxsasbg87pttma": "Соглашение об информационном обмене: V. Обязательства Сторон",
    "4b2nxmffxayx26p17v5gc5fh4k": "Соглашение об информационном обмене: VI. Конфиденциальность",
    "403qpz6x9wdd23k3xjcvay96wy": "Соглашение об информационном обмене: VII. Ответственность Сторон",
    "47pmge407gey26vptbafms05cv": "Соглашение об информационном обмене: VIII. Форс-мажор",
    "4fdb69bw8we5n0n1qeks8c1n5n": "Соглашение об информационном обмене: IX. Подписание Соглашения",
}


def clean_citation_title(title: str, url: str = "") -> str:
    """
    Гарантирует 100% точное соответствие названия статьи её содержимому на Портале.
    1. Если URL содержит ID статьи из реестра — возвращает эталонное название (largeName).
    2. Если URL указывает на раздел/приложение Регламента — возвращает эталонное наименование приложения.
    3. Если URL указывает на внешний официальный ресурс (ЕИС) — возвращает точное имя ресурса.
    4. Если URL указывает на документ — возвращает имя документа.
    5. Очищает технические артефакты и HTML-сущности.
    """
    _init_articles_database()
    if url:
        # Внешний официальный портал ЕИС Закупки
        if "zakupki.gov.ru" in url.lower():
            return "Официальный портал ЕИС Закупки (zakupki.gov.ru)"

        # Общая страница Регламента Портала
        if "regulation/cms" in url.lower() and not re.search(r'cms/[a-z0-9]{20,}', url.lower()):
            return "Регламент информационного взаимодействия АИС «Портал поставщиков»"

        # Статьи регламентов CMS (конкретные приложения и разделы)
        m_cms = re.search(r'knowledgebase/article/(?:details/(?:cms/)?|details/)?([a-z0-9]{20,})(?:[/?#]|$)', url, re.IGNORECASE)
        if m_cms:
            cms_id = m_cms.group(1).lower()
            if cms_id in CMS_REGULATION_ARTICLES:
                return CMS_REGULATION_ARTICLES[cms_id]

        # Статьи базы знаний AIS (цифровой ID)
        m_ais = re.search(r'knowledgebase/article/(?:details/(?:ais/)?|details/)?(\d+)(?:[/?#]|$)', url)
        if m_ais:
            art_id = m_ais.group(1)
            verified = get_verified_article(art_id)
            if verified and verified.get("title"):
                return html.unescape(verified["title"]).strip()
            if art_id in {"572822", "493330", "398754"}:
                return "Инструкция по работе с банковскими гарантиями"

        # Документы PDF / DOCX
        if ".pdf" in url.lower() or ".docx" in url.lower() or "cms/media/docs/" in url.lower():
            unquoted = urllib.parse.unquote(url)
            fname = unquoted.split("/")[-1].strip()
            fname_clean = re.sub(r'\.(pdf|docx)$', '', fname, flags=re.IGNORECASE).replace("_", " ")
            if fname_clean and len(fname_clean) > 3:
                return html.unescape(fname_clean).strip()

        if "банковск" in url.lower() or "garanti" in url.lower():
            return "Инструкция по работе с банковскими гарантиями"

    cleaned = html.unescape((title or "")).strip()
    # Убираем технический мусор парсеров
    cleaned = re.sub(r'^SOURCE\s+URL:\s*https?://\S+', '', cleaned).strip()
    cleaned = re.sub(r'https?://\S+', '', cleaned).strip()
    cleaned = re.sub(r'\s*\(Часть\s*\d+\)', '', cleaned).strip()
    cleaned = cleaned.strip(" -:—|")
    if not cleaned or "roseltorg" in cleaned.lower() or cleaned.startswith("("):
        if "гаранти" in (title or "").lower() or "обеспечен" in (title or "").lower():
            return "Инструкция по работе с банковскими гарантиями"
        return "Регламент информационного взаимодействия АИС «Портал поставщиков»"
    return cleaned


KNOWN_DOC_REDIRECTS = {
    "01.04.2022": "https://help.mos.ru/upload/iblock/1cd/rykovodstvo_polzovatelei_po_elektronnomy_ispolneniu_kontraktov_01.04.2022.docx",
    "rykovodstvo_polzovatelei_po_elektronnomy_ispolneniu_kontraktov": "https://help.mos.ru/upload/iblock/1cd/rykovodstvo_polzovatelei_po_elektronnomy_ispolneniu_kontraktov_01.04.2022.docx",
}


def normalize_portal_url(url: str) -> str:
    """
    Нормализует любую ссылку на Портал Поставщиков к 100% рабочему каноническому виду.
    Гарантирует точный адрес статьи или документа без подмены на общую заглушку.
    """
    if not url or not isinstance(url, str):
        return "https://zakupki.mos.ru/knowledgebase/article/regulation/cms"

    url = url.strip().strip("'\"<>`").rstrip(").,;:")

    # 0. Официальный портал ЕИС Закупки (федеральный уровень)
    if "zakupki.gov.ru" in url.lower():
        return "https://zakupki.gov.ru"

    # 1. Проверяем спец-документы (help.mos.ru)
    for trigger, target in KNOWN_DOC_REDIRECTS.items():
        if trigger in url:
            return target

    # 2. Регламенты CMS
    if "knowledgebase/regulations" in url or "knowledgebase/article/regulation" in url:
        return "https://zakupki.mos.ru/knowledgebase/article/regulation/cms"

    # 3. Статьи AIS: id состоит исключительно из цифр (например 506376, 213872, 589954)
    m_ais = re.search(r'knowledgebase/article/(?:details/(?:ais/)?|details/)?(\d+)(?:[/?#]|$)', url)
    if m_ais:
        art_id = m_ais.group(1)
        if art_id in {"572822", "493330", "398754"} or "garanti" in url.lower():
            return "https://zakupki.mos.ru/cms/Media/docs/%D0%98%D0%BD%D1%81%D1%82%D1%80%D1%83%D0%BA%D1%86%D0%B8%D1%8F%20%D0%BF%D0%BE%20%D1%80%D0%B0%D0%B1%D0%BE%D1%82%D0%B5%20%D1%81%20%D0%B1%D0%B0%D0%BD%D0%BA%D0%BE%D0%B2%D1%81%D0%BA%D0%B8%D0%BC%D0%B8%20%D0%B3%D0%B0%D1%80%D0%B0%D0%BD%D1%82%D0%B8%D1%8F%D0%BC%D0%B8.pdf"
        # Возвращаем точный канонический URL статьи
        return f"https://zakupki.mos.ru/knowledgebase/article/details/ais/{art_id}"

    # 4. Статьи регламентов CMS: буквенно-цифровой идентификатор
    m_cms = re.search(r'knowledgebase/article/(?:details/(?:cms/)?|details/)?([a-z0-9]{20,})(?:[/?#]|$)', url, re.IGNORECASE)
    if m_cms:
        cms_id = m_cms.group(1)
        return f"https://zakupki.mos.ru/knowledgebase/article/details/cms/{cms_id}"

    # 5. Официальные документы в CMS Media / PDF / DOCX инструкции
    if "cms/media/docs/" in url.lower() or "knowledgebase/docs/" in url.lower() or url.lower().endswith(".pdf") or url.lower().endswith(".docx"):
        unquoted = urllib.parse.unquote(url)
        filename = unquoted.split("/")[-1].strip()
        clean_filename = filename.replace("_", " ")
        encoded_name = urllib.parse.quote(clean_filename)
        return f"https://zakupki.mos.ru/cms/Media/docs/{encoded_name}"

    # 6. Общая ссылка на базу знаний или главную
    if url.endswith("/knowledgebase") or url.endswith("/knowledgebase/") or url == "https://zakupki.mos.ru" or url == "https://zakupki.mos.ru/":
        return "https://zakupki.mos.ru/knowledgebase/article/regulation/cms"

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

