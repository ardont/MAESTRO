import os
from logging import getLogger

from .events import NewMessageEvent, NewTokenEvent, NewTokenData, EndGenerationEvent, EndGenerationData
from rag.stream import (
    stream_local_llm_response,
    LLM_TOKEN_EVENT,
    LLM_DONE_EVENT,
    LLM_ERROR_EVENT, REDIRECTED_TO_OPERATOR,
)
from ..constants import (
    EVENT_NEW_TOKEN,
    EVENT_END_GENERATION
)

from .broker import broker

logger = getLogger(__name__)

LLM_RESPONSE_TOPIC = os.getenv("LLM_RESPONSE_TOPIC")
if LLM_RESPONSE_TOPIC is None:
    raise ValueError("LLM_RESPONSE_TOPIC is required")

async def new_message_handler(
        new_message: NewMessageEvent,
):
    prompt = new_message.data.text
    full_msg = ''
    token_id = 0
    logger.info(f"New message: {prompt}; chat_id: {new_message.data.chat_id}")
    async for llm_event in stream_local_llm_response(prompt):
        if llm_event.event == LLM_TOKEN_EVENT:
            logger.info(
                "Kafka publish: key=%r (%s), headers=%r, event=%r (%s)",
                new_message.data.chat_id,
                type(new_message.data.chat_id),
                {"event_name": EVENT_NEW_TOKEN},
                llm_event.data,
                type(llm_event.data),
            )
            await broker.publish(
                NewTokenEvent(
                    data=NewTokenData(
                        user_uuid=new_message.data.user_uuid,
                        chat_id=new_message.data.chat_id,
                        token=llm_event.data,
                        id=token_id,
                    )
                ),
                headers={'event_name': EVENT_NEW_TOKEN},
                topic=LLM_RESPONSE_TOPIC,
                key=new_message.data.chat_id,
            )
            token_id += 1
            full_msg += llm_event.data
        elif llm_event.event == LLM_DONE_EVENT:
            logger.info(
                "PUBLISH END_GENERATION pid=%s chat_id=%s",
                os.getpid(),
                new_message.data.chat_id,
            )
            if llm_event.redirected_to == REDIRECTED_TO_OPERATOR:
                await broker.publish(
                    EndGenerationEvent(
                        data=EndGenerationData(
                            user_uuid=new_message.data.user_uuid,
                            chat_id=new_message.data.chat_id,
                            details="Request was redirected to support",
                            all_text="Извините, быстро найти ответ не вышло."
                                     " Ваш запрос был направлен оператору.",
                        ),
                        meta={"need_to_call_support": True},
                    ),
                    headers={'event_name': EVENT_END_GENERATION},
                    topic=LLM_RESPONSE_TOPIC,
                    key=new_message.data.chat_id,
                )

            else:
                await broker.publish(
                EndGenerationEvent(
                    data=EndGenerationData(
                        user_uuid=new_message.data.user_uuid,
                        chat_id=new_message.data.chat_id,
                        details="Done",
                        all_text=full_msg,
                    )
                ),
                headers={'event_name': EVENT_END_GENERATION},
                topic=LLM_RESPONSE_TOPIC,
                key=new_message.data.chat_id,
            )
        elif llm_event.event == LLM_ERROR_EVENT:
            await broker.publish(
                EndGenerationEvent(
                    data=EndGenerationData(
                        user_uuid=new_message.data.user_uuid,
                        chat_id=new_message.data.chat_id,
                        details="Error",
                        all_text="При обработке запроса произошла ошибка, попробуйте еще раз"
                    ),
                    meta={"error": True},
                ),
                headers={'event_name': EVENT_END_GENERATION},
                topic=LLM_RESPONSE_TOPIC,
                key=new_message.data.chat_id,
            )
        else:
            raise RuntimeError(llm_event.event)