from pathlib import Path
from dotenv import load_dotenv
import os

from faststream.kafka import KafkaBroker

KAFKA_URL = os.getenv("KAFKA_URL")

broker = KafkaBroker(KAFKA_URL)