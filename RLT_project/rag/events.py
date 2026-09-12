"""Transport-independent events produced by the RAG pipeline."""
from abc import ABC
from typing import Literal
from pydantic import BaseModel

class LLMBaseEvent(BaseModel, ABC):
    event: str

LLM_TOKEN_EVENT = 'token'
class LLMTokenEvent(LLMBaseEvent):
    event: Literal[LLM_TOKEN_EVENT] = LLM_TOKEN_EVENT
    data: str

LLM_DONE_EVENT = 'done'
REDIRECTED_TO_OPERATOR = 'operator'
class LLMDoneEvent(LLMBaseEvent):
    event: Literal[LLM_DONE_EVENT] = LLM_DONE_EVENT
    redirected_to: str | None = None

LLM_ERROR_EVENT = 'error'
class LLMErrorEvent(LLMBaseEvent):
    event: Literal[LLM_ERROR_EVENT] = LLM_ERROR_EVENT
    data: str

LLM_BLOCK_EVENT = 'block'
class LLMBlockEvent(LLMBaseEvent):
    event: Literal[LLM_BLOCK_EVENT] = LLM_BLOCK_EVENT
    data: str

LLM_OFF_TOPIC_EVENT = 'off-topic' # сообщение не по теме
class LLMOffTopicEvent(LLMBaseEvent):
    event: Literal[LLM_OFF_TOPIC_EVENT] = LLM_OFF_TOPIC_EVENT
    data: str

LLM_NEED_OPERATOR_EVENT = 'need-operator' # сообщение не по теме
class LLMNeedOperatorEvent(LLMBaseEvent):
    event: Literal[LLM_NEED_OPERATOR_EVENT] = LLM_NEED_OPERATOR_EVENT
    data: str
