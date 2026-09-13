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
        from .router import extract_error_code
        from .escalation import (
            generate_ticket_id,
            determine_support_line,
            format_escalation_reply,
            build_operator_context_card
        )

        cache = chat.context_cache if isinstance(chat.context_cache, dict) else {}
        last_line_info = cache.get("last_line_info") or route_support_line(question)
        
        # Поиск кода ошибки (в текущем сообщении или в истории)
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

        # Определение линии (L3 перенаправляется на L2 с флагом подтверждения)
        line_info = determine_support_line(
            issue_text=question,
            error_code=detected_error,
            current_line=last_line_info.get("line")
        )

        ticket_id = generate_ticket_id(chat.id)

        # Формулировка ответа для пользователя
        if is_toxic:
            reply_text = str(guardrail.get('reply', '')) + f"\n\nДиалог официально зарегистрирован (`№ {ticket_id}`) и передан дежурному оператору поддержки."
        else:
            reply_text = format_escalation_reply(ticket_id, line_info, checkpoints)

        # Формируем Context Card для оператора
        orig_issue = question
        if len(question) <= 15:
            prev_user_msgs = chat.messages.filter(author=user).exclude(id=in_msg.id).order_by('-created_at')
            if prev_user_msgs.exists():
                orig_issue = prev_user_msgs.first().text

        operator_card = build_operator_context_card(
            ticket_id=ticket_id,
            issue=orig_issue,
            line_info=line_info,
            checkpoints=checkpoints,
            error_code=detected_error
        )

        # Сохраняем карточку в кэш контекста чата
        cache["operator_card"] = operator_card
        chat.context_cache = cache
        chat.active_workflow = None
        chat.current_step = 0

        # Назначаем чат на специалиста поддержки
        from django.db.models import Count
        support_agent = User.objects.filter(role="support_staff", is_active=True).annotate(
            active_chats=Count('assigned_chats')
        ).order_by('active_chats').first()
        
        if not support_agent:
            support_agent = User.objects.create(role="support_staff", is_active=True)
            
        chat.assigned_to = support_agent
        chat.save(update_fields=["assigned_to", "context_cache", "active_workflow", "current_step"])

        bot, _ = User.objects.get_or_create(role="llm_bot", defaults={"is_active": True})
        out_msg = Message.objects.create(
            chat=chat,
            author=bot,
            text=reply_text,
            is_read=True
        )

        logger.info(f"=== [OPERATOR ESCALATION CARD] ===")
        logger.info(f"  Тикет: {operator_card['ticket_id']}")
        logger.info(f"  Суть проблемы: {operator_card['issue']}")
        logger.info(f"  Назначенная линия: {operator_card['assigned_line']} ({operator_card['assigned_line_name']})")
        logger.info(f"  Требует L3: {operator_card['needs_l3_confirmation']}")
        logger.info(f"  Чекпоинты: {operator_card['checkpoints']}")
        logger.info(f"==================================")
        print(f"[OPERATOR TRANSFER] Чат {chat.id} передан на {operator_card['assigned_line']} (Тикет: {ticket_id}) оператору {support_agent.id}")

        return JsonResponse({
            "answer": reply_text,
            "citations": [],
            "images": [],
            "line_info": {
                "line": line_info["routed_line"],
                "name": line_info["routed_line_name"],
                "badge_color": line_info.get("badge_color", "#2563eb")
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
        resp_payload = {
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
        }
        if "operator_card" in workflow_res:
            resp_payload["operator_card"] = workflow_res["operator_card"]
            resp_payload["assigned_to"] = str(chat.assigned_to.id) if chat.assigned_to else None
        return JsonResponse(resp_payload, status=200)

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
