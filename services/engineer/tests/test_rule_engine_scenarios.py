from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import unittest

from app.config import EngineerConfig
from app.engine.engine import RuleEngine
from app.telemetry_models import ConnectionState, NormalizedTelemetryState, SourceMode, TireWearMode


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    frames: list[NormalizedTelemetryState]
    expected_messages: list[list[str]]


class RuleEngineScenarioTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = EngineerConfig(
            cooldowns_ms={
                "fuel_margin_healthy": 30000,
                "borderline_fuel": 30000,
                "fuel_save_required": 30000,
                "fuel_critical": 30000,
                "two_laps_remaining": 30000,
                "final_lap": 60000,
                "end_phase_push": 30000,
                "rear_overheating": 20000,
                "front_overheating": 20000,
                "cold_tires": 20000,
                "understeer_building": 20000,
                "rear_grip_falling": 20000,
                "wheelspin_detected": 15000,
                "brake_instability": 15000,
                "overdriving": 30000,
                "on_best_lap_pace": 0,
                "losing_pace": 20000,
                "pace_inconsistency": 20000,
                "degradation_phase_detected": 30000,
                "direct_tire_wear_path": 30000,
                "inferred_tire_life_path": 30000,
            },
            thresholds={
                "fuel_margin_healthy_laps": 2.0,
                "fuel_borderline_laps": 0.5,
                "fuel_save_required_laps": 1.5,
                "fuel_critical_laps": 1.0,
                "end_phase_push_laps": 3.0,
                "tire_temp_hot_c": 98.0,
                "tire_temp_cold_c": 65.0,
                "understeer_temp_delta_c": 4.0,
                "rear_grip_slip": 0.05,
                "rear_exit_slip_index": 0.05,
                "wheelspin_slip": 0.08,
                "wheelspin_throttle_pct": 40.0,
                "brake_instability_index": 0.03,
                "brake_instability_brake_pct": 40.0,
                "best_lap_pace_window_ms": 150.0,
                "pace_drop_ms": 250.0,
                "pace_inconsistency_range_ms": 600.0,
                "degradation_phase_index": 55.0,
                "direct_tire_wear_warning_pct": 45.0,
                "direct_tire_wear_critical_pct": 70.0,
                "inferred_tire_life_warning_pct": 35.0,
                "inferred_tire_life_critical_pct": 15.0,
            },
        )

    def test_rule_engine_scenarios(self) -> None:
        for scenario in self._scenarios():
            with self.subTest(scenario=scenario.name):
                engine = RuleEngine(self.config)
                outputs: list[list[str]] = []
                for frame in scenario.frames:
                    events, _envelopes, _derived = engine.evaluate(frame)
                    outputs.append([event.message for event in events])
                self.assertEqual(outputs, scenario.expected_messages, scenario.description)

    def _scenarios(self) -> list[Scenario]:
        sample_frames = self._load_sample_frames()

        return [
            Scenario(
                name="fuel_critical_before_finish",
                description="Replay sample where fuel margin degrades from borderline to critical before the final lap.",
                frames=sample_frames[2:],
                expected_messages=[
                    ["End-phase push"],
                    ["Borderline fuel"],
                    ["Fuel critical", "Final lap"],
                ],
            ),
            Scenario(
                name="borderline_fuel_with_successful_save",
                description="Synthetic recovery from borderline fuel back to a healthy margin.",
                frames=[
                    self._snapshot(1_000, laps_remaining=5, fuel_laps_remaining_estimate=2.1, projected_fuel_to_finish_liters=0.4),
                    self._snapshot(61_000, laps_remaining=5, fuel_laps_remaining_estimate=3.4, projected_fuel_to_finish_liters=1.7),
                ],
                expected_messages=[
                    ["Borderline fuel"],
                    ["Fuel margin healthy"],
                ],
            ),
            Scenario(
                name="final_lap_trigger",
                description="Synthetic two-lap-to-final-lap transition.",
                frames=[
                    self._snapshot(1_000, laps_remaining=2),
                    self._snapshot(61_000, laps_remaining=1),
                ],
                expected_messages=[
                    ["2 laps remaining"],
                    ["Final lap"],
                ],
            ),
            Scenario(
                name="rear_overheating_from_repeated_exit_slip",
                description="Rear slip ramps until the rear axle overheats and wheelspin appears.",
                frames=[
                    self._snapshot(
                        1_000,
                        tire_temps_c={"front_left": 90.0, "front_right": 90.0, "rear_left": 99.0, "rear_right": 100.0},
                        slip_ratio_by_wheel={"front_left": 0.01, "front_right": 0.01, "rear_left": 0.20, "rear_right": 0.19},
                        throttle_pct=35.0,
                        brake_pct=20.0,
                        fuel_liters=None,
                        fuel_laps_remaining_estimate=None,
                        projected_fuel_to_finish_liters=None,
                        last_lap_time_ms=None,
                        best_lap_time_ms=None,
                    ),
                    self._snapshot(
                        26_000,
                        tire_temps_c={"front_left": 90.0, "front_right": 90.0, "rear_left": 102.0, "rear_right": 103.0},
                        slip_ratio_by_wheel={"front_left": 0.01, "front_right": 0.01, "rear_left": 0.24, "rear_right": 0.23},
                        throttle_pct=45.0,
                        brake_pct=20.0,
                        fuel_liters=None,
                        fuel_laps_remaining_estimate=None,
                        projected_fuel_to_finish_liters=None,
                        last_lap_time_ms=None,
                        best_lap_time_ms=None,
                    ),
                ],
                expected_messages=[
                    ["Rear grip falling", "Rear overheating"],
                    ["Rear grip falling", "Rear overheating", "Wheelspin detected"],
                ],
            ),
            Scenario(
                name="front_overheating_from_repeated_entry_overload",
                description="Repeated trail-brake load overheats the front axle.",
                frames=[
                    self._snapshot(
                        1_000,
                        tire_temps_c={"front_left": 100.0, "front_right": 101.0, "rear_left": 88.0, "rear_right": 88.0},
                        slip_ratio_by_wheel={"front_left": -0.05, "front_right": -0.04, "rear_left": -0.10, "rear_right": -0.10},
                        throttle_pct=20.0,
                        brake_pct=70.0,
                        fuel_liters=None,
                        fuel_laps_remaining_estimate=None,
                        projected_fuel_to_finish_liters=None,
                        last_lap_time_ms=None,
                        best_lap_time_ms=None,
                    ),
                    self._snapshot(
                        26_000,
                        tire_temps_c={"front_left": 103.0, "front_right": 104.0, "rear_left": 88.0, "rear_right": 88.0},
                        slip_ratio_by_wheel={"front_left": -0.06, "front_right": -0.05, "rear_left": -0.11, "rear_right": -0.11},
                        throttle_pct=18.0,
                        brake_pct=75.0,
                        fuel_liters=None,
                        fuel_laps_remaining_estimate=None,
                        projected_fuel_to_finish_liters=None,
                        last_lap_time_ms=None,
                        best_lap_time_ms=None,
                    ),
                ],
                expected_messages=[
                    ["Front overheating", "Brake instability"],
                    ["Front overheating", "Brake instability"],
                ],
            ),
            Scenario(
                name="cold_tires_after_reset",
                description="Cold tires immediately after a reset or reset-like state.",
                frames=[
                    self._snapshot(
                        1_000,
                        tire_temps_c={"front_left": 61.0, "front_right": 62.0, "rear_left": 60.0, "rear_right": 61.0},
                        fuel_liters=None,
                        fuel_laps_remaining_estimate=None,
                        projected_fuel_to_finish_liters=None,
                        last_lap_time_ms=None,
                        best_lap_time_ms=None,
                    )
                ],
                expected_messages=[["Tires cold"]],
            ),
            Scenario(
                name="understeer_trend",
                description="Front axle heats more than the rear until understeer is building.",
                frames=[
                    self._snapshot(
                        1_000,
                        tire_temps_c={"front_left": 90.0, "front_right": 90.0, "rear_left": 88.0, "rear_right": 88.0},
                        slip_ratio_by_wheel={"front_left": 0.01, "front_right": 0.01, "rear_left": 0.02, "rear_right": 0.02},
                        fuel_liters=None,
                        fuel_laps_remaining_estimate=None,
                        projected_fuel_to_finish_liters=None,
                        last_lap_time_ms=None,
                        best_lap_time_ms=None,
                    ),
                    self._snapshot(
                        2_000,
                        tire_temps_c={"front_left": 91.0, "front_right": 91.0, "rear_left": 88.0, "rear_right": 88.0},
                        slip_ratio_by_wheel={"front_left": 0.01, "front_right": 0.01, "rear_left": 0.02, "rear_right": 0.02},
                        fuel_liters=None,
                        fuel_laps_remaining_estimate=None,
                        projected_fuel_to_finish_liters=None,
                        last_lap_time_ms=None,
                        best_lap_time_ms=None,
                    ),
                    self._snapshot(
                        3_000,
                        tire_temps_c={"front_left": 96.0, "front_right": 96.0, "rear_left": 88.0, "rear_right": 88.0},
                        slip_ratio_by_wheel={"front_left": 0.01, "front_right": 0.01, "rear_left": 0.03, "rear_right": 0.03},
                        fuel_liters=None,
                        fuel_laps_remaining_estimate=None,
                        projected_fuel_to_finish_liters=None,
                        last_lap_time_ms=None,
                        best_lap_time_ms=None,
                    ),
                ],
                expected_messages=[[], [], ["Understeer building"]],
            ),
            Scenario(
                name="rear_grip_loss_trend",
                description="Rear slip ramps until the rear grip is clearly falling away.",
                frames=[
                    self._snapshot(
                        1_000,
                        tire_temps_c={"front_left": 90.0, "front_right": 90.0, "rear_left": 90.0, "rear_right": 90.0},
                        slip_ratio_by_wheel={"front_left": 0.01, "front_right": 0.01, "rear_left": 0.10, "rear_right": 0.10},
                        throttle_pct=30.0,
                        fuel_liters=None,
                        fuel_laps_remaining_estimate=None,
                        projected_fuel_to_finish_liters=None,
                        last_lap_time_ms=None,
                        best_lap_time_ms=None,
                    ),
                    self._snapshot(
                        2_000,
                        tire_temps_c={"front_left": 90.0, "front_right": 90.0, "rear_left": 90.0, "rear_right": 90.0},
                        slip_ratio_by_wheel={"front_left": 0.01, "front_right": 0.01, "rear_left": 0.13, "rear_right": 0.13},
                        throttle_pct=30.0,
                        fuel_liters=None,
                        fuel_laps_remaining_estimate=None,
                        projected_fuel_to_finish_liters=None,
                        last_lap_time_ms=None,
                        best_lap_time_ms=None,
                    ),
                    self._snapshot(
                        3_000,
                        tire_temps_c={"front_left": 90.0, "front_right": 90.0, "rear_left": 90.0, "rear_right": 90.0},
                        slip_ratio_by_wheel={"front_left": 0.01, "front_right": 0.01, "rear_left": 0.18, "rear_right": 0.18},
                        throttle_pct=30.0,
                        fuel_liters=None,
                        fuel_laps_remaining_estimate=None,
                        projected_fuel_to_finish_liters=None,
                        last_lap_time_ms=None,
                        best_lap_time_ms=None,
                    ),
                ],
                expected_messages=[[], [], ["Rear grip falling"]],
            ),
            Scenario(
                name="wheelspin_on_throttle",
                description="Throttle application overwhelms the rear axle.",
                frames=[
                    self._snapshot(
                        1_000,
                        tire_temps_c={"front_left": 88.0, "front_right": 88.0, "rear_left": 90.0, "rear_right": 90.0},
                        slip_ratio_by_wheel={"front_left": 0.01, "front_right": 0.01, "rear_left": 0.11, "rear_right": 0.10},
                        throttle_pct=82.0,
                        brake_pct=0.0,
                        fuel_liters=None,
                        fuel_laps_remaining_estimate=None,
                        projected_fuel_to_finish_liters=None,
                        last_lap_time_ms=None,
                        best_lap_time_ms=None,
                    )
                ],
                expected_messages=[["Rear grip falling", "Wheelspin detected"]],
            ),
            Scenario(
                name="brake_instability",
                description="Heavy braking creates front-end instability.",
                frames=[
                    self._snapshot(
                        1_000,
                        tire_temps_c={"front_left": 90.0, "front_right": 90.0, "rear_left": 88.0, "rear_right": 88.0},
                        slip_ratio_by_wheel={"front_left": -0.05, "front_right": -0.04, "rear_left": 0.01, "rear_right": 0.01},
                        throttle_pct=10.0,
                        brake_pct=72.0,
                        fuel_liters=None,
                        fuel_laps_remaining_estimate=None,
                        projected_fuel_to_finish_liters=None,
                        last_lap_time_ms=None,
                        best_lap_time_ms=None,
                    )
                ],
                expected_messages=[["Brake instability"]],
            ),
            Scenario(
                name="best_lap_pace",
                description="A lap matches the best lap closely enough to call out.",
                frames=[
                    self._snapshot(
                        1_000,
                        lap_time_ms=90_000,
                        last_lap_time_ms=90_000,
                        best_lap_time_ms=90_000,
                        fuel_liters=10.0,
                        fuel_laps_remaining_estimate=None,
                        projected_fuel_to_finish_liters=None,
                        tire_temps_c={"front_left": 85.0, "front_right": 85.0, "rear_left": 85.0, "rear_right": 85.0},
                        slip_ratio_by_wheel={"front_left": 0.0, "front_right": 0.0, "rear_left": 0.0, "rear_right": 0.0},
                    )
                ],
                expected_messages=[["On best-lap pace"]],
            ),
            Scenario(
                name="pace_drop_from_degradation",
                description="Pace starts on target, then drops as the stint degrades.",
                frames=[
                    self._snapshot(
                        1_000,
                        lap_time_ms=90_000,
                        last_lap_time_ms=90_000,
                        best_lap_time_ms=90_000,
                        fuel_liters=10.0,
                        fuel_laps_remaining_estimate=None,
                        projected_fuel_to_finish_liters=None,
                        tire_temps_c={"front_left": 85.0, "front_right": 85.0, "rear_left": 85.0, "rear_right": 85.0},
                        slip_ratio_by_wheel={"front_left": 0.0, "front_right": 0.0, "rear_left": 0.0, "rear_right": 0.0},
                    ),
                    self._snapshot(
                        61_000,
                        lap_time_ms=92_300,
                        last_lap_time_ms=92_300,
                        best_lap_time_ms=90_000,
                        fuel_liters=9.3,
                        fuel_laps_remaining_estimate=None,
                        projected_fuel_to_finish_liters=None,
                        tire_temps_c={"front_left": 85.0, "front_right": 85.0, "rear_left": 85.0, "rear_right": 85.0},
                        slip_ratio_by_wheel={"front_left": 0.0, "front_right": 0.0, "rear_left": 0.0, "rear_right": 0.0},
                    ),
                    self._snapshot(
                        121_000,
                        lap_time_ms=94_500,
                        last_lap_time_ms=94_500,
                        best_lap_time_ms=90_000,
                        fuel_liters=8.6,
                        fuel_laps_remaining_estimate=None,
                        projected_fuel_to_finish_liters=None,
                        tire_temps_c={"front_left": 86.0, "front_right": 86.0, "rear_left": 95.0, "rear_right": 95.0},
                        slip_ratio_by_wheel={"front_left": 0.0, "front_right": 0.0, "rear_left": 0.17, "rear_right": 0.17},
                        throttle_pct=30.0,
                        brake_pct=10.0,
                    ),
                ],
                expected_messages=[
                    ["On best-lap pace"],
                    ["Losing pace"],
                    ["Rear grip falling", "Degradation phase", "Losing pace", "Pace inconsistent"],
                ],
            ),
            Scenario(
                name="inferred_tire_life_decline",
                description="Inferred tire life falls from healthy to critical without direct wear telemetry.",
                frames=[
                    self._snapshot(
                        1_000,
                        tire_wear_mode=TireWearMode.inferred,
                        tire_temps_c={"front_left": 95.0, "front_right": 95.0, "rear_left": 96.0, "rear_right": 96.0},
                        slip_ratio_by_wheel={"front_left": 0.05, "front_right": 0.05, "rear_left": 0.06, "rear_right": 0.06},
                        throttle_pct=40.0,
                        brake_pct=20.0,
                        fuel_liters=None,
                        fuel_laps_remaining_estimate=None,
                        projected_fuel_to_finish_liters=None,
                        last_lap_time_ms=None,
                        best_lap_time_ms=None,
                    ),
                    self._snapshot(
                        61_000,
                        tire_wear_mode=TireWearMode.inferred,
                        tire_temps_c={"front_left": 110.0, "front_right": 110.0, "rear_left": 112.0, "rear_right": 112.0},
                        slip_ratio_by_wheel={"front_left": 0.08, "front_right": 0.08, "rear_left": 0.10, "rear_right": 0.10},
                        throttle_pct=60.0,
                        brake_pct=30.0,
                        fuel_liters=None,
                        fuel_laps_remaining_estimate=None,
                        projected_fuel_to_finish_liters=None,
                        last_lap_time_ms=None,
                        best_lap_time_ms=None,
                    ),
                ],
                expected_messages=[[], ["Tire life critical"]],
            ),
        ]

    def _load_sample_frames(self) -> list[NormalizedTelemetryState]:
        path = Path(__file__).resolve().parents[3] / "contracts" / "sample_normalized_telemetry.jsonl"
        frames: list[NormalizedTelemetryState] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            frames.append(NormalizedTelemetryState.model_validate_json(line))
        return frames

    def _snapshot(self, timestamp_ms: int, **overrides) -> NormalizedTelemetryState:
        base = dict(
            event_id=f"evt-{timestamp_ms}",
            timestamp_ms=timestamp_ms,
            session_id="session-1",
            source="replay",
            source_mode=SourceMode.replay,
            connection_state=ConnectionState.connected,
            track_name="Trial Mountain",
            session_type="race",
            lap_number=1,
            laps_total=15,
            laps_remaining=8,
            lap_time_ms=90_000,
            last_lap_time_ms=None,
            best_lap_time_ms=None,
            fuel_liters=None,
            fuel_capacity_liters=60.0,
            fuel_pct=None,
            fuel_laps_remaining_estimate=None,
            projected_fuel_to_finish_liters=None,
            position=1,
            speed_kph=160.0,
            throttle_pct=30.0,
            brake_pct=10.0,
            gear=4,
            rpm=6000,
            tire_temps_c={"front_left": 85.0, "front_right": 85.0, "rear_left": 85.0, "rear_right": 85.0},
            wheel_speeds_mps={"front_left": 40.0, "front_right": 40.0, "rear_left": 40.0, "rear_right": 40.0},
            slip_ratio_by_wheel={"front_left": 0.0, "front_right": 0.0, "rear_left": 0.0, "rear_right": 0.0},
            tire_wear_pct=None,
            tire_wear_mode=TireWearMode.direct,
            flags={"yellow": False, "pit": False},
            weather={"rain_intensity": 0.0, "track_wetness": 0.0},
            derived={},
            raw={},
            validation_warnings=[],
        )
        base.update(overrides)
        return NormalizedTelemetryState(**base)


if __name__ == "__main__":
    unittest.main()
