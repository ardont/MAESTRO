
from uuid import uuid4, UUID
from datetime import datetime, UTC
from enum import Enum

from pydantic import BaseModel, Field

class Role(str, Enum):
    user = 'user'
    support = 'support'

class Message(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    dialog_id: UUID
    text: str
    role: Role = Role.user.value
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class LLMSaveRequest(BaseModel):
    messages: list[Message]
    feedback: int
    feedback_text: str | None