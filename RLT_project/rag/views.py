import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.shortcuts import get_object_or_404
from django.db import transaction

from chat.models import User, Message, Chat
from chat.serializers import MessageSerializer
from .main_rag import rag_pipeline_result
from .router import check_guardrails, route_support_line

logger = logging.getLogger("rag")

OPERATOR_TRIGGERS = [
    "позови человека", "нужен человек", "живой человек",
    "позови оператора", "нужен оператор", "соедини с оператором", "переведи на оператора",
    "позови специалиста", "нужен специалист", "соедини со специалистом", "переведи на специалиста",
    "живой сотрудник", "живой специалист", "переведи на человека", "соедини с человеком", "хочу человека",
    "оператор поддержки", "специалист поддержки", "поговорить с человеком", "поговорить с оператором",
    "свяжи с человеком", "свяжи с оператором", "переключи на человека", "переключи на оператора"
]

EXACT_OPERATOR_WORDS = {"оператор", "оператора", "человек", "человека", "специалист", "специалиста"}

@csrf_exempt
@require_http_methods(["POST"])
def api_ask(request):
    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Невалидный JSON"}, status=400)

    question = (data.get("question") or "").strip()
    if not question:
        return JsonResponse({"error": "Пустой вопрос"}, status=400)

    user_id = data.get("user_id")
    chat_id = data.get("chat_id")
    q_lower = question.lower().strip()

    # 1. Загружаем или создаем пользователя и чат (в атомарной транзакции)
    with transaction.atomic():
        if user_id:
            user = get_object_or_404(User, id=user_id)
        else:
            user = User.objects.create(role="customer")

        if chat_id:
            chat = get_object_or_404(Chat, id=chat_id)
        else:
            chat = Chat.objects.create(user=user)

        in_msg = Message.objects.create(
            chat=chat,
            author=user,
            text=question
        )

    # 2. ПРОВЕРКА НА ПЕРЕВОД НА ОПЕРАТОРА (ПРИОРИТЕТ 4: assigned_to)
    is_operator_requested = (q_lower in EXACT_OPERATOR_WORDS) or any(phrase in q_lower for phrase in OPERATOR_TRIGGERS)
    guardrail = check_guardrails(question)
    is_toxic = guardrail.get("is_blocked", False)

    if is_operator_requested or is_toxic:
        # 1. Анализируем контекст диалога для составления Context Card
        cache = chat.context_cache if isinstance(chat.context_cache, dict) else {}
        last_line_info = cache.get("last_line_info") or route_support_line(question)
        
        # Поиск кода ошибки (в текущем сообщении или в истории)
        from .router import extract_error_code
        detected_error = extract_error_code(question)
        if not detected_error:
            for prev_m in chat.messages.filter(author=user).order_by('-created_at')[:5]:
                ec = extract_error_code(prev_m.text)
                if ec:
                    detected_error = ec
                    break

        # Пройденные чекпоинты из workflow
        checkpoints = cache.get("checkpoints", [])
        if not checkpoints:
            checkpoints = ["Первичное обращение пользователя; пошаговый мастер не запускался"]

        # Определение фактической линии (L1, L2 или L3)
        is_l3 = (last_line_info.get("line") == "L3") or bool(detected_error)
        is_l2 = (last_line_info.get("line") == "L2") and not is_l3
        target_line = "L3" if is_l3 else ("L2" if is_l2 else "L1")

        # Формулировка ответа для пользователя в чате (строго по согласованию)
        if is_toxic:
            reply_text = str(guardrail.get('reply', '')) + "\n\nПередаю диалог дежурному оператору службы поддержки..."
        elif is_l3:
            reply_text = (
                "Данное обращение классифицировано как вопрос 3-й линии (системно-техническая экспертиза / разработчики платформы). "
                "Ваша заявка сформирована и направлена на рассмотрение дежурному инженеру. "
                "Специалист 2-й линии уже подключается к чату для уточнения технических деталей и ведения вашего обращения."
            )
        else:
            line_label = "Линии технической поддержки" if is_l2 else "Линии общей поддержки"
            reply_text = (
                f"Передаю ваш диалог дежурному специалисту {line_label}. "
                "Я передал оператору историю нашей беседы и пройденные шаги, чтобы вам не пришлось повторять всё заново. "
                "Специалист уже подключается..."
            )

        # 2. Формируем Context Card для оператора
        orig_issue = question
        if len(question) <= 15:
            prev_user_msgs = chat.messages.filter(author=user).exclude(id=in_msg.id).order_by('-created_at')
            if prev_user_msgs.exists():
                orig_issue = prev_user_msgs.first().text

        operator_card = {
            "issue": orig_issue,
            "line": target_line,
            "line_name": "Экспертная линия и интеграции (Инженеры / ФАС)" if is_l3 else ("Линия технической поддержки" if is_l2 else "Линия общей поддержки"),
            "checkpoints": checkpoints,
            "error_code": detected_error or "Не обнаружен"
        }

        # Сохраняем карточку в кэш контекста чата
        cache["operator_card"] = operator_card
        chat.context_cache = cache

        # Назначаем чат на специалиста поддержки
        from django.db.models import Count
        support_agent = User.objects.filter(role="support_staff", is_active=True).annotate(
            active_chats=Count('assigned_chats')
        ).order_by('active_chats').first()
        
        if not support_agent:
            support_agent = User.objects.create(role="support_staff", is_active=True)
            
        chat.assigned_to = support_agent
        chat.save(update_fields=["assigned_to", "context_cache"])

        bot, _ = User.objects.get_or_create(role="llm_bot", defaults={"is_active": True})
        out_msg = Message.objects.create(
            chat=chat,
            author=bot,
            text=reply_text,
            is_read=True
        )

        logger.info(f"=== [OPERATOR ESCALATION CARD] ===")
        logger.info(f"  Суть проблемы: {operator_card['issue']}")
        logger.info(f"  Линия: {operator_card['line']} ({operator_card['line_name']})")
        logger.info(f"  Чекпоинты: {operator_card['checkpoints']}")
        logger.info(f"  Код ошибки: {operator_card['error_code']}")
        logger.info(f"==================================")
        print(f"[OPERATOR TRANSFER] Чат {chat.id} передан на {operator_card['line']} оператору {support_agent.id}")

        return JsonResponse({
            "answer": reply_text,
            "citations": [],
            "images": [],
            "line_info": {
                "line": target_line,
                "name": operator_card["line_name"],
                "badge_color": "#d97706" if is_l3 else ("#0284c7" if is_l2 else "#2563eb")
            },
            "operator_card": operator_card,
            "assigned_to": str(support_agent.id),
            "ids": {
                "user": str(user.id),
                "chat": str(chat.id),
                "question_message": str(in_msg.id),
                "answer_message": str(out_msg.id),
            }
        }, status=200)


    # 3. ПРОВЕРКА ПОШАГОВОГО WORKFLOW (МГНОВЕННЫЙ ОТВЕТ БЕЗ LLM)
    from .workflow import handle_workflow
    workflow_res = handle_workflow(question, chat)
    if workflow_res is not None:
        answer_text = workflow_res.get("answer", "")
        citations = workflow_res.get("citations", [])
        wf_line_info = workflow_res.get("line_info") or {
            "line": "L1",
            "name": "Пошаговый интерактивный консультант",
            "badge_color": "#0284c7"
        }
        with transaction.atomic():
            bot, _ = User.objects.get_or_create(role="llm_bot", defaults={"is_active": True})
            out_msg = Message.objects.create(
                chat=chat,
                author=bot,
                text=answer_text,
                is_read=True
            )
        return JsonResponse({
            "answer": answer_text,
            "citations": citations,
            "images": [],
            "line_info": wf_line_info,
            "timings": {"search_sec": 0, "llm_sec": 0, "total_sec": 0.001},
            "ids": {
                "user": str(user.id),
                "chat": str(chat.id),
                "question_message": str(in_msg.id),
                "answer_message": str(out_msg.id),
            }
        }, status=200)

    # 4. СТАНДАРТНЫЙ RAG ЗАПРОС
    line_info = route_support_line(question)
    if chat and hasattr(chat, "context_cache"):
        cache = chat.context_cache if isinstance(chat.context_cache, dict) else {}
        cache["last_line_info"] = line_info
        chat.context_cache = cache
        if hasattr(chat, "save"):
            chat.save(update_fields=["context_cache"])

    try:
        rag_res = rag_pipeline_result(
            question,
            chat=chat,
            category_filter=line_info.get("category_filter")
        )
        answer_text = rag_res.get("answer", "")
        citations = rag_res.get("citations", [])
        images = rag_res.get("images", [])

        with transaction.atomic():
            bot, _ = User.objects.get_or_create(role="llm_bot", defaults={"is_active": True})
            out_msg = Message.objects.create(
                chat=chat,
                author=bot,
                text=answer_text,
                is_read=True
            )

        resp_line = rag_res.get("line_info") or line_info
        logger.info(f"[API ASK SUCCESS] chat={chat.id} line={resp_line['line']} citations_count={len(citations)}")
        print(f"[API ASK SUCCESS] Чат {chat.id} отвечен по линии {resp_line['line']} ({resp_line.get('name')})")

        return JsonResponse({
            "answer": answer_text,
            "citations": citations,
            "images": images,
            "line_info": resp_line,
            "timings": rag_res.get("timings", {}),
            "ids": {
                "user": str(user.id),
                "chat": str(chat.id),
                "question_message": str(in_msg.id),
                "answer_message": str(out_msg.id),
            }
        }, status=200)

    except Exception as e:
        logger.exception(f"[API_ASK ERROR] Ошибка обработки запроса: {e}")
        return JsonResponse({"error": str(e)}, status=500)



@csrf_exempt
def feedback_view(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Метод не поддерживается'}, status=405)

    try:
        data = json.loads(request.body)
        fb_type = data.get('type')
        question = data.get('question')
        answer = data.get('answer')

        if fb_type not in ['like', 'dislike']:
            return JsonResponse({'error': 'Некорректный тип оценки'}, status=400)

        with open('feedback_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps({
                'type': fb_type,
                'question': question,
                'answer': answer,
            }, ensure_ascii=False) + '\n')

        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
