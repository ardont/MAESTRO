import torch
import numpy as np
from .indexer.embedder import get_embedder
from .normalize_query import normalise_query, TERMINS

def get_embedding(text: str, remove_prefix: bool = True) -> np.ndarray:
    """
    Получение эмбеддинга для одного запроса
    """
    if remove_prefix and text.startswith("search_query:"):
        text = text[len("search_query:"):].strip()
        
    embedder = get_embedder()
    return embedder.get_embedding(text)

def get_embeddings_batch(texts: list, batch_size: int = 32) -> np.ndarray:
    """
    Пакетное получение эмбеддингов
    """
    embedder = get_embedder()
    return embedder.get_embeddings_batch(texts, batch_size=batch_size)

def process_queries(queries: list, termins: dict = TERMINS) -> list:
    results = []
    embedder = get_embedder()
    
    for query in queries:
        normalized_query = normalise_query(query, termins)
        embedding = embedder.get_embedding(normalized_query)
        
        results.append({
            "original_query": query,
            "normalized_query": normalized_query,
            "embedding": embedding,
            "embedding_shape": embedding.shape,
            "embedding_norm": float(np.linalg.norm(embedding))
        })
        
    return results

if __name__ == "__main__":
    test_queries = [
        "Как оформить ЭДО для 44 фз и использовать ЛК оператора?",
        "Какие требования к электронной подписи по 223-ФЗ?",
        "Как подать жалобу в ФАС по 44-ФЗ?",
        "Инструкция по работе с ЕИС для начинающих"
    ]
    results = process_queries(test_queries)
    for i, r in enumerate(results, 1):
        print(f"[{i}] {r['original_query']} -> {r['normalized_query']} (shape: {r['embedding_shape']})")
