import re
from typing import Dict, Any

# Регулярные выражения для быстрой фильтрации ненормативной лексики и агрессии (< 5 мс)
TOXICITY_PATTERNS = [
    r"\b(хуй|ху[яеёи]|пизд|бля[тд]|еба[тьнл]|ёб[а-я]|муда[кч]|говн|сук[аи]|ганд|шлюх|уеб)\b",
    r"\b(нахуй|похуй|заеб|доеб|приеб|выеб|отъеб|разъеб)\b"
]
TOXICITY_REGEX = re.compile("|".join(TOXICITY_PATTERNS), re.IGNORECASE)

# Паттерны для классификации линий поддержки
L2_TECH_KEYWORDS = [
    "криптопро", "cryptopro", "эцп", "плагин", "сертификат", "рутокен", "rutoken",
    "токен", "драйвер", "ошибка плагина", "не подписывает", "браузер", "chromium-gost",
    "яндекс браузер", "кэп", "укэп", "мчд", "джакарта", "jacarta", "считыватель",
    "не удается подписать", "ошибка 0x", "ssl", "tls"
]

L3_LEGAL_KEYWORDS = [
    "жалоба в фас", "фас", "рнп", "реестр недобросовестных", "нмцк", "ст 93", "ст 44",
    "статья 93", "статья 44", "отклонили заявку", "отклонение заявки", "протокол разногласий",
    "допсоглашение", "расторжение контракта", "односторонний отказ", "нацрежим",
    "пп 1875", "пп 719", "постановление правительства", "спецсчет", "независимая гарантия",
    "банковская гарантия", "арбитраж", "суд", "44-фз", "223-фз", "615 пп"
]

def check_guardrails(user_message: str) -> Dict[str, Any]:
    """
    Toxicity Gatekeeper: быстрая проверка на нецензурную брань и агрессию
    """
    if TOXICITY_REGEX.search(user_message):
        return {
            "is_blocked": True,
            "reason": "toxicity",
            "reply": "⚠️ Ваше обращение содержит недопустимую лексику. Пожалуйста, переформулируйте ваш вопрос в корректной форме, соблюдая правила делового общения."
        }
    return {"is_blocked": False}

def route_support_line(user_message: str) -> Dict[str, Any]:
    """
    Smart Router: классификация обращения по линиям поддержки L1 / L2 / L3
    """
    msg_lower = user_message.lower()
    
    # 1. Проверка на L2 (Техническая линия: ЭЦП, КриптоПро, плагины)
    l2_score = sum(1 for kw in L2_TECH_KEYWORDS if kw in msg_lower)
    
    # 2. Проверка на L3 (Юридическая / Экспертная линия: споры, ФАС, законы, отклонения)
    l3_score = sum(1 for kw in L3_LEGAL_KEYWORDS if kw in msg_lower)
    
    if l2_score > 0 and l2_score >= l3_score:
        return {
            "line": "L2",
            "name": "Линия технической поддержки (ЭЦП, КриптоПро, ПО)",
            "category_filter": "ecp_mchd",
            "badge_color": "#0284c7"
        }
    elif l3_score > 0:
        return {
            "line": "L3",
            "name": "Линия экспертной правовой поддержки (44-ФЗ / 223-ФЗ)",
            "category_filter": "44fz" if "44" in msg_lower else ("223fz" if "223" in msg_lower else "legislation"),
            "badge_color": "#7c3aed"
        }
    else:
        return {
            "line": "L1",
            "name": "Линия общей поддержки и навигации (FAQ / ЛК)",
            "category_filter": None,
            "badge_color": "#16a34a"
        }
