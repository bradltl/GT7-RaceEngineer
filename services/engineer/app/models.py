from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from json import dumps, loads
from typing import Any, TypeVar


def _serialize(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {field.name: _serialize(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    return value


T = TypeVar("T")


class JsonDataclassMixin:
    def model_dump(self) -> dict[str, Any]:
        return _serialize(self)

    def model_dump_json(self) -> str:
        return dumps(self.model_dump())

    def model_copy(self, update: dict[str, Any] | None = None):
        data = self.model_dump()
        if update:
            data.update(update)
        return self.__class__(**data)

    @classmethod
    def model_validate_json(cls: type[T], data: str) -> T:
        return cls(**loads(data))

    @classmethod
    def model_validate(cls: type[T], data: Any) -> T:
        if isinstance(data, cls):
            return data
        if isinstance(data, str):
            return cls.model_validate_json(data)
        if isinstance(data, dict):
            return cls(**data)
        raise TypeError(f"Unsupported payload for {cls.__name__}: {type(data)!r}")


class ConnectionState(str, Enum):
    connected = "connected"
    degraded = "degraded"
    disconnected = "disconnected"
    unknown = "unknown"


class SourceMode(str, Enum):
    live = "live"
    replay = "replay"
    mock = "mock"
    unknown = "unknown"


class Priority(str, Enum):
    critical = "critical"
    warning = "warning"
    info = "info"


class LapSignalSource(str, Enum):
    explicit = "explicit"
    derived = "derived"


@dataclass
class TelemetrySnapshot(JsonDataclassMixin):
    # Canonical normalized input for the deterministic engineer layer.
    # Assumptions about each GT7 mapping are documented in
    # services/engineer/docs/gt7_field_assumptions.md.
    event_id: str
    timestamp_ms: int
    session_id: str
    source: str
    source_mode: SourceMode = SourceMode.unknown
    connection_state: ConnectionState = ConnectionState.unknown
    track_name: str | None = None
    session_type: str | None = None
    lap_number: int | None = None
    laps_total: int | None = None
    laps_remaining: int | None = None
    laps_remaining_source: LapSignalSource | None = None
    lap_time_ms: int | None = None
    last_lap_time_ms: int | None = None
    best_lap_time_ms: int | None = None
    fuel_liters: float | None = None
    fuel_capacity_liters: float | None = None
    fuel_laps_remaining_estimate: float | None = None
    projected_fuel_to_finish_liters: float | None = None
    tire_wear_pct: float | None = None
    speed_kph: float | None = None
    throttle_pct: float | None = None
    brake_pct: float | None = None
    gear: int | None = None
    rpm: int | None = None
    flags: dict[str, bool] | None = None
    weather: dict[str, float] | None = None
    derived: dict[str, float] | None = None
    raw: dict[str, Any] | None = None
    validation_warnings: list[str] | None = None

    def __post_init__(self) -> None:
        self.source_mode = SourceMode(self.source_mode)
        self.connection_state = ConnectionState(self.connection_state)
        if self.laps_remaining_source is not None:
            self.laps_remaining_source = LapSignalSource(self.laps_remaining_source)
        self.flags = dict(self.flags or {})
        self.weather = dict(self.weather or {})
        self.derived = dict(self.derived or {})
        self.raw = dict(self.raw or {})
        self.validation_warnings = list(self.validation_warnings or [])


@dataclass
class EngineerMessage(JsonDataclassMixin):
    id: str
    timestamp_ms: int
    priority: Priority
    category: str
    text: str
    ttl_ms: int = 5000
    source_event_id: str | None = None
    suppressed: bool = False
    suppression_reason: str | None = None

    def __post_init__(self) -> None:
        self.priority = Priority(self.priority)


@dataclass
class SessionMetrics(JsonDataclassMixin):
    session_id: str | None = None
    track_name: str | None = None
    lap_number: int | None = None
    laps_remaining: int | None = None
    lap_time_ms: int | None = None
    last_lap_time_ms: int | None = None
    best_lap_time_ms: int | None = None
    fuel_liters: float | None = None
    fuel_laps_remaining_estimate: float | None = None
    projected_fuel_to_finish_liters: float | None = None
    connection_state: ConnectionState = ConnectionState.unknown
    source_mode: SourceMode = SourceMode.unknown
    stale_ms: int | None = None

    def __post_init__(self) -> None:
        self.connection_state = ConnectionState(self.connection_state)
        self.source_mode = SourceMode(self.source_mode)


@dataclass
class IngestResponse(JsonDataclassMixin):
    accepted: bool
    messages: list[EngineerMessage]
