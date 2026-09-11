import os
from logging import getLogger

from faststream.kafka import KafkaBroker

from .events import NewMessageEvent, NewTokenEvent, NewTokenData, EndGenerationEvent, EndGenerationData
from rag.stream import (
    stream_local_llm_response,
    LLM_TOKEN_EVENT,
    LLM_DONE_EVENT,
    LLM_ERROR_EVENT, REDIRECTED_TO_OPERATOR,
    LLM_BLOCK_EVENT, LLM_OFF_TOPIC_EVENT,
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

async def publish_error_msg(broker: KafkaBroker, topic: str, new_message: NewMessageEvent, error: str):
    await broker.publish(
        NewTokenEvent(
            data=NewTokenData(
                user_uuid=new_message.data.user_uuid,
                chat_id=new_message.data.chat_id,
                token=error,
                id=0,
            )
        ),
        headers={'event_name': EVENT_NEW_TOKEN},
        topic=LLM_RESPONSE_TOPIC,
        key=new_message.data.chat_id,
    )
    await broker.publish(
        EndGenerationEvent(
            data=EndGenerationData(
                user_uuid=new_message.data.user_uuid,
                chat_id=new_message.data.chat_id,
                details="Error",
                all_text=error,
            ),
            meta={"error": True},
        ),
        headers={'event_name': EVENT_END_GENERATION},
        topic=topic,
        key=new_message.data.chat_id,
    )

async def publish_msg(
        broker: KafkaBroker,
        topic: str,
        new_message: NewMessageEvent,
        message_for_user: str,
        need_to_block_chat: bool = False,
        off_topic_message: bool = False,
) -> None:
    await broker.publish(
        NewTokenEvent(
            data=NewTokenData(
                user_uuid=new_message.data.user_uuid,
                chat_id=new_message.data.chat_id,
                token=message_for_user,
                id=0,
            )
        ),
        headers={'event_name': EVENT_NEW_TOKEN},
        topic=LLM_RESPONSE_TOPIC,
        key=new_message.data.chat_id,
    )
    await broker.publish(
        EndGenerationEvent(
            data=EndGenerationData(
                user_uuid=new_message.data.user_uuid,
                chat_id=new_message.data.chat_id,
                details="Message received",
                all_text=message_for_user,
            ),
            meta={"need_to_block_chat": need_to_block_chat,
                  "off_topic_message": off_topic_message},
        ),
        headers={'event_name': EVENT_END_GENERATION},
        topic=topic,
        key=new_message.data.chat_id,
    )

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
            await publish_error_msg(
                broker=broker,
                topic=LLM_RESPONSE_TOPIC,
                new_message=new_message,
                error="Извините, при обработке вашего запролса произошла ошибка, попробуйте еще раз позднее",
            )
        elif llm_event.event == LLM_BLOCK_EVENT:
            await publish_msg(
                broker=broker,
                topic=LLM_RESPONSE_TOPIC,
                new_message=new_message,
                message_for_user="Вы нарушили правила площадки (использование ненармативной лексики)."
                                 " Впреть соблюдайте прваила."
                                 " Данный чат будет заблокирован."
                                 "Вы можете переформулировать свою проблему и обратится с ней в другом чате.",
                need_to_block_chat=True,
                off_topic_message=False,
            )
        elif llm_event.event == LLM_OFF_TOPIC_EVENT:
            await publish_msg(
                broker=broker,
                topic=LLM_RESPONSE_TOPIC,
                new_message=new_message, # Здравствуйте! Спасибо за обращение.
                message_for_user="Наша платформа работает только с темами по платформе https://zakupki.mos.ru/. "
                                 "Ваш вопрос относится к другой сфере, поэтому мы не сможем вам помочь. "
                                 "Вы можете переформулировать свою проблему и обратится снова.",
                need_to_block_chat=False,
                off_topic_message=True,
            )
        else:
            raise RuntimeError(llm_event.event)