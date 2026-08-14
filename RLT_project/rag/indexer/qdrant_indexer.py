import os
import time
from qdrant_client import QdrantClient
from qdrant_client.http import models
from .config import (
    COLLECTION_NAME, EMBEDDING_DIM, QDRANT_HOST, QDRANT_PORT, QDRANT_STORAGE_DIR
)

def get_qdrant_client() -> QdrantClient:
    """
    Возвращает клиент Qdrant с автоматическим fallback:
    1. Локальный сервер localhost:6333
    2. Локальное встроенное хранилище ./qdrant_storage
    """
    try:
        # Проверяем доступность сервера Qdrant
        client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=2.0)
        client.get_collections()
        print(f"[QDRANT] Connected to Qdrant server at {QDRANT_HOST}:{QDRANT_PORT}")
        return client
    except Exception:
        print(f"[QDRANT] Server not found, using embedded local storage: {QDRANT_STORAGE_DIR}")
        return QdrantClient(path=str(QDRANT_STORAGE_DIR))

def init_collection(client: QdrantClient, recreate: bool = True):
    """
    Создает коллекцию с нужной размерностью и настраивает Payload-индексы
    """
    if recreate:
        client.recreate_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=EMBEDDING_DIM,
                distance=models.Distance.COSINE,
            ),
        )
        print(f"[QDRANT] Collection '{COLLECTION_NAME}' created/recreated.")
        
        # Создаем индексы для быстрой фильтрации по категориям и типам
        try:
            client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name="category",
                field_schema=models.PayloadSchemaType.KEYWORD
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
    Загрузка чанков и векторов в Qdrant батчами
    """
    total = len(chunks)
    for i in range(0, total, batch_size):
        batch_chunks = chunks[i:i + batch_size]
        batch_vectors = embeddings[i:i + batch_size]
        
        points = []
        for ch, vec in zip(batch_chunks, batch_vectors):
            points.append(
                models.PointStruct(
                    id=ch["chunk_id"],
                    vector=vec.tolist() if hasattr(vec, "tolist") else list(vec),
                    payload={
                        "doc_id": ch["doc_id"],
                        "title": ch["title"],
                        "url": ch["url"],
                        "category": ch["category"],
                        "doc_type": ch["doc_type"],
                        "section_header": ch["section_header"],
                        "images": ch.get("images", []),
                        "text": ch["text"]
                    }
                )
            )
            
        client.upsert(
            collection_name=COLLECTION_NAME,
            wait=True,
            points=points
        )
