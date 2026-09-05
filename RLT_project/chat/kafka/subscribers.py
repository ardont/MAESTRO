import os
from logging import getLogger

from faststream.kafka import KafkaMessage

from .broker import broker
from .events import NewMessageEvent
from .handlers import new_message_handler

llm_request_topic = os.environ.get("LLM_REQUEST_TOPIC")
if llm_request_topic is None:
    raise ValueError("LLM_REQUEST_TOPIC is not required")

logger = getLogger(__name__)

@broker.subscribe(topic=llm_request_topic, concurrency=5)
async def llm_request_handler(
    msg: KafkaMessage,
):
    try:
        body = msg.body.decode()
        msg_event = NewMessageEvent.from_json(body)
        await new_message_handler(msg_event)
    except Exception as e:
        logger.error(e)


