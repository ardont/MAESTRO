"""
escalation.py — Агент 3: Диспетчер эскалации и регистрации обращений (Triage & Escalation Agent).

Обязанности:
1. Генерация уникального официального номера обращения (INC-2026-XXXX).
2. Строгое соблюдение регламента 3 линий поддержки:
   - Линия 1 (L1) — Общая поддержка (навигация, регистрация, каталог СТЕ, КС) -> направляем на L1.
   - Линия 2 (L2) — Техническая поддержка (ЭЦП, КриптоПро, УПД, локальные сбои) -> направляем на L2.
   - Линия 3 (L3) — Системные инженеры, разработчики, аварии серверов (ошибка 500), РДИК, ФАС.
     ЖЕСТКОЕ ПРАВИЛО: БОТ НИКОГДА НЕ ОТПРАВЛЯЕТ НАПРЯМУЮ НА L3!
     Все обращения уровня L3 направляются на 2-Ю ЛИНИЮ для верификации и подтверждения необходимости привлечения L3!
3. Формирование исчерпывающей Context Card (чек-листа проверок) для оператора,
   чтобы пользователю не пришлось заново проходить и пересказывать свои действия.
4. Выдача пользователю прозрачного ответа с номером тикета и точным указанием линии.
"""

import time
import random
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger("rag")


def generate_ticket_id(chat_id: Optional[Any] = None) -> str:
    """Генерирует официальный уникальный номер обращения формата INC-2026-XXXX."""
    year = datetime.now().year
    if chat_id:
        # Стабильный суффикс на основе chat_id и времени
        h = abs(hash(str(chat_id))) % 9000 + 1000
    else:
        h = random.randint(1000, 9999)
    return f"INC-{year}-{h}"


def determine_support_line(
    issue_text: str,
    error_code: Optional[str] = None,
    current_line: Optional[str] = None
) -> Dict[str, Any]:
    """
    Определяет линию маршрутизации строго по регламенту:
    - Любые L3-проблемы (ошибка 500, сбой сервера, баги платформы, РДИК, ФАС)
      направляются на L2 с пометкой о подтверждении для L3.
    """
    text_lower = issue_text.lower()
    
    is_server_or_l3 = (
        "500" in text_lower or
        "internal server error" in text_lower or
        "сбой сервера" in text_lower or
        "сервер недоступен" in text_lower or
        "рдик" in text_lower or
        "интеграционн" in text_lower or
        "фас" in text_lower or
        "разработчик" in text_lower or
        (error_code and ("500" in str(error_code) or "РДИК" in str(error_code).upper())) or
        current_line == "L3"
    )
    
    is_l2 = (
        is_server_or_l3 or
        "эцп" in text_lower or
        "криптопро" in text_lower or
        "плагин" in text_lower or
        "сертификат" in text_lower or
        "упд" in text_lower or
        "актирован" in text_lower or
        "токен" in text_lower or
        "рутокен" in text_lower or
        "браузер" in text_lower or
        current_line == "L2"
    )
    
    if is_server_or_l3:
        return {
            "routed_line": "L2",
            "routed_line_name": "Линия технической поддержки (с подтверждением для специалистов 3-й линии)",
            "target_specialist": "3-я линия (системные инженеры и разработчики платформы)",
            "needs_l3_confirmation": True,
            "badge_color": "#d97706"
        }
    elif is_l2:
        return {
            "routed_line": "L2",
            "routed_line_name": "Линия технической поддержки (ЭЦП, ПО, УПД)",
            "target_specialist": "2-я линия (технические специалисты)",
            "needs_l3_confirmation": False,
            "badge_color": "#0284c7"
        }
    else:
        return {
            "routed_line": "L1",
            "routed_line_name": "Линия общей поддержки и навигации по Порталу Поставщиков",
            "target_specialist": "1-я линия (консультанты общей поддержки)",
            "needs_l3_confirmation": False,
            "badge_color": "#2563eb"
        }


def format_escalation_reply(
    ticket_id: str,
    line_info: Dict[str, Any],
    checkpoints: List[str],
    reason: str = ""
) -> str:
    """
    Формирует официальный, доброжелательный и исчерпывающий ответ пользователю
    с указанием номера обращения и конкретной линии, куда передан запрос.
    """
    routed_line = line_info["routed_line"]
    needs_l3 = line_info.get("needs_l3_confirmation", False)
    
    if needs_l3:
        routing_desc = (
            "Запрос передан на **2-ю линию технической поддержки** для проверки логов системы "
            "и подтверждения необходимости привлечения **специалистов 3-й линии (системных инженеров и разработчиков платформы)**."
        )
    elif routed_line == "L2":
        routing_desc = (
            "Запрос передан дежурному специалисту **2-й линии технической поддержки** "
            "(вопросы настройки ЭЦП, КриптоПро, работы с УПД и технические ошибки интерфейса)."
        )
    else:
        routing_desc = (
            "Запрос передан дежурному специалисту **1-й линии общей поддержки** "
            "(навигация по Порталу, котировочные сессии, каталог СТЕ, общие регламенты)."
        )
        
    checklist_text = ""
    if checkpoints and any("выполнен" in c or "сбой" in c or "не помогло" in c or "[✗]" in c or "[✓]" in c or "шаг" in c.lower() for c in checkpoints):
        checklist_text = (
            "\n\n📝 **Переданный оператору чек-лист диагностики:**\n" +
            "\n".join([f"• {c}" for c in checkpoints[-4:]]) +
            "\n*Повторно выполнять эти проверки вам не потребуется.*"
        )
        
    reply = (
        f"📋 **Ваше обращение официально зарегистрировано:** `№ {ticket_id}`\n\n"
        f"🎯 **Маршрутизация:** {routing_desc}"
        f"{checklist_text}\n\n"
        f"Специалист поддержки уже видит историю диалога и подключается к решению вопроса. "
        f"Пожалуйста, ожидайте ответа в этом чате."
    )
    return reply


def build_operator_context_card(
    ticket_id: str,
    issue: str,
    line_info: Dict[str, Any],
    checkpoints: List[str],
    error_code: Optional[str] = None
) -> Dict[str, Any]:
    """Формирует структурированную карточку инцидента для интерфейса оператора."""
    return {
        "ticket_id": ticket_id,
        "issue": issue,
        "assigned_line": line_info["routed_line"],
        "assigned_line_name": line_info["routed_line_name"],
        "target_specialist": line_info.get("target_specialist", "Дежурный специалист"),
        "needs_l3_confirmation": line_info.get("needs_l3_confirmation", False),
        "checkpoints": checkpoints if checkpoints else ["Первичное обращение пользователя"],
        "error_code": error_code or "Не обнаружен",
        "created_at": datetime.now().isoformat(),
        "status": "assigned_to_support"
    }
