from __future__ import annotations

from math import isfinite
from statistics import fmean
from typing import Mapping, Sequence

from .telemetry_models import (
    DerivedTelemetryState,
    NormalizedTelemetryState,
    TireWearMode,
)


def calculate_laps_remaining(
    lap_number: int | None,
    laps_total: int | None,
    explicit_laps_remaining: int | None = None,
) -> int | None:
    if explicit_laps_remaining is not None:
        return max(explicit_laps_remaining, 0)
    if lap_number is None or laps_total is None:
        return None
    return max(laps_total - lap_number, 0)


def calculate_fuel_pct(fuel_liters: float | None, fuel_capacity_liters: float | None) -> float | None:
    if fuel_liters is None or fuel_capacity_liters is None:
        return None
    if fuel_capacity_liters <= 0:
        return None
    return max(0.0, min(100.0, (fuel_liters / fuel_capacity_liters) * 100.0))


def calculate_rolling_fuel_burn_per_lap(
    history: Sequence[NormalizedTelemetryState],
    window_laps: int = 3,
) -> float | None:
    samples = _sorted_completed_lap_samples(history)
    if len(samples) < 2:
        return None

    burns: list[float] = []
    for previous, current in zip(samples[:-1], samples[1:]):
        if previous.fuel_liters is None or current.fuel_liters is None:
            continue
        lap_delta = _lap_delta(previous, current)
        if lap_delta <= 0:
            continue
        burn = previous.fuel_liters - current.fuel_liters
        if burn < 0:
            continue
        burns.append(burn / lap_delta)

    if not burns:
        return None
    window = burns[-max(1, window_laps) :]
    return fmean(window)


def calculate_projected_laps_remaining(
    fuel_liters: float | None,
    rolling_fuel_burn_per_lap: float | None,
) -> float | None:
    if fuel_liters is None or rolling_fuel_burn_per_lap is None:
        return None
    if rolling_fuel_burn_per_lap <= 0:
        return None
    return fuel_liters / rolling_fuel_burn_per_lap


def calculate_projected_finish_margin_laps(
    projected_laps_remaining: float | None,
    laps_remaining: int | None,
) -> float | None:
    if projected_laps_remaining is None or laps_remaining is None:
        return None
    return projected_laps_remaining - laps_remaining


def calculate_avg_front_temp(tire_temps_c: Mapping[str, float] | None) -> float | None:
    values = _temps_for_keys(tire_temps_c, ("front_left", "front_right"))
    return fmean(values) if values else None


def calculate_avg_rear_temp(tire_temps_c: Mapping[str, float] | None) -> float | None:
    values = _temps_for_keys(tire_temps_c, ("rear_left", "rear_right"))
    return fmean(values) if values else None


def calculate_front_rear_temp_delta(
    avg_front_temp: float | None,
    avg_rear_temp: float | None,
) -> float | None:
    if avg_front_temp is None or avg_rear_temp is None:
        return None
    return avg_front_temp - avg_rear_temp


def calculate_front_avg_slip(slip_ratio_by_wheel: Mapping[str, float] | None) -> float | None:
    values = _slip_for_keys(slip_ratio_by_wheel, ("front_left", "front_right"))
    return fmean(values) if values else None


def calculate_rear_avg_slip(slip_ratio_by_wheel: Mapping[str, float] | None) -> float | None:
    values = _slip_for_keys(slip_ratio_by_wheel, ("rear_left", "rear_right"))
    return fmean(values) if values else None


def calculate_rear_exit_slip_index(
    rear_avg_slip: float | None,
    throttle_pct: float | None,
) -> float | None:
    if rear_avg_slip is None or throttle_pct is None:
        return None
    throttle_factor = max(0.0, min(1.0, throttle_pct / 100.0))
    return max(0.0, rear_avg_slip) * throttle_factor


def calculate_front_brake_instability_index(
    front_avg_slip: float | None,
    brake_pct: float | None,
) -> float | None:
    if front_avg_slip is None or brake_pct is None:
        return None
    brake_factor = max(0.0, min(1.0, brake_pct / 100.0))
    return max(0.0, -front_avg_slip) * brake_factor


def calculate_lap_delta_vs_best(
    last_lap_time_ms: int | None,
    best_lap_time_ms: int | None,
) -> float | None:
    if last_lap_time_ms is None or best_lap_time_ms is None:
        return None
    return float(last_lap_time_ms - best_lap_time_ms)


def calculate_pace_trend_last_n_laps(
    lap_times_ms: Sequence[int | None],
    n: int = 3,
) -> float | None:
    if n < 2:
        return None
    values = [value for value in lap_times_ms if value is not None]
    if len(values) < n:
        return None
    window = values[-n:]
    if len(window) < 2:
        return None
    return float(window[-1] - window[0]) / float(len(window) - 1)


def calculate_degradation_index(
    pace_trend_last_n_laps: float | None,
    front_rear_temp_delta: float | None,
    rear_exit_slip_index: float | None,
    front_brake_instability_index: float | None,
    tire_life_inferred_front: float | None = None,
    tire_life_inferred_rear: float | None = None,
) -> float | None:
    components: list[float] = []

    if pace_trend_last_n_laps is not None and pace_trend_last_n_laps > 0:
        components.append(_clamp((pace_trend_last_n_laps / 1000.0) * 40.0, 0.0, 40.0))
    else:
        components.append(0.0)

    if front_rear_temp_delta is not None:
        components.append(_clamp((abs(front_rear_temp_delta) / 10.0) * 20.0, 0.0, 20.0))
    else:
        components.append(0.0)

    slip_total = 0.0
    if rear_exit_slip_index is not None:
        slip_total += rear_exit_slip_index
    if front_brake_instability_index is not None:
        slip_total += front_brake_instability_index
    components.append(_clamp(slip_total * 20.0, 0.0, 20.0))

    if tire_life_inferred_front is not None or tire_life_inferred_rear is not None:
        life_values = [value for value in (tire_life_inferred_front, tire_life_inferred_rear) if value is not None]
        if life_values:
            average_life = fmean(life_values)
            components.append(_clamp(((100.0 - average_life) / 100.0) * 20.0, 0.0, 20.0))
        else:
            components.append(0.0)
    else:
        components.append(0.0)

    total = sum(components)
    return _clamp(total, 0.0, 100.0)


def calculate_tire_life_inferred_front(
    direct_tire_wear_pct: float | None,
    direct_tire_wear_enabled: bool,
    inferred_tire_life_enabled: bool,
    avg_front_temp: float | None = None,
    front_avg_slip: float | None = None,
    front_brake_instability_index: float | None = None,
    degradation_index: float | None = None,
) -> float | None:
    return _calculate_tire_life(
        direct_tire_wear_pct=direct_tire_wear_pct,
        direct_tire_wear_enabled=direct_tire_wear_enabled,
        inferred_tire_life_enabled=inferred_tire_life_enabled,
        avg_temp=avg_front_temp,
        avg_slip=front_avg_slip,
        brake_instability_index=front_brake_instability_index,
        degradation_index=degradation_index,
        axle_bias=0.0,
    )


def calculate_tire_life_inferred_rear(
    direct_tire_wear_pct: float | None,
    direct_tire_wear_enabled: bool,
    inferred_tire_life_enabled: bool,
    avg_rear_temp: float | None = None,
    rear_avg_slip: float | None = None,
    rear_exit_slip_index: float | None = None,
    degradation_index: float | None = None,
) -> float | None:
    return _calculate_tire_life(
        direct_tire_wear_pct=direct_tire_wear_pct,
        direct_tire_wear_enabled=direct_tire_wear_enabled,
        inferred_tire_life_enabled=inferred_tire_life_enabled,
        avg_temp=avg_rear_temp,
        avg_slip=rear_avg_slip,
        brake_instability_index=rear_exit_slip_index,
        degradation_index=degradation_index,
        axle_bias=2.0,
    )


def build_derived_telemetry_state(
    current: NormalizedTelemetryState,
    history: Sequence[NormalizedTelemetryState],
    *,
    rolling_window_laps: int = 3,
    direct_tire_wear_enabled: bool = False,
    inferred_tire_life_enabled: bool = True,
) -> DerivedTelemetryState:
    laps_remaining = calculate_laps_remaining(
        current.lap_number,
        current.laps_total,
        current.laps_remaining,
    )
    fuel_pct = calculate_fuel_pct(current.fuel_liters, current.fuel_capacity_liters)
    rolling_fuel = calculate_rolling_fuel_burn_per_lap(history, window_laps=rolling_window_laps)
    projected_laps_remaining = calculate_projected_laps_remaining(current.fuel_liters, rolling_fuel)
    projected_finish_margin_laps = calculate_projected_finish_margin_laps(projected_laps_remaining, laps_remaining)
    avg_front_temp = calculate_avg_front_temp(current.tire_temps_c)
    avg_rear_temp = calculate_avg_rear_temp(current.tire_temps_c)
    front_rear_temp_delta = calculate_front_rear_temp_delta(avg_front_temp, avg_rear_temp)
    front_avg_slip = calculate_front_avg_slip(current.slip_ratio_by_wheel)
    rear_avg_slip = calculate_rear_avg_slip(current.slip_ratio_by_wheel)
    rear_exit_slip_index = calculate_rear_exit_slip_index(rear_avg_slip, current.throttle_pct)
    front_brake_instability_index = calculate_front_brake_instability_index(front_avg_slip, current.brake_pct)
    lap_delta_vs_best = calculate_lap_delta_vs_best(current.last_lap_time_ms, current.best_lap_time_ms)
    pace_trend_last_n_laps = calculate_pace_trend_last_n_laps(
        [sample.last_lap_time_ms for sample in _sorted_completed_lap_samples(history) if sample.last_lap_time_ms is not None]
        + ([current.last_lap_time_ms] if current.last_lap_time_ms is not None else []),
        n=rolling_window_laps,
    )
    tire_life_front = calculate_tire_life_inferred_front(
        current.tire_wear_pct,
        direct_tire_wear_enabled,
        inferred_tire_life_enabled,
        avg_front_temp=avg_front_temp,
        front_avg_slip=front_avg_slip,
        front_brake_instability_index=front_brake_instability_index,
        degradation_index=None,
    )
    tire_life_rear = calculate_tire_life_inferred_rear(
        current.tire_wear_pct,
        direct_tire_wear_enabled,
        inferred_tire_life_enabled,
        avg_rear_temp=avg_rear_temp,
        rear_avg_slip=rear_avg_slip,
        rear_exit_slip_index=rear_exit_slip_index,
        degradation_index=None,
    )
    degradation_index = calculate_degradation_index(
        pace_trend_last_n_laps,
        front_rear_temp_delta,
        rear_exit_slip_index,
        front_brake_instability_index,
        tire_life_front,
        tire_life_rear,
    )

    return DerivedTelemetryState(
        laps_remaining=laps_remaining,
        fuel_pct=fuel_pct,
        rolling_fuel_burn_per_lap=rolling_fuel,
        projected_laps_remaining=projected_laps_remaining,
        projected_finish_margin_laps=projected_finish_margin_laps,
        avg_front_temp=avg_front_temp,
        avg_rear_temp=avg_rear_temp,
        front_rear_temp_delta=front_rear_temp_delta,
        front_avg_slip=front_avg_slip,
        rear_avg_slip=rear_avg_slip,
        rear_exit_slip_index=rear_exit_slip_index,
        front_brake_instability_index=front_brake_instability_index,
        lap_delta_vs_best=lap_delta_vs_best,
        pace_trend_last_n_laps=pace_trend_last_n_laps,
        degradation_index=degradation_index,
        tire_life_inferred_front=tire_life_front,
        tire_life_inferred_rear=tire_life_rear,
        tire_wear_mode=TireWearMode.direct if direct_tire_wear_enabled else TireWearMode.inferred if inferred_tire_life_enabled else TireWearMode.unknown,
    )


def _calculate_tire_life(
    *,
    direct_tire_wear_pct: float | None,
    direct_tire_wear_enabled: bool,
    inferred_tire_life_enabled: bool,
    avg_temp: float | None,
    avg_slip: float | None,
    brake_instability_index: float | None,
    degradation_index: float | None,
    axle_bias: float,
) -> float | None:
    if direct_tire_wear_enabled and direct_tire_wear_pct is not None:
        return _clamp(100.0 - direct_tire_wear_pct, 0.0, 100.0)
    if not inferred_tire_life_enabled:
        return None

    wear_penalty = 0.0
    if avg_temp is not None:
        wear_penalty += max(0.0, avg_temp - 80.0) * 0.6
    if avg_slip is not None:
        wear_penalty += abs(avg_slip) * 400.0
    if brake_instability_index is not None:
        wear_penalty += brake_instability_index * 500.0
    if degradation_index is not None:
        wear_penalty += degradation_index * 0.6

    wear_penalty += axle_bias
    return _clamp(100.0 - wear_penalty, 0.0, 100.0)


def _sorted_completed_lap_samples(history: Sequence[NormalizedTelemetryState]) -> list[NormalizedTelemetryState]:
    samples = [
        sample
        for sample in history
        if sample.lap_number is not None and sample.fuel_liters is not None
    ]
    return sorted(samples, key=lambda sample: (sample.lap_number or 0, sample.timestamp_ms))


def _lap_delta(previous: NormalizedTelemetryState, current: NormalizedTelemetryState) -> int:
    if previous.lap_number is None or current.lap_number is None:
        return 0
    return max(current.lap_number - previous.lap_number, 0)


def _temps_for_keys(tire_temps_c: Mapping[str, float] | None, keys: Sequence[str]) -> list[float]:
    if not tire_temps_c:
        return []
    values = [tire_temps_c[key] for key in keys if key in tire_temps_c and isfinite(tire_temps_c[key])]
    return values


def _slip_for_keys(slip_ratio_by_wheel: Mapping[str, float] | None, keys: Sequence[str]) -> list[float]:
    if not slip_ratio_by_wheel:
        return []
    values = [slip_ratio_by_wheel[key] for key in keys if key in slip_ratio_by_wheel and isfinite(slip_ratio_by_wheel[key])]
    return values


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))
