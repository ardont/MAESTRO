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
        # Назначаем чат на специалиста поддержки (Алгоритм: наименьшая загруженность)
        from django.db.models import Count
        support_agent = User.objects.filter(role="support_staff", is_active=True).annotate(
            active_chats=Count('assigned_chats')
        ).order_by('active_chats').first()
        
        if not support_agent:
            # Фолбэк: если в базе вообще нет операторов, создаем дежурного
            support_agent = User.objects.create(role="support_staff", is_active=True)
            
        chat.assigned_to = support_agent
        chat.save(update_fields=["assigned_to"])

        reply_text = (
            "Перевожу на специалиста."
            if is_operator_requested else
            str(guardrail.get('reply', '')) + "\n\nПеревожу на специалиста."
        )

        bot, _ = User.objects.get_or_create(role="llm_bot", defaults={"is_active": True})
        out_msg = Message.objects.create(
            chat=chat,
            author=bot,
            text=reply_text,
            is_read=True
        )

        logger.info(f"[OPERATOR TRANSFER] Чат {chat.id} переведен на специалиста (User ID: {support_agent.id})")

        return JsonResponse({
            "answer": reply_text,
            "citations": [],
            "images": [],
            "line_info": {
                "line": "OPERATOR",
                "name": "Переведено на дежурного специалиста",
                "badge_color": "#2563eb"
            },
            "assigned_to": str(support_agent.id),
            "ids": {
                "user": str(user.id),
                "chat": str(chat.id),
                "question_message": str(in_msg.id),
                "answer_message": str(out_msg.id),
            }
        }, status=200)

    # 4. СТАНДАРТНЫЙ RAG ЗАПРОС
    line_info = route_support_line(question)

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

        return JsonResponse({
            "answer": answer_text,
            "citations": citations,
            "images": images,
            "line_info": line_info,
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
