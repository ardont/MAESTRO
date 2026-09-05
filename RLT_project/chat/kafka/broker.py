import os
import json

from faststream import FastStream
from faststream.kafka import KafkaBroker

KAFKA_URL = os.getenv("KAFKA_URL", "kafka:29092")


def json_serializer(data) -> bytes:
    return json.dumps(
        data,
        ensure_ascii=False,
    ).encode("utf-8")


def key_serializer(data) -> bytes:
    return str(data).encode("utf-8")


broker = KafkaBroker(
    KAFKA_URL,
    key_serializer=key_serializer,
    value_serializer=json_serializer,
)

app = FastStream(broker)

from . import subscribers  # noqa: E402, F401
