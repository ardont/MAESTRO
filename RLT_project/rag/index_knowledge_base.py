"""
Скрипт: index_knowledge_base.py (ГЛАВНЫЙ ОРКЕСТРАТОР ИНДЕКСАЦИИ RAG)

Назначение:
  Полный сквозной цикл индексации всей базы знаний Портала Поставщиков Москвы
  (zakupki.mos.ru) в векторную базу данных Qdrant.

Пайплайн состоит из 5 этапов:
  1. Загрузка документов (document_loader.py):
     - 516 статей базы знаний (инструкции, регламенты, FAQ)
     - Федеральные законы РФ (44-ФЗ, 223-ФЗ, 63-ФЗ, 135-ФЗ, ГК РФ)
     - Практические руководства по работе с закупками Москвы
  2. Иерархический чанкинг и извлечение скриншотов (chunker.py):
     - Привязка дерева разделов (Breadcrumbs)
     - Сохранение таблиц СТЕ и пошаговых инструкций
     - Привязка локальных изображений (dataset/images/)
  3. Батчевая векторизация (embedder.py):
     - Модель: ai-forever/ru-en-RoSBERTa (1024-мерные эмбеддинги)
     - Батчевая обработка с контролем видеопамяти / RAM
  4. Сохранение в Qdrant (qdrant_indexer.py):
     - Создание векторной коллекции с косинусным расстоянием (Distance.COSINE)
     - Построение payload-индексов по category, doc_type, doc_id для мгновенной фильтрации
     - Пакетная загрузка точек (Points) с полными метаданными
  5. Автоматическое тестирование качества поиска:
     - Проверка скора релевантности (Cosine Similarity)
     - Проверка точности привязки категорий и скриншотов
"""

import os
import sys
import time
from pathlib import Path

# Принудительно настраиваем UTF-8 для Windows консоли
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from tqdm import tqdm
import numpy as np

# Добавляем родительский каталог в sys.path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from RLT_project.rag.indexer.config import BATCH_SIZE, COLLECTION_NAME
from RLT_project.rag.indexer.document_loader import load_all_documents
from RLT_project.rag.indexer.chunker import process_document_to_chunks
from RLT_project.rag.indexer.embedder import get_embedder
from RLT_project.rag.indexer.qdrant_indexer import (
    get_qdrant_client, init_collection, upsert_chunks_batch
)


def run_indexing_pipeline(sample_limit: int = None):
    """
    Запуск полного цикла индексации базы знаний в Qdrant.
    
    Аргументы:
      sample_limit: если указан (например, через --test), ограничивает число
                    обрабатываемых документов для быстрой верификации пайплайна.
    """
    print("=" * 75)
    print("RLT.Tender_Guide: ИНТЕЛЛЕКТУАЛЬНАЯ ИНДЕКСАЦИЯ БАЗЫ ЗНАНИЙ В QDRANT")
    print("=" * 75)
    start_time = time.time()

    # 1. Загрузка документов
    print("\n[ШАГ 1/5] Загрузка и первичная агрегация документов базы знаний...")
    docs = load_all_documents()
    if sample_limit:
        print(f"[ТЕСТОВЫЙ РЕЖИМ] Ограничение первыми {sample_limit} документами.")
        docs = docs[:sample_limit]

    print(f"[OK] Загружено документов для индексации: {len(docs)}")

    # 2. Умный чанкинг и извлечение изображений
    print("\n[ШАГ 2/5] Иерархический чанкинг с привязкой контекста и скриншотов...")
    all_chunks = []
    category_stats = {}
    chunks_with_images_count = 0
    chunks_with_tables_count = 0

    for doc in tqdm(docs, desc="Чанкинг документов"):
        doc_chunks = process_document_to_chunks(doc)
        for ch in doc_chunks:
            cat = ch.get("category", "kb_article")
            category_stats[cat] = category_stats.get(cat, 0) + 1
            if ch.get("images"):
                chunks_with_images_count += 1
            if "|" in ch.get("text", "") and "---" in ch.get("text", ""):
                chunks_with_tables_count += 1
            all_chunks.append(ch)

    print(f"[OK] Всего создано семантических чанков: {len(all_chunks)}")
    print(f"[IMAGES] Чанков с привязанными скриншотами интерфейса: {chunks_with_images_count}")
    print(f"[TABLES] Чанков со структурированными таблицами: {chunks_with_tables_count}")
    print("[STATS] Распределение чанков по категориям:")
    for cat, count in sorted(category_stats.items(), key=lambda x: x[1], reverse=True):
        print(f"   * {cat:20}: {count} чанков")

    if not all_chunks:
        print("[ОШИБКА] Нет чанков для индексации!")
        return

    # 3. Батчевая векторизация
    print(f"\n[ШАГ 3/5] Батчевая векторизация через ru-en-RoSBERTa (размер батча: {BATCH_SIZE})...")
    embedder = get_embedder()
    chunk_texts = [ch["text"] for ch in all_chunks]

    embeddings = []
    for i in tqdm(range(0, len(chunk_texts), BATCH_SIZE), desc="Расчет эмбеддингов"):
        batch = chunk_texts[i:i + BATCH_SIZE]
        batch_vecs = embedder.get_embeddings_batch(batch, batch_size=BATCH_SIZE)
        embeddings.append(batch_vecs)

    all_embeddings = np.vstack(embeddings)
    print(f"[OK] Рассчитано эмбеддингов: {len(all_embeddings)} (размерность вектора: {all_embeddings.shape[1]})")

    # 4. Инициализация Qdrant и загрузка
    print(f"\n[ШАГ 4/5] Подключение к Qdrant и сохранение коллекции '{COLLECTION_NAME}'...")
    client = get_qdrant_client()
    init_collection(client, recreate=True)

    upsert_chunks_batch(client, all_chunks, all_embeddings, batch_size=100)
    print(f"[OK] Успешно сохранено {len(all_chunks)} точек в векторной коллекции Qdrant!")

    elapsed = time.time() - start_time
    print(f"\n[УСПЕХ] ИНДЕКСАЦИЯ ЗАВЕРШЕНА за {elapsed:.2f} сек ({elapsed/60:.2f} мин)!")

    # 5. Автоматическое тестирование качества поиска
    print("\n" + "=" * 75)
    print("[ШАГ 5/5] АВТОМАТИЧЕСКАЯ ВЕРИФИКАЦИЯ КАЧЕСТВА ПОИСКА (БЕНЧМАРК)")
    print("=" * 75)

    test_queries = [
        ("Как установить сертификат ЭЦП на компьютер и настроить КриптоПро?", "ecp_mchd"),
        ("В каких случаях победа переходит к следующему за победителем участнику котировочной сессии?", "quotation_session"),
        ("Сколько характеристик нужно для добавления заявки на СТЕ?", "ste_catalog"),
        ("Как сформировать и подписать УПД при электронном исполнении контракта?", "contract_execution"),
        ("Как зарегистрироваться на Портале поставщиков через Госуслуги?", "registration"),
        ("Как подать жалобу в ФАС по 44-ФЗ при необоснованном отклонении заявки?", "44fz"),
        ("Закупки малого объема у субъектов МСП по 223-ФЗ", "223fz"),
    ]

    for q_idx, (q_text, expected_cat) in enumerate(test_queries, 1):
        print(f"\n[ТЕСТ {q_idx}] «{q_text}» (Ожидаемая категория: {expected_cat})")
        q_vec = embedder.get_embedding(q_text).tolist()

        if hasattr(client, "query_points"):
            hits = client.query_points(
                collection_name=COLLECTION_NAME,
                query=q_vec,
                limit=2
            ).points
        else:
            hits = client.search(
                collection_name=COLLECTION_NAME,
                query_vector=q_vec,
                limit=2
            )

        for h_idx, hit in enumerate(hits, 1):
            p = hit.payload
            imgs = p.get("images", [])
            imgs_info = f" | Скриншотов: {len(imgs)} шт." if imgs else ""
            step_info = f" | Шаг: {p.get('step_number')}" if p.get('step_number') else ""
            print(f"  [{h_idx}] Косинус: {hit.score:.4f} | Категория: {p.get('category')}{step_info}{imgs_info}")
            print(f"      Заголовок: {p.get('title')}")
            print(f"      Раздел: {p.get('section_header')} | URL: {p.get('url')}")
            if imgs:
                print(f"      Прикрепленные скриншоты: {imgs[:2]}")
            snippet = p.get('text', '').replace('\n', ' ')[:130]
            print(f"      Фрагмент: {snippet}...")


if __name__ == "__main__":
    limit = 10 if "--test" in sys.argv else None
    run_indexing_pipeline(sample_limit=limit)
