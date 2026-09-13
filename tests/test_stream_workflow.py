"""Streaming latency and persisted multi-turn workflow regression tests."""
import asyncio
import json
import threading
import unittest
from unittest.mock import Mock, patch
from rag import main_rag
from rag.conversation import load_conversation
from rag.workflow import handle_workflow


class MemoryRedis:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value):
        self.values[key] = value


class WorkflowTests(unittest.TestCase):
    def test_state_survives_reload_and_is_isolated(self):
        redis = MemoryRedis()
        with patch.object(main_rag, 'redis_client', redis):
            chat = load_conversation('user', 42)
            chat.context_cache = {'suggested_workflow': 'registration_44fz'}
            chat.save()
            result = main_rag.rag_pipeline_result('Да, давайте!', chat=chat)
            self.assertIn('Шаг 1 из', result['answer'])
            chat = load_conversation('user', 42)
            self.assertEqual(chat.current_step, 1)
            self.assertIsNone(handle_workflow('Где найти сертификат?', chat))
            self.assertEqual(chat.current_step, 1)
            self.assertIn('Шаг 2 из', handle_workflow('Готово', chat)['answer'])
            self.assertIsNone(handle_workflow('дайте другой ответ', chat))
            self.assertIsNone(load_conversation('other', 42).active_workflow)
            self.assertIsNone(load_conversation('user', 43).active_workflow)
            handle_workflow('Завершить', chat)
            chat = load_conversation('user', 42)
            self.assertIsNone(chat.active_workflow)
            self.assertIsNone(handle_workflow('Да', chat))

    def test_completion_after_last_step(self):
        with patch.object(main_rag, 'redis_client', MemoryRedis()):
            chat = load_conversation('user', 1)
            chat.context_cache = {'suggested_workflow': 'registration_44fz'}
            handle_workflow('Да', chat)
            for _ in range(5):
                result = handle_workflow('Далее', chat)
            self.assertIn('Все шаги', result['answer'])
            self.assertIsNone(chat.active_workflow)

    def test_affirmative_and_advance_variations(self):
        with patch.object(main_rag, 'redis_client', MemoryRedis()):
            phrases = ["давай", "давай по шагам", "давай пройдемся по шагам", "пройдемся по шагам", "давай пошагово", "ок давай"]
            for i, phrase in enumerate(phrases):
                chat = load_conversation('user', 100 + i)
                chat.context_cache = {'suggested_workflow': 'ecp_cryptopro'}
                res = handle_workflow(phrase, chat)
                self.assertIsNotNone(res, f"Failed on phrase: {phrase}")
                self.assertIn("Шаг 1 из", res["answer"])
                self.assertEqual(res["line_info"]["line"], "L2")

            # Test advancing variations
            chat = load_conversation('user', 200)
            chat.active_workflow = 'ecp_cryptopro'
            chat.current_step = 1
            chat.save()
            for advance_cmd in ["давай дальше", "идем дальше", "следующий шаг", "готово", "понял"]:
                res = handle_workflow(advance_cmd, chat)
                self.assertIsNotNone(res, f"Failed on advance cmd: {advance_cmd}")

    def test_topic_switching_clears_active_workflow(self):
        with patch.object(main_rag, 'redis_client', MemoryRedis()):
            chat = load_conversation('user', 300)
            chat.active_workflow = 'ecp_cryptopro'
            chat.current_step = 1
            chat.context_cache = {'suggested_workflow': 'ecp_cryptopro'}
            chat.save()

            # Asking about quotation session should clear the active workflow and return None to let RAG handle it
            res = handle_workflow('Как подать ценовое предложение во время котировочной сессии?', chat)
            self.assertIsNone(res)
            reloaded = load_conversation('user', 300)
            self.assertIsNone(reloaded.active_workflow)
            self.assertEqual(reloaded.current_step, 0)


class StreamingTests(unittest.IsolatedAsyncioTestCase):
    async def test_first_token_arrives_while_ollama_still_generating(self):
        release = threading.Event()
        response = Mock(status_code=200)

        def lines(**kwargs):
            yield json.dumps({'response': 'Первый '}).encode()
            if not release.wait(2):
                raise RuntimeError('Buffered until completion')
            yield json.dumps({'response': 'второй', 'done': True}).encode()

        response.iter_lines.side_effect = lines

        def pipeline(message, chat=None, category_filter=None, on_token=None):
            answer = main_rag._call_local_gpt(message, on_token=on_token)
            return {'answer': answer + '\nИсточник'}

        with patch.object(main_rag.requests, 'post', return_value=response) as post, patch.object(
            main_rag, 'rag_pipeline_result', side_effect=pipeline
        ):
            stream = main_rag.rag_pipeline('question')
            try:
                first = await asyncio.wait_for(anext(stream), 1)
                self.assertEqual(first.data, 'Первый ')
            finally:
                release.set()
            rest = [event async for event in stream]
        self.assertEqual([event.event for event in rest], ['token', 'done'])
        self.assertEqual(rest[-1].answer, 'Первый второй\nИсточник')
        self.assertTrue(post.call_args.kwargs['json']['stream'])
        self.assertTrue(post.call_args.kwargs['stream'])
        response.close.assert_called_once()

    async def test_broken_stream_is_error_not_success(self):
        response = Mock(status_code=200)
        response.iter_lines.return_value = [b'{"response":"partial"}']
        def pipeline(message, **kwargs):
            return {'answer': main_rag._call_local_gpt(message, on_token=kwargs['on_token'])}
        with patch.object(main_rag.requests, 'post', return_value=response), patch.object(
            main_rag, 'rag_pipeline_result', side_effect=pipeline
        ):
            events = [event async for event in main_rag.rag_pipeline('question')]
        self.assertEqual([event.event for event in events], ['token', 'error'])

class WorkflowPipelineTests(unittest.TestCase):
    def test_offer_acceptance_and_clarification_use_same_workflow(self):
        import sys
        import types
        from rag.graph_rag import PROCUREMENT_KNOWLEDGE_GRAPH
        search = types.ModuleType('rag.search')
        search.search_hybrid = Mock(return_value=[])
        node = PROCUREMENT_KNOWLEDGE_GRAPH['registration_44fz']
        answer = 'Для регистрации выполните действия из официальной инструкции.'
        with patch.object(main_rag, 'redis_client', MemoryRedis()), patch.dict(
            sys.modules, {'rag.search': search}
        ), patch.object(main_rag, 'normalise_query', side_effect=lambda text, _: text), patch.object(
            main_rag, 'find_graph_node', return_value=node
        ), patch.object(main_rag, '_call_local_gpt', side_effect=['ON_TOPIC', answer]) as llm:
            chat = load_conversation('user', 1)
            result = main_rag.rag_pipeline_result('Регистрация в ЕРУЗ', chat=chat)
            self.assertIn('по шагам', result['answer'])
            chat = load_conversation('user', 1)
            accepted = main_rag.rag_pipeline_result('Да', chat=chat)
            self.assertIn('Шаг 1 из', accepted['answer'])
            self.assertEqual(llm.call_count, 2)  # Acceptance never invokes the LLM.
            llm.side_effect = ['ON_TOPIC', answer]
            main_rag.rag_pipeline_result('Где получить сертификат?', chat=chat)
            self.assertIn('текущий шаг 1', llm.call_args.args[0])
            self.assertEqual(load_conversation('user', 1).current_step, 1)
