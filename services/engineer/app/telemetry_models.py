from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from json import dumps, loads
from typing import Any, Mapping, Sequence, TypeVar


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


class SourceMode(str, Enum):
    live = "live"
    replay = "replay"
    mock = "mock"
    unknown = "unknown"


class ConnectionState(str, Enum):
    connected = "connected"
    degraded = "degraded"
    disconnected = "disconnected"
    unknown = "unknown"


class Priority(str, Enum):
    critical = "critical"
    warning = "warning"
    info = "info"


class TireWearMode(str, Enum):
    direct = "direct"
    inferred = "inferred"
    unknown = "unknown"


class TireCorner(str, Enum):
    front_left = "front_left"
    front_right = "front_right"
    rear_left = "rear_left"
    rear_right = "rear_right"


@dataclass
class RawTelemetryInput(JsonDataclassMixin):
    """Raw GT7 telemetry or parser output before normalization.

    TODO: validate source field names against live GT7 packets and the parser
    ecosystem. Fields that are uncertain stay optional so replay files and live
    packets can coexist safely.
    """

    timestamp_ms: int
    session_id: str
    source: str
    source_mode: SourceMode = SourceMode.unknown
    raw_payload: dict[str, Any] | None = None
    event_id: str | None = None
    speed_kph: float | None = None
    fuel_liters: float | None = None
    fuel_capacity_liters: float | None = None
    lap_number: int | None = None
    laps_total: int | None = None
    laps_remaining: int | None = None
    lap_time_ms: int | None = None
    last_lap_time_ms: int | None = None
    best_lap_time_ms: int | None = None
    position: int | None = None
    throttle_pct: float | None = None
    brake_pct: float | None = None
    gear: int | None = None
    rpm: int | None = None
    tire_temps_c: dict[str, float] | None = None
    wheel_speeds_mps: dict[str, float] | None = None
    slip_ratio_by_wheel: dict[str, float] | None = None
    tire_wear_pct: float | None = None
    tire_wear_mode: TireWearMode = TireWearMode.unknown
    flags: dict[str, bool] | None = None
    weather: dict[str, float] | None = None
    validation_warnings: list[str] | None = None

    def __post_init__(self) -> None:
        self.source_mode = SourceMode(self.source_mode)
        self.tire_wear_mode = TireWearMode(self.tire_wear_mode)
        self.raw_payload = dict(self.raw_payload or {})
        self.tire_temps_c = dict(self.tire_temps_c or {})
        self.wheel_speeds_mps = dict(self.wheel_speeds_mps or {})
        self.slip_ratio_by_wheel = dict(self.slip_ratio_by_wheel or {})
        self.flags = dict(self.flags or {})
        self.weather = dict(self.weather or {})
        self.validation_warnings = list(self.validation_warnings or [])


@dataclass
class NormalizedTelemetryState(JsonDataclassMixin):
    """Canonical telemetry consumed by deterministic logic.

    TODO: keep optional any field that cannot be validated directly from GT7.
    """

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
    lap_time_ms: int | None = None
    last_lap_time_ms: int | None = None
    best_lap_time_ms: int | None = None
    fuel_liters: float | None = None
    fuel_capacity_liters: float | None = None
    fuel_pct: float | None = None
    fuel_laps_remaining_estimate: float | None = None
    projected_fuel_to_finish_liters: float | None = None
    position: int | None = None
    speed_kph: float | None = None
    throttle_pct: float | None = None
    brake_pct: float | None = None
    gear: int | None = None
    rpm: int | None = None
    tire_temps_c: dict[str, float] | None = None
    wheel_speeds_mps: dict[str, float] | None = None
    slip_ratio_by_wheel: dict[str, float] | None = None
    tire_wear_pct: float | None = None
    tire_wear_mode: TireWearMode = TireWearMode.unknown
    flags: dict[str, bool] | None = None
    weather: dict[str, float] | None = None
    derived: dict[str, float] | None = None
    raw: dict[str, Any] | None = None
    validation_warnings: list[str] | None = None

    def __post_init__(self) -> None:
        self.source_mode = SourceMode(self.source_mode)
        self.connection_state = ConnectionState(self.connection_state)
        self.tire_wear_mode = TireWearMode(self.tire_wear_mode)
        self.tire_temps_c = dict(self.tire_temps_c or {})
        self.wheel_speeds_mps = dict(self.wheel_speeds_mps or {})
        self.slip_ratio_by_wheel = dict(self.slip_ratio_by_wheel or {})
        self.flags = dict(self.flags or {})
        self.weather = dict(self.weather or {})
        self.derived = dict(self.derived or {})
        self.raw = dict(self.raw or {})
        self.validation_warnings = list(self.validation_warnings or [])


@dataclass
class DerivedTelemetryState(JsonDataclassMixin):
    """Deterministic fields derived from normalized telemetry and history."""

    laps_remaining: int | None = None
    fuel_pct: float | None = None
    rolling_fuel_burn_per_lap: float | None = None
    projected_laps_remaining: float | None = None
    projected_finish_margin_laps: float | None = None
    avg_front_temp: float | None = None
    avg_rear_temp: float | None = None
    front_rear_temp_delta: float | None = None
    front_avg_slip: float | None = None
    rear_avg_slip: float | None = None
    rear_exit_slip_index: float | None = None
    front_brake_instability_index: float | None = None
    lap_delta_vs_best: float | None = None
    pace_trend_last_n_laps: float | None = None
    degradation_index: float | None = None
    tire_life_inferred_front: float | None = None
    tire_life_inferred_rear: float | None = None
    tire_wear_mode: TireWearMode = TireWearMode.unknown
    calculation_notes: list[str] | None = None

    def __post_init__(self) -> None:
        self.tire_wear_mode = TireWearMode(self.tire_wear_mode)
        self.calculation_notes = list(self.calculation_notes or [])


@dataclass
class EngineerEvent(JsonDataclassMixin):
    event_id: str
    timestamp_ms: int
    rule_id: str
    dedupe_key: str
    family: str
    priority: Priority
    category: str
    message: str
    recommended_action: str
    state_rank: int = 0
    source_event_id: str | None = None
    suppressed: bool = False
    suppression_reason: str | None = None
    required_fields: list[str] | None = None
    source_fields: list[str] | None = None
    validation_notes: list[str] | None = None

    def __post_init__(self) -> None:
        self.priority = Priority(self.priority)
        self.required_fields = list(self.required_fields or [])
        self.source_fields = list(self.source_fields or [])
        self.validation_notes = list(self.validation_notes or [])


@dataclass
class MessageEnvelope(JsonDataclassMixin):
    envelope_id: str
    timestamp_ms: int
    channel: str
    event: EngineerEvent
    delivery_priority: Priority
    ttl_ms: int = 5000
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        self.delivery_priority = Priority(self.delivery_priority)
        self.metadata = dict(self.metadata or {})
