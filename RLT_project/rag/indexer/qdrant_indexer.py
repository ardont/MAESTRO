"""
qdrant_indexer.py — Модуль работы с векторной базой Qdrant.

Qdrant — это СПЕЦИАЛЬНАЯ БД для векторов. Отличия от обычной БД:
  - Обычная БД (PostgreSQL): SELECT WHERE name = 'закупка'  → точное совпадение
  - Qdrant: дай 5 ближайших векторов к [0.12, -0.34, ...]     → семантический поиск

Этот модуль отвечает за:
  1. Подключение к Qdrant (сервер или локальный файл)
  2. Создание коллекции с нужной размерностью (1024)
  3. Загрузку чанков и их векторов в базу
"""

import os
import time
from qdrant_client import QdrantClient           # Официальный Python-клиент Qdrant
from qdrant_client.http import models             # Типы данных Qdrant (VectorParams, PointStruct и пр.)
from .config import (
    COLLECTION_NAME, EMBEDDING_DIM, QDRANT_HOST, QDRANT_PORT, QDRANT_STORAGE_DIR
)

# Кэшированный экземпляр клиента (аналог Singleton)
_cached_qdrant_client = None


def get_qdrant_client() -> QdrantClient:
    """
    Возвращает клиент Qdrant с автоматическим fallback и кэшированием.

    Стратегия подключения (с приоритетом):
      1. Локальный сервер Qdrant на localhost:6333
         (запускается отдельно: docker run -p 6333:6333 qdrant/qdrant)
      2. Встроенное локальное хранилище (./qdrant_storage)
         (не требует отдельного процесса, работает через файлы)

    Кэширование: клиент создаётся один раз и переиспользуется.
    """
    global _cached_qdrant_client
    if _cached_qdrant_client is not None:
        return _cached_qdrant_client

    try:
        # Попытка 1: подключиться к Qdrant-серверу (timeout=2сек)
        client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=2.0)
        client.get_collections()  # Проверка: если сервер не отвечает — выбросится исключение
        print(f"[QDRANT] Connected to Qdrant server at {QDRANT_HOST}:{QDRANT_PORT}")
        _cached_qdrant_client = client
        return client
    except Exception:
        # Попытка 2: сервер недоступен → используем локальное файловое хранилище
        print(f"[QDRANT] Server not found, using embedded local storage: {QDRANT_STORAGE_DIR}")
        _cached_qdrant_client = QdrantClient(path=str(QDRANT_STORAGE_DIR))
        return _cached_qdrant_client

def init_collection(client: QdrantClient, recreate: bool = True):
    """
    Создаёт (или пересоздаёт) коллекцию в Qdrant.

    Коллекция — аналог таблицы в SQL. Хранит:
      - Вектор (1024 числа) — семантическое представление чанка
      - Payload (метаданные) — title, url, category, text, images

    Также создаёт индексы по полям category и doc_type для быстрой фильтрации.

    Аргументы:
      client   — экземпляр QdrantClient
      recreate — если True, удаляет старую коллекцию и создаёт новую
    """
    if recreate:
        # Удаляем старую и создаём новую коллекцию с нужными параметрами:
        #   size=1024  — размерность вектора (должна совпадать с EMBEDDING_DIM)
        #   COSINE    — метрика близости (косинусное сходство, 1.0 = идентичны)
        client.recreate_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=EMBEDDING_DIM,
                distance=models.Distance.COSINE,
            ),
        )
        print(f"[QDRANT] Collection '{COLLECTION_NAME}' created/recreated.")

        # Создаём payload-индексы — аналог CREATE INDEX в SQL.
        # Это позволяет быстро фильтровать чанки по категории
        # (например, искать только по категории "44fz" или "ecp_mchd")
        try:
            client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name="category",
                field_schema=models.PayloadSchemaType.KEYWORD  # Точное совпадение строк
            )
            client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name="doc_type",
                field_schema=models.PayloadSchemaType.KEYWORD
            )
            print("[QDRANT] Payload indexes created (category, doc_type).")
        except Exception as e:
            print(f"[QDRANT] Note on payload index creation: {e}")

def upsert_chunks_batch(client: QdrantClient, chunks: list, embeddings: list, batch_size: int = 100):
    """
    Загрузка чанков и их векторов в Qdrant батчами.

    upsert = insert + update: если точка с таким ID уже есть — обновить.

    Каждый «поинт» (Point) в Qdrant содержит:
      - id       — уникальный идентификатор (chunk_id из чанкера)
      - vector   — эмбеддинг [1024 float]
      - payload  — метаданные (title, url, text, category, images...)

    Аргументы:
      chunks     — список словарей чанков (из chunker.py)
      embeddings — соответствующие векторы (из embedder.py)
      batch_size — сколько записей отправлять за один запрос (100)
    """
    total = len(chunks)

    # Отправляем данные порциями по batch_size штук
    for i in range(0, total, batch_size):
        batch_chunks = chunks[i:i + batch_size]
        batch_vectors = embeddings[i:i + batch_size]

        # Формируем список «точек» для Qdrant
        points = []
        for ch, vec in zip(batch_chunks, batch_vectors):
            points.append(
                models.PointStruct(
                    id=ch["chunk_id"],  # UUID чанка
                    # Конвертируем numpy-массив в обычный список Python
                    vector=vec.tolist() if hasattr(vec, "tolist") else list(vec),
                    # Метаданные чанка — эти поля возвращаются при поиске
                    payload={
                        "doc_id": ch["doc_id"],             # Имя исходного файла
                        "title": ch["title"],               # Заголовок документа
                        "url": ch["url"],                   # Ссылка-источник
                        "category": ch["category"],         # Категория (для фильтрации)
                        "doc_type": ch["doc_type"],         # Тип документа
                        "section_header": ch["section_header"],  # Заголовок раздела
                        "images": ch.get("images", []),     # Ссылки на скриншоты
                        "text": ch["text"]                  # Текст чанка
                    }
                )
            )

        # Отправляем батч в Qdrant. wait=True — ждём подтверждения записи.
        client.upsert(
            collection_name=COLLECTION_NAME,
            wait=True,
            points=points
        )
