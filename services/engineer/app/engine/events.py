from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ..models import Priority


class EngineerEventType(str, Enum):
    laps_remaining = "laps_remaining"
    final_lap = "final_lap"
    projected_fuel_to_finish = "projected_fuel_to_finish"
    fuel_critical = "fuel_critical"
    box_this_lap = "box_this_lap"
    best_lap = "best_lap"


@dataclass(frozen=True)
class EngineerSignal:
    event_type: EngineerEventType
    priority: Priority
    text: str
    ttl_ms: int
    payload: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ReasonedEvent:
    event_type: EngineerEventType
    priority: Priority
    text: str
    ttl_ms: int
    payload: dict[str, object] = field(default_factory=dict)

