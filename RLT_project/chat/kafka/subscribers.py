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

@broker.subscriber(llm_request_topic, max_workers=1)
async def llm_request_handler(msg: KafkaMessage):
    try:
        logger.info("SUBSCRIBER START")

        body = msg.body.decode()
        logger.info(f"BODY: {body}")

        msg_event = NewMessageEvent.from_json(body)
        logger.info(f"EVENT: {msg_event}")

        logger.info("CALL HANDLER")

        await new_message_handler(msg_event)

        print("HANDLER FINISHED")

    except Exception:
        logger.exception("Error processing Kafka message")
        raise