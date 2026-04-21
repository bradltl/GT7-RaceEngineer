from __future__ import annotations

from math import isclose
from pathlib import Path
import unittest

from app.telemetry_calculations import (
    build_derived_telemetry_state,
    calculate_avg_front_temp,
    calculate_avg_rear_temp,
    calculate_degradation_index,
    calculate_fuel_pct,
    calculate_front_avg_slip,
    calculate_front_brake_instability_index,
    calculate_front_rear_temp_delta,
    calculate_lap_delta_vs_best,
    calculate_laps_remaining,
    calculate_pace_trend_last_n_laps,
    calculate_projected_finish_margin_laps,
    calculate_projected_laps_remaining,
    calculate_rear_avg_slip,
    calculate_rear_exit_slip_index,
    calculate_rolling_fuel_burn_per_lap,
    calculate_tire_life_inferred_front,
    calculate_tire_life_inferred_rear,
)
from app.telemetry_models import NormalizedTelemetryState, TireWearMode


class TelemetryCalculationTests(unittest.TestCase):
    def test_laps_remaining(self) -> None:
        self.assertEqual(calculate_laps_remaining(10, 15), 5)
        self.assertEqual(calculate_laps_remaining(10, 15, explicit_laps_remaining=4), 4)
        self.assertIsNone(calculate_laps_remaining(None, 15))

    def test_fuel_pct(self) -> None:
        self.assertTrue(isclose(calculate_fuel_pct(11.8, 60.0), 19.6666666667, rel_tol=1e-9))
        self.assertIsNone(calculate_fuel_pct(10.0, 0.0))

    def test_rolling_fuel_burn_per_lap(self) -> None:
        history = self._load_sample_frames()
        burn = calculate_rolling_fuel_burn_per_lap(history, window_laps=3)
        self.assertTrue(isclose(burn, 2.9666666667, rel_tol=1e-9))

    def test_projected_laps_remaining(self) -> None:
        self.assertTrue(isclose(calculate_projected_laps_remaining(1.0, 2.0), 0.5, rel_tol=1e-9))
        self.assertIsNone(calculate_projected_laps_remaining(1.0, 0.0))

    def test_projected_finish_margin_laps(self) -> None:
        self.assertTrue(isclose(calculate_projected_finish_margin_laps(2.5, 1), 1.5, rel_tol=1e-9))
        self.assertIsNone(calculate_projected_finish_margin_laps(None, 1))

    def test_temp_calculations(self) -> None:
        temps = {
            "front_left": 92.0,
            "front_right": 96.0,
            "rear_left": 88.0,
            "rear_right": 90.0,
        }
        front = calculate_avg_front_temp(temps)
        rear = calculate_avg_rear_temp(temps)
        delta = calculate_front_rear_temp_delta(front, rear)

        self.assertTrue(isclose(front, 94.0, rel_tol=1e-9))
        self.assertTrue(isclose(rear, 89.0, rel_tol=1e-9))
        self.assertTrue(isclose(delta, 5.0, rel_tol=1e-9))

    def test_slip_calculations(self) -> None:
        slip = {
            "front_left": -0.04,
            "front_right": -0.06,
            "rear_left": 0.10,
            "rear_right": 0.14,
        }
        front_avg = calculate_front_avg_slip(slip)
        rear_avg = calculate_rear_avg_slip(slip)
        rear_exit = calculate_rear_exit_slip_index(rear_avg, 80.0)
        brake_instability = calculate_front_brake_instability_index(front_avg, 70.0)

        self.assertTrue(isclose(front_avg, -0.05, rel_tol=1e-9))
        self.assertTrue(isclose(rear_avg, 0.12, rel_tol=1e-9))
        self.assertTrue(isclose(rear_exit, 0.096, rel_tol=1e-9))
        self.assertTrue(isclose(brake_instability, 0.035, rel_tol=1e-9))

    def test_lap_delta_vs_best(self) -> None:
        self.assertEqual(calculate_lap_delta_vs_best(90970, 90780), 190.0)
        self.assertIsNone(calculate_lap_delta_vs_best(None, 90780))

    def test_pace_trend_last_n_laps(self) -> None:
        lap_times = [92000, 91800, 91950, 92100]
        self.assertTrue(isclose(calculate_pace_trend_last_n_laps(lap_times, n=4), 33.3333333333, rel_tol=1e-9))
        self.assertIsNone(calculate_pace_trend_last_n_laps([92000, 91800], n=3))

    def test_degradation_index(self) -> None:
        degradation = calculate_degradation_index(
            pace_trend_last_n_laps=60.0,
            front_rear_temp_delta=8.0,
            rear_exit_slip_index=0.06,
            front_brake_instability_index=0.04,
            tire_life_inferred_front=70.0,
            tire_life_inferred_rear=65.0,
        )
        self.assertTrue(isclose(degradation, 26.9, rel_tol=1e-9))

    def test_tire_life_direct_mode(self) -> None:
        self.assertTrue(
            isclose(
                calculate_tire_life_inferred_front(
                    direct_tire_wear_pct=42.0,
                    direct_tire_wear_enabled=True,
                    inferred_tire_life_enabled=False,
                    avg_front_temp=94.0,
                    front_avg_slip=-0.05,
                    front_brake_instability_index=0.03,
                    degradation_index=20.0,
                ),
                58.0,
                rel_tol=1e-9,
            )
        )

    def test_tire_life_inferred_mode(self) -> None:
        front = calculate_tire_life_inferred_front(
            direct_tire_wear_pct=None,
            direct_tire_wear_enabled=False,
            inferred_tire_life_enabled=True,
            avg_front_temp=95.0,
            front_avg_slip=0.05,
            front_brake_instability_index=0.02,
            degradation_index=20.0,
        )
        rear = calculate_tire_life_inferred_rear(
            direct_tire_wear_pct=None,
            direct_tire_wear_enabled=False,
            inferred_tire_life_enabled=True,
            avg_rear_temp=96.0,
            rear_avg_slip=0.06,
            rear_exit_slip_index=0.03,
            degradation_index=20.0,
        )

        self.assertTrue(isclose(front, 49.0, rel_tol=1e-9))
        self.assertTrue(isclose(rear, 37.4, rel_tol=1e-9))

    def test_build_derived_state_from_sample_frames(self) -> None:
        frames = self._load_sample_frames()
        derived = build_derived_telemetry_state(frames[-1], frames[:-1])

        self.assertEqual(derived.laps_remaining, 1)
        self.assertTrue(isclose(derived.fuel_pct, 1.6666666667, rel_tol=1e-9))
        self.assertTrue(derived.projected_laps_remaining is not None)
        self.assertTrue(derived.projected_finish_margin_laps is not None)
        self.assertEqual(derived.tire_wear_mode, TireWearMode.inferred)

    def _load_sample_frames(self) -> list[NormalizedTelemetryState]:
        path = Path(__file__).resolve().parents[3] / "contracts" / "sample_normalized_telemetry.jsonl"
        frames: list[NormalizedTelemetryState] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            frames.append(NormalizedTelemetryState.model_validate_json(line))
        return frames


if __name__ == "__main__":
    unittest.main()
