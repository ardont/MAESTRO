import json
import subprocess
import requests
from qdrant_client import QdrantClient
from .normalize_query import normalise_query, TERMINS
from .embed_query import get_embedding
from .indexer.config import COLLECTION_NAME
from .indexer.qdrant_indexer import get_qdrant_client

# === 1. Подключение к Qdrant ===
client = get_qdrant_client()

# === 2. Вызов локальной модели через Ollama ===
def _call_local_gpt(prompt: str) -> str:
    """
    Вызов LLM через Ollama HTTP API (быстрее) или fallback на CLI
    """
    # 1. Попытка через HTTP API (быстрее, без создания процесса ОС)
    try:
        res = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "gpt-oss:20b",
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.2,
                    "top_p": 0.9
                }
            },
            timeout=30
        )
        if res.status_code == 200:
            return res.json().get("response", "").strip()
    except Exception:
        pass

    # 2. Fallback на CLI subprocess
    try:
        result = subprocess.run(
            ["ollama", "run", "gpt-oss:20b"],
            input=prompt,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except Exception as e:
        return f"Ошибка обращения к LLM: {e}"

# === 3. Поиск релевантных документов в Qdrant ===
def search_in_qdrant(query: str, top_k: int = 3, category_filter: str = None):
    vector = get_embedding(query).tolist()
    
    # При необходимости можно добавить фильтр по категории
    query_filter = None
    if category_filter:
        from qdrant_client.http import models
        query_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="category",
                    match=models.MatchValue(value=category_filter)
                )
            ]
        )
        
    hits = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=vector,
        query_filter=query_filter,
        limit=top_k,
    )
    return hits

# === 4. Основной пайплайн RAG ===
def rag_pipeline(user_message: str):
    """
    Полный RAG пайплайн:
    1. Нормализация запроса
    2. Семантический поиск в Qdrant с метаданными
    3. Проверка порога уверенности (Strict Fallback)
    4. Формирование ответа с цитатами и изображениями
    """
    normalized_query = normalise_query(user_message, TERMINS)

    # Шаг 1: Поиск в Qdrant
    hits = search_in_qdrant(normalized_query, top_k=3)

    if not hits or (hits and hits[0].score < 0.40):
        return {
            "answer": "К сожалению, в официальной базе знаний нет регламентированного ответа на данный вопрос. Перевожу ваш запрос на дежурного специалиста службы поддержки.",
            "citations": [],
            "images": []
        }

    # Шаг 2: Собираем контекст, ссылки и изображения
    context_parts = []
    citations = []
    images = []

    for hit in hits:
        payload = hit.payload
        title = payload.get("title", "Документ")
        url = payload.get("url", "")
        sec_header = payload.get("section_header", "")
        text_chunk = payload.get("text", "")
        chunk_images = payload.get("images", [])

        context_parts.append(f"### {title} ({sec_header})\n{text_chunk}")
        
        if url and url not in [c.get("url") for c in citations]:
            citations.append({
                "title": title,
                "section": sec_header,
                "url": url
            })
            
        for img in chunk_images:
            if img not in images:
                images.append(img)

    context = "\n\n".join(context_parts)

    # Шаг 3: Промпт для LLM
    prompt = f"""Ты — интеллектуальный эксперт службы поддержки пользователей электронной торговой площадки Росэлторг.
Ответь на вопрос пользователя, опираясь ИСКЛЮЧИТЕЛЬНО на предоставленную базу знаний.

Вопрос пользователя: "{user_message}"

База знаний:
{context}

Инструкции для ответа:
1. Сформулируй четкий, доброжелательный и структурированный по шагам ответ (1, 2, 3).
2. Если в базе знаний описаны конкретные кнопки, пункты меню или разделы ЛК — укажи их в кавычках.
3. Не придумывай факты, которых нет в базе знаний.
4. В конце укажи главный первоисточник в формате: "Источник: {citations[0]['title'] if citations else 'База знаний'} ({citations[0]['url'] if citations else ''})"
"""

    llm_answer = _call_local_gpt(prompt)
    
    # Очищаем системные маркеры thinking, если модель их выводит
    marker = "...done thinking."
    if marker in llm_answer:
        llm_answer = llm_answer.split(marker, 1)[1].strip()

    return {
        "answer": llm_answer,
        "citations": citations,
        "images": images
    }

if __name__ == "__main__":
    test_query = "Как зарегистрироваться поставщику по 44-ФЗ?"
    res = rag_pipeline(test_query)
    print("🤖 Ответ:\n", res["answer"])
    print("📚 Источники:\n", res["citations"])
    print("🖼️ Изображения:\n", res["images"])
