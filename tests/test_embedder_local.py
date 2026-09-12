"""Verify local loading cannot silently fall back to downloading weights."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rag.indexer.embedder import RoSBERTaEmbedder


class LocalEmbedderTests(unittest.TestCase):
    def test_local_directory_is_passed_to_both_loaders_offline(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            'rag.indexer.embedder.AutoTokenizer.from_pretrained'
        ) as tokenizer, patch('rag.indexer.embedder.AutoModel.from_pretrained') as model:
            RoSBERTaEmbedder(directory)
            expected = str(Path(directory).resolve())
            tokenizer.assert_called_once_with(expected, local_files_only=True)
            model.assert_called_once_with(expected, local_files_only=True)

    def test_missing_local_directory_fails_before_loading(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            'rag.indexer.embedder.AutoTokenizer.from_pretrained'
        ) as tokenizer, patch('rag.indexer.embedder.AutoModel.from_pretrained') as model:
            with self.assertRaisesRegex(FileNotFoundError, 'EMBEDDING_MODEL_HOST_PATH'):
                RoSBERTaEmbedder(str(Path(directory) / 'missing'))
            tokenizer.assert_not_called()
            model.assert_not_called()
