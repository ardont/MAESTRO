"""Registration replies must create a support request on every escalation path."""
import unittest
from unittest.mock import patch
from rag import main_rag


class EscalationDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_and_out_of_knowledge_escalations(self):
        for extra in ({'event': 'need-operator'}, {'operator_card': {'ticket_id': '42'}}):
            with self.subTest(extra=extra), patch.object(main_rag, 'rag_pipeline_result', return_value={
                'answer': '📋 **Ваше обращение официально зарегистрировано:** `№ 42`', **extra
            }):
                events = [event async for event in main_rag.rag_pipeline('Вопрос пользователя')]
                self.assertEqual([event.event for event in events], ['need-operator'])
                self.assertIn('Ваше обращение официально', events[0].data)
                self.assertEqual(events[0].user_query, 'Вопрос пользователя')

    async def test_normal_reply_does_not_request_support(self):
        with patch.object(main_rag, 'rag_pipeline_result', return_value={'answer': 'Инструкция'}):
            events = [event async for event in main_rag.rag_pipeline('Вопрос')]
            self.assertEqual([event.event for event in events], ['token', 'done'])
