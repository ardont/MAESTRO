"""Contract tests; no running Kafka, Ollama, Redis, Qdrant or Django required.

Run: PYTHONPATH=RLT_project .venv/bin/python -m unittest discover -s tests -v
"""
import asyncio
import importlib
import os
import sys
import threading
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from rag import main_rag
from rag.events import LLMTokenEvent, LLMDoneEvent, LLMBlockEvent, LLMOffTopicEvent


class OllamaModelTests(unittest.TestCase):
    def test_requests_use_configured_model_without_autodiscovery(self):
        for configured, expected in [(None, 'gpt-oss:20b'), ('gpt-oss:20b', 'gpt-oss:20b'),
                                     ('custom:latest', 'custom:latest')]:
            env = {} if configured is None else {'OLLAMA_MODEL': configured}
            with self.subTest(configured=configured), patch.dict(os.environ, env, clear=True), patch.object(
                main_rag.requests, 'get'
            ) as get, patch.object(main_rag.requests, 'post') as post:
                post.return_value.status_code = 200
                post.return_value.json.return_value = {'response': 'ON_TOPIC'}
                self.assertEqual(main_rag._call_local_gpt('test prompt'), 'ON_TOPIC')
                self.assertEqual(post.call_args.kwargs['json']['model'], expected)
                get.assert_not_called()

    def test_missing_model_logs_error_without_switching_model(self):
        with patch.dict(os.environ, {'OLLAMA_MODEL': 'gpt-oss:20b'}), patch.object(
            main_rag.requests, 'post'
        ) as post, self.assertLogs('rag', level='WARNING') as logs:
            post.return_value.status_code = 404
            post.return_value.text = 'model not found'
            self.assertEqual(main_rag._call_local_gpt('test prompt'), '')
        self.assertEqual(post.call_count, 1)
        self.assertIn('model=gpt-oss:20b status=404', '\n'.join(logs.output))


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.search = Mock(return_value=[])
        search_module = types.ModuleType('rag.search')
        search_module.search_hybrid = self.search
        self.patches = [
            patch.dict(sys.modules, {'rag.search': search_module}),
            patch.object(main_rag, 'redis_client', None),
            patch.object(main_rag, 'normalise_query', side_effect=lambda text, _: text),
            patch.object(main_rag, 'find_graph_node', return_value=None),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    async def collect(self, text):
        return [event async for event in main_rag.rag_pipeline(text)]

    async def test_profanity_precedes_llm_and_search(self):
        with patch.object(main_rag, '_call_local_gpt') as llm:
            events = await self.collect('хуй')
        self.assertEqual([e.event for e in events], ['block'])
        self.assertTrue(events[0].data)
        llm.assert_not_called()
        self.search.assert_not_called()

    async def test_off_topic_is_terminal_before_search(self):
        with patch.object(main_rag, '_call_local_gpt', return_value='OFF_TOPIC'), self.assertLogs('rag', level='INFO') as logs:
            events = await self.collect('Как приготовить борщ?')
        self.assertEqual([e.event for e in events], ['off-topic'])
        self.search.assert_not_called()
        self.assertTrue(any('[RAG START]' in line for line in logs.output))
        self.assertTrue(any("verdict='OFF_TOPIC'" in line for line in logs.output))
        self.assertTrue(any('event=off-topic' in line for line in logs.output))

    async def test_invalid_classifier_response_continues_search(self):
        for verdict in ['', 'Ответ: OFF_TOPIC']:
            with self.subTest(verdict=verdict), patch.object(main_rag, '_call_local_gpt', return_value=verdict):
                events = await self.collect('Как зарегистрироваться?')
            self.assertEqual([e.event for e in events], ['token', 'done'])
        self.assertEqual(self.search.call_count, 2)

    async def test_missing_context_is_not_off_topic(self):
        with patch.object(main_rag, '_call_local_gpt', return_value='ON_TOPIC'):
            events = await self.collect('Как зарегистрироваться?')
        self.assertEqual([e.event for e in events], ['token', 'done'])
        self.assertIn('службы поддержки', events[0].data)

    async def test_generation_and_fallback_are_sanitized(self):
        self.search.return_value = [types.SimpleNamespace(payload={
            'title': 'Регистрация', 'url': 'https://zakupki.mos.ru/knowledgebase/main',
            'text': 'Откройте личный кабинет и заполните форму регистрации.',
        })]
        for answer in ['', 'Для регистрации откройте [форму](https://example.com/unsafe).']:
            with self.subTest(answer=answer), patch.object(
                main_rag, '_call_local_gpt', side_effect=['ON_TOPIC', answer]
            ):
                events = await self.collect('Регистрация на портале')
            self.assertEqual([e.event for e in events], ['token', 'done'])
            self.assertIn('Источник:', events[0].data)
            self.assertNotIn('example.com', events[0].data)
            self.assertNotIn('Хотите я помогу', events[0].data)

    async def test_cache_hit_and_category_isolation(self):
        cache = Mock()
        cache.get.return_value = b'{"answer":"cached", "citations":[], "images":[]}'
        with patch.object(main_rag, 'redis_client', cache), patch.object(
            main_rag, '_call_local_gpt', return_value='ON_TOPIC'
        ):
            for category in ['first', 'second']:
                events = [e async for e in main_rag.rag_pipeline('Вопрос', category_filter=category)]
                self.assertEqual([e.event for e in events], ['token', 'done'])
                self.assertEqual(events[0].data, 'cached')
        self.assertNotEqual(cache.get.call_args_list[0], cache.get.call_args_list[1])
        self.search.assert_not_called()

    async def test_failure_becomes_one_error(self):
        with patch.object(main_rag, 'rag_pipeline_result', side_effect=RuntimeError('failure')):
            events = await self.collect('Вопрос')
        self.assertEqual([e.event for e in events], ['error'])

    async def test_worker_does_not_block_loop(self):
        started, release = threading.Event(), threading.Event()
        def work(*args, **kwargs):
            started.set()
            if not release.wait(2):
                raise RuntimeError('event loop blocked')
            return {'answer': 'OK'}
        with patch.object(main_rag, 'rag_pipeline_result', side_effect=work):
            task = asyncio.create_task(self.collect('Вопрос'))
            try:
                for _ in range(100):
                    if started.is_set():
                        break
                    await asyncio.sleep(.01)
                self.assertTrue(started.is_set())
            finally:
                release.set()
            self.assertEqual([e.event for e in await task], ['token', 'done'])


class KafkaTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        broker_module = types.ModuleType('chat.kafka.broker')
        broker_module.broker = types.SimpleNamespace(publish=AsyncMock())
        with patch.dict(sys.modules, {'chat.kafka.broker': broker_module}), patch.dict(
            os.environ, {'LLM_RESPONSE_TOPIC': 'test-responses'}
        ):
            cls.handlers = importlib.import_module('chat.kafka.handlers')
        from chat.kafka.events import NewMessageEvent, NewMessageData
        cls.message = NewMessageEvent(data=NewMessageData(
            user_uuid=uuid4(), chat_id=42, text='Вопрос',
        ))

    def setUp(self):
        loader = patch.object(self.handlers, 'load_conversation', return_value=None)
        loader.start()
        self.addCleanup(loader.stop)

    async def test_all_terminal_events_publish_once(self):
        from rag.events import LLMErrorEvent
        cases = [
            ([LLMTokenEvent(data='A'), LLMTokenEvent(data='B'), LLMDoneEvent()], {}, 'AB', 3),
            ([LLMTokenEvent(data='draft'), LLMDoneEvent(answer='Final with source')], {}, 'Final with source', 2),
            ([LLMBlockEvent(data='Blocked'), LLMDoneEvent()],
             {'need_to_block_chat': True, 'off_topic_message': False, 'need_to_call_support': False, 'user_query': None}, 'Blocked', 2),
            ([LLMOffTopicEvent(data='Off topic'), LLMDoneEvent()],
             {'need_to_block_chat': False, 'off_topic_message': True, 'need_to_call_support': False, 'user_query': None}, 'Off topic', 2),
            ([LLMErrorEvent(data='internal'), LLMDoneEvent()], {'error': True}, None, 2),
            ([LLMDoneEvent(redirected_to='operator')], {'need_to_call_support': True}, None, 1),
        ]
        for events, meta, full_text, count in cases:
            with self.subTest(events=events):
                async def generate(prompt, chat=None):
                    self.assertEqual(prompt, self.message.data.text)
                    for event in events:
                        yield event
                publish = AsyncMock()
                with patch.object(self.handlers, 'rag_pipeline', generate), patch.object(
                    self.handlers.broker, 'publish', publish
                ):
                    await self.handlers.new_message_handler(self.message)
                calls = publish.call_args_list
                self.assertEqual(len(calls), count)
                end = calls[-1].args[0]
                self.assertEqual(end.event, 'END_GENERATION')
                self.assertEqual(end.meta, meta)
                if full_text is not None:
                    self.assertEqual(end.data.all_text, full_text)
                for i, call in enumerate(calls):
                    event = call.args[0]
                    self.assertEqual(event.data.chat_id, 42)
                    self.assertEqual(event.data.user_uuid, self.message.data.user_uuid)
                    self.assertEqual(call.kwargs['key'], 42)
                    self.assertEqual(call.kwargs['topic'], 'test-responses')
                    self.assertEqual(call.kwargs['headers']['event_name'], event.event)
                    if event.event == 'NEW_TOKEN':
                        self.assertEqual(event.data.id, i)
                    event.model_dump_json()  # Must be serializable for Kafka.

    async def test_real_pipeline_to_handler(self):
        publish = AsyncMock()
        with patch.object(main_rag, '_call_local_gpt', return_value='OFF_TOPIC'), patch.object(
            self.handlers.broker, 'publish', publish
        ):
            await self.handlers.new_message_handler(self.message)
        self.assertEqual(publish.call_count, 2)
        self.assertTrue(publish.call_args.args[0].meta['off_topic_message'])

    async def test_workflow_escalation_calls_support_and_preserves_reply(self):
        from rag.conversation import Conversation
        from rag.escalation import format_escalation_reply
        from rag import workflow

        for node in ['registration_44fz', 'ecp_cryptopro', 'system_error_troubleshooting']:
            with self.subTest(node=node):
                chat = Conversation(id='42', client=Mock(), key='test',
                                    active_workflow=node, current_step=1)
                message = self.message.model_copy(update={
                    'data': self.message.data.model_copy(update={'text': 'не помогло'}),
                })
                publish = AsyncMock()
                with patch.object(self.handlers, 'load_conversation', return_value=chat), \
                     patch.object(self.handlers.broker, 'publish', publish), \
                     patch.object(workflow, 'format_escalation_reply', wraps=format_escalation_reply) as formatter, \
                     patch.object(main_rag, '_call_local_gpt') as llm:
                    await self.handlers.new_message_handler(message)
                llm.assert_not_called()
                formatter.assert_called_once()
                expected = format_escalation_reply(*formatter.call_args.args, **formatter.call_args.kwargs)
                self.assertEqual(publish.call_count, 2)
                token, end = [call.args[0] for call in publish.call_args_list]
                self.assertEqual(token.event, 'NEW_TOKEN')
                self.assertEqual(token.data.token, expected)
                self.assertEqual(end.event, 'END_GENERATION')
                self.assertEqual(end.data.all_text, expected)
                self.assertIs(end.meta['need_to_call_support'], True)
                self.assertEqual(end.meta['user_query'], message.data.text)
                self.assertFalse(end.meta['need_to_block_chat'])
                self.assertFalse(end.meta['off_topic_message'])
                self.assertIsNone(chat.active_workflow)
                for call in publish.call_args_list:
                    self.assertEqual(call.kwargs['headers']['event_name'], call.args[0].event)
                    self.assertEqual(call.kwargs['key'], 42)
                    self.assertEqual(call.args[0].data.user_uuid, message.data.user_uuid)
                    call.args[0].model_dump_json()

    async def test_real_profanity_pipeline_to_handler(self):
        message = self.message.model_copy(update={
            'data': self.message.data.model_copy(update={'text': 'хуй'}),
        })
        publish = AsyncMock()
        with patch.object(main_rag, '_call_local_gpt') as llm, patch.object(
            self.handlers.broker, 'publish', publish
        ):
            await self.handlers.new_message_handler(message)
        llm.assert_not_called()
        self.assertEqual(publish.call_count, 2)
        self.assertEqual(publish.call_args.args[0].meta, {
            'need_to_block_chat': True, 'off_topic_message': False,
            'need_to_call_support': False, 'user_query': None,
        })
