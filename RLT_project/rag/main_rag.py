"""
main_rag.py — Главный RAG-пайплайн (ЯДРО СИСТЕМЫ).

Интегрирует:
1. Семантический гибридный поиск через search.py (Dense + Sparse BM25 + Qdrant RRF).
2. Графовые связи GraphRAG (graph_rag.py) — экономия токенов, устранение галлюцинаций.
3. Кэширование контекста в модели Chat (context_cache) для мгновенных ответов на уточнения.
4. Интерактивный Workflow-помощник (пошаговое прохождение процедур по 44-ФЗ, 223-ФЗ и регламентам).
5. Быстрый вызов локальной LLM в Ollama (gpt-oss:20b) с надежным fallback.
"""

import os
import asyncio
import re
import json
import time
import logging
import requests
from typing import Dict, Any, List, Optional, AsyncIterator

from .normalize_query import normalise_query, TERMINS
from .url_utils import (
    normalize_portal_url, normalize_markdown_links,
    clean_citation_title, clean_citation_section
)


from .workflow import handle_workflow
from .graph_rag import PROCUREMENT_KNOWLEDGE_GRAPH
from .router import check_guardrails
from .events import (
    LLMBaseEvent, LLMTokenEvent, LLMDoneEvent, LLMErrorEvent,
    LLMBlockEvent, LLMOffTopicEvent, LLMNeedOperatorEvent,
)

import hashlib

logger = logging.getLogger("rag")

redis_client = None
try:
    import redis

    redis_client = redis.Redis(
        host=os.environ.get('REDIS_HOST', 'localhost'),
        port=int(os.environ.get('REDIS_PORT', 6379)),
        db=0, socket_connect_timeout=1.5, socket_timeout=1.5
    )
except Exception as e:
    logger.warning(f"Redis недоступен: {e}")
    redis_client = None

def _get_active_ollama_model() -> str:
    """Use the configured model without silently selecting another installed model."""
    return os.environ.get("OLLAMA_MODEL", "gpt-oss:20b").strip() or "gpt-oss:20b"


def _call_local_gpt(prompt: str, on_token=None, max_tokens: Optional[int] = None) -> str:
    """
    Вызов локальной LLM в Ollama через HTTP API.
    """
    model_name = _get_active_ollama_model()
    ollama_url = f"{os.environ.get('OLLAMA_HOST', 'http://localhost:11434').rstrip('/')}/api/generate"
    started = time.monotonic()
    logger.info("[OLLAMA START] model=%s endpoint=%s", model_name, ollama_url)

    try:
        options = {
            "temperature": 0.2,
            "top_p": 0.9,
            "num_ctx": 4096
        }
        if max_tokens:
            options["num_predict"] = max_tokens

        res = requests.post(
            ollama_url,
            json={
                "model": model_name,
                "prompt": prompt,
                "stream": on_token is not None,
                "options": options
            },
            timeout=90,
            stream=on_token is not None,
        )
        if res.status_code == 200:
            if on_token is not None:
                parts = []
                try:
                    for line in res.iter_lines(chunk_size=1):
                        if not line:
                            continue
                        packet = json.loads(line)
                        if packet.get("error"):
                            raise RuntimeError(packet["error"])
                        token = packet.get("response", "")
                        if token:
                            parts.append(token)
                            on_token(token)
                        if packet.get("done"):
                            break
                    else:
                        raise RuntimeError("Ollama stream ended without done")
                finally:
                    res.close()
                response_text = "".join(parts).strip()
            else:
                response_text = res.json().get("response", "").strip()
            # Очистка возможных маркеров thinking
            marker = "...done thinking."
            if marker in response_text:
                response_text = response_text.split(marker, 1)[1].strip()
            logger.info("[OLLAMA END] model=%s status=%s chars=%s duration_sec=%.3f",
                        model_name, res.status_code, len(response_text), time.monotonic() - started)
            return response_text
        logger.warning("[OLLAMA HTTP ERROR] model=%s status=%s body=%r",
                       model_name, res.status_code, res.text[:500])
    except Exception as e:
        logger.warning(f"[OLLAMA GENERATE ERROR] {e}")
        if on_token is not None:
            raise

    return ""


def rag_pipeline_result(user_message: str, chat=None, category_filter: Optional[str] = None, on_token=None) -> Dict[str, Any]:
    """
    Полный сквозной RAG-пайплайн с памятью (context_cache), GraphRAG и пошаговым Workflow.
    """
    t0 = time.time()
    logger.info("[RAG START] query=%r category=%s", user_message, category_filter)
    guardrail = check_guardrails(user_message)
    logger.info("[GUARDRAIL] blocked=%s reason=%s", guardrail["is_blocked"], guardrail.get("reason"))
    if guardrail["is_blocked"]:
        return {"event": "block", "answer": guardrail["reply"], "citations": [], "images": []}

    workflow_result = handle_workflow(user_message, chat)
    if workflow_result is not None:
        return workflow_result

    # Мгновенная проверка на очевидный оффтопик (бытовые темы, рецепты, погода, игры) — 0 мс задержки
    OFF_TOPIC_STOP_WORDS = [
        "омлет", "рецепт", "сварить", "приготовить", "пицц", "борщ", "суп", "салат", "погод",
        "анекдот", "гороскоп", "фильм", "сериал", "сыграем", "поиграем", "расскажи сказку",
        "стишок", "песн", "курс валют", "биткоин", "футбол", "хоккей", "гороскоп"
    ]
    DOMAIN_KEYWORDS = [
        "портал", "закуп", "поставщ", "заказчик", "контракт", "оферт", "сте", "кэп", "эцп",
        "крипто", "упд", "еис", "еруз", "рдик", "котиров", "акт", "счет", "лот", "фз",
        "жалоб", "фас", "мчд", "доверенност", "профил", "организац", "инн", "огрн", "кпп",
        "ошибк", "статус", "подпис", "рутокен", "браузер", "плагин", "оператор", "поддержк",
        "калуг", "астрал", "гаранти", "спецсчет", "ктру", "окпд", "реестр", "рнп", "нмцк",
        "регистрац", "зарегистрир", "вход", "логин", "парол", "здравствуй", "привет", "добрый",
        "подскажи", "как работать", "что делать", "помоги", "услуг", "товар"
    ]
    query_lower = user_message.lower().strip()
    is_explicit_offtopic = any(sw in query_lower for sw in OFF_TOPIC_STOP_WORDS)
    has_domain_keywords = any(kw in query_lower for kw in DOMAIN_KEYWORDS)

    if is_explicit_offtopic and not has_domain_keywords:
        logger.info(f"[INSTANT OFF-TOPIC] Запрос '{user_message}' отсечен по стоп-словам оффтопика.")
        return {
            "event": "off-topic",
            "answer": "Мы помогаем исключительно с вопросами о Портале поставщиков Москвы (https://zakupki.mos.ru/) и законодательстве о закупках (44-ФЗ, 223-ФЗ). Ваш вопрос относится к другой сфере. Пожалуйста, задайте вопрос по теме работы сервисов Портала или процедур закупок.",
            "citations": [],
            "images": []
        }

    # Classify before retrieval/cache: unrelated nearest neighbours are not evidence
    # that the user is asking about the platform. Ambiguous follow-ups stay on topic.
    logger.info("[TOPIC START] query=%r", user_message)
    verdict = _call_local_gpt(
        "Ты классификатор тематики поддержки Портала поставщиков Москвы (zakupki.mos.ru).\n"
        "Тематика: работа портала, регистрация, закупки, 44-ФЗ, 223-ФЗ, контракты, "
        "оплата, электронная подпись, технические ошибки и поддержка пользователей.\n"
        "Верни ровно OFF_TOPIC только если запрос явно и полностью о другой сфере "
        "(например, рецепты, погода, развлечения, не относящиеся к закупкам).\n"
        "Для вопросов по теме, приветствий, коротких уточнений и любых сомнений верни ON_TOPIC.\n"
        "Твой ответ должен содержать только одно слово: ON_TOPIC или OFF_TOPIC.\n"
        "Запрос: " + json.dumps(user_message, ensure_ascii=False),
        max_tokens=60
    )
    logger.info("[TOPIC RESULT] query=%r verdict=%r", user_message, verdict[:200])
    clean_verdict = verdict.strip().upper()
    if "OFF_TOPIC" in clean_verdict and "ON_TOPIC" not in clean_verdict:
        return {
            "event": "off-topic",
            "answer": "Мы помогаем с вопросами о Портале поставщиков Москвы "
                      "(https://zakupki.mos.ru/) и закупках. Ваш вопрос относится "
                      "к другой сфере. Пожалуйста, задайте вопрос по теме платформы.",
            "citations": [], "images": [],
        }

    # Load heavy retrieval dependencies inside the worker, after moderation.
    logger.info("[RETRIEVAL LOAD] Loading search dependencies")
    from .search import search_hybrid

    logger.info(f"=== [RAG PIPELINE START] Запрос: '{user_message}' ===")
    print(f"\\n--- [RAG PIPELINE] СТАРТ ЗАПРОСА: '{user_message}' ---")

    # 0. ПРОВЕРКА В КЭШЕ REDIS
    cache_key = None
    if redis_client and chat is None:
        cache_input = json.dumps([user_message.lower().strip(), category_filter], ensure_ascii=False)
        cache_key = f"rag_query:v2:{hashlib.sha256(cache_input.encode('utf-8')).hexdigest()}"
        try:
            cached_result = redis_client.get(cache_key)
            if cached_result:
                logger.info(f"[REDIS CACHE] Найден кэш для запроса: {user_message}")
                res = json.loads(cached_result.decode('utf-8'))
                res['timings'] = {"search_sec": 0, "llm_sec": 0, "total_sec": round(time.time() - t0, 3)}
                return res
        except Exception as e:
            logger.warning(f"[REDIS CACHE ERROR] {e}")

    # 1. ПРОВЕРКА КЭША КОНТЕКСТА В ЧАТЕ (ПРИОРИТЕТ 3)
    cached_context = []
    if chat and hasattr(chat, "context_cache") and chat.context_cache:
        # Если в кэше есть сохраненные документы предыдущих шагов диалога
        cache_items = chat.context_cache.get("items", []) if isinstance(chat.context_cache, dict) else chat.context_cache
        for item in cache_items:
            if isinstance(item, dict) and "text" in item:
                # Простая проверка релевантности кэша текущему вопросу
                kw_matches = sum(1 for w in user_message.lower().split() if len(w) > 3 and w in item.get("text", "").lower())
                if kw_matches >= 2:
                    cached_context.append(item)

    # 2. ПОИСК В ГРАФЕ ЗНАНИЙ (GraphRAG / Graphify) (ПРИОРИТЕТ 2)
    new_graph_node = find_graph_node(user_message)
    active_node_id = getattr(chat, "active_workflow", None)
    active_node = PROCUREMENT_KNOWLEDGE_GRAPH.get(active_node_id) if active_node_id else None

    # Проверяем, является ли вопрос продолжением текущего пошагового workflow
    is_workflow_continuation = False
    if active_node:
        msg_l = user_message.lower().strip()
        step_words = ["дальше", "далее", "следующ", "продолж", "потом", "шаг", "второй", "третий", "четверт", "давай", "ок", "понял"]
        has_step_intent = any(w in msg_l for w in step_words)
        has_node_keywords = any(kw in msg_l for kw in active_node.get("keywords", []))
        if has_step_intent or has_node_keywords:
            is_workflow_continuation = True

    if new_graph_node:
        if active_node and new_graph_node["id"] != active_node["id"]:
            logger.info(f"[TOPIC SWITCH] Смена темы с '{active_node['id']}' на '{new_graph_node['id']}'. Сброс контекста.")
            if chat:
                chat.active_workflow = None
                chat.current_step = 0
                if hasattr(chat, "save"):
                    try:
                        chat.save(update_fields=["active_workflow", "current_step"])
                    except Exception:
                        pass
        graph_node = new_graph_node
    elif is_workflow_continuation:
        graph_node = active_node
    else:
        # Новый независимый вопрос — сбрасываем залипший workflow
        if active_node and chat:
            logger.info(f"[WORKFLOW RESET] Запрос '{user_message}' не относится к '{active_node['id']}'. Сброс active_workflow.")
            chat.active_workflow = None
            chat.current_step = 0
            if hasattr(chat, "save"):
                try:
                    chat.save(update_fields=["active_workflow", "current_step"])
                except Exception:
                    pass
        graph_node = None

    graph_context_text = ""
    if graph_node:
        graph_context_text = format_graph_context_for_llm(graph_node)
        logger.info(f"[GRAPHRAG] Найдена вершина графа: '{graph_node['id']}' ({graph_node['title']})")
        print(f"[GRAPHRAG] Точное совпадение с графом знаний: '{graph_node['title']}'")

    # 3. ГИБРИДНЫЙ ПОИСК В QDRANT (Dense + Sparse)
    normalized_query = normalise_query(user_message, TERMINS)
    t_search0 = time.time()
    logger.info("[SEARCH START] query=%r category=%s", normalized_query, category_filter)
    
    # Ищем чанки в Qdrant через search_hybrid
    hits = search_hybrid(normalized_query, top_k=4, category_filter=category_filter)
    if not hits and category_filter:
        hits = search_hybrid(normalized_query, top_k=4, category_filter=None)
        
    t_search1 = time.time()
    search_duration = t_search1 - t_search0
    max_score = max([getattr(h, "score", 0.0) for h in hits], default=0.0)
    logger.info(f"[SEARCH TIMING] Поиск в Qdrant занял: {search_duration:.3f} сек. Найдено точек: {len(hits)} (Max Score: {max_score:.4f})")
    print(f"[RAG PIPELINE] Поиск в базе занял: {search_duration:.2f} сек. Найдено документов: {len(hits)} (Max Score: {max_score:.4f})")

    # ПОРОГ РЕЛЕВАНТНОСТИ (исключение случайных источников и галлюцинаций на бессмысленные запросы вроде "хочу омлет")
    has_lexical_overlap = False
    query_words = [w for w in re.findall(r'[a-zA-Zа-яА-ЯёЁ0-9]{3,}', user_message.lower()) 
                   if w not in {"как", "что", "где", "куда", "когда", "почему", "зачем", "если", "для", "или", "под", "над", "при", "про", "меня", "тебя", "хочу", "могу", "надо", "нужно"}]
    if query_words:
        for h in hits:
            pl = getattr(h, "payload", {}) or {}
            content = (pl.get("title", "") + " " + pl.get("section_header", "") + " " + pl.get("text", "")).lower()
            if any(qw in content for qw in query_words):
                has_lexical_overlap = True
                break
    else:
        has_lexical_overlap = True

    if not graph_node and (not has_lexical_overlap or max_score < 0.15):
        logger.info(f"[SCORE/LEXICAL THRESHOLD] Запрос '{user_message}' отсечен (lexical_overlap={has_lexical_overlap}, max_score={max_score:.4f}). Гарантированный отказ без ложных источников.")
        return {
            "answer": "Извините, но я могу отвечать только на вопросы, связанные с Порталом поставщиков Москвы (zakupki.mos.ru) и законодательством о закупках (44-ФЗ, 223-ФЗ). Пожалуйста, задайте вопрос по теме закупок или работе сервисов Портала.",
            "citations": [],
            "images": []
        }

    # 4. АГРЕГАЦИЯ КОНТЕКСТА И ИСТОЧНИКОВ
    context_parts = []
    citations = []
    images = []
    new_cache_items = []

    # Если есть графовый контекст — добавляем его первым (он самый авторитетный и точный)
    if graph_context_text:
        context_parts.append(graph_context_text)
        graph_url = normalize_portal_url(graph_node.get("url", "https://zakupki.mos.ru/knowledgebase/main"))
        graph_title = clean_citation_title(graph_node["title"], graph_url)
        citations.append({
            "title": graph_title,
            "section": "Нормативно-правовая база",
            "url": graph_url
        })

    for hit in hits:
        payload = hit.payload or {}
        raw_title = payload.get("title", "Документ")
        raw_url = payload.get("url", "")
        url = normalize_portal_url(raw_url) if raw_url else ""
        title = clean_citation_title(raw_title, url)
        sec_header = clean_citation_section(payload.get("section_header", ""))
        text_chunk = payload.get("text", "")
        chunk_images = payload.get("images", [])

        sec_label = f" ({sec_header})" if sec_header else ""
        context_parts.append(f"### {title}{sec_label}\n{text_chunk}")

        # Добавляем в цитаты ТОЛЬКО проверенные ссылки
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
            workflow_to_offer = graph_node["id"] if graph_node else None
            chat.context_cache = {
                "items": new_cache_items[:6],
                "suggested_workflow": workflow_to_offer,
                "graph_node_id": graph_node["id"] if graph_node else None
            }
            if hasattr(chat, "save"):
                chat.save(update_fields=["context_cache"])
            logger.info(f"[CHAT CACHE] Контекст сохранен в БД для чата {getattr(chat, 'id', '')}")
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
    primary_url = normalize_portal_url(primary_citation.get("url") or "https://zakupki.mos.ru/knowledgebase/main")
    primary_title = primary_citation.get("title") or "Портал поставщиков Москвы"

    # 5. СОСТАВЛЕНИЕ ПРОМПТА ДЛЯ LLM
    chat_history_text = ""
    if active_node:
        chat_history_text = (f"Пользователь проходит процесс {active_node['title']}, "
                             f"текущий шаг {chat.current_step}. Ответь на уточнение по этому шагу; "
                             "не начинай процесс заново и не переходи к следующему шагу.\n\n")
    if chat and hasattr(chat, "messages"):
        # Получаем последние 4 сообщения из чата (кроме текущего, которое уже добавлено в БД)
        # Сортируем по created_at, чтобы получить хронологию
        recent_messages = chat.messages.order_by('-created_at')[1:5]
        if recent_messages:
            history_lines = []
            for m in reversed(recent_messages):
                role_name = "Пользователь" if m.author.role == "customer" else "Ассистент"
                history_lines.append(f"{role_name}: {m.text}")
            chat_history_text += "История предыдущих сообщений диалога:\n" + "\n".join(history_lines) + "\n\n"

    prompt = f"""Ты — интеллектуальный эксперт единой службы поддержки пользователей Портала поставщиков Москвы (zakupki.mos.ru).
ВАЖНЕЙШЕЕ ПРАВИЛО РОЛИ: ТЫ САМ ЯВЛЯЕШЬСЯ СЛУЖБОЙ ПОДДЕРЖКИ. Пользователь уже обратился в службу поддержки в этом чате.
Категорически запрещено писать фразы вроде «обратитесь в службу поддержки», «напишите в техподдержку» или «позвоните на горячую линию».
Вместо этого формулируй ответ от первого лица поддержки: «Служба поддержки Портала поставщиков рекомендует...», «Если сбой не удастся устранить — мы зарегистрируем инцидент и передадим обращение дежурным инженерам».

{chat_history_text}Вопрос пользователя: "{user_message}"

База знаний:
{full_context}

Инструкции для ответа:
1. Опирайся ИСКЛЮЧИТЕЛЬНО на предоставленную базу знаний. СТРОЖАЙШЕ ЗАПРЕЩЕНО выдумывать несуществующие разделы личного кабинета, формы, кнопки, калькуляторы (например, «калькулятор "Проверка стоимости"», раздел «Параметры публикации», несуществующие кнопки) или регламентные сроки, которых нет в тексте базы знаний.
2. Способы закупок на Портале поставщиков Москвы — это ИСКЛЮЧИТЕЛЬНО: «Котировочная сессия», «Прямая закупка» и «Закупка по потребностям». Других способов закупок малого объема на Портале нет.
3. По 223-ФЗ заказчики проводят закупки в соответствии со своим Положением о закупке. Закон-основание (44-ФЗ или 223-ФЗ) и способ закупки не выбираются поставщиком в оферте, а определяются заказчиком при публикации закупки или формировании контракта.
4. Сформулируй четкий, доброжелательный, исчерпывающий и структурированный по шагам ответ (1, 2, 3).
5. Указывай финансовые условия (бесплатно / размер пошлины) и каналы подачи ТОЛЬКО если вопрос касается регламентных закупочных процедур (жалоба в ФАС, банковская гарантия, котировочная сессия). НЕ пиши о финансовых условиях при технических сбоях, ошибках (500 и др.) или настройке браузера.
6. В самом конце ответа ОБЯЗАТЕЛЬНО укажи первоисточник в формате:
📖 **Источник:** [{primary_title}]({primary_url})
СТРОЖАЙШИЙ ЗАПРЕТ: Ссылка должна вести исключительно на https://zakupki.mos.ru. Не придумывай никаких сторонних ссылок.
"""

    logger.debug(f"[LLM PROMPT] Длина промпта: {len(prompt)} символов")
    print(f"[RAG PIPELINE] Отправка запроса в Ollama...")
    t_llm0 = time.time()
    llm_answer = _call_local_gpt(prompt, on_token=on_token) if on_token else _call_local_gpt(prompt)
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

    # Нормализуем ссылки в тексте LLM
    llm_answer = normalize_markdown_links(llm_answer)

    # Допустимые проверенные URL из найденных документов базы знаний (все нормализованы)
    valid_urls_set = {normalize_portal_url(c['url']) for c in citations if c.get('url') and c['url'].startswith('https://zakupki.mos.ru')}
    valid_urls_set.add(primary_url)
    valid_urls_set.add("https://zakupki.mos.ru/knowledgebase/main")
    valid_urls_set.add("https://zakupki.mos.ru/knowledgebase/article/regulation/cms")

    def _sanitize_md_link(match):
        text = match.group(1)
        url = match.group(2).strip()
        norm_url = normalize_portal_url(url)
        if norm_url in valid_urls_set:
            return f"[{text}]({norm_url})"
        if norm_url.startswith("https://zakupki.mos.ru") and ("/knowledgebase/article/" in norm_url or norm_url.endswith("/knowledgebase/main")):
            return f"[{text}]({norm_url})"
        return f"[{text}]({primary_url})"

    llm_answer = re.sub(r'\[([^\]]+)\]\((https?://[^\)]+)\)', _sanitize_md_link, llm_answer)

    # Проверяем наличие кликабельного источника в конце ответа
    if "📖 **Источник:**" not in llm_answer and "Источник:" not in llm_answer:
        llm_answer = llm_answer.strip() + f"\n\n📖 **Источник:** [{primary_title}]({primary_url})"

    # 8. ОБЯЗАТЕЛЬНОЕ ПРЕДЛОЖЕНИЕ ПОШАГОВОГО WORKFLOW (ПРИОРИТЕТ 4)
    workflow_offer = "\n\nХотите я помогу вам пройти этот процесс по шагам?"
    if chat and graph_node and not active_node and workflow_offer.strip() not in llm_answer:
        llm_answer = llm_answer.strip() + workflow_offer

    t_end = time.time()
    total_duration = t_end - t0
    logger.info(f"=== [RAG PIPELINE END] Запрос обработан за {total_duration:.2f} сек. ===")
    print(f"--- [RAG PIPELINE] КОНЕЦ ЗАПРОСА (Всего: {total_duration:.2f} сек) ---")

    res = {
        "answer": llm_answer,
        "citations": citations,
        "images": images,
        "timings": {
            "search_sec": round(search_duration, 3),
            "llm_sec": round(llm_duration, 3),
            "total_sec": round(total_duration, 3)
        }
    }

    if redis_client and cache_key:
        try:
            # Кэшируем на 24 часа
            redis_client.setex(cache_key, 86400, json.dumps({
                "answer": llm_answer,
                "citations": citations,
                "images": images
            }, ensure_ascii=False))
        except Exception as e:
            logger.warning(f"[REDIS CACHE SET ERROR] {e}")

    return res


async def rag_pipeline(
    user_message: str, chat=None, category_filter: Optional[str] = None,
) -> AsyncIterator[LLMBaseEvent]:
    """Bridge blocking retrieval/Ollama to live asynchronous token events."""
    loop = asyncio.get_running_loop()
    queue = asyncio.Queue()
    streamed = False

    def emit(token):
        loop.call_soon_threadsafe(queue.put_nowait, ("token", token))

    async def run():
        try:
            result = await asyncio.to_thread(
                rag_pipeline_result, user_message, chat=chat,
                category_filter=category_filter, on_token=emit,
            )
            await queue.put(("result", result))
        except Exception as exc:
            await queue.put(("error", exc))

    if user_message.strip().lower() == "оператор":
        yield LLMNeedOperatorEvent(user_query=user_message, data='Запрос был передан оператору')
        return
    worker = asyncio.create_task(run())
    try:
        while True:
            kind, value = await queue.get()
            if kind == "token":
                streamed = True
                yield LLMTokenEvent(data=value)
                continue
            if kind == "error":
                raise value
            result = value
            logger.info("[RAG RESULT] event=%s answer_chars=%s",
                        result.get("event", "token+done"), len(result.get("answer", "")))
            if result.get("event") == "block":
                yield LLMBlockEvent(data=result["answer"])
            elif result.get("event") == "off-topic":
                yield LLMOffTopicEvent(data=result["answer"])
            else:
                if not streamed:
                    yield LLMTokenEvent(data=result["answer"])
                yield LLMDoneEvent(answer=result["answer"])
            return
    except Exception:
        logger.exception("RAG pipeline failed")
        yield LLMErrorEvent(data="Не удалось обработать запрос. Попробуйте позже.")
    finally:
        worker.cancel()
