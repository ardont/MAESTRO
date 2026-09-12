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

@broker.subscriber(llm_request_topic, group_id="llm-workers", max_workers=2)
async def llm_request_handler(msg: KafkaMessage):
    try:
        logger.info("SUBSCRIBER START")

        body = msg.body.decode()
        logger.info(f"BODY: {body}")

        msg_event = NewMessageEvent.model_validate_json(body)
        logger.info(f"EVENT: {msg_event}")

        logger.info("CALL HANDLER")

        await new_message_handler(msg_event)

        logger.info("HANDLER FINISHED chat_id=%s", msg_event.data.chat_id)

    except Exception:
        logger.exception("Error processing Kafka message")
        raise
