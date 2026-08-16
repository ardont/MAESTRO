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
def _get_active_ollama_model() -> str:
    """
    Автоматически определяет доступную модель в Ollama
    """
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=1.0)
        if r.status_code == 200:
            models_list = r.json().get("models", [])
            installed = [m.get("name") for m in models_list if m.get("name")]
            if installed:
                # Если установлена gpt-oss:20b - берем её, иначе любую доступную
                for preferred in ["gpt-oss:20b", "gpt-oss", "qwen2.5:7b", "llama3.2", "mistral", "gemma"]:
                    for m in installed:
                        if preferred in m:
                            return m
                return installed[0]
    except Exception:
        pass
    return "gpt-oss:20b"

def _call_local_gpt(prompt: str) -> str:
    """
    Вызов LLM через Ollama HTTP API с достаточным таймаутом для медленных ПК
    """
    model_name = _get_active_ollama_model()
    
    # 1. Попытка через HTTP API
    try:
        res = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model_name,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.2,
                    "top_p": 0.9
                }
            },
            timeout=120  # Достаточный таймаут для генерации на CPU
        )
        if res.status_code == 200:
            return res.json().get("response", "").strip()
    except Exception:
        pass

    # 2. Попытка через CLI
    try:
        result = subprocess.run(
            ["ollama", "run", model_name],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=120,
            check=True
        )
        return result.stdout.strip()
    except Exception as e:
        return ""


# === 3. Поиск релевантных документов в Qdrant ===
def search_in_qdrant(query: str, top_k: int = 3, category_filter: str = None):
    vector = get_embedding(query).tolist()
    
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
        
    client = get_qdrant_client()
    try:
        if hasattr(client, "query_points"):
            res = client.query_points(
                collection_name=COLLECTION_NAME,
                query=vector,
                query_filter=query_filter,
                limit=top_k,
            )
            return res.points
        elif hasattr(client, "search"):
            return client.search(
                collection_name=COLLECTION_NAME,
                query_vector=vector,
                query_filter=query_filter,
                limit=top_k,
            )
        return []
    except Exception as e:
        print(f"[QDRANT SEARCH ERROR] {e}")
        return []

# === 4. Основной пайплайн RAG ===
def rag_pipeline(user_message: str, category_filter: str = None):
    """
    Полный RAG пайплайн:
    1. Нормализация запроса
    2. Семантический поиск в Qdrant с метаданными и фильтрацией по категории
    3. Проверка порога уверенности
    4. Формирование ответа через LLM или умный синтез из базы знаний
    """
    normalized_query = normalise_query(user_message, TERMINS)

    # Шаг 1: Поиск в Qdrant
    hits = search_in_qdrant(normalized_query, top_k=3, category_filter=category_filter)

    # Если с фильтром ничего не найдено - пробуем глобальный поиск без фильтра
    if not hits and category_filter:
        hits = search_in_qdrant(normalized_query, top_k=3, category_filter=None)

    if not hits:
        return {
            "answer": "К сожалению, в официальной базе знаний пока нет регламентированного ответа на данный вопрос. Пожалуйста, обратитесь к дежурному специалисту службы поддержки.",
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

        sec_label = f" ({sec_header})" if sec_header else ""
        context_parts.append(f"### {title}{sec_label}\n{text_chunk}")
        
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

    # Шаг 4: Надежный Fallback-синтез, если LLM недоступна или долго отвечает
    if not llm_answer or len(llm_answer.strip()) < 10:
        main_source = citations[0] if citations else {"title": "Регламент Росэлторг", "url": "https://www.roseltorg.ru"}
        extracted_text = hits[0].payload.get("text", "").strip()
        
        # Красивое структурирование текста из базы знаний
        lines = [line.strip() for line in extracted_text.splitlines() if line.strip()]
        formatted_body = "\n\n".join(lines[:6])
        
        llm_answer = (
            f"По вашему запросу найдена официальная инструкция:\n\n"
            f"📌 **{main_source['title']}**" + (f" (*{main_source.get('section')}*)" if main_source.get('section') else "") + "\n\n"
            f"{formatted_body}\n\n"
            f"---\n"
            f"📖 **Источник:** [{main_source['title']}]({main_source.get('url', '#')})"
        )

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
