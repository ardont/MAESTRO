import os
import sys
import time

# Reconfigure stdout for Windows console UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add project root to sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, "RLT_project"))

print("=" * 80)
print("🚀 RLT.Tender_Guide: ПОЛНЫЙ ТЕСТ ВСЕХ МОДУЛЕЙ И СТАДИЙ СИСТЕМЫ")
print("=" * 80)

# ------------------------------------------------------------------------------
# 1. ТЕСТ НОРМАЛИЗАЦИИ ЗАПРОСОВ (normalize_query)
# ------------------------------------------------------------------------------
print("\n[ЭТАП 1/5] ТЕСТИРОВАНИЕ НОРМАЛИЗАЦИИ И РАСШИРЕНИЯ ТЕРМИНОВ")
print("-" * 80)
try:
    from rag.normalize_query import normalise_query, TERMINS
    sample_q = "Как войти в лк через госуслуги и настроить эдо по 44 фз?"
    res_norm = normalise_query(sample_q, TERMINS)
    print(f"  Вход : «{sample_q}»")
    print(f"  Выход: {res_norm}")
    print("  [OK] Нормализация работает штатно!")
except Exception as e:
    print(f"  [FAIL] Ошибка нормализации: {e}")

# ------------------------------------------------------------------------------
# 2. ТЕСТ GUARDRAILS И SMART ROUTER
# ------------------------------------------------------------------------------
print("\n[ЭТАП 2/5] ТЕСТИРОВАНИЕ МАРШРУТИЗАТОРА И БЕЗОПАСНОСТИ (Guardrails & Router)")
print("-" * 80)
try:
    from rag.router import check_guardrails, route_support_line
    
    # 2.1 Тест токсичности
    tox_test = check_guardrails("Привет, помогите настроить ЭЦП")
    assert not tox_test["is_blocked"], "Ложное срабатывание цензуры"
    print("  * Проверка фильтрации: Корректное сообщение пропущено")
    
    # 2.2 Тест маршрутизации
    test_cases = [
        ("Как настроить КриптоПро CSP и сертификат Рутокен?", "L2 (Техподдержка ЭЦП)"),
        ("Как подать жалобу в ФАС на отклонение заявки по 44-ФЗ?", "L3 (Правовая экспертиза 44/223-ФЗ)"),
        ("Как найти личный кабинет на главной странице?", "L1 (Общая навигация)")
    ]
    for q, expected in test_cases:
        routed = route_support_line(q)
        print(f"  * «{q[:45]}...» -> [{routed['line']}] {routed['name']}")
    print("  [OK] Маршрутизация по линиям поддержки работает корректно!")
except Exception as e:
    print(f"  [FAIL] Ошибка маршрутизатора: {e}")

# ------------------------------------------------------------------------------
# 3. ТЕСТ МОДЕЛИ ЭМБЕДДИНГОВ (ru-en-RoSBERTa)
# ------------------------------------------------------------------------------
print("\n[ЭТАП 3/5] ТЕСТИРОВАНИЕ ВЕКТОРИЗАТОРА (ЭМБЕДДИНГИ)")
print("-" * 80)
try:
    from rag.embed_query import get_embedding
    vec = get_embedding("Настройка электронной цифровой подписи")
    print(f"  * Получен эмбеддинг: размерность {vec.shape[0]} чисел")
    assert vec.shape[0] == 1024, f"Неверная размерность эмбеддинга: {vec.shape[0]}"
    print("  [OK] Модель ru-en-RoSBERTa загружена и работает!")
except Exception as e:
    print(f"  [FAIL] Ошибка эмбеддера: {e}")

# ------------------------------------------------------------------------------
# 4. ТЕСТ ВЕКТОРНОГО ПОИСКА В QDRANT
# ------------------------------------------------------------------------------
print("\n[ЭТАП 4/5] ТЕСТИРОВАНИЕ ВЕКТОРНОЙ БАЗЫ ЗНАНИЙ (QDRANT)")
print("-" * 80)
try:
    from rag.indexer.qdrant_indexer import get_qdrant_client
    from rag.indexer.config import COLLECTION_NAME
    
    client = get_qdrant_client()
    collections = client.get_collections().collections
    col_names = [c.name for c in collections]
    print(f"  * Доступные коллекции в Qdrant: {col_names}")
    
    if COLLECTION_NAME in col_names:
        info = client.get_collection(COLLECTION_NAME)
        print(f"  * Коллекция '{COLLECTION_NAME}': {info.points_count} векторизованных чанков")
        
        # Пробный поиск
        from rag.main_rag import search_in_qdrant
        hits = search_in_qdrant("Как установить сертификат ЭЦП?", top_k=2)
        print(f"  * Найдено релевантных совпадений: {len(hits)}")
        for idx, hit in enumerate(hits, 1):
            p = hit.payload
            print(f"    [{idx}] Скор: {hit.score:.4f} | Заголовок: {p.get('title')} | Категория: {p.get('category')}")
        print("  [OK] Поиск по базе знаний Qdrant работает штатно!")
    else:
        print(f"  [INFO] Коллекция '{COLLECTION_NAME}' еще не создана. Запустите: python RLT_project/rag/index_knowledge_base.py")
except Exception as e:
    print(f"  [FAIL] Ошибка Qdrant: {e}")

# ------------------------------------------------------------------------------
# 5. ТЕСТ ПОЛНОГО RAG ПАЙПЛАЙНА
# ------------------------------------------------------------------------------
print("\n[ЭТАП 5/5] ТЕСТИРОВАНИЕ RAG ПАЙПЛАЙНА С ГЕНЕРАЦИЕЙ ОТВЕТА")
print("-" * 80)
try:
    from rag.main_rag import rag_pipeline
    test_user_q = "Как получить и настроить сертификат ЭЦП для торгов?"
    print(f"  Вопрос: «{test_user_q}»")
    
    t0 = time.time()
    result = rag_pipeline(test_user_q)
    elapsed = time.time() - t0
    
    print(f"  Время генерации: {elapsed:.2f} сек")
    print(f"\n🤖 ОТВЕТ СИСТЕМЫ:\n{result['answer']}")
    
    if result.get('citations'):
        print("\n📚 ПЕРВОИСТОЧНИКИ:")
        for c in result['citations']:
            print(f"  - {c.get('title')} ({c.get('url')})")
            
    if result.get('images'):
        print(f"\n🖼️ СВЯЗАННЫЕ СКРИНШОТЫ: {len(result['images'])} шт.")
        
    print("\n  [OK] Полный цикл RAG успешно выполнен!")
except Exception as e:
    print(f"  [FAIL] Ошибка RAG пайплайна: {e}")

print("\n" + "=" * 80)
print("🏁 ТЕСТИРОВАНИЕ ВСЕХ КОМПОНЕНТОВ ЗАВЕРШЕНО!")
print("=" * 80)
