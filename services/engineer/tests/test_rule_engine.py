from __future__ import annotations

import unittest

from app.config import EngineerConfig
from app.engine.engine import RuleEngine
from app.telemetry_models import ConnectionState, NormalizedTelemetryState, SourceMode, TireWearMode


class RuleEngineTests(unittest.TestCase):
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
        self.engine = RuleEngine(self.config)

    def test_fuel_strategy_escalates_and_dedupes(self) -> None:
        snapshots = [
            self._snapshot(1_000, laps_remaining=5, fuel_laps_remaining_estimate=6.0, projected_fuel_to_finish_liters=3.0),
            self._snapshot(5_000, laps_remaining=5, fuel_laps_remaining_estimate=2.1, projected_fuel_to_finish_liters=1.2),
            self._snapshot(10_000, laps_remaining=5, fuel_laps_remaining_estimate=1.2, projected_fuel_to_finish_liters=0.3),
            self._snapshot(15_000, laps_remaining=5, fuel_laps_remaining_estimate=0.8, projected_fuel_to_finish_liters=-0.4),
            self._snapshot(16_000, laps_remaining=5, fuel_laps_remaining_estimate=0.7, projected_fuel_to_finish_liters=-0.5),
        ]

        outputs = [self._messages(snapshot) for snapshot in snapshots]

        self.assertEqual(outputs[0], ["Fuel margin healthy"])
        self.assertEqual(outputs[1], ["Borderline fuel"])
        self.assertEqual(outputs[2], ["Fuel save required"])
        self.assertEqual(outputs[3], ["Fuel critical"])
        self.assertEqual(outputs[4], [])

    def test_race_phase_messages(self) -> None:
        snapshots = [
            self._snapshot(1_000, laps_remaining=3, fuel_laps_remaining_estimate=10.0, projected_fuel_to_finish_liters=5.0),
            self._snapshot(61_000, laps_remaining=2, fuel_laps_remaining_estimate=10.0, projected_fuel_to_finish_liters=5.0),
            self._snapshot(121_000, laps_remaining=1, fuel_laps_remaining_estimate=10.0, projected_fuel_to_finish_liters=5.0),
        ]

        outputs = [self._messages(snapshot) for snapshot in snapshots]

        self.assertEqual(outputs[0], ["End-phase push"])
        self.assertEqual(outputs[1], ["2 laps remaining"])
        self.assertEqual(outputs[2], ["Final lap"])

    def test_tire_grip_and_traction_rules(self) -> None:
        hot = self._snapshot(
            1_000,
            laps_remaining=6,
            tire_wear_mode=TireWearMode.direct,
            tire_wear_pct=None,
            tire_temps_c={"front_left": 103.0, "front_right": 102.0, "rear_left": 101.0, "rear_right": 100.0},
            slip_ratio_by_wheel={"front_left": -0.05, "front_right": -0.04, "rear_left": 0.12, "rear_right": 0.10},
            throttle_pct=80.0,
            brake_pct=60.0,
        )
        cold = self._snapshot(
            61_000,
            laps_remaining=6,
            tire_wear_mode=TireWearMode.direct,
            tire_wear_pct=None,
            tire_temps_c={"front_left": 60.0, "front_right": 61.0, "rear_left": 59.0, "rear_right": 60.0},
            slip_ratio_by_wheel={"front_left": 0.0, "front_right": 0.0, "rear_left": 0.0, "rear_right": 0.0},
            throttle_pct=20.0,
            brake_pct=10.0,
        )
        understeer = self._snapshot(
            121_000,
            laps_remaining=6,
            tire_wear_mode=TireWearMode.direct,
            tire_wear_pct=None,
            tire_temps_c={"front_left": 94.0, "front_right": 94.0, "rear_left": 88.0, "rear_right": 88.0},
            slip_ratio_by_wheel={"front_left": 0.01, "front_right": 0.01, "rear_left": 0.06, "rear_right": 0.06},
            throttle_pct=30.0,
            brake_pct=10.0,
        )

        hot_messages = self._messages(hot)
        cold_messages = self._messages(cold)
        understeer_messages = self._messages(understeer)

        self.assertIn("Rear overheating", hot_messages)
        self.assertIn("Front overheating", hot_messages)
        self.assertIn("Rear grip falling", hot_messages)
        self.assertIn("Wheelspin detected", hot_messages)
        self.assertIn("Brake instability", hot_messages)
        self.assertIn("Overdriving", hot_messages)
        self.assertEqual(cold_messages, ["Tires cold"])
        self.assertEqual(understeer_messages, ["Understeer building"])

    def test_pace_and_degradation_rules(self) -> None:
        snapshots = [
            self._snapshot(
                1_000,
                laps_remaining=7,
                lap_time_ms=90_000,
                last_lap_time_ms=90_000,
                best_lap_time_ms=90_000,
                tire_wear_mode=TireWearMode.direct,
                tire_wear_pct=None,
                tire_temps_c={"front_left": 85.0, "front_right": 85.0, "rear_left": 85.0, "rear_right": 85.0},
                slip_ratio_by_wheel={"front_left": 0.0, "front_right": 0.0, "rear_left": 0.0, "rear_right": 0.0},
                throttle_pct=40.0,
                brake_pct=10.0,
            ),
            self._snapshot(
                61_000,
                laps_remaining=7,
                lap_time_ms=92_000,
                last_lap_time_ms=92_000,
                best_lap_time_ms=90_000,
                tire_wear_mode=TireWearMode.direct,
                tire_wear_pct=None,
                tire_temps_c={"front_left": 85.0, "front_right": 85.0, "rear_left": 85.0, "rear_right": 85.0},
                slip_ratio_by_wheel={"front_left": 0.0, "front_right": 0.0, "rear_left": 0.0, "rear_right": 0.0},
                throttle_pct=40.0,
                brake_pct=10.0,
            ),
            self._snapshot(
                121_000,
                laps_remaining=7,
                lap_time_ms=94_000,
                last_lap_time_ms=94_000,
                best_lap_time_ms=90_000,
                tire_wear_mode=TireWearMode.direct,
                tire_wear_pct=None,
                tire_temps_c={"front_left": 130.0, "front_right": 130.0, "rear_left": 120.0, "rear_right": 120.0},
                slip_ratio_by_wheel={"front_left": 0.02, "front_right": 0.02, "rear_left": 0.02, "rear_right": 0.02},
                throttle_pct=20.0,
                brake_pct=10.0,
            ),
        ]

        outputs = [self._messages(snapshot) for snapshot in snapshots]

        self.assertIn("On best-lap pace", outputs[0])
        self.assertIn("Losing pace", outputs[1])
        self.assertIn("Pace inconsistent", outputs[2])
        self.assertIn("Degradation phase", outputs[2])

    def test_tire_life_paths(self) -> None:
        direct = self._snapshot(
            1_000,
            laps_remaining=6,
            tire_wear_mode=TireWearMode.direct,
            tire_wear_pct=72.0,
        )
        inferred = self._snapshot(
            61_000,
            laps_remaining=6,
            tire_wear_mode=TireWearMode.inferred,
            tire_temps_c={"front_left": 130.0, "front_right": 130.0, "rear_left": 130.0, "rear_right": 130.0},
            slip_ratio_by_wheel={"front_left": 0.12, "front_right": 0.12, "rear_left": 0.12, "rear_right": 0.12},
            throttle_pct=20.0,
            brake_pct=0.0,
        )

        self.assertEqual(self._messages(direct), ["Tire wear critical"])
        self.assertEqual(self._messages(inferred), ["Tire life critical"])

    def _messages(self, snapshot: NormalizedTelemetryState) -> list[str]:
        events, _envelopes, _derived = self.engine.evaluate(snapshot)
        return [event.message for event in events]

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
            laps_remaining=14,
            lap_time_ms=90_000,
            last_lap_time_ms=90_000,
            best_lap_time_ms=90_000,
            fuel_liters=10.0,
            fuel_capacity_liters=60.0,
            fuel_pct=16.6666666667,
            fuel_laps_remaining_estimate=5.0,
            projected_fuel_to_finish_liters=2.0,
            position=1,
            speed_kph=160.0,
            throttle_pct=40.0,
            brake_pct=10.0,
            gear=4,
            rpm=6000,
            tire_temps_c={"front_left": 85.0, "front_right": 85.0, "rear_left": 85.0, "rear_right": 85.0},
            wheel_speeds_mps={"front_left": 40.0, "front_right": 40.0, "rear_left": 40.0, "rear_right": 40.0},
            slip_ratio_by_wheel={"front_left": 0.0, "front_right": 0.0, "rear_left": 0.0, "rear_right": 0.0},
            tire_wear_pct=None,
            tire_wear_mode=TireWearMode.unknown,
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

