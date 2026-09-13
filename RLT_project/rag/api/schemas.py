
from uuid import uuid4, UUID
from datetime import datetime, UTC
from enum import Enum

from pydantic import BaseModel, Field, model_validator

class Role(str, Enum):
    user = 'user'
    support = 'support'

class Message(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    dialog_id: UUID
    text: str = Field(min_length=1, max_length=60000)
    role: Role = Role.user
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class LLMSaveRequest(BaseModel):
    dialog_id: UUID | None = None
    messages: list[Message] = Field(min_length=1, max_length=1000)
    feedback: int = Field(ge=1, le=5)
    feedback_text: str | None = None

    @model_validator(mode='after')
    def same_dialog(self):
        ids = {message.dialog_id for message in self.messages}
        if len(ids) != 1 or (self.dialog_id is not None and self.dialog_id not in ids):
            raise ValueError('All messages must belong to the requested dialog')
        self.dialog_id = self.messages[0].dialog_id
        return self
