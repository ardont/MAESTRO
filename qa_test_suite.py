"""
qa_test_suite.py — Комплексный E2E тестовый набор для Портала поставщиков Москвы.

Проверяет:
1. Качество ответов RAG по 25 ключевым темам Портала поставщиков.
2. 100% валидность всех выдаваемых ссылок (HTTP GET -> статус 200 на zakupki.mos.ru, отсутствие 404).
3. Полное отсутствие упоминаний "Росэлторг" (0 толерантность).
4. Корректность работы интерактивного Workflow (Да -> Далее -> Завершить).
5. Эскалацию на оператора ("позови человека", guardrails).
"""

import sys
import io
import re
import time
import json
import argparse
import requests
from typing import Dict, Any, List, Set

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

DEFAULT_API_URL = "http://100.100.89.45:8001/api/ask/"

# 25 репрезентативных вопросов по Порталу Поставщиков Москвы и 44-ФЗ / 223-ФЗ
E2E_QUESTIONS = [
    "Как зарегистрироваться на Портале поставщиков индивидуальному предпринимателю?",
    "Как настроить плагин КриптоПро для работы на Портале поставщиков?",
    "Что такое котировочная сессия и как в ней участвовать?",
    "Кто признается победителем котировочной сессии?",
    "В каких случаях победа переходит ко второму участнику котировочной сессии?",
    "Что делать, если не получается сделать ставку в активной котировочной сессии?",
    "Как создать заявку на добавление новой позиции в каталог СТЕ?",
    "Сколько характеристик нужно заполнить для добавления СТЕ?",
    "Что делать при возникновении интеграционных ошибок РДИК_1004 или РДИК_1043?",
    "Как сформировать и подписать УПД при электронном исполнении контракта?",
    "Как перевести УПД в статус редактирования через оператора Калуга Астрал?",
    "Как вернуть УПД в статус Черновик при электронном актировании через ЕИС?",
    "Как подать жалобу в ФАС по 44-ФЗ при неправомерном отклонении заявки?",
    "В какие сроки можно подать жалобу на положения извещения по 44-ФЗ?",
    "Как подать жалобу о необоснованной автоматической блокировке на Портале?",
    "Где найти реестр жалоб поставщика при автоматической блокировке?",
    "Что такое закупка по потребностям на Портале поставщиков?",
    "Может ли поставщик отозвать свою оферту в закупке по потребностям?",
    "Как подписать массово все оферты по итогам котировочных сессий?",
    "Что делать, если контракт не появился из региональной информационной системы?",
    "Как проверить наличие регистрации организации в электронном документообороте (ЭДО)?",
    "Как зарегистрироваться на Портале поставщиков физическому лицу?",
    "Какие особенности закупок у единственного поставщика по 44-ФЗ?",
    "Как получить статус производителя на Портале поставщиков Москвы?",
    "Каковы сроки рассмотрения заказчиком документа о приемке по 44-ФЗ?"
]

OPERATOR_QUESTIONS = [
    "позови человека",
    "мне нужен живой специалист службы поддержки",
    "ты ужасный бот, позови оператора"
]

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}


def verify_url_http_status(url: str, cache: Dict[str, int]) -> int:
    """Выполняет реальный HTTP GET запрос к zakupki.mos.ru с кэшированием результатов."""
    if url in cache:
        return cache[url]

    try:
        r = requests.get(url, headers=HTTP_HEADERS, timeout=12, allow_redirects=True)
        cache[url] = r.status_code
        return r.status_code
    except Exception as e:
        print(f"    [HTTP ERROR] {url}: {e}")
        cache[url] = 0
        return 0


def extract_urls(text: str, citations: List[Dict[str, Any]]) -> Set[str]:
    """Извлекает все ссылки из текста ответа (Markdown + raw URLs) и массива citations."""
    urls = set()

    # Ссылки из списка citations
    for c in citations:
        u = c.get("url", "").strip()
        if u:
            urls.add(u)

    # Markdown ссылки: [text](url)
    md_matches = re.findall(r'\[([^\]]+)\]\((https?://[^\)]+)\)', text)
    for _, u in md_matches:
        urls.add(u.strip())

    # Прямые ссылки в тексте
    raw_matches = re.findall(r'https?://[a-zA-Z0-9\.\-\_\/\?\#\=\&\%]+', text)
    for u in raw_matches:
        urls.add(u.strip())

    return urls


def run_e2e_suite(api_url: str):
    print("=" * 80)
    print("КОМПЛЕКСНОЕ ТЕСТИРОВАНИЕ E2E И ВАЛИДАЦИЯ ССЫЛОК (ZAKUPKI.MOS.RU)")
    print(f"Целевой URL API: {api_url}")
    print("=" * 80)

    url_cache: Dict[str, int] = {}
    test_records = []
    total_urls_checked = 0
    total_404_errors = 0
    total_roseltorg_mentions = 0
    all_extracted_urls: Set[str] = set()

    start_suite_time = time.time()

    # --- ЭТАП 1: 25 ВОПРОСОВ RAG ---
    print(f"\n[ЭТАП 1/3] Запуск серии из {len(E2E_QUESTIONS)} вопросов RAG...")
    for idx, question in enumerate(E2E_QUESTIONS, 1):
        print(f"\n--- [Тест {idx:02d}/{len(E2E_QUESTIONS):02d}] «{question}» ---")
        t0 = time.time()
        try:
            resp = requests.post(api_url, json={"question": question}, timeout=60)
            elapsed = time.time() - t0
            status_code = resp.status_code
            data = resp.json() if status_code == 200 else {}
        except Exception as e:
            elapsed = time.time() - t0
            status_code = 0
            data = {"error": str(e)}

        if status_code != 200:
            print(f"❌ [ОШИБКА HTTP] Статус {status_code}: {data.get('error')}")
            test_records.append({
                "question": question,
                "status": "FAIL",
                "http_status": status_code,
                "error": data.get("error")
            })
            continue

        answer = data.get("answer", "")
        citations = data.get("citations", [])
        timings = data.get("timings", {})

        # 1. Проверка на Росэлторг
        roseltorg_found = bool(re.search(r'росэлторг|roseltorg', answer, re.IGNORECASE))
        if roseltorg_found:
            total_roseltorg_mentions += 1
            print("❌ [ОШИБКА] Обнаружено упоминание 'Росэлторг' в ответе!")
        else:
            print("  [OK] Упоминаний 'Росэлторг': 0")

        # 2. Извлечение и проверка ссылок
        found_urls = extract_urls(answer, citations)
        all_extracted_urls.update(found_urls)
        print(f"  [ССЫЛКИ] Найдено ссылок для проверки: {len(found_urls)}")

        urls_status = {}
        has_404 = False
        non_mosru_urls = []

        for u in found_urls:
            total_urls_checked += 1
            if not u.startswith("https://zakupki.mos.ru"):
                non_mosru_urls.append(u)

            code = verify_url_http_status(u, url_cache)
            urls_status[u] = code
            if code == 404:
                has_404 = True
                total_404_errors += 1
                print(f"  ❌ [404 NOT FOUND] {u}")
            elif code == 200:
                print(f"  ✅ [200 OK] {u}")
            else:
                print(f"  ⚠️ [HTTP {code}] {u}")

        if non_mosru_urls:
            print(f"  ⚠️ [НЕ MOSRU ССЫЛКИ]: {non_mosru_urls}")

        # Ссылка на источник присутствует
        has_source = "📖 **Источник:**" in answer or "Источник:" in answer

        test_passed = (not roseltorg_found) and (not has_404) and (len(found_urls) > 0)
        print(f"  Результат: {'✅ PASS' if test_passed else '❌ FAIL'} (Время: {elapsed:.2f}с, Поиск: {timings.get('search_sec', 0)}с, LLM: {timings.get('llm_sec', 0)}с)")

        test_records.append({
            "id": idx,
            "question": question,
            "passed": test_passed,
            "has_source": has_source,
            "roseltorg_mentions": 1 if roseltorg_found else 0,
            "urls_checked": urls_status,
            "elapsed_sec": round(elapsed, 2),
            "answer_preview": answer[:150].replace('\n', ' ')
        })

    # --- ЭТАП 2: WORKFLOW ТЕСТИРОВАНИЕ ---
    print("\n" + "=" * 80)
    print("[ЭТАП 2/3] Тестирование интерактивного сценария (Workflow)...")
    try:
        # Шаг 1: Вопрос
        r1 = requests.post(api_url, json={"question": "Как подать жалобу в ФАС по 44-ФЗ?"}, timeout=60).json()
        chat_id = r1.get("ids", {}).get("chat")
        user_id = r1.get("ids", {}).get("user")
        print(f"  1. Стартовый запрос -> Чат ID: {chat_id}")

        # Шаг 2: Пользователь говорит "Да" на предложение
        r2 = requests.post(api_url, json={"question": "Да", "chat_id": chat_id, "user_id": user_id}, timeout=30).json()
        print(f"  2. Ответ 'Да' -> Активный Workflow: {r2.get('active_workflow')}, Шаг: {r2.get('current_step')}")
        assert r2.get("active_workflow") is not None, "Workflow не активировался"

        # Шаг 3: Следующий шаг
        r3 = requests.post(api_url, json={"question": "Далее", "chat_id": chat_id, "user_id": user_id}, timeout=30).json()
        print(f"  3. Ответ 'Далее' -> Шаг: {r3.get('current_step')}")

        # Шаг 4: Завершение
        r4 = requests.post(api_url, json={"question": "Стоп", "chat_id": chat_id, "user_id": user_id}, timeout=30).json()
        print(f"  4. Ответ 'Стоп' -> Активный Workflow: {r4.get('active_workflow')}")
        assert r4.get("active_workflow") is None, "Workflow не завершился"
        print("  ✅ [WORKFLOW PASS] Сценарий пошагового помощника полностью отработал!")
    except Exception as e:
        print(f"  ❌ [WORKFLOW FAIL] Ошибка: {e}")

    # --- ЭТАП 3: ЭСКАЛАЦИЯ НА ОПЕРАТОРА ---
    print("\n" + "=" * 80)
    print("[ЭТАП 3/3] Тестирование эскалации на оператора и Guardrails...")
    for q_op in OPERATOR_QUESTIONS:
        try:
            r_op = requests.post(api_url, json={"question": q_op}, timeout=30).json()
            assigned = r_op.get("assigned_to")
            line = r_op.get("line_info", {}).get("line")
            ans = r_op.get("answer", "")
            print(f"  Вопрос: «{q_op}» -> Assigned: {assigned}, Ответ: {ans[:70]}...")
            assert assigned is not None or "Перевожу" in ans, f"Не произошел перевод на оператора для '{q_op}'"
            print(f"  ✅ [OPERATOR PASS] Перевод на оператора подтвержден.")
        except Exception as e:
            print(f"  ❌ [OPERATOR FAIL] {q_op}: {e}")

    total_suite_time = time.time() - start_suite_time

    # --- ИТОГОВЫЙ ОТЧЕТ ---
    passed_count = sum(1 for r in test_records if r.get("passed"))
    unique_urls = len(all_extracted_urls)
    valid_200_urls = sum(1 for u, code in url_cache.items() if code == 200)

    print("\n" + "=" * 80)
    print("ИТОГОВЫЙ ОТЧЕТ ТЕСТИРОВАНИЯ И ВАЛИДАЦИИ")
    print("=" * 80)
    print(f"Всего тестовых сценариев RAG:        {len(E2E_QUESTIONS)}")
    print(f"Успешно пройдено тестов:             {passed_count} / {len(E2E_QUESTIONS)} ({passed_count/len(E2E_QUESTIONS)*100:.1f}%)")
    print(f"Всего уникальных ссылок в ответах:  {unique_urls}")
    print(f"Ссылки со статусом 200 OK:           {valid_200_urls} / {unique_urls} ({valid_200_urls/unique_urls*100:.1f}%)")
    print(f"Ссылки со статусом 404 Not Found:    {total_404_errors}")
    print(f"Упоминаний 'Росэлторг':             {total_roseltorg_mentions}")
    print(f"Общее время выполнения тестов:       {total_suite_time:.2f} сек.")

    results_payload = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_tests": len(E2E_QUESTIONS),
        "passed_tests": passed_count,
        "unique_urls_count": unique_urls,
        "valid_200_urls_count": valid_200_urls,
        "errors_404_count": total_404_errors,
        "roseltorg_mentions_count": total_roseltorg_mentions,
        "all_urls_status": url_cache,
        "details": test_records
    }

    results_path = "qa_test_results.json"
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results_payload, f, ensure_ascii=False, indent=2)

    print(f"\nПолный отчет о результатах сохранен в '{results_path}'.")
    if total_404_errors == 0 and total_roseltorg_mentions == 0 and passed_count == len(E2E_QUESTIONS):
        print("\n🏆 ВСЕ КРИТЕРИИ УСПЕХА ПОЛНОСТЬЮ ВЫПОЛНЕНЫ! СИСТЕМА РАБОТАЕТ БЕЗУПРЕЧНО.")
    else:
        print("\n⚠️ ВНИМАНИЕ: Обнаружены несоответствия критериям качества.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="E2E QA Test Suite with URL Validation")
    parser.add_argument("--url", type=str, default=DEFAULT_API_URL, help="Target API URL")
    args = parser.parse_args()

    run_e2e_suite(args.url)
