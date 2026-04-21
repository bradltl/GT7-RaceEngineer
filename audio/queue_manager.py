from __future__ import annotations

from dataclasses import replace
from threading import Condition
from time import time
from typing import Optional

from .models import AudioConfig, AudioPriority, QueuedAudioItem


class AudioQueueManager:
    def __init__(self, config: AudioConfig):
        self.config = config
        self._pending: list[QueuedAudioItem] = []
        self._pending_intents: dict[str, QueuedAudioItem] = {}
        self._last_played_ms: dict[str, int] = {}
        self._last_enqueued_ms: dict[str, int] = {}
        self._condition = Condition()
        self._sequence = 0

    def enqueue(self, item: QueuedAudioItem, *, force: bool = False) -> bool:
        now_ms = item.created_at_ms
        cooldown_ms = self.config.cooldown_for(item.intent, 0)

        with self._condition:
            # Dedupe first: the same intent should not stack in the queue or repeat too quickly.
            last_played = self._last_played_ms.get(item.intent)
            last_enqueued = self._last_enqueued_ms.get(item.intent)
            if not force:
                if last_played is not None and now_ms - last_played < cooldown_ms:
                    return False
                if last_enqueued is not None and now_ms - last_enqueued < max(250, cooldown_ms // 2):
                    return False

            existing = self._pending_intents.get(item.intent)
            if existing is not None:
                if item.priority.rank <= existing.priority.rank:
                    return False
                self._remove_pending(existing.intent)

            if len(self._pending) >= self.config.queue_size:
                worst = min(
                    self._pending,
                    key=lambda queued: (queued.priority.rank, queued.created_at_ms, queued.sequence),
                )
                if item.priority.rank <= worst.priority.rank:
                    return False
                self._remove_pending(worst.intent)

            self._sequence += 1
            self._pending.append(replace(item, sequence=self._sequence))
            self._pending_intents[item.intent] = item
            self._last_enqueued_ms[item.intent] = now_ms
            self._condition.notify()
            return True

    def pop_next(self, timeout: float | None = None) -> QueuedAudioItem | None:
        with self._condition:
            if not self._pending:
                self._condition.wait(timeout=timeout)
            if not self._pending:
                return None

            next_item = max(
                self._pending,
                key=lambda queued: (queued.priority.rank, -queued.created_at_ms, -queued.sequence),
            )
            self._remove_pending(next_item.intent)
            return next_item

    def mark_played(self, item: QueuedAudioItem) -> None:
        with self._condition:
            self._last_played_ms[item.intent] = int(time() * 1000)

    def clear(self) -> None:
        with self._condition:
            self._pending.clear()
            self._pending_intents.clear()
            self._condition.notify_all()

    def size(self) -> int:
        with self._condition:
            return len(self._pending)

    def pending_intents(self) -> list[str]:
        with self._condition:
            return [item.intent for item in self._pending]

    def _remove_pending(self, intent: str) -> None:
        existing = self._pending_intents.pop(intent, None)
        if existing is None:
            return
        self._pending = [item for item in self._pending if item.intent != intent]

