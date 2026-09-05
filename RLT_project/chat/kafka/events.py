from datetime import datetime, timezone
from typing import Literal
from uuid import UUID
from enum import Enum

from pydantic import BaseModel, Field

from ..constants import (
    EVENT_NEW_TOKEN,
    EVENT_NEW_MESSAGE,
    EVENT_END_GENERATION,
    EVENT_MESSAGE_RESPONSE,
    EVENT_GENERATION_RESTORE,
    STATUS_OK
)

class Role(str, Enum):
    USER = "user"
    BOT = "bot"
    OPERATOR = "operator"

class EventDataBase(BaseModel):
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )

class EventBase(BaseModel):
    event: str
    data: EventDataBase
    status: str = "OK"
    meta: dict = Field(default_factory=dict)
    def get_event_data(self) -> str:
        return self.event

class NewTokenData(EventDataBase):
    token: str
    chat_id: int
    id: int
    user_uuid: UUID

class EndGenerationData(EventDataBase):
    chat_id: int
    user_uuid: UUID
    details: str
    all_text: str

class NewMessageData(EventDataBase):
    user_uuid: UUID
    chat_id: int
    text: str = Field(min_length=1, max_length=1000)
    answered_to: int | None = None
    role: str = Role.USER.value

# events
class NewTokenEvent(EventBase):
    event: Literal[EVENT_NEW_TOKEN] = EVENT_NEW_TOKEN
    status: Literal[STATUS_OK] = STATUS_OK
    data: NewTokenData

class EndGenerationEvent(EventBase):
    event: Literal[EVENT_END_GENERATION] = EVENT_END_GENERATION
    status: Literal[STATUS_OK] = STATUS_OK
    data: EndGenerationData

class NewMessageEvent(EventBase):
    event: Literal[EVENT_NEW_MESSAGE] = EVENT_NEW_MESSAGE
    status: Literal[STATUS_OK] = STATUS_OK
    data: NewMessageData