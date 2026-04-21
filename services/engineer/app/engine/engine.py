from __future__ import annotations

from dataclasses import dataclass, field
from statistics import pstdev
from typing import Any, Iterable, Sequence

from ..config import EngineerConfig
from ..models import (
    ConnectionState as LegacyConnectionState,
    EngineerMessage as LegacyEngineerMessage,
    Priority as LegacyPriority,
    SessionMetrics as LegacySessionMetrics,
    SourceMode as LegacySourceMode,
)
from ..telemetry_calculations import (
    build_derived_telemetry_state,
)
from ..telemetry_models import (
    ConnectionState,
    DerivedTelemetryState,
    EngineerEvent,
    MessageEnvelope,
    NormalizedTelemetryState,
    Priority,
    RawTelemetryInput,
    SourceMode,
    TireWearMode,
)


_PRIORITY_RANK = {
    Priority.critical: 3,
    Priority.warning: 2,
    Priority.info: 1,
}

_INFO_FAMILY_RANK = {
    "race_phase": 40,
    "tire_grip": 30,
    "pace_degradation": 20,
    "fuel_strategy": 10,
}


@dataclass
class _EmissionRecord:
    priority: Priority
    state_rank: int
    fingerprint: str
    timestamp_ms: int


@dataclass
class RuleEngine:
    config: EngineerConfig
    _history: list[NormalizedTelemetryState] = field(default_factory=list)
    _last_emissions: dict[str, _EmissionRecord] = field(default_factory=dict)
    _legacy_last_emissions: dict[str, int] = field(default_factory=dict)
    latest_snapshot: NormalizedTelemetryState | None = None
    latest_derived: DerivedTelemetryState | None = None

    def evaluate(
        self,
        snapshot: NormalizedTelemetryState | RawTelemetryInput | Any,
        history: Sequence[NormalizedTelemetryState] | None = None,
    ) -> tuple[list[EngineerEvent], list[MessageEnvelope], DerivedTelemetryState]:
        normalized = self._coerce_snapshot(snapshot)
        self.latest_snapshot = normalized

        prior_history = list(history) if history is not None else list(self._history)
        derived = build_derived_telemetry_state(
            normalized,
            prior_history,
            direct_tire_wear_enabled=normalized.tire_wear_mode == TireWearMode.direct,
            inferred_tire_life_enabled=normalized.tire_wear_mode != TireWearMode.direct,
        )
        self.latest_derived = derived

        candidates = self._build_candidates(normalized, derived, prior_history)
        prioritized = self._prioritize(candidates)
        emitted = self._filter_emittable(normalized.timestamp_ms, prioritized)
        envelopes = [
            MessageEnvelope(
                envelope_id=f"env-{event.event_id}",
                timestamp_ms=event.timestamp_ms,
                channel="engineer",
                event=event,
                delivery_priority=event.priority,
                ttl_ms=self._cooldown_for(event.rule_id, 5000),
                metadata={"dedupe_key": event.dedupe_key},
            )
            for event in emitted
        ]

        self._history.append(normalized)
        if len(self._history) > 200:
            self._history = self._history[-200:]

        return emitted, envelopes, derived

    def process(
        self,
        snapshot: NormalizedTelemetryState | RawTelemetryInput | Any,
        history: Sequence[NormalizedTelemetryState] | None = None,
    ) -> tuple[list[LegacyEngineerMessage], LegacySessionMetrics]:
        normalized = self._coerce_snapshot(snapshot)
        self.latest_snapshot = normalized
        legacy_messages = self._build_legacy_messages(normalized, history)
        latest = self.latest_snapshot
        if latest is None:
            latest = normalized
        metrics = LegacySessionMetrics(
            session_id=latest.session_id,
            track_name=latest.track_name,
            lap_number=latest.lap_number,
            laps_remaining=latest.laps_remaining,
            lap_time_ms=latest.lap_time_ms,
            last_lap_time_ms=latest.last_lap_time_ms,
            best_lap_time_ms=latest.best_lap_time_ms,
            fuel_liters=latest.fuel_liters,
            fuel_laps_remaining_estimate=latest.fuel_laps_remaining_estimate,
            projected_fuel_to_finish_liters=latest.projected_fuel_to_finish_liters,
            connection_state=self._to_legacy_connection_state(latest.connection_state),
            source_mode=self._to_legacy_source_mode(latest.source_mode),
            stale_ms=self._stale_ms(latest),
        )
        self._history.append(normalized)
        if len(self._history) > 200:
            self._history = self._history[-200:]
        return legacy_messages, metrics

    def _build_candidates(
        self,
        snapshot: NormalizedTelemetryState,
        derived: DerivedTelemetryState,
        history: Sequence[NormalizedTelemetryState],
    ) -> list[EngineerEvent]:
        events: list[EngineerEvent] = []
        events.extend(self._fuel_strategy(snapshot, derived))
        events.extend(self._race_phase(snapshot, derived))
        events.extend(self._tire_grip(snapshot, derived))
        events.extend(self._slip_traction(snapshot, derived))
        events.extend(self._pace_degradation(snapshot, derived, history))
        events.extend(self._tire_life(snapshot, derived))
        return events

    def _fuel_strategy(self, snapshot: NormalizedTelemetryState, derived: DerivedTelemetryState) -> list[EngineerEvent]:
        margin = derived.projected_finish_margin_laps
        fuel_laps = snapshot.fuel_laps_remaining_estimate
        healthy_threshold = self._threshold("fuel_margin_healthy_laps", 2.0)
        borderline_threshold = self._threshold("fuel_borderline_laps", 0.5)
        save_threshold = self._threshold("fuel_save_required_laps", 0.0)

        if margin is None and fuel_laps is None:
            return []

        state = "healthy"
        priority = Priority.info
        message = "Fuel margin healthy"
        action = "Hold pace"
        rule_id = "fuel_margin_healthy"
        if self._fuel_is_critical(margin, fuel_laps):
            state = "critical"
            priority = Priority.critical
            message = "Fuel critical"
            action = "Box this lap"
            rule_id = "fuel_critical"
        elif self._fuel_needs_save(margin, fuel_laps, save_threshold):
            state = "save_required"
            priority = Priority.warning
            message = "Fuel save required"
            action = "Save fuel now"
            rule_id = "fuel_save_required"
        elif self._fuel_borderline(margin, fuel_laps, borderline_threshold, healthy_threshold):
            state = "borderline"
            priority = Priority.warning
            message = "Borderline fuel"
            action = "Manage fuel"
            rule_id = "borderline_fuel"

        if state == "healthy" and not self._should_emit_healthy_fuel():
            return []

        return [
            self._event(
                rule_id=rule_id,
                family="fuel_strategy",
                dedupe_key="fuel_strategy",
                priority=priority,
                message=message,
                recommended_action=action,
                snapshot=snapshot,
                required_fields=["fuel_liters", "fuel_capacity_liters", "fuel_laps_remaining_estimate", "projected_fuel_to_finish_liters"],
                source_fields=["fuel_liters", "fuel_capacity_liters", "fuel_laps_remaining_estimate", "projected_fuel_to_finish_liters"],
                validation_notes=["TODO: confirm fuel projection semantics against live GT7 packets"],
                state_tag=state,
                state_rank=self._state_rank_for_fuel(state),
            )
        ]

    def _race_phase(self, snapshot: NormalizedTelemetryState, derived: DerivedTelemetryState) -> list[EngineerEvent]:
        laps_remaining = derived.laps_remaining
        if laps_remaining is None:
            return []
        if laps_remaining == 1:
            return [
                self._event(
                    rule_id="final_lap",
                    family="race_phase",
                    dedupe_key="race_phase",
                    priority=Priority.warning,
                    message="Final lap",
                    recommended_action="Finish clean",
                    snapshot=snapshot,
                    required_fields=["laps_remaining", "lap_number", "laps_total"],
                    source_fields=["lap_number", "laps_total", "laps_remaining"],
                    validation_notes=["TODO: validate lap count off-by-one behavior in live GT7 telemetry"],
                    state_tag="final_lap",
                    state_rank=3,
                )
            ]
        if laps_remaining == 2:
            return [
                self._event(
                    rule_id="two_laps_remaining",
                    family="race_phase",
                    dedupe_key="race_phase",
                    priority=Priority.info,
                    message="2 laps remaining",
                    recommended_action="Plan final stint",
                    snapshot=snapshot,
                    required_fields=["laps_remaining", "lap_number", "laps_total"],
                    source_fields=["lap_number", "laps_total", "laps_remaining"],
                    validation_notes=["TODO: validate lap count off-by-one behavior in live GT7 telemetry"],
                    state_tag="two_laps_remaining",
                    state_rank=2,
                )
            ]
        if laps_remaining <= self._threshold("end_phase_push_laps", 3) and not self._fuel_is_critical(
            derived.projected_finish_margin_laps,
            snapshot.fuel_laps_remaining_estimate,
        ):
            return [
                self._event(
                    rule_id="end_phase_push",
                    family="race_phase",
                    dedupe_key="race_phase",
                    priority=Priority.info,
                    message="End-phase push",
                    recommended_action="Increase pace",
                    snapshot=snapshot,
                    required_fields=["laps_remaining"],
                    source_fields=["laps_remaining"],
                    validation_notes=[],
                    state_tag=f"push_{laps_remaining}",
                    state_rank=1,
                )
            ]
        return []

    def _tire_grip(self, snapshot: NormalizedTelemetryState, derived: DerivedTelemetryState) -> list[EngineerEvent]:
        if snapshot.tire_wear_mode != TireWearMode.direct:
            return []
        events: list[EngineerEvent] = []
        front_temp = derived.avg_front_temp
        rear_temp = derived.avg_rear_temp
        temp_hot = self._threshold("tire_temp_hot_c", 98.0)
        temp_cold = self._threshold("tire_temp_cold_c", 65.0)
        understeer_delta = self._threshold("understeer_temp_delta_c", 4.0)
        rear_grip_slip = self._threshold("rear_grip_slip", 0.05)
        front_overheat_slip = self._threshold("front_overheat_slip", 0.03)

        if rear_temp is not None and rear_temp >= temp_hot and derived.rear_avg_slip is not None and derived.rear_avg_slip >= rear_grip_slip:
            events.append(
                self._event(
                    rule_id="rear_overheating",
                    family="tire_grip",
                    dedupe_key="rear_overheating",
                    priority=Priority.warning,
                    message="Rear overheating",
                    recommended_action="Reduce rear slip",
                    snapshot=snapshot,
                    required_fields=["tire_temps_c"],
                    source_fields=["tire_temps_c.rear_left", "tire_temps_c.rear_right"],
                    validation_notes=["TODO: validate tire temperature channels from live GT7 packets"],
                    state_tag=f"rear_hot_{int(rear_temp)}",
                    state_rank=2,
                )
            )
        if front_temp is not None and front_temp >= temp_hot and derived.front_avg_slip is not None and abs(derived.front_avg_slip) >= front_overheat_slip:
            events.append(
                self._event(
                    rule_id="front_overheating",
                    family="tire_grip",
                    dedupe_key="front_overheating",
                    priority=Priority.warning,
                    message="Front overheating",
                    recommended_action="Protect the front tires",
                    snapshot=snapshot,
                    required_fields=["tire_temps_c"],
                    source_fields=["tire_temps_c.front_left", "tire_temps_c.front_right"],
                    validation_notes=["TODO: validate tire temperature channels from live GT7 packets"],
                    state_tag=f"front_hot_{int(front_temp)}",
                    state_rank=2,
                )
            )
        if front_temp is not None and rear_temp is not None and front_temp <= temp_cold and rear_temp <= temp_cold:
            events.append(
                self._event(
                    rule_id="cold_tires",
                    family="tire_grip",
                    dedupe_key="cold_tires",
                    priority=Priority.warning,
                    message="Tires cold",
                    recommended_action="Build grip",
                    snapshot=snapshot,
                    required_fields=["tire_temps_c"],
                    source_fields=["tire_temps_c.front_left", "tire_temps_c.front_right", "tire_temps_c.rear_left", "tire_temps_c.rear_right"],
                    validation_notes=["TODO: validate tire temperature channels from live GT7 packets"],
                    state_tag="cold",
                    state_rank=1,
                )
            )
        if derived.front_rear_temp_delta is not None and derived.front_rear_temp_delta >= understeer_delta and (
            derived.front_avg_slip is not None and derived.rear_avg_slip is not None and derived.front_avg_slip < derived.rear_avg_slip
        ):
            events.append(
                self._event(
                    rule_id="understeer_building",
                    family="tire_grip",
                    dedupe_key="understeer_building",
                    priority=Priority.info,
                    message="Understeer building",
                    recommended_action="Smoother turn-in",
                    snapshot=snapshot,
                    required_fields=["tire_temps_c", "slip_ratio_by_wheel"],
                    source_fields=["tire_temps_c", "slip_ratio_by_wheel"],
                    validation_notes=["TODO: validate understeer proxy against live sessions"],
                    state_tag=f"understeer_{derived.front_rear_temp_delta:.1f}",
                    state_rank=1,
                )
            )
        if derived.rear_avg_slip is not None and derived.rear_exit_slip_index is not None:
            if derived.rear_avg_slip >= rear_grip_slip and derived.rear_exit_slip_index >= self._threshold("rear_exit_slip_index", 0.05):
                events.append(
                    self._event(
                        rule_id="rear_grip_falling",
                        family="tire_grip",
                        dedupe_key="rear_grip_falling",
                        priority=Priority.warning,
                        message="Rear grip falling",
                        recommended_action="Ease throttle",
                        snapshot=snapshot,
                        required_fields=["slip_ratio_by_wheel", "throttle_pct"],
                        source_fields=["slip_ratio_by_wheel", "throttle_pct"],
                        validation_notes=["TODO: validate rear exit slip thresholds against real data"],
                        state_tag=f"rear_grip_{derived.rear_exit_slip_index:.2f}",
                        state_rank=2,
                    )
                )
        return events

    def _slip_traction(self, snapshot: NormalizedTelemetryState, derived: DerivedTelemetryState) -> list[EngineerEvent]:
        if snapshot.tire_wear_mode != TireWearMode.direct:
            return []
        events: list[EngineerEvent] = []
        wheelspin_threshold = self._threshold("wheelspin_slip", 0.08)
        brake_threshold = self._threshold("brake_instability_index", 0.03) * 0.8

        wheelspin = (
            derived.rear_exit_slip_index is not None
            and derived.rear_exit_slip_index >= wheelspin_threshold
            and (snapshot.throttle_pct or 0.0) >= self._threshold("wheelspin_throttle_pct", 40.0)
        )
        brake_instability = (
            derived.front_brake_instability_index is not None
            and derived.front_brake_instability_index >= brake_threshold
            and (snapshot.brake_pct or 0.0) >= self._threshold("brake_instability_brake_pct", 40.0)
        )

        if wheelspin:
            events.append(
                self._event(
                    rule_id="wheelspin_detected",
                    family="slip_traction",
                    dedupe_key="wheelspin_detected",
                    priority=Priority.warning,
                    message="Wheelspin detected",
                    recommended_action="Roll throttle",
                    snapshot=snapshot,
                    required_fields=["slip_ratio_by_wheel", "throttle_pct"],
                    source_fields=["slip_ratio_by_wheel", "throttle_pct"],
                    validation_notes=["TODO: confirm wheel speed and slip ratio derivation"],
                    state_tag=f"wheelspin_{derived.rear_exit_slip_index:.2f}",
                    state_rank=2,
                )
            )
        if brake_instability:
            events.append(
                self._event(
                    rule_id="brake_instability",
                    family="slip_traction",
                    dedupe_key="brake_instability",
                    priority=Priority.warning,
                    message="Brake instability",
                    recommended_action="Softer brake release",
                    snapshot=snapshot,
                    required_fields=["slip_ratio_by_wheel", "brake_pct"],
                    source_fields=["slip_ratio_by_wheel", "brake_pct"],
                    validation_notes=["TODO: confirm brake lockup proxy against live data"],
                    state_tag=f"brake_{derived.front_brake_instability_index:.2f}",
                    state_rank=2,
                )
            )
        if wheelspin and brake_instability:
            events.append(
                self._event(
                    rule_id="overdriving",
                    family="slip_traction",
                    dedupe_key="overdriving",
                    priority=Priority.critical,
                    message="Overdriving",
                    recommended_action="Back off one step",
                    snapshot=snapshot,
                    required_fields=["slip_ratio_by_wheel", "throttle_pct", "brake_pct"],
                    source_fields=["slip_ratio_by_wheel", "throttle_pct", "brake_pct"],
                    validation_notes=["TODO: validate overdriving composite trigger"],
                    state_tag="overdriving",
                    state_rank=3,
                )
            )
        return events

    def _pace_degradation(
        self,
        snapshot: NormalizedTelemetryState,
        derived: DerivedTelemetryState,
        history: Sequence[NormalizedTelemetryState],
    ) -> list[EngineerEvent]:
        if snapshot.tire_wear_mode == TireWearMode.unknown:
            return []
        events: list[EngineerEvent] = []
        lap_delta = derived.lap_delta_vs_best
        pace_trend = derived.pace_trend_last_n_laps
        degradation_index = derived.degradation_index
        recent_laps = self._recent_lap_times(history, snapshot)
        inconsistency_threshold = self._threshold("pace_inconsistency_range_ms", 600.0)
        pace_drop_threshold = self._threshold("pace_drop_ms", 250.0)

        if lap_delta is not None and abs(lap_delta) <= self._threshold("best_lap_pace_window_ms", 150.0):
            events.append(
                self._event(
                    rule_id="on_best_lap_pace",
                    family="pace_degradation",
                    dedupe_key="on_best_lap_pace",
                    priority=Priority.info,
                    message="On best-lap pace",
                    recommended_action="Repeat the lap",
                    snapshot=snapshot,
                    required_fields=["last_lap_time_ms", "best_lap_time_ms"],
                    source_fields=["last_lap_time_ms", "best_lap_time_ms"],
                    validation_notes=[],
                    state_tag=f"best_{int(lap_delta)}",
                    state_rank=1,
                )
            )
        elif lap_delta is not None and lap_delta > pace_drop_threshold:
            events.append(
                self._event(
                    rule_id="losing_pace",
                    family="pace_degradation",
                    dedupe_key="losing_pace",
                    priority=Priority.warning,
                    message="Losing pace",
                    recommended_action="Clean up the lap",
                    snapshot=snapshot,
                    required_fields=["last_lap_time_ms", "best_lap_time_ms"],
                    source_fields=["last_lap_time_ms", "best_lap_time_ms"],
                    validation_notes=[],
                    state_tag=f"lose_{int(lap_delta)}",
                    state_rank=2,
                )
            )

        if len(recent_laps) >= 3 and pstdev(recent_laps) >= inconsistency_threshold:
            events.append(
                self._event(
                    rule_id="pace_inconsistency",
                    family="pace_degradation",
                    dedupe_key="pace_inconsistency",
                    priority=Priority.info,
                    message="Pace inconsistent",
                    recommended_action="Stabilize laps",
                    snapshot=snapshot,
                    required_fields=["last_lap_time_ms", "best_lap_time_ms"],
                    source_fields=["last_lap_time_ms", "best_lap_time_ms"],
                    validation_notes=[],
                    state_tag=f"inconsistent_{int(pstdev(recent_laps))}",
                    state_rank=1,
                )
            )

        if degradation_index is not None and (
            degradation_index >= self._threshold("degradation_phase_index", 55.0)
            or (pace_trend is not None and pace_trend > pace_drop_threshold and self._tire_life_is_low(derived))
        ):
            events.append(
                self._event(
                    rule_id="degradation_phase_detected",
                    family="pace_degradation",
                    dedupe_key="degradation_phase_detected",
                    priority=Priority.warning,
                    message="Degradation phase",
                    recommended_action="Protect the stint",
                    snapshot=snapshot,
                    required_fields=["lap_time_ms", "last_lap_time_ms", "best_lap_time_ms"],
                    source_fields=["lap_time_ms", "last_lap_time_ms", "best_lap_time_ms"],
                    validation_notes=["TODO: validate degradation index thresholds against live sessions"],
                    state_tag=f"degradation_{int(degradation_index)}",
                    state_rank=2,
                )
            )
        return events

    def _tire_life(self, snapshot: NormalizedTelemetryState, derived: DerivedTelemetryState) -> list[EngineerEvent]:
        events: list[EngineerEvent] = []
        wear_warning = self._threshold("direct_tire_wear_warning_pct", 45.0)
        wear_critical = self._threshold("direct_tire_wear_critical_pct", 70.0)
        life_warning = self._threshold("inferred_tire_life_warning_pct", 35.0)
        life_critical = self._threshold("inferred_tire_life_critical_pct", 15.0)

        if snapshot.tire_wear_mode == TireWearMode.direct and snapshot.tire_wear_pct is not None:
            wear = snapshot.tire_wear_pct
            if wear >= wear_critical:
                priority = Priority.critical
                message = "Tire wear critical"
                action = "Protect the tires"
            elif wear >= wear_warning:
                priority = Priority.warning
                message = "Tire wear high"
                action = "Protect the tires"
            else:
                return []
            events.append(
                self._event(
                    rule_id="direct_tire_wear_path",
                    family="tire_life",
                    dedupe_key="direct_tire_wear_path",
                    priority=priority,
                    message=message,
                    recommended_action=action,
                    snapshot=snapshot,
                    required_fields=["tire_wear_pct"],
                    source_fields=["tire_wear_pct"],
                    validation_notes=["TODO: validate direct tire wear support in live GT7 telemetry"],
                    state_tag=f"wear_{int(wear)}",
                    state_rank=3 if wear >= wear_critical else 2 if wear >= wear_warning else 1,
                )
            )
            return events

        if snapshot.tire_wear_mode in {TireWearMode.inferred, TireWearMode.unknown}:
            front = derived.tire_life_inferred_front
            rear = derived.tire_life_inferred_rear
            worst = self._worst_tire_life(front, rear)
            if worst is None:
                return []
            if worst <= life_critical:
                priority = Priority.critical
                message = "Tire life critical"
                action = "Protect the tires"
            elif worst <= life_warning:
                priority = Priority.warning
                message = "Tire life fading"
                action = "Reduce slip"
            else:
                return []
            events.append(
                self._event(
                    rule_id="inferred_tire_life_path",
                    family="tire_life",
                    dedupe_key="inferred_tire_life_path",
                    priority=priority,
                    message=message,
                    recommended_action=action,
                    snapshot=snapshot,
                    required_fields=["tire_temps_c", "slip_ratio_by_wheel", "throttle_pct", "brake_pct"],
                    source_fields=["tire_temps_c", "slip_ratio_by_wheel", "throttle_pct", "brake_pct"],
                    validation_notes=["TODO: validate inferred tire life formula against live sessions"],
                    state_tag=f"life_{int(worst)}",
                    state_rank=3 if worst <= life_critical else 2 if worst <= life_warning else 1,
                )
            )
        return events

    def _prioritize(self, events: list[EngineerEvent]) -> list[EngineerEvent]:
        deduped: dict[str, EngineerEvent] = {}
        for event in events:
            current = deduped.get(event.dedupe_key)
            if current is None:
                deduped[event.dedupe_key] = event
                continue
            if _PRIORITY_RANK[event.priority] > _PRIORITY_RANK[current.priority]:
                deduped[event.dedupe_key] = event
                continue
            if event.state_rank > current.state_rank:
                deduped[event.dedupe_key] = event
                continue
            if _PRIORITY_RANK[event.priority] == _PRIORITY_RANK[current.priority]:
                # Prefer the more specific state transition when severity is equal.
                if event.rule_id != current.rule_id:
                    deduped[event.dedupe_key] = event
        ordered = list(deduped.values())
        severe = [event for event in ordered if event.priority != Priority.info]
        if severe:
            severe_families = {event.family for event in severe}
            info = [event for event in ordered if event.priority == Priority.info and event.family in severe_families]
            return sorted(
                severe + info,
                key=lambda event: (
                    -_PRIORITY_RANK[event.priority],
                    -event.state_rank,
                    -_INFO_FAMILY_RANK.get(event.family, 0),
                    event.rule_id,
                ),
            )

        if not ordered:
            return []

        best_family = max(
            ordered,
            key=lambda event: (
                _INFO_FAMILY_RANK.get(event.family, 0),
                event.state_rank,
                event.rule_id,
            ),
        ).family
        family_events = [event for event in ordered if event.family == best_family]
        return sorted(family_events, key=lambda event: (-event.state_rank, event.rule_id))

    def _filter_emittable(self, timestamp_ms: int, events: list[EngineerEvent]) -> list[EngineerEvent]:
        emitted: list[EngineerEvent] = []
        for event in events:
            record = self._last_emissions.get(event.dedupe_key)
            fingerprint = self._fingerprint(event)
            cooldown_ms = self._cooldown_for(event.rule_id, 5000)

            if record is None:
                emitted.append(event)
                self._last_emissions[event.dedupe_key] = _EmissionRecord(event.priority, event.state_rank, fingerprint, timestamp_ms)
                continue

            worsened = _PRIORITY_RANK[event.priority] > _PRIORITY_RANK[record.priority]
            rank_worsened = event.state_rank > record.state_rank
            same_state = record.fingerprint == fingerprint
            cooldown_active = timestamp_ms - record.timestamp_ms < cooldown_ms

            if worsened or rank_worsened:
                emitted.append(event)
                self._last_emissions[event.dedupe_key] = _EmissionRecord(event.priority, event.state_rank, fingerprint, timestamp_ms)
                continue

            if same_state and cooldown_active:
                continue

            if not same_state and cooldown_active and _PRIORITY_RANK[event.priority] <= _PRIORITY_RANK[record.priority]:
                continue

            emitted.append(event)
            self._last_emissions[event.dedupe_key] = _EmissionRecord(event.priority, event.state_rank, fingerprint, timestamp_ms)
        return emitted

    def _build_legacy_messages(self, snapshot: NormalizedTelemetryState, history: Sequence[NormalizedTelemetryState] | None) -> list[LegacyEngineerMessage]:
        enabled = dict(getattr(self.config, "enabled_callouts", {}) or {})
        messages: list[LegacyEngineerMessage] = []

        # Compatibility path for the older test suite and the existing web/API shell.
        if enabled.get("fuel_status") or enabled.get("fuel_critical") or enabled.get("projected_fuel_to_finish") or enabled.get("box_this_lap"):
            if snapshot.fuel_laps_remaining_estimate is not None and snapshot.fuel_laps_remaining_estimate <= self._threshold("fuel_critical_laps", 1.0):
                if enabled.get("fuel_status") or enabled.get("fuel_critical"):
                    if self._legacy_can_emit("fuel_critical", snapshot.timestamp_ms):
                        messages.append(
                            LegacyEngineerMessage(
                                id=f"fuel-critical:{snapshot.event_id}",
                                timestamp_ms=snapshot.timestamp_ms,
                                priority=LegacyPriority.critical,
                                category="fuel",
                                text=f"Fuel critical, {snapshot.fuel_laps_remaining_estimate:.1f} laps left",
                            )
                        )
            projected_margin = snapshot.projected_fuel_to_finish_liters
            if projected_margin is not None and projected_margin < 0:
                if enabled.get("box_this_lap"):
                    if self._legacy_can_emit("box_this_lap", snapshot.timestamp_ms):
                        messages.append(
                            LegacyEngineerMessage(
                                id=f"box:{snapshot.event_id}",
                                timestamp_ms=snapshot.timestamp_ms,
                                priority=LegacyPriority.critical,
                                category="fuel",
                                text="Box this lap",
                            )
                        )
                if enabled.get("projected_fuel_to_finish"):
                    if self._legacy_can_emit("projected_fuel_to_finish", snapshot.timestamp_ms):
                        messages.append(
                            LegacyEngineerMessage(
                                id=f"fuel-margin:{snapshot.event_id}",
                                timestamp_ms=snapshot.timestamp_ms,
                                priority=LegacyPriority.warning,
                                category="fuel",
                                text=f"Fuel to finish: deficit {abs(projected_margin):.1f} L",
                            )
                        )

        if enabled.get("laps_remaining") and snapshot.laps_remaining == 2:
            if self._legacy_can_emit("laps_remaining", snapshot.timestamp_ms):
                messages.append(
                    LegacyEngineerMessage(
                        id=f"laps-remaining:{snapshot.event_id}",
                        timestamp_ms=snapshot.timestamp_ms,
                        priority=LegacyPriority.info,
                        category="race",
                        text="2 laps remaining",
                    )
                )

        if enabled.get("final_lap") and snapshot.laps_remaining == 1:
            if self._legacy_can_emit("final_lap", snapshot.timestamp_ms):
                messages.append(
                    LegacyEngineerMessage(
                        id=f"final-lap:{snapshot.event_id}",
                        timestamp_ms=snapshot.timestamp_ms,
                        priority=LegacyPriority.warning,
                        category="race",
                        text="Final lap",
                    )
                )

        if enabled.get("best_lap") and snapshot.last_lap_time_ms is not None and snapshot.best_lap_time_ms is not None:
            improvement = snapshot.best_lap_time_ms - snapshot.last_lap_time_ms
            if improvement >= self._threshold("best_lap_improvement_ms", 250.0):
                if self._legacy_can_emit("best_lap", snapshot.timestamp_ms):
                    messages.append(
                        LegacyEngineerMessage(
                            id=f"best-lap:{snapshot.event_id}",
                            timestamp_ms=snapshot.timestamp_ms,
                            priority=LegacyPriority.info,
                            category="pace",
                            text=f"New best lap, {improvement / 1000.0:.3f}s quicker",
                        )
                    )

        return messages

    def _legacy_can_emit(self, key: str, timestamp_ms: int) -> bool:
        cooldown_ms = self._cooldown_for(key, 0 if key == "best_lap" else 30000)
        last_timestamp = self._legacy_last_emissions.get(key)
        if last_timestamp is not None and timestamp_ms - last_timestamp < cooldown_ms:
            return False
        self._legacy_last_emissions[key] = timestamp_ms
        return True

    def _event(
        self,
        *,
        rule_id: str,
        family: str,
        dedupe_key: str,
        priority: Priority,
        message: str,
        recommended_action: str,
        snapshot: NormalizedTelemetryState,
        required_fields: list[str],
        source_fields: list[str],
        validation_notes: list[str],
        state_tag: str,
        state_rank: int,
    ) -> EngineerEvent:
        return EngineerEvent(
            event_id=f"{rule_id}:{snapshot.session_id}:{snapshot.timestamp_ms}",
            timestamp_ms=snapshot.timestamp_ms,
            rule_id=rule_id,
            dedupe_key=dedupe_key,
            family=family,
            priority=priority,
            category=family,
            message=message,
            recommended_action=recommended_action,
            state_rank=state_rank,
            source_event_id=snapshot.event_id,
            required_fields=required_fields,
            source_fields=source_fields,
            validation_notes=validation_notes + [f"state={state_tag}"],
        )

    def _coerce_snapshot(
        self, snapshot: NormalizedTelemetryState | RawTelemetryInput | Any
    ) -> NormalizedTelemetryState:
        if isinstance(snapshot, NormalizedTelemetryState):
            return snapshot
        if isinstance(snapshot, RawTelemetryInput):
            data = snapshot.model_dump()
        elif hasattr(snapshot, "model_dump"):
            data = snapshot.model_dump()
        elif isinstance(snapshot, dict):
            data = dict(snapshot)
        else:
            data = {
                key: getattr(snapshot, key)
                for key in self._normalized_field_names()
                if hasattr(snapshot, key)
            }
        filtered = {key: value for key, value in data.items() if key in self._normalized_field_names()}
        filtered.setdefault("source_mode", SourceMode.unknown)
        filtered.setdefault("connection_state", ConnectionState.unknown)
        if "event_id" not in filtered:
            filtered["event_id"] = f"{filtered.get('session_id', 'session')}-{filtered.get('timestamp_ms', 0)}"
        return NormalizedTelemetryState(**filtered)

    def _normalized_field_names(self) -> set[str]:
        return set(NormalizedTelemetryState.__dataclass_fields__.keys())

    def _fingerprint(self, event: EngineerEvent) -> str:
        return "|".join(
            [
                event.rule_id,
                event.priority.value,
                event.message,
                event.recommended_action,
                ",".join(event.validation_notes or []),
            ]
        )

    def _threshold(self, key: str, default: float) -> float:
        return float(self.config.thresholds.get(key, default))

    def _cooldown_for(self, key: str, default: int) -> int:
        return int(self.config.cooldowns_ms.get(key, default))

    def _state_rank_for_fuel(self, state: str) -> int:
        return {
            "healthy": 0,
            "borderline": 1,
            "save_required": 2,
            "critical": 3,
        }.get(state, 0)

    def _fuel_is_critical(self, projected_margin: float | None, fuel_laps: float | None) -> bool:
        if projected_margin is not None and projected_margin < 0:
            return True
        if fuel_laps is not None and fuel_laps <= self._threshold("fuel_critical_laps", 1.0):
            return True
        return False

    def _fuel_needs_save(self, projected_margin: float | None, fuel_laps: float | None, save_threshold: float) -> bool:
        if projected_margin is None and fuel_laps is None:
            return False
        if projected_margin is not None and projected_margin < save_threshold:
            return True
        if fuel_laps is not None and fuel_laps <= self._threshold("fuel_save_required_laps", 1.5):
            return True
        return False

    def _fuel_borderline(
        self,
        projected_margin: float | None,
        fuel_laps: float | None,
        borderline_threshold: float,
        healthy_threshold: float,
    ) -> bool:
        if projected_margin is not None and borderline_threshold <= projected_margin < healthy_threshold:
            return True
        if fuel_laps is not None and self._threshold("fuel_save_required_laps", 1.5) < fuel_laps < healthy_threshold + 1.0:
            return True
        return False

    def _should_emit_healthy_fuel(self) -> bool:
        return True

    def _tire_life_is_low(self, derived: DerivedTelemetryState) -> bool:
        values = [value for value in (derived.tire_life_inferred_front, derived.tire_life_inferred_rear) if value is not None]
        return bool(values and min(values) <= self._threshold("inferred_tire_life_warning_pct", 35.0))

    def _worst_tire_life(self, front: float | None, rear: float | None) -> float | None:
        values = [value for value in (front, rear) if value is not None]
        if not values:
            return None
        return min(values)

    def _recent_lap_times(
        self,
        history: Sequence[NormalizedTelemetryState],
        current: NormalizedTelemetryState,
    ) -> list[int]:
        times = [sample.last_lap_time_ms for sample in history if sample.last_lap_time_ms is not None]
        if current.last_lap_time_ms is not None:
            times.append(current.last_lap_time_ms)
        return [time for time in times if time is not None]

    def _to_legacy_message(self, envelope: MessageEnvelope) -> LegacyEngineerMessage:
        event = envelope.event
        return LegacyEngineerMessage(
            id=event.event_id,
            timestamp_ms=event.timestamp_ms,
            priority=LegacyPriority(event.priority.value),
            category=event.category,
            text=event.message,
            ttl_ms=envelope.ttl_ms,
            source_event_id=event.source_event_id,
            suppressed=event.suppressed,
            suppression_reason=event.suppression_reason,
        )

    def _to_legacy_connection_state(self, state: ConnectionState) -> LegacyConnectionState:
        return LegacyConnectionState(state.value)

    def _to_legacy_source_mode(self, state: SourceMode) -> LegacySourceMode:
        return LegacySourceMode(state.value)

    def _stale_ms(self, snapshot: NormalizedTelemetryState) -> int:
        if snapshot.source_mode == SourceMode.live:
            import time

            return max(0, int(time.time() * 1000) - snapshot.timestamp_ms)
        return 0
