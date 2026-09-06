import os
import json

from faststream import FastStream
from faststream.kafka import KafkaBroker

KAFKA_URL = os.getenv("KAFKA_URL", "kafka:29092")


def serialize_kafka_key(value: object) -> bytes:
    return str(value).encode("utf-8")


broker = KafkaBroker(
    KAFKA_URL,
    key_serializer=serialize_kafka_key,
)

app = FastStream(broker)

from . import subscribers  # noqa: E402, F401