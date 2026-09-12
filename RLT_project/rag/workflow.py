"""Shared workflow routing for HTTP and Kafka conversations."""
import re
from .graph_rag import PROCUREMENT_KNOWLEDGE_GRAPH, get_workflow_step_response, find_graph_node

WORKFLOW_TO_LINE = {
    "ecp_cryptopro": {
        "line": "L2",
        "name": "Линия технической поддержки (ЭЦП, КриптоПро, МЧД, ПО)",
        "badge_color": "#0284c7"
    },
    "quotation_session": {
        "line": "L3",
        "name": "Линия котировочных сессий и мини-аукционов",
        "badge_color": "#eab308"
    },
    "registration_44fz": {
        "line": "L6",
        "name": "Линия регистрации, аккредитации и управления профилем",
        "badge_color": "#14b8a6"
    },
    "contract_execution_upd": {
        "line": "L5",
        "name": "Линия электронного актирования и исполнения контрактов (УПД/ЕИС)",
        "badge_color": "#8b5cf6"
    },
    "fas_complaint_44fz": {
        "line": "L7",
        "name": "Линия правовой экспертизы (44-ФЗ / 223-ФЗ / ФАС)",
        "badge_color": "#7c3aed"
    }
}


def handle_workflow(message, chat):
    if chat is None:
        return None
    command = re.sub(r"[^\w\s]", "", message.lower()).strip()
    command = " ".join(command.split())
    words = command.split()
    if not words:
        return None

    exact_affirmative = {
        "да", "давай", "давайте", "да давай", "да давайте", "хочу", "хочу по шагам",
        "да хочу", "согласен", "помоги", "готов", "конечно", "ага", "по шагам",
        "давай по шагам", "давайте по шагам", "начать", "начнем", "начнём",
        "давай начнем", "давайте начнем", "пройдемся по шагам", "давай пройдемся по шагам",
        "давай пошагово", "пошагово", "пройдемся", "погнали", "поехали", "ок давай",
        "хорошо давай", "давай попробуем", "пройти по шагам", "давай по порядку", "по шагам давай"
    }
    has_step_intent = bool(re.search(r'\b(по\s*шагам|пошагов\w*|пройд[её]м\w*|шаг|шагам)\b', command))
    has_aff_start = bool(re.search(r'^(да|давай|давайте|ок|хорошо|готов|согласен|хочу|начн[её]м|начать|поехали|погнали|помоги)\b', command))
    affirmative = (command in exact_affirmative) or (has_step_intent and len(words) <= 6) or (has_aff_start and len(words) <= 4)

    exact_advance = {
        "далее", "дальше", "готово", "сделал", "сделала", "продолжить", "продолжим",
        "следующий шаг", "сделано", "ок", "следующий", "вперед", "вперёд",
        "давай дальше", "идем дальше", "идём дальше", "понял", "понятно",
        "след шаг", "след", "перейти к следующему", "переходи дальше", "давай следующий"
    }
    has_advance_kw = bool(re.search(r'\b(далее|дальше|готов[оа]?|сделал[оа]?|продолж\w*|следующ\w*|впер[её]д|ид[её]м дальше|поня[лт])\b', command))
    advance = (command in exact_advance) or (has_advance_kw and len(words) <= 5)

    exact_stop = {
        "стоп", "отмена", "отменить", "завершить", "выход", "остановить", "хватит", "выйти", "закончить", "прекратить"
    }
    has_stop_kw = bool(re.search(r'\b(стоп|отмен\w*|заверш\w*|выход\w*|останов\w*|хватит|выйти|законч\w*|прекрат\w*)\b', command))
    stop = (command in exact_stop) or (has_stop_kw and len(words) <= 4)

    cache = chat.context_cache if isinstance(chat.context_cache, dict) else {}
    active = getattr(chat, "active_workflow", None)
    suggested = cache.get("suggested_workflow")

    if not active and not (affirmative and suggested):
        return None

    if active and stop:
        chat.active_workflow = None
        chat.current_step = 0
        cache.pop("suggested_workflow", None)
        chat.context_cache = cache
        if hasattr(chat, "save"):
            chat.save(update_fields=["active_workflow", "current_step", "context_cache"])
        return {
            "answer": "Пошаговый процесс завершён. Если появятся вопросы — я помогу.",
            "citations": [],
            "images": [],
            "line_info": {
                "line": "L1",
                "name": "Линия общей поддержки и навигации по Порталу Поставщиков",
                "badge_color": "#2563eb"
            }
        }

    if active and not (affirmative or advance):
        # Если пользователь задал новый вопрос по совершенно другой теме:
        new_node = find_graph_node(message)
        if new_node and new_node["id"] != active:
            chat.active_workflow = None
            chat.current_step = 0
            cache.pop("suggested_workflow", None)
            chat.context_cache = cache
            if hasattr(chat, "save"):
                chat.save(update_fields=["active_workflow", "current_step", "context_cache"])
            return None
        # Уточняющий вопрос по текущему шагу — используем контекст шага без смены номера шага
        return None

    node_id = active or suggested
    if node_id not in PROCUREMENT_KNOWLEDGE_GRAPH:
        return None

    step = chat.current_step if active else 0
    result = get_workflow_step_response(node_id, step)
    chat.active_workflow = None if result["is_finished"] else node_id
    chat.current_step = result["next_step"]
    if result["is_finished"]:
        cache.pop("suggested_workflow", None)
        chat.context_cache = cache
    if hasattr(chat, "save"):
        chat.save(update_fields=["active_workflow", "current_step", "context_cache"])

    node = PROCUREMENT_KNOWLEDGE_GRAPH.get(node_id, {})
    citations = []
    if node.get("url"):
        citations.append({
            "title": node.get("title", "Официальный регламент"),
            "section": f"Пошаговый регламент (Шаг {result.get('next_step', step + 1)})",
            "url": node.get("url")
        })

    line_info = WORKFLOW_TO_LINE.get(node_id, {
        "line": "L1",
        "name": "Пошаговый интерактивный консультант",
        "badge_color": "#0284c7"
    })

    return {
        "answer": result["reply"],
        "citations": citations,
        "images": [],
        "line_info": line_info,
        "active_workflow": chat.active_workflow,
        "current_step": chat.current_step
    }

