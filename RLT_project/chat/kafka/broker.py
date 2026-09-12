import os
import json
import logging

from faststream import FastStream
from faststream.kafka import KafkaBroker

KAFKA_URL = os.getenv("KAFKA_URL", "kafka:29092")

# This entry point does not run django.setup() or Django's LOGGING config.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
for name in ("rag", "search", "chat.kafka"):
    logging.getLogger(name).setLevel(logging.INFO)


def serialize_kafka_key(value: object) -> bytes:
    return str(value).encode("utf-8")


broker = KafkaBroker(
    KAFKA_URL,
    key_serializer=serialize_kafka_key,
)

app = FastStream(broker)

from . import subscribers  # noqa: E402, F401
