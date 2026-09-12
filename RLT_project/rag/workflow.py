"""Shared workflow routing for HTTP and Kafka conversations."""
import re
from .graph_rag import PROCUREMENT_KNOWLEDGE_GRAPH, get_workflow_step_response


def handle_workflow(message, chat):
    if chat is None:
        return None
    command = re.sub(r"[^\w\s]", "", message.lower()).strip()
    command = " ".join(command.split())
    affirmative = command in {
        "да", "давай", "давайте", "да давай", "да давайте", "хочу", "хочу по шагам",
        "да хочу", "согласен", "помоги", "готов", "конечно", "ага", "по шагам", "давай по шагам", "давайте по шагам", "начать", "начнем", "начнём",
    }
    advance = command in {"далее", "дальше", "готово", "сделал", "сделала", "продолжить", "продолжим", "следующий шаг", "сделано", "ок", "следующий", "вперед", "вперёд"}
    stop = command in {"стоп", "отмена", "отменить", "завершить", "выход", "остановить", "хватит", "выйти", "закончить"}
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
        chat.save(update_fields=["active_workflow", "current_step", "context_cache"])
        return {"answer": "Пошаговый процесс завершён. Если появятся вопросы — я помогу.", "citations": [], "images": []}
    if active and not (affirmative or advance):
        # Clarifying questions use the retained context without advancing the step.
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
    chat.save(update_fields=["active_workflow", "current_step", "context_cache"])
    return {"answer": result["reply"], "citations": [], "images": [],
            "active_workflow": chat.active_workflow, "current_step": chat.current_step}
