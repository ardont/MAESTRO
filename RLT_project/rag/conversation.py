"""Redis-backed state for external chats (AlphaRAG IDs are not Django UUIDs)."""
import json
from dataclasses import dataclass, field


@dataclass
class Conversation:
    id: str
    client: object
    key: str
    context_cache: dict = field(default_factory=dict)
    active_workflow: str | None = None
    current_step: int = 0
    collected_data: dict = field(default_factory=dict)

    def save(self, update_fields=None):
        state = {name: getattr(self, name) for name in (
            "context_cache", "active_workflow", "current_step", "collected_data"
        )}
        # Fail visibly rather than pretending the next turn will remember the offer.
        self.client.set(self.key, json.dumps(state, ensure_ascii=False))


def load_conversation(user_uuid, chat_id):
    from .main_rag import redis_client
    if redis_client is None:
        raise RuntimeError("Redis is required for Kafka conversation state")
    key = f"rag:conversation:v1:{user_uuid}:{chat_id}"
    raw = redis_client.get(key)
    state = json.loads(raw) if raw else {}
    return Conversation(id=str(chat_id), client=redis_client, key=key, **state)
