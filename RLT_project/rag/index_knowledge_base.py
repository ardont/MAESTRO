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
    Запуск полного цикла индексации базы знаний
    """
    print("=" * 70)
    print("RLT.Tender_Guide: ЗАПУСК ИНДЕКСАЦИИ БАЗЫ ЗНАНИЙ В QDRANT")
    print("=" * 70)
    start_time = time.time()

    # 1. Загрузка документов
    print("\n[ШАГ 1/5] Загрузка и первичная категоризация документов...")
    docs = load_all_documents()
    if sample_limit:
        print(f"[TEST MODE] Ограничение {sample_limit} документов.")
        docs = docs[:sample_limit]
        
    print(f"[OK] Загружено документов: {len(docs)}")

    # 2. Умный чанкинг и извлечение изображений
    print("\n[ШАГ 2/5] Умный чанкинг с привязкой к иерархии разделов...")
    all_chunks = []
    category_stats = {}
    chunks_with_images_count = 0

    for doc in tqdm(docs, desc="Чанкинг документов"):
        doc_chunks = process_document_to_chunks(doc)
        for ch in doc_chunks:
            cat = ch["category"]
            category_stats[cat] = category_stats.get(cat, 0) + 1
            if ch.get("images"):
                chunks_with_images_count += 1
            all_chunks.append(ch)

    print(f"[OK] Всего создано чанков: {len(all_chunks)}")
    print(f"[IMAGES] Чанков с привязанными изображениями/скриншотами: {chunks_with_images_count}")
    print("[STATS] Распределение по категориям:")
    for cat, count in sorted(category_stats.items(), key=lambda x: x[1], reverse=True):
        print(f"   * {cat}: {count} чанков")

    if not all_chunks:
        print("[ERROR] Ошибка: нет чанков для индексации!")
        return

    # 3. Батчевая векторизация
    print(f"\n[ШАГ 3/5] Батчевая векторизация (размер батча: {BATCH_SIZE})...")
    embedder = get_embedder()
    chunk_texts = [ch["text"] for ch in all_chunks]
    
    embeddings = []
    for i in tqdm(range(0, len(chunk_texts), BATCH_SIZE), desc="Расчет эмбеддингов"):
        batch = chunk_texts[i:i + BATCH_SIZE]
        batch_vecs = embedder.get_embeddings_batch(batch, batch_size=BATCH_SIZE)
        embeddings.append(batch_vecs)

    import numpy as np
    all_embeddings = np.vstack(embeddings)
    print(f"[OK] Рассчитано эмбеддингов: {len(all_embeddings)} (размерность: {all_embeddings.shape[1]})")

    # 4. Инициализация Qdrant и загрузка
    print("\n[ШАГ 4/5] Подключение к Qdrant и сохранение коллекции...")
    client = get_qdrant_client()
    init_collection(client, recreate=True)

    upsert_chunks_batch(client, all_chunks, all_embeddings, batch_size=100)
    print(f"[OK] Успешно загружено {len(all_chunks)} точек в коллекцию '{COLLECTION_NAME}'")

    elapsed = time.time() - start_time
    print(f"\nИНДЕКСАЦИЯ УСПЕШНО ЗАВЕРШЕНА за {elapsed:.2f} сек ({elapsed/60:.2f} мин)!")

    # 5. Автоматическое тестирование качества поиска
    print("\n" + "=" * 70)
    print("[ШАГ 5/5] АВТОМАТИЧЕСКИЙ ТЕСТ ПОИСКА ПО БАЗЕ ЗНАНИЙ")
    print("=" * 70)
    
    test_queries = [
        ("Как установить сертификат ЭЦП на компьютер и настроить КриптоПро?", "ecp_mchd"),
        ("Как подать жалобу в ФАС по 44-ФЗ?", "44fz"),
        ("Закупки малого объема до 3 млн рублей по 223-ФЗ", "223fz"),
        ("Регистрация поставщика в ЕИС и ЕРУЗ через Госуслуги", "registration"),
        ("Банковская гарантия на обеспечение заявки и контракта", "services")
    ]

    for q_idx, (q_text, expected_cat) in enumerate(test_queries, 1):
        print(f"\n[QUERY {q_idx}] «{q_text}» (Ожидается: {expected_cat})")
        q_vec = embedder.get_embedding(q_text).tolist()
        
        hits = client.search(
            collection_name=COLLECTION_NAME,
            query_vector=q_vec,
            limit=2
        )
        
        for h_idx, hit in enumerate(hits, 1):
            p = hit.payload
            imgs = p.get("images", [])
            imgs_info = f", Изображения: {len(imgs)} шт." if imgs else ""
            print(f"  [{h_idx}] Скор: {hit.score:.4f} | Категория: {p.get('category')} | Заголовок: {p.get('title')}")
            print(f"      Раздел: {p.get('section_header')} | URL: {p.get('url')}{imgs_info}")
            if imgs:
                print(f"      Ссылки на скриншоты: {imgs[:2]}")
            snippet = p.get('text', '').replace('\n', ' ')[:140]
            print(f"      Текст: {snippet}...")

if __name__ == "__main__":
    limit = 10 if "--test" in sys.argv else None
    run_indexing_pipeline(sample_limit=limit)
