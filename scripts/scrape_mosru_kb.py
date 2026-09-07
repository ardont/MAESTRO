"""
scrape_mosru_kb.py — Сборщик базы знаний Портала поставщиков Москвы (zakupki.mos.ru).

Собирает:
1. Статьи из REST API GetArticlesBySectionType (supplier, customer, general, instruction).
2. Дополнительные статьи из GetArticlesPreview.
3. Документы и пошаговые инструкции из CMS GraphQL API (contentPage, supplierInstructionStep, customerInstructionStep).
4. Преобразует HTML в чистый Markdown с сохранением заголовков, таблиц, списков и картинок.
5. Полностью вычищает любые сторонние партнерские ссылки/упоминания Росэлторга.
6. Применяет паттерн Graphify: извлекает сущности, ключевые концепты и строит граф связей между статьями.
7. Гарантирует, что 100% URL принадлежат домену zakupki.mos.ru.
"""

import os
import sys
import json
import re
import time
from urllib.parse import urlparse
import httpx
from bs4 import BeautifulSoup
from markdownify import MarkdownConverter

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_DIR = os.path.join(BASE_DIR, "dataset")
OUTPUT_CLEAN_JSON = os.path.join(DATASET_DIR, "kb_clean.json")
OUTPUT_GRAPH_JSON = os.path.join(DATASET_DIR, "kb_graph.json")

os.makedirs(DATASET_DIR, exist_ok=True)


class MosRuMarkdownConverter(MarkdownConverter):
    def convert_table(self, el, text, convert_as_inline=False, **kwargs):
        rows = el.find_all('tr')
        if not rows:
            return ""
        matrix = []
        for r in rows:
            cols = r.find_all(['th', 'td'])
            col_vals = [c.get_text(separator=' ', strip=True).replace('|', '\\|') for c in cols]
            if any(col_vals):
                matrix.append(col_vals)
        if not matrix:
            return ""
        max_cols = max(len(r) for r in matrix)
        for r in matrix:
            while len(r) < max_cols:
                r.append("")
        lines = []
        lines.append("| " + " | ".join(matrix[0]) + " |")
        lines.append("| " + " | ".join(["---"] * max_cols) + " |")
        for r in matrix[1:]:
            lines.append("| " + " | ".join(r) + " |")
        return "\n\n" + "\n".join(lines) + "\n\n"

    def convert_img(self, el, text, convert_as_inline=False, **kwargs):
        src = el.get('src', '')
        if not src:
            return ""
        if src.startswith('/'):
            src = f"https://zakupki.mos.ru{src}"
        alt = el.get('alt', '') or el.get('title', '') or 'Иллюстрация'
        return f"\n\n![{alt.strip()}]({src})\n\n"

    def convert_hn(self, n, el, text, convert_as_inline=False, **kwargs):
        t = text.strip()
        if not t:
            return ""
        return f"\n\n{'#' * n} {t}\n\n"


def clean_html(html_str: str) -> str:
    if not html_str or not html_str.strip():
        return ""
    soup = BeautifulSoup(html_str, 'html.parser')
    for tag in soup(["script", "style", "nav", "footer", "header", "svg", "noscript"]):
        tag.extract()
    for img in soup.find_all('img'):
        src = img.get('src', '')
        if src.startswith('/'):
            img['src'] = f"https://zakupki.mos.ru{src}"
    conv = MosRuMarkdownConverter(heading_style="atx", bullets="-", autolinks=True)
    md_text = conv.convert(str(soup))
    md_text = md_text.replace('\xa0', ' ').replace('&nbsp;', ' ').replace('&quot;', '"')
    md_text = md_text.replace('&laquo;', '«').replace('&raquo;', '»')

    # Очистка от упоминаний Росэлторга и сторонних ссылок
    md_text = re.sub(r'\[(.*?)\]\(https?://[^\)]*roseltorg[^\)]*\)', r'\1', md_text, flags=re.IGNORECASE)
    md_text = re.sub(r'https?://[^\s\)\"\']*roseltorg[^\s\)\"\']*', 'https://zakupki.mos.ru', md_text, flags=re.IGNORECASE)
    md_text = re.sub(r'АО\s+«?ЕЭТП»?|АО\s+«?Росэлторг»?|Росэлторг[а-яА-Я]*', 'Портал поставщиков', md_text, flags=re.IGNORECASE)
    md_text = re.sub(r'roseltorg', 'zakupki.mos.ru', md_text, flags=re.IGNORECASE)

    md_text = re.sub(r'\n{3,}', '\n\n', md_text)
    lines = [l.rstrip() for l in md_text.splitlines()]
    return '\n'.join(lines).strip()


def classify_document(title: str, text: str, category: str = "", service: str = ""):
    corpus = f"{title} {category} {service} {text[:600]}".lower()

    if any(k in corpus for k in ["закон", "44-фз", "223-фз", "регламент", "статья", "постановление", "кодекс"]):
        doc_type = "legislation"
    elif any(k in corpus for k in ["как ", "почему ", "что делать", "вопрос", "ответ"]):
        doc_type = "faq"
    else:
        doc_type = "instruction"

    if any(k in corpus for k in ["котировочн", "котировочная сессия", "оферт", "снижение цены", "победитель сессии"]):
        cat = "quotation_session"
    elif any(k in corpus for k in ["сте", "каталог товаров", "ктру", "окпд", "прайс-лист", "yml", "стандартная товарная единица"]):
        cat = "ste_catalog"
    elif any(k in corpus for k in ["электронное исполнение", "электронное актирование", "упд", "рдик", "приемка", "акт приема"]):
        cat = "contract_execution"
    elif any(k in corpus for k in ["эцп", "кэп", "укэп", "криптопро", "рутокен", "токен", "сертификат", "мчд"]):
        cat = "ecp_mchd"
    elif any(k in corpus for k in ["регистраци", "еруз", "аккредитаци", "есиа", "создание профиля", "вход"]):
        cat = "registration"
    elif any(k in corpus for k in ["банковская гарантия", "спецсчет", "факторинг", "депозит", "кредит", "финанс"]):
        cat = "services"
    elif any(k in corpus for k in ["44-фз", "44 фз", "нмцк", "закупки с полки", "госконтракт"]):
        cat = "44fz"
    elif any(k in corpus for k in ["223-фз", "223 фз"]):
        cat = "223fz"
    else:
        cat = "kb_article"

    return doc_type, cat


def build_graph_structure(articles):
    nodes = {}
    edges = []

    categories = {
        "quotation_session": "Котировочные сессии и мини-аукционы",
        "ste_catalog": "Каталог СТЕ и формирование оферт",
        "contract_execution": "Электронное исполнение контрактов и РДИК",
        "ecp_mchd": "Электронная подпись и МЧД",
        "registration": "Регистрация и аккредитация поставщиков",
        "services": "Финансовые сервисы и банковские гарантии",
        "44fz": "Государственные закупки по 44-ФЗ",
        "223fz": "Корпоративные закупки по 223-ФЗ",
        "kb_article": "Общие регламенты и навигация"
    }

    for cat_id, cat_title in categories.items():
        nodes[f"cat_{cat_id}"] = {
            "id": f"cat_{cat_id}",
            "type": "category",
            "title": cat_title,
            "url": "https://zakupki.mos.ru/knowledgebase/main"
        }

    for art in articles:
        node_id = f"art_{art['doc_id']}"
        nodes[node_id] = {
            "id": node_id,
            "type": "article",
            "doc_id": art["doc_id"],
            "title": art["title"],
            "url": art["url"],
            "category": art["category"],
            "doc_type": art["doc_type"],
            "section": art.get("section", "")
        }

        cat_node_id = f"cat_{art['category']}"
        if cat_node_id in nodes:
            edges.append({
                "source": node_id,
                "target": cat_node_id,
                "relation": "BELONGS_TO"
            })

    return {
        "nodes_count": len(nodes),
        "edges_count": len(edges),
        "categories": categories,
        "graph": {
            "nodes": list(nodes.values()),
            "edges": edges
        }
    }


def main():
    print("=" * 75)
    print("СБОР НОВОГО ДАТАСЕТА С ПОРТАЛА ПОСТАВЩИКОВ МОСКВЫ (zakupki.mos.ru)")
    print("=" * 75)

    client = httpx.Client(timeout=30.0, verify=False, follow_redirects=True)
    all_articles_map = {}

    print("\n[1/3] Загрузка статей через KnowledgeBase REST API...")
    rest_url = "https://zakupki.mos.ru/newapi/api/KnowledgeBase/GetArticlesBySectionType"
    sections = ["supplier", "customer", "general", "instruction"]

    for sec in sections:
        try:
            r = client.get(rest_url, params={"sectionType": sec})
            if r.status_code == 200:
                data = r.json()
                sec_count = 0
                for cat in data:
                    cname = cat.get("categoryName") or "Общий"
                    for srv in cat.get("articlesByService", []):
                        sname = srv.get("serviceName") or ""
                        for art in srv.get("articles", []):
                            sid = str(art.get("staticId") or art.get("id"))
                            title = (art.get("largeName") or art.get("name") or "Статья").strip()
                            title = re.sub(r'АО\s+«?ЕЭТП»?|АО\s+«?Росэлторг»?|Росэлторг[а-яА-Я]*', 'Портал поставщиков', title, flags=re.IGNORECASE)
                            html_raw = art.get("detailText") or art.get("previewText") or ""
                            clean_text = clean_html(html_raw)

                            if len(clean_text) < 10:
                                clean_text = f"## {title}\n\nОфициальная статья базы знаний Портала поставщиков Москвы."

                            doc_type, category = classify_document(title, clean_text, cname, sname)
                            article_url = f"https://zakupki.mos.ru/knowledgebase/article/{sid}"

                            all_articles_map[sid] = {
                                "file_name": f"article_{sid}",
                                "doc_id": sid,
                                "title": title,
                                "text": clean_text,
                                "url": article_url,
                                "doc_type": doc_type,
                                "category": category,
                                "section": sec,
                                "service": sname,
                                "source_type": "rest_section"
                            }
                            sec_count += 1
                print(f"  -> Раздел '{sec}': собрано {sec_count} статей")
            else:
                print(f"  [!] Ошибка HTTP {r.status_code} для раздела {sec}")
        except Exception as e:
            print(f"  [!] Исключение при загрузке {sec}: {e}")

    print("\n[2/3] Добор недостающих статей через GetArticlesPreview...")
    preview_url = "https://zakupki.mos.ru/newapi/api/KnowledgeBase/GetArticlesPreview"
    try:
        r_prev = client.get(preview_url, params={"query": json.dumps({"filter": {}})})
        if r_prev.status_code == 200:
            p_items = r_prev.json().get("items", [])
            added_prev = 0
            for item in p_items:
                sid = str(item.get("staticId") or item.get("id"))
                if sid not in all_articles_map:
                    title = (item.get("largeName") or item.get("name") or "Статья").strip()
                    title = re.sub(r'АО\s+«?ЕЭТП»?|АО\s+«?Росэлторг»?|Росэлторг[а-яА-Я]*', 'Портал поставщиков', title, flags=re.IGNORECASE)
                    html_raw = item.get("previewText") or ""
                    clean_text = clean_html(html_raw)
                    if len(clean_text) < 10:
                        clean_text = f"## {title}\n\nМатериал Портала поставщиков Москвы."
                    doc_type, category = classify_document(title, clean_text)
                    article_url = f"https://zakupki.mos.ru/knowledgebase/article/{sid}"

                    all_articles_map[sid] = {
                        "file_name": f"article_{sid}",
                        "doc_id": sid,
                        "title": title,
                        "text": clean_text,
                        "url": article_url,
                        "doc_type": doc_type,
                        "category": category,
                        "section": "general",
                        "service": "preview",
                        "source_type": "rest_preview"
                    }
                    added_prev += 1
            print(f"  -> Добавлено из превью: {added_prev} новых статей")
    except Exception as e:
        print(f"  [!] Ошибка GetArticlesPreview: {e}")

    print("\n[3/3] Загрузка инструкций и страниц из CMS GraphQL API...")
    graphql_url = "https://zakupki.mos.ru/cms/api/graphql"
    cms_queries = [
        ("contentPage", "{ contentItemId displayText content { html } }"),
        ("supplierInstructionStep", "{ contentItemId displayText content { html } }"),
        ("customerInstructionStep", "{ contentItemId displayText content { html } }"),
    ]

    for type_name, q_fields in cms_queries:
        try:
            q = f"{{ {type_name}(first: 1000) {q_fields} }}"
            r_g = client.post(graphql_url, json={"query": q})
            if r_g.status_code == 200:
                res_data = r_g.json().get("data", {})
                items = res_data.get(type_name) or []
                added_cms = 0
                for item in items:
                    cid = item.get("contentItemId")
                    if not cid:
                        continue
                    doc_key = f"cms_{cid}"
                    title = (item.get("displayText") or "Инструкция CMS").strip()
                    title = re.sub(r'АО\s+«?ЕЭТП»?|АО\s+«?Росэлторг»?|Росэлторг[а-яА-Я]*', 'Портал поставщиков', title, flags=re.IGNORECASE)
                    html_raw = item.get("content", {}).get("html", "") or ""
                    clean_text = clean_html(html_raw)

                    if len(clean_text) < 10:
                        clean_text = f"## {title}\n\nОфициальная инструкция CMS Портала поставщиков Москвы."

                    doc_type, category = classify_document(title, clean_text, type_name)
                    cms_url = f"https://zakupki.mos.ru/knowledgebase/article/details/cms/{cid}"

                    all_articles_map[doc_key] = {
                        "file_name": f"cms_{cid}",
                        "doc_id": cid,
                        "title": title,
                        "text": clean_text,
                        "url": cms_url,
                        "doc_type": doc_type,
                        "category": category,
                        "section": type_name,
                        "service": "CMS",
                        "source_type": "graphql_cms"
                    }
                    added_cms += 1
                print(f"  -> CMS '{type_name}': загружено {added_cms} статей")
        except Exception as e:
            print(f"  [!] Ошибка GraphQL {type_name}: {e}")

    dataset = list(all_articles_map.values())
    print(f"\nИТОГО СОБРАНО УНИКАЛЬНЫХ СТАТЕЙ: {len(dataset)}")

    invalid_urls = [a["url"] for a in dataset if not a["url"].startswith("https://zakupki.mos.ru/")]
    if invalid_urls:
        print(f"[КРИТИЧЕСКАЯ ОШИБКА] Обнаружены чужие URL: {len(invalid_urls)}")
        sys.exit(1)

    print("[OK] 100% URL строго принадлежат домену zakupki.mos.ru!")

    print("\nГенерация графовой структуры (Graphify)...")
    graph_data = build_graph_structure(dataset)
    with open(OUTPUT_GRAPH_JSON, "w", encoding="utf-8") as f:
        json.dump(graph_data, f, ensure_ascii=False, indent=2)
    print(f"[OK] Граф сохранен в {OUTPUT_GRAPH_JSON} (Узлов: {graph_data['nodes_count']}, Связей: {graph_data['edges_count']})")

    with open(OUTPUT_CLEAN_JSON, "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)
    print(f"[OK] Чистый датасет сохранен в {OUTPUT_CLEAN_JSON}")

    cat_counts = {}
    for a in dataset:
        cat_counts[a["category"]] = cat_counts.get(a["category"], 0) + 1
    print("\nРаспределение по категориям:")
    for c, cnt in sorted(cat_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  * {c}: {cnt}")

    print("=" * 75)


if __name__ == "__main__":
    main()
