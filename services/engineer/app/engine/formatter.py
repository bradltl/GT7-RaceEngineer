from __future__ import annotations

from ..models import EngineerMessage
from .reasoner import ReasonedEvent


class MessageFormatter:
    def format(self, event: ReasonedEvent, timestamp_ms: int, source_event_id: str | None) -> EngineerMessage:
        return EngineerMessage(
            id=f"{event.event_type.value}-{timestamp_ms}",
            timestamp_ms=timestamp_ms,
            priority=event.priority,
            category=event.event_type.value,
            text=event.text,
            ttl_ms=event.ttl_ms,
            source_event_id=source_event_id,
        )
