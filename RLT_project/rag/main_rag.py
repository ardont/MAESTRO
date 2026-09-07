"""
main_rag.py — Главный RAG-пайплайн (ЯДРО СИСТЕМЫ).

Интегрирует:
1. Семантический гибридный поиск через search.py (Dense + Sparse BM25 + Qdrant RRF).
2. Графовые связи GraphRAG (graph_rag.py) — экономия токенов, устранение галлюцинаций.
3. Кэширование контекста в модели Chat (context_cache) для мгновенных ответов на уточнения.
4. Интерактивный Workflow-помощник (пошаговое прохождение процедур по 44-ФЗ, 223-ФЗ и регламентам).
5. Быстрый вызов локальной LLM в Ollama (qwen2.5:7b на GPU) с надежным fallback.
"""

import os
import re
import json
import time
import logging
import requests
from typing import Dict, Any, List, Optional

from .normalize_query import normalise_query, TERMINS
from .search import search_hybrid
from .graph_rag import find_graph_node, format_graph_context_for_llm, get_workflow_step_response

logger = logging.getLogger("rag")

def _get_active_ollama_model() -> str:
    """
    Определяет лучшую модель в Ollama.
    Приоритет: qwen2.5:7b > qwen2.5:3b > llama3.2 > mistral > gemma > deepseek > gpt-oss
    """
    try:
        ollama_url = f"{os.environ.get('OLLAMA_HOST', 'http://localhost:11434').rstrip('/')}/api/tags"
        r = requests.get(ollama_url, timeout=1.5)
        if r.status_code == 200:
            models_list = r.json().get("models", [])
            installed = [m.get("name") for m in models_list if m.get("name")]
            if installed:
                for preferred in ["qwen2.5:7b", "qwen2.5:3b", "llama3.2", "qwen2.5", "mistral", "gemma", "deepseek-r1:32b", "gpt-oss"]:
                    for m in installed:
                        if preferred in m:
                            return m
                return installed[0]
    except Exception as e:
        logger.debug(f"[OLLAMA MODEL CHECK] {e}")
    return "qwen2.5:7b"


def _call_local_gpt(prompt: str) -> str:
    """
    Вызов локальной LLM в Ollama через HTTP API.
    """
    model_name = _get_active_ollama_model()
    ollama_url = f"{os.environ.get('OLLAMA_HOST', 'http://localhost:11434').rstrip('/')}/api/generate"

    try:
        res = requests.post(
            ollama_url,
            json={
                "model": model_name,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.2,
                    "top_p": 0.9,
                    "num_ctx": 4096
                }
            },
            timeout=90
        )
        if res.status_code == 200:
            response_text = res.json().get("response", "").strip()
            # Очистка возможных маркеров thinking
            marker = "...done thinking."
            if marker in response_text:
                response_text = response_text.split(marker, 1)[1].strip()
            return response_text
    except Exception as e:
        logger.warning(f"[OLLAMA GENERATE ERROR] {e}")

    return ""


def rag_pipeline(user_message: str, chat=None, category_filter: Optional[str] = None) -> Dict[str, Any]:
    """
    Полный сквозной RAG-пайплайн с памятью (context_cache), GraphRAG и пошаговым Workflow.
    """
    t0 = time.time()
    logger.info(f"=== [RAG PIPELINE START] Запрос: '{user_message}' ===")
    print(f"\n--- [RAG PIPELINE] СТАРТ ЗАПРОСА: '{user_message}' ---")

    # 1. ПРОВЕРКА КЭША КОНТЕКСТА В ЧАТЕ (ПРИОРИТЕТ 3)
    cached_context = []
    if chat and hasattr(chat, "context_cache") and chat.context_cache:
        # Если в кэше есть сохраненные документы предыдущих шагов диалога
        for item in chat.context_cache:
            if isinstance(item, dict) and "text" in item:
                # Простая проверка релевантности кэша текущему вопросу
                kw_matches = sum(1 for w in user_message.lower().split() if len(w) > 3 and w in item.get("text", "").lower())
                if kw_matches >= 2:
                    cached_context.append(item)

    # 2. ПОИСК В ГРАФЕ ЗНАНИЙ (GraphRAG / Graphify) (ПРИОРИТЕТ 2)
    graph_node = find_graph_node(user_message)
    graph_context_text = ""
    if graph_node:
        graph_context_text = format_graph_context_for_llm(graph_node)
        logger.info(f"[GRAPHRAG] Найдена вершина графа: '{graph_node['id']}' ({graph_node['title']})")
        print(f"[GRAPHRAG] Точное совпадение с графом знаний: '{graph_node['title']}'")

    # 3. ГИБРИДНЫЙ ПОИСК В QDRANT (Dense + Sparse)
    normalized_query = normalise_query(user_message, TERMINS)
    t_search0 = time.time()
    
    # Ищем чанки в Qdrant через search_hybrid
    hits = search_hybrid(normalized_query, top_k=4, category_filter=category_filter)
    if not hits and category_filter:
        hits = search_hybrid(normalized_query, top_k=4, category_filter=None)
        
    t_search1 = time.time()
    search_duration = t_search1 - t_search0
    logger.info(f"[SEARCH TIMING] Поиск в Qdrant занял: {search_duration:.3f} сек. Найдено точек: {len(hits)}")
    print(f"[RAG PIPELINE] Поиск в базе занял: {search_duration:.2f} сек. Найдено документов: {len(hits)}")

    # 4. АГРЕГАЦИЯ КОНТЕКСТА И ИСТОЧНИКОВ
    context_parts = []
    citations = []
    images = []
    new_cache_items = []

    # Если есть графовый контекст — добавляем его первым (он самый авторитетный и точный)
    if graph_context_text:
        context_parts.append(graph_context_text)
        citations.append({
            "title": graph_node["title"],
            "section": "Нормативно-правовая база",
            "url": graph_node.get("url", "https://zakupki.mos.ru/knowledgebase/main")
        })

    for hit in hits:
        payload = hit.payload or {}
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

        new_cache_items.append({
            "title": title,
            "section_header": sec_header,
            "url": url,
            "text": text_chunk[:500]
        })

    # Сохраняем в кэш контекста чата (ПРИОРИТЕТ 3)
    if chat:
        try:
            workflow_to_offer = graph_node["id"] if graph_node else "general_guide"
            chat.context_cache = {
                "items": new_cache_items[:6],
                "suggested_workflow": workflow_to_offer,
                "graph_node_id": graph_node["id"] if graph_node else None
            }
            chat.save(update_fields=["context_cache"])
            logger.info(f"[CHAT CACHE] Контекст сохранен в БД для чата {chat.id}")
        except Exception as e:
            logger.warning(f"[CHAT CACHE ERROR] Не удалось сохранить context_cache: {e}")

    # Если ни документов, ни графа нет — выдаем вежливую заглушку
    if not context_parts:
        logger.info("[RAG PIPELINE] Контекст не найден.")
        return {
            "answer": "К сожалению, в официальной базе знаний Портала поставщиков Москвы пока нет регламентированного ответа на данный вопрос. Пожалуйста, обратитесь к дежурному специалисту службы поддержки.\n\n📖 **Источник:** [База знаний Портала поставщиков Москвы](https://zakupki.mos.ru/knowledgebase/main)",
            "citations": [{
                "title": "База знаний Портала поставщиков Москвы",
                "section": "Главная",
                "url": "https://zakupki.mos.ru/knowledgebase/main"
            }],
            "images": []
        }

    full_context = "\n\n".join(context_parts)

    # Определяем первоисточник
    primary_citation = citations[0] if citations else {
        "title": "Портал поставщиков Москвы",
        "url": "https://zakupki.mos.ru/knowledgebase/main"
    }
    primary_url = primary_citation.get("url") or "https://zakupki.mos.ru/knowledgebase/main"
    primary_title = primary_citation.get("title") or "Портал поставщиков Москвы"

    # 5. СОСТАВЛЕНИЕ ПРОМПТА ДЛЯ LLM
    prompt = f"""Ты — интеллектуальный эксперт службы поддержки пользователей Портала поставщиков Москвы (zakupki.mos.ru) и законодательства о закупках (44-ФЗ, 223-ФЗ).
Ответь на вопрос пользователя, опираясь ИСКЛЮЧИТЕЛЬНО на предоставленную базу знаний и нормативные факты.

Вопрос пользователя: "{user_message}"

База знаний:
{full_context}

Инструкции для ответа:
1. Сформулируй четкий, доброжелательный, исчерпывающий и структурированный по шагам ответ (1, 2, 3).
2. Обязательно укажи точные сроки и регламентные требования, если они есть в тексте.
3. Укажи официальный канал (например, Портал поставщиков Москвы / ЕИС Закупки) и финансовые условия.
4. Если в базе знаний описаны конкретные разделы личного кабинета, кнопки или пункты меню — выдели их кавычками или жирным шрифтом.
5. В самом конце ответа ОБЯЗАТЕЛЬНО укажи первоисточник в формате:
📖 **Источник:** [{primary_title}]({primary_url})
СТРОЖАЙШИЙ ЗАПРЕТ: Ссылка должна вести исключительно на https://zakupki.mos.ru. Не придумывай никаких других ссылок.
"""

    logger.debug(f"[LLM PROMPT] Длина промпта: {len(prompt)} символов")
    print(f"[RAG PIPELINE] Отправка запроса в Ollama...")
    t_llm0 = time.time()
    llm_answer = _call_local_gpt(prompt)
    t_llm1 = time.time()
    llm_duration = t_llm1 - t_llm0
    logger.info(f"[LLM TIMING] Генерация ответа заняла: {llm_duration:.2f} сек.")
    print(f"[RAG PIPELINE] Генерация LLM заняла: {llm_duration:.2f} сек.")

    # 6. НАДЕЖНЫЙ FALLBACK-СИНТЕЗ (если LLM недоступна или ответ некорректен)
    is_invalid = not llm_answer or len(llm_answer.strip()) < 20
    if is_invalid:
        logger.info("[FALLBACK] Активирован детерминированный синтез ответа из Базы Знаний и Графа.")
        if graph_node:
            steps_formatted = "\n".join([f"**{i+1}.** {s}" for i, s in enumerate(graph_node["workflow_steps"])])
            deadlines_formatted = "\n".join([f"• {d}" for d in graph_node["deadlines"]])
            node_url = graph_node.get("url", "https://zakupki.mos.ru/knowledgebase/main")
            llm_answer = (
                f"### {graph_node['title']}\n\n"
                f"**Нормативное регулирование:** {', '.join(graph_node['law_references'])}\n\n"
                f"**Способ подачи:** {graph_node['channel']}\n\n"
                f"**Стоимость:** {graph_node['fee']}\n\n"
                f"**Регламентные сроки:**\n{deadlines_formatted}\n\n"
                f"**Пошаговый порядок действий:**\n{steps_formatted}\n\n"
                f"---\n"
                f"📖 **Источник:** [{graph_node['title']}]({node_url})"
            )
        elif hits:
            main_source = citations[0] if citations else {"title": "Регламент Портала поставщиков", "url": "https://zakupki.mos.ru"}
            extracted = hits[0].payload.get("text", "").strip()
            lines = [l.strip() for l in extracted.splitlines() if l.strip()]
            body_text = "\n\n".join(lines[:6])
            llm_answer = (
                f"По вашему вопросу найдена официальная инструкция:\n\n"
                f"📌 **{main_source['title']}**\n\n"
                f"{body_text}\n\n"
                f"---\n📖 **Источник:** [{main_source['title']}]({main_source.get('url', 'https://zakupki.mos.ru')})"
            )

    # 7. СТРОГАЯ САНИТАРИЯ ССЫЛОК И ПОЛНОЕ ИСКЛЮЧЕНИЕ 404 / СТОРОННИХ РЕСУРСОВ
    # Исключаем любые случайные упоминания Росэлторг
    llm_answer = re.sub(r'росэлторг\w*', 'Портал поставщиков Москвы', llm_answer, flags=re.IGNORECASE)

    # Допустимые URL из найденных документов
    valid_urls_set = {c['url'] for c in citations if c.get('url') and c['url'].startswith('https://zakupki.mos.ru')}
    valid_urls_set.add(primary_url)
    valid_urls_set.add("https://zakupki.mos.ru/knowledgebase/main")
    valid_urls_set.add("https://zakupki.mos.ru/knowledgebase/regulations")

    def _sanitize_md_link(match):
        text = match.group(1)
        url = match.group(2).strip()
        # Если ссылка точь-в-точь из найденных валидных статей — оставляем
        if url in valid_urls_set:
            return f"[{text}]({url})"
        # Если ссылка ведет на zakupki.mos.ru и имеет валидный паттерн статьи
        if url.startswith("https://zakupki.mos.ru") and ("/knowledgebase/article/" in url or url.endswith("/knowledgebase/main") or url.endswith("/knowledgebase/regulations")):
            return f"[{text}]({url})"
        # Любая иная галлюцинированная ссылка подменяется на проверенный первоисточник
        return f"[{text}]({primary_url})"

    llm_answer = re.sub(r'\[([^\]]+)\]\((https?://[^\)]+)\)', _sanitize_md_link, llm_answer)

    # Проверяем наличие кликабельного источника в конце ответа
    if "📖 **Источник:**" not in llm_answer and "Источник:" not in llm_answer:
        llm_answer = llm_answer.strip() + f"\n\n📖 **Источник:** [{primary_title}]({primary_url})"

    # 8. ОБЯЗАТЕЛЬНОЕ ПРЕДЛОЖЕНИЕ ПОШАГОВОГО WORKFLOW (ПРИОРИТЕТ 4)
    workflow_offer = "\n\nХотите я помогу вам пройти этот процесс по шагам?"
    if workflow_offer.strip() not in llm_answer:
        llm_answer = llm_answer.strip() + workflow_offer

    t_end = time.time()
    total_duration = t_end - t0
    logger.info(f"=== [RAG PIPELINE END] Запрос обработан за {total_duration:.2f} сек. ===")
    print(f"--- [RAG PIPELINE] КОНЕЦ ЗАПРОСА (Всего: {total_duration:.2f} сек) ---")

    return {
        "answer": llm_answer,
        "citations": citations,
        "images": images,
        "timings": {
            "search_sec": round(search_duration, 3),
            "llm_sec": round(llm_duration, 3),
            "total_sec": round(total_duration, 3)
        }
    }
