"""
test_3_agents_architecture.py — Комплексные тесты 3-агентной архитектуры поддержки:
- Агент 1: Инструктор-Аналитик (Grounding, идентичность поддержки, регламентные шаги).
- Агент 2: Диагност-Проводник (интерактивный пошаговый диалог, чек-лист [✓]/[✗], распознавание "не помогло", "ошибка осталась").
- Агент 3: Диспетчер инцидентов и эскалации (генерация № INC-XXXX, строгая маршрутизация L3 -> L2 с подтверждением, Context Card оператора).
"""

import unittest
from unittest.mock import patch
from rag import main_rag
from rag.workflow import handle_workflow, classify_workflow_intent
from rag.escalation import (
    generate_ticket_id,
    determine_support_line,
    format_escalation_reply,
    build_operator_context_card
)


class MemoryRedis:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value):
        self.values[key] = value


class MockChat:
    def __init__(self, chat_id=123):
        self.id = chat_id
        self.context_cache = {}
        self.active_workflow = None
        self.current_step = 0
        self.assigned_to = None

    def save(self, update_fields=None):
        pass


class TestThreeAgentsArchitecture(unittest.TestCase):

    def setUp(self):
        self.chat = MockChat(chat_id=999)

    def test_agent3_ticket_and_strict_l3_routing(self):
        """Агент 3: Проверка генерации тикета и обязательной маршрутизации L3 -> L2 с подтверждением."""
        # 1. Генерация тикета
        ticket = generate_ticket_id(12345)
        self.assertTrue(ticket.startswith("INC-"))
        self.assertIn("2026", ticket)

        # 2. Проблема уровня L3 (ошибка 500 / сервер) ДОЛЖНА маршрутизироваться на L2
        line_500 = determine_support_line("Что делать при ошибке 500 на сервере?")
        self.assertEqual(line_500["routed_line"], "L2", "L3-проблема должна направляться на L2!")
        self.assertTrue(line_500["needs_l3_confirmation"], "Должен быть выставлен флаг подтверждения 3-й линии!")
        self.assertIn("3-я линия", line_500["target_specialist"])

        # 3. Формирование ответа пользователю
        reply = format_escalation_reply(ticket, line_500, ["[✗] Шаг 1: Ошибка 500 сохраняется"])
        self.assertIn(ticket, reply)
        self.assertIn("2-ю линию технической поддержки", reply)
        self.assertIn("специалистов 3-й линии", reply)
        self.assertIn("чек-лист диагностики", reply.lower())

        # 4. Формирование Context Card оператора
        card = build_operator_context_card(
            ticket_id=ticket,
            issue="Ошибка 500 на Портале",
            line_info=line_500,
            checkpoints=["[✗] Шаг 1: Проверка в инкогнито — не помогло"],
            error_code="500"
        )
        self.assertEqual(card["ticket_id"], ticket)
        self.assertEqual(card["assigned_line"], "L2")
        self.assertTrue(card["needs_l3_confirmation"])
        self.assertEqual(len(card["checkpoints"]), 1)

    def test_agent2_intent_classification(self):
        """Агент 2: Проверка распознавания живого языка (Успех / Сбой / Уточнение / Отказ)."""
        # Успех / Продвижение (ADVANCE)
        self.assertEqual(classify_workflow_intent("готово"), "ADVANCE")
        self.assertEqual(classify_workflow_intent("сделал"), "ADVANCE")
        self.assertEqual(classify_workflow_intent("дальше"), "ADVANCE")
        self.assertEqual(classify_workflow_intent("следующий шаг"), "ADVANCE")
        self.assertEqual(classify_workflow_intent("получилось"), "ADVANCE")

        # Сбой / Проблема (FAILURE)
        self.assertEqual(classify_workflow_intent("не помогло"), "FAILURE")
        self.assertEqual(classify_workflow_intent("ошибка осталась"), "FAILURE")
        self.assertEqual(classify_workflow_intent("всё равно пишет 500"), "FAILURE")
        self.assertEqual(classify_workflow_intent("выдает ту же ошибку"), "FAILURE")
        self.assertEqual(classify_workflow_intent("нет такой кнопки"), "FAILURE")
        self.assertEqual(classify_workflow_intent("не работает"), "FAILURE")

        # Согласие начать (AFFIRMATIVE)
        self.assertEqual(classify_workflow_intent("давай"), "AFFIRMATIVE")
        self.assertEqual(classify_workflow_intent("давай по шагам"), "AFFIRMATIVE")
        self.assertEqual(classify_workflow_intent("поехали"), "AFFIRMATIVE")

        # Запрос оператора / человека (OPERATOR)
        self.assertEqual(classify_workflow_intent("позови человека"), "OPERATOR")
        self.assertEqual(classify_workflow_intent("оператор"), "OPERATOR")

    def test_agent2_step_advancement_and_checklist(self):
        """Агент 2: Пошаговое продвижение с сохранением [✓] в чек-лист."""
        self.chat.context_cache = {'suggested_workflow': 'ecp_cryptopro'}
        
        # Шаг 1
        res1 = handle_workflow("Давай", self.chat)
        self.assertIsNotNone(res1)
        self.assertIn("Шаг 1 из", res1["answer"])
        self.assertEqual(self.chat.active_workflow, "ecp_cryptopro")
        self.assertEqual(self.chat.current_step, 1)

        # Шаг 2 (пользователь написал "сделал")
        res2 = handle_workflow("сделал, всё получилось", self.chat)
        self.assertIsNotNone(res2)
        self.assertIn("Шаг 2 из", res2["answer"])
        self.assertEqual(self.chat.current_step, 2)
        
        # Проверяем, что в чек-листе зафиксированы шаги
        checkpoints = self.chat.context_cache.get("checkpoints", [])
        self.assertTrue(any("[✓]" in cp for cp in checkpoints))

    def test_agent2_failure_triggers_agent3_escalation(self):
        """Агент 2 + Агент 3: Если пользователь на шаге сообщает о сбое -> мгновенная эскалация с тикетом."""
        self.chat.active_workflow = "system_error_troubleshooting"
        self.chat.current_step = 1
        self.chat.context_cache = {"suggested_workflow": "system_error_troubleshooting"}

        # Пользователь отвечает нестандартной репликой о сохранении ошибки 500
        res = handle_workflow("попробовал в инкогнито, всё равно пишет 500", self.chat)
        self.assertIsNotNone(res)

        # Проверяем, что сработала эскалация (Агент 3)
        self.assertIn("официально зарегистрировано", res["answer"])
        self.assertIn("INC-2026-", res["answer"])
        self.assertIn("2-ю линию технической поддержки", res["answer"])
        self.assertIn("специалистов 3-й линии", res["answer"])
        
        # Маршрутизация на L2 (не напрямую на L3!)
        self.assertEqual(res["line_info"]["line"], "L2")

        # В карточке оператора зафиксирован чек-лист сбоя
        operator_card = res.get("operator_card")
        self.assertIsNotNone(operator_card)
        self.assertTrue(operator_card["needs_l3_confirmation"])
        self.assertEqual(operator_card["assigned_line"], "L2")
        self.assertTrue(any("[✗]" in cp for cp in operator_card["checkpoints"]))

        # Активный процесс снят, чтобы чат не залипал
        self.assertIsNone(self.chat.active_workflow)


if __name__ == '__main__':
    unittest.main()
