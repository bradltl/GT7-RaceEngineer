# Telemetry Field Mapping

This document maps the normalized telemetry model to known or likely GT7 telemetry source fields.

When a field is uncertain, it is explicitly marked as such.

## Mapping Rules

- Normalized fields are the contract consumed by the rule engine.
- Source fields are the best-known upstream GT7 or community-parser fields.
- If a source field is uncertain, mark it as `unknown / needs validation`.
- Do not treat any uncertain field as authoritative until live telemetry confirms it.

## Core Session Fields

| Normalized field | Known / likely source field | Confidence | Derived formula / notes |
| --- | --- | --- | --- |
| `session_id` | `session identifier` or replay file session id | medium | May be synthetic in replay mode |
| `timestamp_ms` | capture timestamp | high | capture time in ms |
| `source_mode` | `live`, `replay`, `mock` | high | set by transport |
| `connection_state` | capture health / freshness state | high | derived from ingest timing and packet continuity |
| `track_name` | track name | medium | community parsers may expose a string field |
| `session_type` | race / practice / qualifying | medium | source-specific naming may vary |

## Lap and Race State

| Normalized field | Known / likely source field | Confidence | Derived formula / notes |
| --- | --- | --- | --- |
| `lap_number` | current lap | high | direct when available |
| `laps_total` | race lap count | medium | may be absent for timed sessions |
| `laps_remaining` | laps remaining | medium | direct if provided by source; otherwise derived |
| `laps_remaining_source` | normalized metadata | high | `explicit` if source provided, `derived` if computed |
| `lap_time_ms` | current lap time | medium | live lap timer or session clock derivative |
| `last_lap_time_ms` | last lap time | high | community ecosystem commonly exposes this |
| `best_lap_time_ms` | best lap time | high | community ecosystem commonly exposes this |

### Lap Remaining Derivation

- If `laps_remaining` is explicit, use it.
- If `laps_remaining` is missing and both `lap_number` and `laps_total` are known:
  - `laps_remaining = max(laps_total - lap_number, 0)`

TODO: validate whether GT7 ever reports an off-by-one race-phase offset that should be handled before this derivation.

## Fuel Fields

| Normalized field | Known / likely source field | Confidence | Derived formula / notes |
| --- | --- | --- | --- |
| `fuel_liters` | fuel remaining | high | direct field in known ecosystem |
| `fuel_capacity_liters` | fuel tank capacity | medium | may be source-specific |
| `fuel_laps_remaining_estimate` | fuel estimation / projected laps | medium | may be direct or derived |
| `projected_fuel_to_finish_liters` | derived fuel delta to finish | medium | `fuel_liters - (laps_remaining * avg_fuel_per_lap)` |

### Fuel Derivations

Recommended default formula:

- `avg_fuel_per_lap = fuel_used_over_recent_laps / recent_lap_count`
- `projected_fuel_to_finish_liters = fuel_liters - (laps_remaining * avg_fuel_per_lap)`

If recent-lap history is not available:

- `projected_fuel_to_finish_liters` may be estimated from `fuel_laps_remaining_estimate`
- confidence should be lowered in the normalized payload

TODO: validate the actual GT7 fuel semantics against live packets before treating projected fuel as high-confidence.

## Vehicle Dynamics

| Normalized field | Known / likely source field | Confidence | Derived formula / notes |
| --- | --- | --- | --- |
| `speed_kph` | vehicle speed | high | direct field in the ecosystem |
| `gear` | current gear | high | direct field in the ecosystem |
| `rpm` | engine RPM | high | direct field in the ecosystem |
| `throttle_pct` | throttle input | high | direct field in the ecosystem |
| `brake_pct` | brake input | high | direct field in the ecosystem |
| `steering_angle_deg` | steering angle | unknown / needs validation | add only if validated by the parser |
| `yaw_rate` | vehicle rotation rate | unknown / needs validation | future derivation source |

## Tire State

| Normalized field | Known / likely source field | Confidence | Derived formula / notes |
| --- | --- | --- | --- |
| `tire_temps_c` | tire temperature by corner | medium | known in public ecosystem, but exact channel names may vary |
| `tire_wear_pct` | tire wear percentage | low to medium | not consistently supported across public ecosystem |
| `tire_wear_source` | normalized metadata | high | `direct`, `inferred`, or `unknown` |
| `tire_life_estimate_pct` | inferred tire life | medium | derived from heat, slip, and pace degradation |

### Tire Wear Modes

Support both:

- `direct_tire_wear_enabled`
- `inferred_tire_life_enabled`

Recommended interpretation:

- `direct_tire_wear_enabled`: use `tire_wear_pct` if the source is validated
- `inferred_tire_life_enabled`: estimate tire life from telemetry when direct wear is absent or unreliable

Recommended inferred inputs:

- tire temperature excursions
- repeated slip ratio spikes
- lap-time degradation versus session best
- braking lockup / wheelspin frequency

TODO: confirm whether direct tire wear exists in the live GT7 UDP stream or whether it is only available through derived/community tooling.

## Tire Temperature and Slip

| Normalized field | Known / likely source field | Confidence | Derived formula / notes |
| --- | --- | --- | --- |
| `tire_temps_c` | tire temperatures per corner | medium | front left/right, rear left/right |
| `wheel_speeds_mps` | wheel speed per corner | medium | often derivable from raw wheel rotational speed |
| `slip_ratio_by_wheel` | derived slip ratio | high for derivation, medium for source availability | `(wheel_speed_mps - vehicle_speed_mps) / max(vehicle_speed_mps, epsilon)` |
| `avg_slip_ratio` | derived average slip ratio | high | mean of active wheel slip ratios |
| `traction_loss_index` | derived traction score | medium | weighted slip + throttle + brake instability |

### Slip Ratio Formula

For each driven wheel:

- `slip_ratio = (wheel_speed_mps - speed_mps) / max(speed_mps, 0.1)`

Interpretation:

- positive slip during throttle application suggests wheelspin
- negative slip during braking suggests lockup or near-lockup

TODO: verify whether wheel-speed channels are stable enough in GT7 to support per-corner slip coaching without excessive noise.

## Degradation / Health

| Normalized field | Known / likely source field | Confidence | Derived formula / notes |
| --- | --- | --- | --- |
| `ingest_lag_ms` | capture timestamp minus snapshot time | high | internal telemetry health metric |
| `validation_warnings` | normalized warnings | high | carries assumptions / warnings forward |
| `raw` | raw source payload snapshot | high | for later validation and replay |

## Explicit Unknowns

Mark these as unknown until live validation or another adapter is added:

- yellow flags
- opponent gaps
- pit entry state of other cars
- rain forecast
- tire wear direct support if not present in the validated stream
- any field not explicitly documented above

TODO: add a source-by-source matrix once live GT7 packets and community parser output are compared directly.

