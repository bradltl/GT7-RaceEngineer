# GT7 Field Mapping Assumptions

This document records the assumptions used by the deterministic engineer layer.
These mappings are treated as provisional until validated against live GT7 telemetry.

## General Rules

- `TelemetrySnapshot` is the canonical normalized input to the engineer layer.
- The engineer layer does not parse raw GT7 UDP packets.
- Unknown or unvalidated raw GT7 fields must stay out of the deterministic logic until confirmed.

## Lap Fields

- `lap_number` is the current completed lap index in the session.
- `laps_total` is the total planned race distance in laps, when the session is lap-based.
- `laps_remaining` is the remaining laps reported by normalization when available.
- If `laps_remaining` is missing but both `lap_number` and `laps_total` are present, the engineer layer may derive `laps_total - lap_number`.
- `laps_remaining_source` should be set to `explicit` when GT7 or upstream normalization provided the value, and `derived` when the engineer layer derives it.

## Lap Timing Fields

- `lap_time_ms` is the current lap time when the snapshot was produced.
- `last_lap_time_ms` is the most recently completed lap time.
- `best_lap_time_ms` is the current session best lap time.
- A "best lap" callout is triggered only when `last_lap_time_ms` is faster than `best_lap_time_ms` by at least the configured improvement threshold.

## Fuel Fields

- `fuel_liters` is absolute fuel remaining in liters, not a percentage.
- `fuel_capacity_liters` is the maximum tank size in liters when known.
- `fuel_laps_remaining_estimate` is the estimated laps remaining at the current pace.
- `projected_fuel_to_finish_liters` is the predicted fuel margin at the end of the race.
- Positive values mean fuel is left over at finish.
- Negative values mean the driver is projected to run out before the finish.
- `fuel_critical` is triggered when the fuel-lap estimate falls below the configured critical threshold or when projected finish fuel is negative.
- `box_this_lap` is triggered when fuel is critical and the projection indicates no safe finish margin.

## Session Metadata

- `track_name` is informational and not used by phase 1 rules.
- `session_type` is informational and not used by phase 1 rules.
- `connection_state` is tracked in the model for future health reporting, but it is not part of the phase 1 deterministic callout rules.

