# load_test_data.py

import json
from qdrant_client import QdrantClient
from qdrant_client.http import models
from .embed_query import get_embedding  # твоя функция
import uuid

# === Тестовые документы (Портал поставщиков Москвы) ===
docs = [
  {
    "title": "Регистрация поставщиков на Портале поставщиков Москвы",
    "url": "https://zakupki.mos.ru/knowledgebase/article/details/ais/171501",
    "text": "Регистрация юридических лиц, ИП и самозанятых на Портале поставщиков города Москвы осуществляется через единую систему идентификации ЕСИА (Госуслуги) либо с использованием сертификата усиленной квалифицированной электронной подписи (КЭП). Для участия в закупках малого объема и котировочных сессиях необходимо заполнить профиль организации и подтвердить полномочия."
  },
  {
    "title": "Участие в котировочных сессиях",
    "url": "https://zakupki.mos.ru/knowledgebase/article/details/ais/171505",
    "text": "Котировочная сессия — оперативная закупка товаров, работ и услуг малого объема в электронной форме на Портале поставщиков Москвы. Поставщики подают ценовые предложения на понижение цены в течение установленного времени (3, 6 или 24 часа). Победителем признается участник, предложивший наименьшую цену с соблюдением требований технического задания."
  }
]

# === Подключение к Qdrant ===
client = QdrantClient(host="localhost", port=6333)
collection_name = "docs"

# === Создаем коллекцию (если ещё не создана) ===
client.recreate_collection(
    collection_name=collection_name,
    vectors_config=models.VectorParams(
        size=768,        # размерность эмбеддингов RoSBERTa
        distance=models.Distance.COSINE,
    ),
)

# === Загружаем документы ===
points = []
for doc in docs:
    vector = get_embedding(doc["text"]).tolist()
    point_id = str(uuid.uuid4())  # уникальный id
    points.append(
        models.PointStruct(
            id=point_id,
            vector=vector,
            payload={
                "title": doc["title"],
                "url": doc["url"],
                "text": doc["text"]
            }
        )
    )

# === Отправляем в Qdrant ===
client.upsert(
    collection_name=collection_name,
    wait=True,
    points=points,
)

print(f"✅ Загружено {len(points)} документов в коллекцию '{collection_name}'")
