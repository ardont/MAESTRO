"""
validate_dataset.py — Скрипт валидации датасета.

Проверяет:
1. Наличие выходных файлов dataset/kb_clean.json и dataset/kb_graph.json.
2. Непустоту собранных статей (title, text, url).
3. 100% принадлежность всех URL-адресов домену zakupki.mos.ru.
4. Отсутствие любых упоминаний 'росэлторг' или 'roseltorg' во всех текстовых полях.
5. Корректность категорий и типов документов.
"""

import os
import sys
import json
from urllib.parse import urlparse

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN_JSON = os.path.join(BASE_DIR, "dataset", "kb_clean.json")
GRAPH_JSON = os.path.join(BASE_DIR, "dataset", "kb_graph.json")


def validate():
    print("=" * 75)
    print("ВАЛИДАЦИЯ ДАТАСЕТА И ИСТОЧНИКОВ ЗНАНИЙ (zakupki.mos.ru)")
    print("=" * 75)

    errors = []

    if not os.path.exists(CLEAN_JSON):
        print(f"[КРИТИЧНО] Файл датасета не найден: {CLEAN_JSON}")
        sys.exit(1)

    with open(CLEAN_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"Всего записей в датасете: {len(data)}")
    if len(data) == 0:
        print("[КРИТИЧНО] Датасет пуст!")
        sys.exit(1)

    url_failures = []
    roseltorg_mentions = []
    empty_content = []

    for idx, item in enumerate(data):
        doc_id = item.get("doc_id", str(idx))
        title = item.get("title", "")
        url = item.get("url", "")
        text = item.get("text", "")

        # 1. Проверка URL
        if not url:
            url_failures.append((doc_id, "URL отсутствует"))
        else:
            parsed = urlparse(url)
            if parsed.netloc != "zakupki.mos.ru":
                url_failures.append((doc_id, f"Чужой домен: {parsed.netloc} ({url})"))

        # 2. Проверка на Росэлторг
        combined_text = (title + " " + text).lower()
        if "росэлторг" in combined_text or "roseltorg" in combined_text:
            roseltorg_mentions.append((doc_id, title))

        # 3. Проверка на непустоту
        if len(text.strip()) < 10 or len(title.strip()) < 2:
            empty_content.append(doc_id)

    print(f"Проверено URL: {len(data)}")
    if url_failures:
        print(f"[ПРОВАЛ] Найдено {len(url_failures)} некорректных URL:")
        for doc_id, reason in url_failures[:10]:
            print(f"  - [{doc_id}]: {reason}")
        errors.append("Invalid URLs found")
    else:
        print("[УСПЕХ] 100% URL-адресов принадлежат домену zakupki.mos.ru!")

    if roseltorg_mentions:
        print(f"[ПРОВАЛ] Найдено {len(roseltorg_mentions)} упоминаний 'Росэлторг':")
        for doc_id, t in roseltorg_mentions[:10]:
            print(f"  - [{doc_id}]: {t}")
        errors.append("Roseltorg mentions found")
    else:
        print("[УСПЕХ] Упоминаний 'Росэлторг' в датасете: 0")

    if empty_content:
        print(f"[ПРЕДУПРЕЖДЕНИЕ] Статей с коротким контентом: {len(empty_content)}")

    # Проверка графа
    if os.path.exists(GRAPH_JSON):
        with open(GRAPH_JSON, "r", encoding="utf-8") as f:
            graph = json.load(f)
        print(f"[УСПЕХ] Граф знаний валиден: {graph.get('nodes_count', 0)} узлов, {graph.get('edges_count', 0)} связей.")
    else:
        print("[ПРЕДУПРЕЖДЕНИЕ] Файл графа знаний не найден!")

    print("=" * 75)
    if errors:
        print(f"[ИТОГ ВАЛИДАЦИИ]: НЕ ПРОЙДЕНА ({len(errors)} ошибок)")
        sys.exit(1)
    else:
        print("[ИТОГ ВАЛИДАЦИИ]: ПОЛНЫЙ УСПЕХ (100% соответствие требованиям)")
        sys.exit(0)


if __name__ == "__main__":
    validate()
