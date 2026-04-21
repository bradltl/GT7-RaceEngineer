# Rule Engine Scenarios

This document captures the deterministic engineer scenarios used for regression coverage.

## Conventions

- All scenarios are driven from normalized telemetry snapshots.
- Replay-based scenarios use `contracts/sample_normalized_telemetry.jsonl`.
- Synthetic scenarios use generated frames that isolate a single rule family.
- Expected messages are shown in the order the engineer should emit them for each frame.

## Scenarios

| Scenario | Type | Description | Sample telemetry frames or generated sequence | Expected engineer messages |
|---|---|---|---|---|
| Fuel critical before finish | Replay | Fuel margin starts borderline and ends at critical before the finish. | Sample frames `evt-0003` -> `evt-0005` from `contracts/sample_normalized_telemetry.jsonl`. | `["Borderline fuel"]`, `["Borderline fuel"]`, `["Fuel critical", "Final lap"]` |
| Borderline fuel with successful save | Synthetic | Driver lifts enough to return from borderline fuel to a healthy margin. | Frame 1: `fuel_laps_remaining_estimate=2.1`, `projected_fuel_to_finish_liters=0.4`. Frame 2: `fuel_laps_remaining_estimate=3.4`, `projected_fuel_to_finish_liters=1.7`. | `["Borderline fuel"]`, `["Fuel margin healthy"]` |
| Final lap trigger | Synthetic | Race transitions from two laps remaining to final lap. | Frame 1: `laps_remaining=2`. Frame 2: `laps_remaining=1`. | `["2 laps remaining"]`, `["Final lap"]` |
| Rear overheating from repeated exit slip | Synthetic | Rear slip builds until the rear axle overheats. | Frame 1: `rear slip=0.10/0.11`, `rear temps=99/100`, `throttle=80`. Frame 2: `rear slip=0.12/0.13`, `rear temps=102/103`, `throttle=82`. | `["Rear grip falling", "Rear overheating"]`, `["Rear grip falling", "Rear overheating", "Wheelspin detected"]` |
| Front overheating from repeated entry overload | Synthetic | Front axle heats up under repeated trail-brake load. | Frame 1: `front temps=100/101`, `front slip=-0.05/-0.04`, `brake=70`. Frame 2: `front temps=103/104`, `front slip=-0.06/-0.05`, `brake=75`. | `["Front overheating", "Brake instability"]`, `["Front overheating", "Brake instability"]` |
| Cold tires after reset | Synthetic | After a reset or pit exit, the car needs grip build-up. | Single frame: `front temps=61/62`, `rear temps=60/61`. | `["Tires cold"]` |
| Understeer trend | Synthetic | Front axle gets hotter than the rear, indicating a growing understeer balance. | Frames: `90/90 vs 88/88`, then `91/91 vs 88/88`, then `96/96 vs 88/88` with front slip below rear slip on the trigger frame. | `[]`, `[]`, `["Understeer building"]` |
| Rear grip loss trend | Synthetic | Rear slip ramps up until rear grip is falling away. | Frames with rear slip increasing from `0.10` to `0.13` to `0.18`, throttle held at `30`. | `[]`, `[]`, `["Rear grip falling"]` |
| Wheelspin on throttle | Synthetic | Throttle application produces exit slip and wheelspin. | Single frame: `rear slip=0.11/0.10`, `throttle=82`. | `["Rear grip falling", "Wheelspin detected"]` |
| Brake instability | Synthetic | Heavy braking produces entry instability. | Single frame: `front slip=-0.05/-0.04`, `brake=72`. | `["Brake instability"]` |
| Best-lap pace | Synthetic | Lap time matches the best lap closely enough to call it out. | Single frame: `last_lap_time_ms=90000`, `best_lap_time_ms=90000`. | `["On best-lap pace"]` |
| Pace drop from degradation | Synthetic | Pace starts good, then degrades as the stint breaks down. | Frame 1: best lap pace. Frame 2: `last_lap_time_ms=92300`. Frame 3: `front temps=86/86`, `rear temps=95/95`, `rear slip=0.17`, `lap_time_ms=94500`. | `["On best-lap pace"]`, `["Losing pace"]`, `["Rear grip falling", "Degradation phase", "Losing pace", "Pace inconsistent"]` |
| Inferred tire life decline | Synthetic | With inferred tire life enabled, wear declines until the tire life is critical. | Frame 1: moderate heat/slip. Frame 2: higher heat/slip, inferred mode. | `[]`, `["Tire life critical"]` |

## Validation notes

- `TODO`: confirm the replay sample frame assumptions against live GT7 packets.
- `TODO`: confirm the rear grip, wheelspin, and degradation thresholds against a broader set of recorded laps.
- `TODO`: verify whether future telemetry support should split grip coaching from tire-life coaching more aggressively.
