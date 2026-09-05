import os

from faststream import FastStream
from faststream.kafka import KafkaBroker

KAFKA_URL = os.getenv("KAFKA_URL", "kafka:29092")

broker = KafkaBroker(KAFKA_URL)
app = FastStream(broker)

from . import subscribers  # noqa: E402, F401
