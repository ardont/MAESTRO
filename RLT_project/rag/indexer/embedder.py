"""
embedder.py — Модуль векторизации текстов (превращение текста в числовые векторы).

Зачем нужна векторизация?
  Чтобы искать документы ПО СМЫСЛУ, а не по словам. Например:
  - "как подписать документ" и "ЭЦП для закупок" близки по смыслу → их векторы близки.
  - "как подписать документ" и "как приготовить пирог" далеки → векторы далеки.

Модель: ru-en-RoSBERTa от ai-forever (Сбер)
Размерность: 1024 числа (float32) на каждый текст
Устройство: CUDA (GPU) > MPS (Apple Silicon) > CPU (fallback)
"""

import torch                    # PyTorch — фреймворк для нейросетей
from transformers import AutoTokenizer, AutoModel  # HuggingFace: загрузка BERT-модели
import numpy as np              # NumPy — для работы с числовыми массивами
import warnings
from .config import EMBEDDING_MODEL_NAME  # Имя модели из config.py

# Подавляем предупреждение HuggingFace о неинициализированных весах
# (это нормально для ряда моделей — веса потом загружаются из чекпоинта)
warnings.filterwarnings("ignore", message="Some weights of.*were not initialized")

class RoSBERTaEmbedder:
    """
    Обёртка над моделью ru-en-RoSBERTa.

    При создании:
      - Автоматически определяет лучшее устройство (GPU/CPU)
      - Загружает токенизатор и модель с HuggingFace
      - Переводит модель в режим вывода (eval) — без обучения

    Методы:
      get_embedding()        — один текст → вектор [1024]
      get_embeddings_batch() — список текстов → матрица [N, 1024]
    """

    def __init__(self, model_name: str = EMBEDDING_MODEL_NAME):
        import os
        local_model_path = "/models/ru-en-RoSBERTa"
        if os.path.exists(local_model_path):
            print(f"[EMBEDDER] Найдена локальная модель: {local_model_path}")
            model_name = local_model_path
        # Определяем, на каком устройстве считать:
        # CUDA (GPU NVIDIA) > MPS (GPU Apple M1/M2/M3) > CPU
        if torch.cuda.is_available():
            self.device = torch.device("cuda")
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            self.device = torch.device("mps")
        else:
            self.device = torch.device("cpu")
        print(f"[EMBEDDER] Initializing '{model_name}' on device: {self.device}")

        # Токенизатор: превращает текст в последовательность чисел (token IDs)
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        # Сама BERT-модель: принимает token IDs → возвращает эмбеддинги
        self.model = AutoModel.from_pretrained(model_name)
        self.model.to(self.device)  # Переносим модель на выбранное устройство
        self.model.eval()           # Режим вывода (отключаем dropout и batch normalization)

    def get_embedding(self, text: str) -> np.ndarray:
        """
        Получение нормализованного эмбеддинга для одного текста.

        Процесс:
          Текст → токены → BERT → CLS-вектор → L2-нормализация → numpy float32

        Возвращает: numpy-массив формы (1024,)
        """
        # Пустой текст → нулевой вектор (чтобы не ломать пайплайн)
        if not text:
            return np.zeros(1024, dtype=np.float32)

        # Токенизация: превращаем текст в числовые ID токенов.
        # max_length=512 — ограничение BERT (всё, что длиннее — обрезается)
        inputs = self.tokenizer(
            text,
            padding=True,           # Дополняем короткие тексты нулями
            truncation=True,        # Обрезаем длинные тексты
            return_tensors="pt",    # Возвращаем PyTorch-тензоры
            max_length=512
        ).to(self.device)           # Переносим входные данные на то же устройство, что и модель

        # Пропускаем через BERT без подсчёта градиентов (т.к. не обучаем)
        with torch.no_grad():
            outputs = self.model(**inputs)

        # Извлекаем вектор [CLS]-токена (1-й токен, индекс 0).
        # CLS-токен в BERT агрегирует смысл всего входного текста.
        embedding = outputs.last_hidden_state[:, 0, :]
        # L2-нормализация: приводим вектор к единичной длине.
        # Это нужно для корректного cosine similarity в Qdrant.
        embedding = torch.nn.functional.normalize(embedding, p=2, dim=1)
        # Переносим на CPU, конвертируем в numpy float32
        return embedding.cpu().numpy().flatten().astype(np.float32)

    def get_embeddings_batch(self, texts: list, batch_size: int = 32) -> np.ndarray:
        """
        Пакетная векторизация списка текстов.

        Почему батчами? Потому что обрабатывать 32 текста за раз
        намного быстрее, чем 32 раза по одному.

        Возвращает: numpy-матрицу формы (N, 1024)
        """
        if not texts:
            return np.empty((0, 1024), dtype=np.float32)

        all_embeddings = []

        # Обрабатываем тексты порциями (батчами) для экономии памяти
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]  # Берём срез размером batch_size

            # Токенизация всего батча сразу
            inputs = self.tokenizer(
                batch_texts,
                padding=True,
                truncation=True,
                return_tensors="pt",
                max_length=512
            ).to(self.device)

            with torch.no_grad():
                outputs = self.model(**inputs)

            # CLS-векторы для каждого текста в батче
            embeddings = outputs.last_hidden_state[:, 0, :]
            embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
            all_embeddings.append(embeddings.cpu().numpy().astype(np.float32))

        # Склеиваем все батчи в одну матрицу
        return np.vstack(all_embeddings)

# ─────────────────────────────────────────────
# СИНГЛТОН: один экземпляр эмбеддера на весь процесс
# ─────────────────────────────────────────────
# Модель занимает ~1.3 ГБ памяти, поэтому создаём её один раз
# и переиспользуем во всех модулях через get_embedder().

_global_embedder = None  # Глобальная переменная для хранения единственного экземпляра (Dense)
_global_sparse_embedder = None # Глобальная переменная для Sparse (BM25)

def get_embedder() -> RoSBERTaEmbedder:
    """
    Возвращает единственный экземпляр эмбеддера (Singleton-паттерн).
    При первом вызове создаёт и загружает модель, далее — отдаёт готовый.
    """
    global _global_embedder
    if _global_embedder is None:
        _global_embedder = RoSBERTaEmbedder()
    return _global_embedder

class SparseBM25Embedder:
    """
    Обёртка над разряженными векторами (BM25/SPLADE) через FastEmbed.
    Используется для точного поиска по ключевым словам.
    """
    def __init__(self, model_name: str = "Qdrant/bm25"):
        # lazy import чтобы не грузить библиотеку при старте, если не нужна
        from fastembed import SparseTextEmbedding 
        print(f"[SPARSE EMBEDDER] Initializing '{model_name}'")
        self.model = SparseTextEmbedding(model_name=model_name)
        
    def get_sparse_embedding(self, text: str):
        if not text:
            from qdrant_client.http import models
            return models.SparseVector(indices=[], values=[])
            
        # FastEmbed возвращает генератор, берем первый элемент
        embedding = list(self.model.embed([text]))[0]
        
        from qdrant_client.http import models
        return models.SparseVector(
            indices=embedding.indices.tolist(),
            values=embedding.values.tolist()
        )

    def get_sparse_embeddings_batch(self, texts: list):
        if not texts:
            return []
        embeddings = list(self.model.embed(texts))
        from qdrant_client.http import models
        return [
            models.SparseVector(
                indices=emb.indices.tolist(),
                values=emb.values.tolist()
            ) for emb in embeddings
        ]

def get_sparse_embedder() -> SparseBM25Embedder:
    global _global_sparse_embedder
    if _global_sparse_embedder is None:
        _global_sparse_embedder = SparseBM25Embedder()
    return _global_sparse_embedder
