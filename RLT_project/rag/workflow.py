"""
workflow.py — Агент 2: Диагност-Проводник (Interactive Walkthrough & Diagnostic Agent).

Обязанности:
1. Интерактивное ведение пользователя по шагам регламентных процедур.
2. Понимание свободного естественного языка (Успех / Сбой / Уточнение / Отказ / Оператор).
3. Ведение живого Чек-листа решения проблемы ([✓] выполнено, [✗] не помогло).
4. При возникновении неустранимого сбоя или исчерпании шагов — автоматический вызов
   Агента 3 (escalation.py) для регистрации обращения и маршрутизации на L1/L2.
"""

import re
import logging
from typing import Dict, Any, List, Optional
from .events import LLM_NEED_OPERATOR_EVENT
from .graph_rag import PROCUREMENT_KNOWLEDGE_GRAPH, get_workflow_step_response, find_graph_node
from .escalation import (
    generate_ticket_id,
    determine_support_line,
    format_escalation_reply,
    build_operator_context_card
)

logger = logging.getLogger("rag")

WORKFLOW_TO_LINE = {
    "ecp_cryptopro": {
        "line": "L2",
        "name": "Линия технической поддержки (ЭЦП, ПО, УПД)",
        "badge_color": "#0284c7"
    },
    "contract_execution_upd": {
        "line": "L2",
        "name": "Линия технической поддержки (ЭЦП, ПО, УПД)",
        "badge_color": "#0284c7"
    },
    "quotation_session": {
        "line": "L1",
        "name": "Линия общей поддержки и навигации по Порталу Поставщиков",
        "badge_color": "#2563eb"
    },
    "registration_portal": {
        "line": "L1",
        "name": "Линия общей поддержки и навигации по Порталу Поставщиков",
        "badge_color": "#2563eb"
    },
    "registration_eruz": {
        "line": "L1",
        "name": "Линия общей поддержки и навигации по Порталу Поставщиков",
        "badge_color": "#2563eb"
    },
    "registration_44fz": {
        "line": "L1",
        "name": "Линия общей поддержки и навигации по Порталу Поставщиков",
        "badge_color": "#2563eb"
    },
    "system_error_troubleshooting": {
        "line": "L2",
        "name": "Линия технической поддержки (с подтверждением для специалистов 3-й линии)",
        "needs_l3_confirmation": True,
        "badge_color": "#d97706"
    },
    "bank_guarantee": {
        "line": "L1",
        "name": "Линия общей поддержки (Финансовые сервисы)",
        "badge_color": "#2563eb"
    },
    "fas_complaint_44fz": {
        "line": "L3",
        "name": "Экспертная линия и интеграции (Инженеры / ФАС)",
        "needs_l3_confirmation": True,
        "badge_color": "#d97706"
    },
    "portal_complaint_arbitration": {
        "line": "L2",
        "name": "Линия технической поддержки (Арбитражная комиссия Портала)",
        "needs_l3_confirmation": True,
        "badge_color": "#0284c7"
    }
}


def classify_workflow_intent(command: str, active: bool = False) -> str:
    """
    Классифицирует реплику пользователя при прохождении пошаговой инструкции:
    - AFFIRMATIVE: согласие начать процесс
    - ADVANCE: успешное выполнение шага, переход далее
    - FAILURE: сбой на шаге, ошибка не устранена, кнопка не найдена
    - CLARIFY: уточняющий вопрос по текущему шагу
    - STOP: отмена / завершение
    - OPERATOR: требование переключить на человека
    """
    c = command.lower().strip()
    words = c.split()
    
    # 1. Запрос оператора / человека
    if re.search(r'\b(оператор|человек|специалист|позови|переведи на|живой)\b', c):
        return "OPERATOR"

    # 2. Остановка / отказ
    if re.search(r'\b(стоп|отмен\w*|заверш\w*|выход\w*|останов\w*|хватит|выйти|законч\w*|прекрат\w*)\b', c):
        if len(words) <= 4:
            return "STOP"

    # 3. Сбой / Проблема на шаге
    failure_patterns = [
        r'\b(не помогл\w*|ошибк\w* остал\w*|вс[её] равно ошибк\w*|пишет 500|пишет ошибк\w*)\b',
        r'\b(выдает ошибк\w*|выда[её]т ту же|нет так\w* кнопк\w*|не нажима\w*|не работа\w*)\b',
        r'\b(не получ\w*|не наш[её]л|не могу найти|завис\w*|страниц\w* недоступн\w*|не открыва\w*)\b',
        r'\b(белый экран|сбой|ничего не изменил\w*|та же проблема|то же самое|вс[её] так же)\b',
        r'\b(500|internal server error|не удалось|не пускает|не грузит)\b'
    ]
    for pat in failure_patterns:
        if re.search(pat, c):
            return "FAILURE"

    # 4. Согласие начать (START / AFFIRMATIVE): давай, по шагам, ок давай, начнем, да, хочу
    if re.search(r'\b(давай|давайте|по\s*шагам|пошагов\w*|пройд[её]м\w*|начн[её]м|начать|погнали|поехали)\b', c) and len(words) <= 6:
        return "AFFIRMATIVE"
    if re.match(r'^(да|готов|согласен|хочу|помоги)\b', c) and len(words) <= 4:
        return "AFFIRMATIVE"

    # 5. Успех / Переход дальше (ADVANCE): далее, дальше, готово, сделал, следующий, ок
    advance_patterns = [
        r'\b(далее|дальше|готов[оа]?|сделал[оа]?|продолж\w*|следующ\w*|впер[её]д|ид[её]м дальше|поня[лт])\b',
        r'^(ок|хорошо|сделано|готово|перешел|перешла|выполнил[а]?|получилось)$'
    ]
    for pat in advance_patterns:
        if re.search(pat, c) and len(words) <= 5:
            return "ADVANCE"
    if re.match(r'^(ок|хорошо)\b', c) and len(words) <= 2:
        return "AFFIRMATIVE" if not active else "ADVANCE"

    # 6. Уточняющий вопрос
    if "?" in c or re.search(r'^(где|как|куда|что|почему|зачем|а если)\b', c):
        return "CLARIFY"

    return "UNKNOWN"


def handle_workflow(message: str, chat: Any) -> Optional[Dict[str, Any]]:
    """
    Главная точка входа Агента 2 (Диагноста-Проводника).
    """
    if chat is None:
        return None

    cleaned_command = re.sub(r"[^\w\s\?]", " ", message.lower()).strip()
    cleaned_command = " ".join(cleaned_command.split())
    if not cleaned_command:
        return None

    cache = chat.context_cache if isinstance(chat.context_cache, dict) else {}
    active = getattr(chat, "active_workflow", None)
    suggested = cache.get("suggested_workflow")
    intent = classify_workflow_intent(message, active=bool(active))

    # Если процесса нет и пользователь не выразил согласие начать предложенный
    if not active and not (intent == "AFFIRMATIVE" and suggested):
        return None

    node_id = active or suggested
    if node_id not in PROCUREMENT_KNOWLEDGE_GRAPH:
        return None

    node = PROCUREMENT_KNOWLEDGE_GRAPH[node_id]
    step = chat.current_step if active else 0
    steps = node.get("workflow_steps", [])
    total_steps = len(steps)
    step_title = steps[step] if step < total_steps else "Шаг регламента"
    wf_info = WORKFLOW_TO_LINE.get(node_id, {
        "line": "L1",
        "name": "Линия общей поддержки",
        "badge_color": "#2563eb"
    })

    checkpoints = cache.get("checkpoints", [])
    if not isinstance(checkpoints, list):
        checkpoints = []

    citations = []
    if node.get("url"):
        citations.append({
            "title": node.get("title", "Официальный регламент"),
            "section": f"Пошаговый регламент (Шаг {step + 1} из {total_steps})",
            "url": node.get("url")
        })

    # ─────────────────────────────────────────────────────────────
    # ВЕТКА 1: Требование оператора или Сбой шага (FAILURE)
    # ─────────────────────────────────────────────────────────────
    if active and (intent in ("FAILURE", "OPERATOR")):
        logger.info(f"[WORKFLOW FAILURE/OPERATOR] Реплика: '{message}' | node={node_id} step={step}")
        fail_note = f"[✗] Шаг {step + 1}: {step_title[:45]}... — сбой/не помогло ({message})"
        if fail_note not in checkpoints:
            checkpoints.append(fail_note)
        cache["checkpoints"] = checkpoints

        ticket_id = generate_ticket_id(getattr(chat, "id", None))
        line_info = determine_support_line(
            issue_text=f"{node.get('title', '')} {message}",
            error_code="500" if "500" in message else None,
            current_line=wf_info.get("line")
        )
        if wf_info.get("needs_l3_confirmation"):
            line_info["needs_l3_confirmation"] = True
            line_info["routed_line"] = "L2"
            line_info["routed_line_name"] = "Линия технической поддержки (с подтверждением для специалистов 3-й линии)"
            line_info["target_specialist"] = "3-я линия (системные инженеры / разработчики платформы)"

        operator_card = build_operator_context_card(
            ticket_id=ticket_id,
            issue=f"Сбой при прохождении пошаговой инструкции: «{node.get('title')}». Проблема: {message}",
            line_info=line_info,
            checkpoints=checkpoints,
            error_code="500" if "500" in message else None
        )

        chat.active_workflow = None
        chat.current_step = 0
        cache.pop("suggested_workflow", None)
        cache["operator_card"] = operator_card
        chat.context_cache = cache

        # Назначаем чат на оператора поддержки
        try:
            from chat.models import User
            support_agent = User.objects.filter(role="support_staff", is_active=True).first()
            if not support_agent:
                support_agent = User.objects.create(role="support_staff", is_active=True)
            chat.assigned_to = support_agent
        except Exception as e:
            logger.warning(f"Не удалось назначить сотрудника: {e}")

        if hasattr(chat, "save"):
            chat.save(update_fields=["active_workflow", "current_step", "context_cache", "assigned_to"])

        reply_text = format_escalation_reply(ticket_id, line_info, checkpoints, reason=message)
        return {
            "event": LLM_NEED_OPERATOR_EVENT,
            "answer": reply_text,
            "citations": citations,
            "images": [],
            "line_info": {
                "line": line_info["routed_line"],
                "name": line_info["routed_line_name"],
                "badge_color": line_info.get("badge_color", "#d97706")
            },
            "operator_card": operator_card,
            "active_workflow": None,
            "current_step": 0
        }

    # ─────────────────────────────────────────────────────────────
    # ВЕТКА 2: Остановка пользователем (STOP)
    # ─────────────────────────────────────────────────────────────
    if active and intent == "STOP":
        chat.active_workflow = None
        chat.current_step = 0
        cache.pop("suggested_workflow", None)
        chat.context_cache = cache
        if hasattr(chat, "save"):
            chat.save(update_fields=["active_workflow", "current_step", "context_cache"])
        return {
            "answer": "Пошаговый процесс завершён. Если появятся вопросы — я всегда готов помочь.",
            "citations": [],
            "images": [],
            "line_info": {
                "line": "L1",
                "name": "Линия общей поддержки и навигации по Порталу Поставщиков",
                "badge_color": "#2563eb"
            },
            "active_workflow": None,
            "current_step": 0
        }

    # ─────────────────────────────────────────────────────────────
    # ВЕТКА 3: Пользователь задал вопрос по совершенно другой теме
    # ─────────────────────────────────────────────────────────────
    if active and intent not in ("AFFIRMATIVE", "ADVANCE"):
        new_node = find_graph_node(message)
        if new_node and new_node["id"] != active:
            logger.info(f"[WORKFLOW SWITCH] Смена темы с {active} на {new_node['id']}")
            chat.active_workflow = None
            chat.current_step = 0
            cache.pop("suggested_workflow", None)
            chat.context_cache = cache
            if hasattr(chat, "save"):
                chat.save(update_fields=["active_workflow", "current_step", "context_cache"])
            return None
        # Уточняющий вопрос по текущему шагу — передаем управление в RAG с контекстом шага
        return None

    # ─────────────────────────────────────────────────────────────
    # ВЕТКА 4: Продвижение по шагам (AFFIRMATIVE или ADVANCE)
    # ─────────────────────────────────────────────────────────────
    result = get_workflow_step_response(node_id, step)
    chat.active_workflow = None if result["is_finished"] else node_id
    chat.current_step = result["next_step"]

    step_note = f"[✓] Шаг {step + 1}: {step_title[:45]}... — выполнено"
    if step_note not in checkpoints and step < total_steps:
        checkpoints.append(step_note)
    cache["checkpoints"] = checkpoints

    if result["is_finished"]:
        cache.pop("suggested_workflow", None)
        checkpoints.append(f"[✓] Процесс «{node.get('title', '')}» успешно завершен пользователем.")

    chat.context_cache = cache
    if hasattr(chat, "save"):
        chat.save(update_fields=["active_workflow", "current_step", "context_cache"])

    line_info = {
        "line": wf_info["line"],
        "name": wf_info["name"],
        "badge_color": wf_info.get("badge_color", "#0284c7")
    }

    return {
        "answer": result["reply"],
        "citations": citations,
        "images": [],
        "line_info": line_info,
        "active_workflow": chat.active_workflow,
        "current_step": chat.current_step
    }
