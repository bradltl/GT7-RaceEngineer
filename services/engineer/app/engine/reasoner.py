from __future__ import annotations

from dataclasses import dataclass

from ..config import EngineerConfig
from ..models import Priority
from .events import EngineerEventType, EngineerSignal


@dataclass
class ReasonedEvent:
    event_type: EngineerEventType
    priority: Priority
    text: str
    ttl_ms: int
    payload: dict[str, object]


class RaceReasoner:
    def __init__(self, config: EngineerConfig) -> None:
        self.config = config

    def reason(self, signals: list[EngineerSignal]) -> list[ReasonedEvent]:
        events: list[ReasonedEvent] = []
        for signal in signals:
            if not self._enabled(signal.event_type):
                continue
            events.append(self._reason_signal(signal))
        return events

    def _enabled(self, event_type: EngineerEventType) -> bool:
        mapping = {
            EngineerEventType.laps_remaining: "laps_remaining",
            EngineerEventType.final_lap: "final_lap",
            EngineerEventType.projected_fuel_to_finish: "projected_fuel_to_finish",
            EngineerEventType.fuel_critical: "fuel_status",
            EngineerEventType.box_this_lap: "box_this_lap",
            EngineerEventType.best_lap: "best_lap",
        }
        enabled_key = mapping.get(event_type, event_type.value)
        return self.config.enabled_callouts.get(enabled_key, True)

    def _reason_signal(self, signal: EngineerSignal) -> ReasonedEvent:
        return ReasonedEvent(
            event_type=signal.event_type,
            priority=signal.priority,
            text=signal.text,
            ttl_ms=signal.ttl_ms,
            payload=signal.payload,
        )
