import os
from pathlib import Path

# Базовые пути
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DATASET_DIR = BASE_DIR / "dataset"
LEG_DIR = DATASET_DIR / "1_legislation"
INST_DIR = DATASET_DIR / "2_instructions"
INST_KB_DIR = INST_DIR / "roseltorg_kb_articles"
INST_OFFICIAL_DIR = INST_DIR / "roseltorg_official_docs"
PDF_CACHE_DIR = BASE_DIR / "pdf_cache"
MEDIA_DIR = BASE_DIR / "media" / "kb_images"
QDRANT_STORAGE_DIR = BASE_DIR / "qdrant_storage"

os.makedirs(MEDIA_DIR, exist_ok=True)
os.makedirs(QDRANT_STORAGE_DIR, exist_ok=True)

# Настройки модели эмбеддингов
EMBEDDING_MODEL_NAME = "ai-forever/ru-en-RoSBERTa"
EMBEDDING_DIM = 1024
BATCH_SIZE = 32  # Размер батча для векторизации

# Настройки чанкинга
CHUNK_SIZE = 750  # Оптимальный размер чанка (символов)
CHUNK_OVERLAP = 120  # Перекрытие между чанками (символов)

# Настройки Qdrant
COLLECTION_NAME = "data_files"
QDRANT_HOST = "localhost"
QDRANT_PORT = 6333

# Ключевые слова для вторичной классификации категорий
CATEGORY_KEYWORDS = {
    "ecp_mchd": [
        "криптопро", "cryptopro", "эцп", "электронная подпись", "сертификат", "рутокен", 
        "rutoken", "токен", "мчд", "доверенность", "плагин", "браузер", "кэп", "укэп", 
        "джакарта", "jacarta", "драйвер"
    ],
    "44fz": [
        "44-фз", "44 фз", "44fz", "госзакупки", "государственный контракт", "нмцк",
        "реестр контрактов", "закупка с полки", "есклп", "нацрежим", "аукцион в электронной форме"
    ],
    "223fz": [
        "223-фз", "223 фз", "223fz", "корпоративные закупки", "корп", "росатом",
        "интер рао", "россети", "русгидро", "ростех", "план закупки", "субъекты мсп"
    ],
    "registration": [
        "регистрация", "аккредитация", "еруз", "еис", "госуслуги", "есиа",
        "личный кабинет", "росэлторг.id", "росэлторгид", "росэлторг id", "авторизация", "вход"
    ],
    "services": [
        "банковская гарантия", "независимая гарантия", "спецсчет", "специальный счет",
        "кредит", "факторинг", "страхование", "тариф", "оплата услуг", "финансовый сервис"
    ],
    "trading_sections": [
        "ким", "каталог", "агро", "реализация госимущества", "178-фз", "имущественные торги",
        "земельный", "аренда", "приватизация", "банкрот"
    ]
}
