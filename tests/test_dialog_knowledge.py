import json
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
from qdrant_client import QdrantClient, models
from rag.api.dialogs_memory import app
from rag.api.schemas import LLMSaveRequest
from rag import dialog_knowledge as knowledge
from rag.indexer import qdrant_indexer as indexer
from rag.indexer.config import COLLECTION_NAME, EMBEDDING_DIM


def payload(feedback=5):
    dialog = str(uuid4())
    return {'dialog_id': dialog, 'feedback': feedback, 'messages': [
        {'dialog_id': dialog, 'role': 'user', 'text': 'Не работает подпись'},
        {'dialog_id': dialog, 'role': 'support', 'text': 'Обновите плагин и перезапустите браузер'},
    ]}


class DialogKnowledgeTests(unittest.TestCase):
    def test_route_rating_gate_and_validation(self):
        with TestClient(app) as client, patch.object(knowledge, 'summarize_dialog') as summarize:
            for rating in (1, 2, 3, 4):
                response = client.post('/memory', json=payload(rating))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['status'], 'skipped')
            summarize.assert_not_called()
            for invalid in (payload(6), {**payload(), 'messages': []},
                            {**payload(), 'dialog_id': str(uuid4())}):
                self.assertEqual(client.post('/memory', json=invalid).status_code, 422)

    def test_summary_uses_configured_ollama_and_checks_output(self):
        req = LLMSaveRequest.model_validate(payload())
        with patch.object(knowledge.requests, 'post') as post, patch.dict('os.environ', {
            'OLLAMA_HOST': 'http://ollama:11434/', 'OLLAMA_MODEL': 'gpt-oss:20b',
        }):
            post.return_value.json.return_value = {'done': True, 'response': json.dumps({
                'question': 'Не работает подпись', 'solution': 'Обновить плагин и перезапустить браузер',
            })}
            result = knowledge.summarize_dialog(req)
            self.assertIn('плагин', result.solution)
            self.assertEqual(post.call_args.args[0], 'http://ollama:11434/api/generate')
            self.assertEqual(post.call_args.kwargs['json']['model'], 'gpt-oss:20b')
            post.return_value.json.return_value = {'done': True, 'response': '{"skip": true}'}
            self.assertIsNone(knowledge.summarize_dialog(req))
            for output in ('not JSON', '{"question":"", "solution":""}'):
                post.return_value.json.return_value = {'done': True, 'response': output}
                with self.assertRaises(ValueError):
                    knowledge.summarize_dialog(req)

    def test_hybrid_write_replay_and_existing_points_preserved(self):
        client = QdrantClient(':memory:')
        self.addCleanup(client.close)
        indexer.init_collection(client)
        original = {'chunk_id': str(uuid4()), 'doc_id': 'existing', 'title': 'Existing',
                    'text': 'Existing knowledge', 'url': 'https://example.com/knowledge'}
        dense_vector = [1.0] + [0.0] * (EMBEDDING_DIM - 1)
        sparse_vector = models.SparseVector(indices=[1, 7], values=[1.0, 2.0])
        indexer.upsert_chunks_batch(client, [original], [dense_vector], [sparse_vector])
        req = LLMSaveRequest.model_validate(payload())
        with patch.object(knowledge, 'summarize_dialog', return_value=knowledge.DialogSummary(
            question='Не работает подпись', solution='Обновить плагин и перезапустить браузер',
        )), patch('rag.indexer.embedder.get_embedder', return_value=Mock(
            get_embeddings_batch=Mock(return_value=[dense_vector]),
        )), patch('rag.indexer.embedder.get_sparse_embedder', return_value=Mock(
            get_sparse_embeddings_batch=Mock(return_value=[sparse_vector]),
        )), patch.object(indexer, 'get_qdrant_client', return_value=client):
            first = knowledge.save_dialog_knowledge(req)
            second = knowledge.save_dialog_knowledge(req)
        self.assertEqual(first, second)
        self.assertEqual(client.count(COLLECTION_NAME).count, 2)
        record = client.retrieve(COLLECTION_NAME, [first['point_id']], with_vectors=True)[0]
        self.assertEqual(set(record.vector), {'', 'bm25'})
        self.assertEqual(record.payload['feedback'], 5)
        self.assertIn('Рекомендация оператора:', record.payload['text'])
        self.assertEqual(record.payload['dialog_id'], str(req.dialog_id))

    def test_empty_knowledge_skipped_and_outage_not_acknowledged(self):
        with TestClient(app) as client, patch.object(knowledge, 'summarize_dialog', return_value=None):
            self.assertEqual(client.post('/memory', json=payload()).json()['status'], 'skipped')
        with TestClient(app) as client, patch.object(knowledge, 'summarize_dialog', side_effect=RuntimeError('offline')):
            self.assertEqual(client.post('/memory', json=payload()).status_code, 503)
