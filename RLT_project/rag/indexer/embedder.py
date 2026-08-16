import torch
from transformers import AutoTokenizer, AutoModel
import numpy as np
import warnings
from .config import EMBEDDING_MODEL_NAME

warnings.filterwarnings("ignore", message="Some weights of.*were not initialized")

class RoSBERTaEmbedder:
    def __init__(self, model_name: str = EMBEDDING_MODEL_NAME):
        if torch.cuda.is_available():
            self.device = torch.device("cuda")
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            self.device = torch.device("mps")
        else:
            self.device = torch.device("cpu")
        print(f"[EMBEDDER] Initializing '{model_name}' on device: {self.device}")
        
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name, use_safetensors=True)
        self.model.to(self.device)
        self.model.eval()

    def get_embedding(self, text: str) -> np.ndarray:
        """
        Получение нормализованного эмбеддинга для одного текста (1024d)
        """
        if not text:
            return np.zeros(1024, dtype=np.float32)
            
        inputs = self.tokenizer(
            text,
            padding=True,
            truncation=True,
            return_tensors="pt",
            max_length=512
        ).to(self.device)
        
        with torch.no_grad():
            outputs = self.model(**inputs)
            
        # CLS токен
        embedding = outputs.last_hidden_state[:, 0, :]
        embedding = torch.nn.functional.normalize(embedding, p=2, dim=1)
        return embedding.cpu().numpy().flatten().astype(np.float32)

    def get_embeddings_batch(self, texts: list, batch_size: int = 32) -> np.ndarray:
        """
        Пакетная векторизация списка текстов с ускорением через батчинг
        """
        if not texts:
            return np.empty((0, 1024), dtype=np.float32)
            
        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]
            
            inputs = self.tokenizer(
                batch_texts,
                padding=True,
                truncation=True,
                return_tensors="pt",
                max_length=512
            ).to(self.device)
            
            with torch.no_grad():
                outputs = self.model(**inputs)
                
            embeddings = outputs.last_hidden_state[:, 0, :]
            embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
            all_embeddings.append(embeddings.cpu().numpy().astype(np.float32))
            
        return np.vstack(all_embeddings)

# Синглтон эмбеддера
_global_embedder = None

def get_embedder() -> RoSBERTaEmbedder:
    global _global_embedder
    if _global_embedder is None:
        _global_embedder = RoSBERTaEmbedder()
    return _global_embedder
