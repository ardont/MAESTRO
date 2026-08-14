import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.shortcuts import get_object_or_404
from django.db import transaction

from chat.models import User, Message, Chat
from chat.serializers import MessageSerializer
from .main_rag import rag_pipeline
from .router import check_guardrails, route_support_line


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

    # 1) Guardrail: Проверка на токсичность и нецензурную лексику
    guardrail = check_guardrails(question)
    if guardrail.get("is_blocked"):
        return JsonResponse({
            "answer": guardrail.get("reply"),
            "citations": [],
            "images": [],
            "line_info": {
                "line": "BLOCKED",
                "name": "Обращение отклонено системой безопасности",
                "badge_color": "#dc2626"
            },
            "is_blocked": True
        }, status=200)

    # 2) Smart Router: определение линии поддержки L1 / L2 / L3
    line_info = route_support_line(question)

    try:
        with transaction.atomic():
            # 3) Находим / создаем пользователя
            if user_id:
                user = get_object_or_404(User, id=user_id)
            else:
                user = User.objects.create(role="customer")

            # 4) Находим / создаем чат
            if chat_id:
                chat = get_object_or_404(Chat, id=chat_id)
            else:
                chat = Chat.objects.create(user=user)

            # 5) Сохраняем входящее сообщение пользователя
            in_msg_ser = MessageSerializer(data={
                "chat": str(chat.id),
                "author": str(user.id),
                "text": question,
            })
            if not in_msg_ser.is_valid():
                return JsonResponse({"errors": in_msg_ser.errors}, status=400)
            in_msg = in_msg_ser.save()

            # 6) Получаем ответ из RAG пайплайна с учетом категории линии
            rag_res = rag_pipeline(question, category_filter=line_info.get("category_filter"))
            answer_text = rag_res.get("answer", "")
            citations = rag_res.get("citations", [])
            images = rag_res.get("images", [])

            # 7) Создаем сообщение от бота
            bot, _ = User.objects.get_or_create(role="llm_bot", defaults={"is_active": True})
            out_msg_ser = MessageSerializer(data={
                "chat": str(chat.id),
                "author": str(bot.id),
                "text": answer_text,
                "is_read": True,
            })
            if not out_msg_ser.is_valid():
                return JsonResponse({"errors": out_msg_ser.errors}, status=400)
            out_msg = out_msg_ser.save()

        return JsonResponse({
            "answer": answer_text,
            "citations": citations,
            "images": images,
            "line_info": line_info,
            "ids": {
                "user": str(user.id),
                "chat": str(chat.id),
                "question_message": str(in_msg.id),
                "answer_message": str(out_msg.id),
            }
        }, status=200)

    except Exception as e:
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

        # Логирование оценки пользователя
        with open('feedback_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps({
                'type': fb_type,
                'question': question,
                'answer': answer,
            }, ensure_ascii=False) + '\n')

        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
