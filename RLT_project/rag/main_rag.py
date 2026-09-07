"""
main_rag.py — Главный RAG-пайплайн (ЯДРО СИСТЕМЫ).

RAG = Retrieval-Augmented Generation (генерация с подкреплением из базы знаний).

Как работает:
  1. Пользователь задаёт вопрос → "Как настроить ЭЦП?"
  2. Нормализация запроса  → "настройка электронная подпись (ЭЦП)"
  3. Векторизация          → [0.12, -0.34, 0.56, ...] (1024 числа)
  4. Поиск в Qdrant        → 3 ближайших чанка из базы знаний
  5. Составляем промпт    → контекст + вопрос → LLM
  6. LLM генерирует ответ → структурированный ответ + ссылки
"""

import json
import subprocess
import requests                              # HTTP-запросы к Ollama API
from qdrant_client import QdrantClient
from .normalize_query import normalise_query, TERMINS  # Нормализация запросов
from .embed_query import get_embedding                 # Векторизация текста
from .indexer.config import COLLECTION_NAME            # Имя коллекции в Qdrant
from .indexer.qdrant_indexer import get_qdrant_client   # Подключение к Qdrant

# === 1. Подключение к Qdrant (создаём клиент при импорте модуля) ===
client = get_qdrant_client()

# === 2. Вызов локальной LLM-модели через Ollama ===

def _get_active_ollama_model() -> str:
    """
    Автоматически определяет доступную LLM-модель в Ollama.

    Ollama — тоол для запуска LLM локально на компьютере.
    Запрашиваем список установленных моделей и выбираем лучшую.

    Приоритет: gpt-oss:20b > qwen2.5:7b > llama3.2 > mistral > gemma
    Если Ollama недоступна — возвращаем "gpt-oss:20b" по умолчанию.
    """
    try:
        import os
        ollama_url = f"{os.environ.get('OLLAMA_HOST', 'http://localhost:11434').rstrip('/')}/api/tags"
        r = requests.get(ollama_url, timeout=1.0)
        if r.status_code == 200:
            models_list = r.json().get("models", [])
            installed = [m.get("name") for m in models_list if m.get("name")]
            if installed:
                # Приоритет: легкие быстрые модели (3B-8B) в начале, тяжелые (20b) в конце
                for preferred in ["gpt-oss:20b", "llama3.2", "qwen2.5:3b", "qwen2.5:7b", "mistral", "gemma", "gpt-oss"]:
                    for m in installed:
                        if preferred in m:
                            return m
                # Если ни одна приоритетная не найдена — берём любую доступную
                return installed[0]
    except Exception:
        pass
    return "gpt-oss:20b"  # Дефолтная модель

def _call_local_gpt(prompt: str) -> str:
    """
    Вызов локальной LLM через Ollama. Два способа (с fallback):
      1. HTTP API (http://localhost:11434/api/generate) — основной
      2. CLI (ollama run model_name) — запасной

    Таймаут 120сек — достаточно для генерации на CPU.
    Возвращает пустую строку, если LLM недоступна.
    """
    model_name = _get_active_ollama_model()

    # Способ 1: HTTP API Ollama
    try:
        import os
        ollama_generate_url = f"{os.environ.get('OLLAMA_HOST', 'http://localhost:11434').rstrip('/')}/api/generate"
        res = requests.post(
            ollama_generate_url,
            json={
                "model": model_name,
                "prompt": prompt,
                "stream": False,     # Ждём полный ответ (не стриминг)
                "options": {
                    "temperature": 0.2,  # Низкая температура = более точный ответ
                    "top_p": 0.9
                }
            },
            timeout=120  # 2 минуты на CPU-генерацию
        )
        if res.status_code == 200:
            return res.json().get("response", "").strip()
    except Exception:
        pass

    # Способ 2: CLI (subprocess) — запускаем как команду в консоли
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
        return ""  # LLM недоступна — система переключится на fallback-синтез


# === 3. Поиск релевантных документов в Qdrant ===

def search_in_qdrant(query: str, top_k: int = 3, category_filter: str = None):
    """
    Семантический поиск (HYBRID SEARCH: Dense + BM25):
    """
    from rag.indexer.embedder import get_embedder, get_sparse_embedder
    
    vector = get_embedder().get_embedding(query).tolist()
    sparse_vector = get_sparse_embedder().get_sparse_embedding(query)

    query_filter = None
    from qdrant_client.http import models
    if category_filter:
        query_filter = models.Filter(
            must=[models.FieldCondition(key="category", match=models.MatchValue(value=category_filter))]
        )

    client = get_qdrant_client()
    try:
        # Гибридный поиск: Qdrant использует Reciprocal Rank Fusion (RRF)
        res = client.query_points(
            collection_name=COLLECTION_NAME,
            prefetch=[
                models.Prefetch(
                    query=vector,
                    using="",
                    limit=top_k * 2,
                    filter=query_filter
                ),
                models.Prefetch(
                    query=sparse_vector,
                    using="bm25",
                    limit=top_k * 2,
                    filter=query_filter
                )
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=top_k,
        )
        return res.points
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
    import time
    
    print(f"\n--- [RAG PIPELINE] СТАРТ ЗАПРОСА: '{user_message}' ---")
    t0 = time.time()
    normalized_query = normalise_query(user_message, TERMINS)

    # Шаг 1: Поиск в Qdrant
    t1 = time.time()
    hits = search_in_qdrant(normalized_query, top_k=3, category_filter=category_filter)
    if not hits and category_filter:
        hits = search_in_qdrant(normalized_query, top_k=3, category_filter=None)
    t2 = time.time()
    print(f"[RAG PIPELINE] Поиск в Qdrant занял: {t2 - t1:.2f} сек. Найдено документов: {len(hits)}")

    if not hits:
        print("[RAG PIPELINE] Документы не найдены, возврат заглушки.")
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

    print(f"[RAG PIPELINE] Отправка запроса в локальную LLM (Ollama)... Ждем генерации...")
    t3 = time.time()
    llm_answer = _call_local_gpt(prompt)
    t4 = time.time()
    print(f"[RAG PIPELINE] Генерация LLM заняла: {t4 - t3:.2f} сек.")
    print(f"--- [RAG PIPELINE] КОНЕЦ ЗАПРОСА ---")
    
    # Очищаем системные маркеры thinking, если модель их выводит
    marker = "...done thinking."
    if marker in llm_answer:
        llm_answer = llm_answer.split(marker, 1)[1].strip()

    # Шаг 4: Надежный Fallback-синтез, если LLM недоступна, вернула массив или долго отвечает
    is_invalid_output = not llm_answer or len(llm_answer.strip()) < 10 or (llm_answer.strip().startswith('[') and llm_answer.strip().endswith(']'))
    if is_invalid_output:
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
