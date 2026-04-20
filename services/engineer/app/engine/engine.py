from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Iterable

from ..config import EngineerConfig
from ..models import EngineerMessage, Priority, SessionMetrics, TelemetrySnapshot
from .detectors import SignalDetector
from .events import EngineerEventType
from .formatter import MessageFormatter
from .reasoner import RaceReasoner, ReasonedEvent


@dataclass
class RuleEngine:
    config: EngineerConfig
    detector: SignalDetector = field(init=False)
    reasoner: RaceReasoner = field(init=False)
    formatter: MessageFormatter = field(default_factory=MessageFormatter)
    last_emitted_at_ms: dict[EngineerEventType, int] = field(default_factory=dict)
    latest_snapshot: TelemetrySnapshot | None = None

    def __post_init__(self) -> None:
        self.detector = SignalDetector(self.config)
        self.reasoner = RaceReasoner(self.config)

    def process(self, snapshot: TelemetrySnapshot) -> tuple[list[EngineerMessage], SessionMetrics]:
        self.latest_snapshot = snapshot
        signals = self.detector.detect(snapshot)
        reasoned = self.reasoner.reason(signals)
        ordered = self._order_reasoned(self._dedupe_reasoned(reasoned))

        messages: list[EngineerMessage] = []
        for event in ordered:
            if self._should_suppress(event.event_type, snapshot.timestamp_ms, event.ttl_ms):
                continue
            message = self.formatter.format(event, snapshot.timestamp_ms, snapshot.event_id)
            messages.append(message)
            self.last_emitted_at_ms[event.event_type] = snapshot.timestamp_ms
        return messages, self._build_metrics(snapshot)

    def _dedupe_reasoned(self, events: Iterable[ReasonedEvent]) -> list[ReasonedEvent]:
        deduped: dict[EngineerEventType, ReasonedEvent] = {}
        for event in events:
            current = deduped.get(event.event_type)
            if current is None or self._priority_rank(event.priority) > self._priority_rank(current.priority):
                deduped[event.event_type] = event
        return list(deduped.values())

    def _order_reasoned(self, events: Iterable[ReasonedEvent]) -> list[ReasonedEvent]:
        order = {
            EngineerEventType.fuel_critical: 0,
            EngineerEventType.box_this_lap: 1,
            EngineerEventType.final_lap: 2,
            EngineerEventType.projected_fuel_to_finish: 3,
            EngineerEventType.laps_remaining: 4,
            EngineerEventType.best_lap: 5,
        }
        return sorted(
            events,
            key=lambda event: (-self._priority_rank(event.priority), order.get(event.event_type, 99)),
        )

    def _should_suppress(self, event_type: EngineerEventType, timestamp_ms: int, cooldown_ms: int) -> bool:
        last = self.last_emitted_at_ms.get(event_type)
        if last is None:
            return False
        return timestamp_ms - last < cooldown_ms

    def _priority_rank(self, priority: Priority) -> int:
        return {
            Priority.critical: 3,
            Priority.warning: 2,
            Priority.info: 1,
        }[priority]

    def _build_metrics(self, snapshot: TelemetrySnapshot) -> SessionMetrics:
        stale_ms = None
        if snapshot.source_mode.value == "live":
            stale_ms = max(0, int(time.time() * 1000) - snapshot.timestamp_ms)
        elif snapshot.source_mode.value in {"replay", "mock"}:
            stale_ms = 0

        return SessionMetrics(
            session_id=snapshot.session_id,
            track_name=snapshot.track_name,
            lap_number=snapshot.lap_number,
            laps_remaining=snapshot.laps_remaining,
            lap_time_ms=snapshot.lap_time_ms,
            last_lap_time_ms=snapshot.last_lap_time_ms,
            best_lap_time_ms=snapshot.best_lap_time_ms,
            fuel_liters=snapshot.fuel_liters,
            fuel_laps_remaining_estimate=snapshot.fuel_laps_remaining_estimate,
            projected_fuel_to_finish_liters=snapshot.projected_fuel_to_finish_liters,
            connection_state=snapshot.connection_state,
            source_mode=snapshot.source_mode,
            stale_ms=stale_ms,
        )
