from __future__ import annotations

from dataclasses import dataclass

from ..config import EngineerConfig
from ..models import LapSignalSource, Priority, TelemetrySnapshot
from .events import EngineerEventType, EngineerSignal


@dataclass
class SignalDetector:
    config: EngineerConfig

    def detect(self, snapshot: TelemetrySnapshot) -> list[EngineerSignal]:
        signals: list[EngineerSignal] = []
        laps_remaining = self._resolve_laps_remaining(snapshot)

        if laps_remaining is not None:
            signals.extend(self._detect_lap_countdown(laps_remaining))

        signals.extend(self._detect_fuel(snapshot))
        signals.extend(self._detect_projection(snapshot))
        signals.extend(self._detect_best_lap(snapshot))
        return signals

    def _resolve_laps_remaining(self, snapshot: TelemetrySnapshot) -> int | None:
        if snapshot.laps_remaining is not None:
            if snapshot.laps_remaining_source is None:
                snapshot.laps_remaining_source = LapSignalSource.explicit
            return snapshot.laps_remaining

        if snapshot.lap_number is not None and snapshot.laps_total is not None:
            derived = max(snapshot.laps_total - snapshot.lap_number, 0)
            snapshot.laps_remaining_source = LapSignalSource.derived
            return derived

        return None

    def _detect_lap_countdown(self, laps_remaining: int) -> list[EngineerSignal]:
        if laps_remaining == 2:
            return [
                EngineerSignal(
                    event_type=EngineerEventType.laps_remaining,
                    priority=Priority.info,
                    text="2 laps remaining",
                    ttl_ms=self.config.cooldown("laps_remaining", 30000),
                    payload={"laps_remaining": 2},
                )
            ]
        if laps_remaining == 1:
            return [
                EngineerSignal(
                    event_type=EngineerEventType.final_lap,
                    priority=Priority.warning,
                    text="Final lap",
                    ttl_ms=self.config.cooldown("final_lap", 60000),
                    payload={"laps_remaining": 1},
                )
            ]
        return []

    def _detect_fuel(self, snapshot: TelemetrySnapshot) -> list[EngineerSignal]:
        signals: list[EngineerSignal] = []
        critical_laps = self.config.threshold("fuel_critical_laps", 1.0)

        if snapshot.fuel_laps_remaining_estimate is not None and snapshot.fuel_laps_remaining_estimate <= critical_laps:
            signals.append(
                EngineerSignal(
                    event_type=EngineerEventType.fuel_critical,
                    priority=Priority.critical,
                    text=self._format_fuel_critical(snapshot.fuel_laps_remaining_estimate),
                    ttl_ms=self.config.cooldown("fuel_critical", 30000),
                    payload={"fuel_laps_remaining_estimate": snapshot.fuel_laps_remaining_estimate},
                )
            )

        if self._should_box_this_lap(snapshot):
            signals.append(
                EngineerSignal(
                    event_type=EngineerEventType.box_this_lap,
                    priority=Priority.critical,
                    text="Box this lap",
                    ttl_ms=self.config.cooldown("box_this_lap", 30000),
                    payload={},
                )
            )

        return signals

    def _detect_projection(self, snapshot: TelemetrySnapshot) -> list[EngineerSignal]:
        if snapshot.projected_fuel_to_finish_liters is None:
            return []

        margin_liters = self.config.threshold("fuel_to_finish_margin_liters", 0.5)
        projected = snapshot.projected_fuel_to_finish_liters
        if projected > margin_liters:
            return []

        return [
            EngineerSignal(
                event_type=EngineerEventType.projected_fuel_to_finish,
                priority=Priority.warning if projected >= 0 else Priority.critical,
                text=self._format_projected_margin(projected),
                ttl_ms=self.config.cooldown("projected_fuel_to_finish", 30000),
                payload={"projected_fuel_to_finish_liters": projected},
            )
        ]

    def _detect_best_lap(self, snapshot: TelemetrySnapshot) -> list[EngineerSignal]:
        if snapshot.last_lap_time_ms is None or snapshot.best_lap_time_ms is None:
            return []

        improvement_ms = snapshot.best_lap_time_ms - snapshot.last_lap_time_ms
        threshold_ms = int(self.config.threshold("best_lap_improvement_ms", 250))
        if improvement_ms < threshold_ms:
            return []

        return [
            EngineerSignal(
                event_type=EngineerEventType.best_lap,
                priority=Priority.info,
                text=f"New best lap, {self._format_delta(improvement_ms)} quicker",
                ttl_ms=self.config.cooldown("best_lap", 0),
                payload={
                    "last_lap_time_ms": snapshot.last_lap_time_ms,
                    "previous_best_lap_time_ms": snapshot.best_lap_time_ms,
                    "improvement_ms": improvement_ms,
                },
            )
        ]

    def _should_box_this_lap(self, snapshot: TelemetrySnapshot) -> bool:
        if snapshot.projected_fuel_to_finish_liters is not None and snapshot.projected_fuel_to_finish_liters < 0:
            return True
        if snapshot.fuel_laps_remaining_estimate is not None and snapshot.fuel_laps_remaining_estimate <= 1.0:
            return True
        return False

    def _format_projected_margin(self, projected: float) -> str:
        if projected < 0:
            return f"Fuel to finish: deficit {abs(projected):.1f} L"
        return f"Fuel to finish: +{projected:.1f} L"

    def _format_fuel_critical(self, fuel_laps: float) -> str:
        return f"Fuel critical, {fuel_laps:.1f} laps left"

    def _format_delta(self, improvement_ms: int) -> str:
        return f"{improvement_ms / 1000:.3f}s"

