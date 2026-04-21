# Rule Engine Specification

This document defines the deterministic rule-engine foundation for the GT7 race engineer assistant.

The engine is a signal processor, not a narrator.

## Design Principles

- Deterministic logic first
- Short, actionable messages only
- Prefer high-confidence race-critical callouts over broad commentary
- Never invent a GT7 field mapping that has not been validated
- Keep unsupported features behind explicit extension points
- Separate raw signal detection, race-state reasoning, and message formatting

## Normalized Input Contract

The rule engine consumes a normalized telemetry snapshot, not raw GT7 packets.

Required categories:

- session state
- lap state
- fuel state
- pace state
- tire state
- vehicle dynamics
- connection / freshness state
- optional extension payloads for later sources

## Priority Model

- `critical`: immediate action required, highest priority
- `warning`: likely action required soon
- `info`: useful but non-urgent

## Cooldown and Suppression Model

The engine uses:

- rule-level cooldowns to prevent repeated callouts
- state-change suppression to avoid repeating identical messages
- priority-based deduplication when multiple rules target the same driver action
- staleness suppression when telemetry freshness drops below acceptable bounds

General suppression rules:

- suppress if the same `rule_id` emitted within its cooldown window
- suppress if the normalized values have not changed materially since the last emission
- suppress if a higher-priority rule already produced the same driver action
- suppress informational updates while a critical action is active

## Rule Families

### 1. Fuel Strategy

#### Rule: `fuel_projected_deficit`

- Purpose: warn when fuel projection indicates a finish deficit
- Trigger logic: `projected_fuel_to_finish_liters < 0`
- Required normalized fields: `fuel_liters`, `laps_remaining`, `projected_fuel_to_finish_liters`, `fuel_laps_remaining_estimate`
- Priority: `critical`
- Cooldown: 30s
- Suppression conditions:
  - suppress if `box_this_lap` already emitted for the same stint state
  - suppress if the deficit magnitude improves materially but remains in the same band
- Example messages:
  - `Fuel to finish: deficit 0.1 L`
  - `Fuel margin gone`
- Recommended driver action: pit this lap or switch to fuel-saving mode immediately

#### Rule: `fuel_critical`

- Purpose: identify fuel state that is close to or below safe race completion
- Trigger logic: `fuel_laps_remaining_estimate <= fuel_critical_laps`
- Required normalized fields: `fuel_laps_remaining_estimate`, `fuel_liters`, `laps_remaining`
- Priority: `critical`
- Cooldown: 30s
- Suppression conditions:
  - suppress if the car is already boxed under `box_this_lap`
  - suppress if the estimate improves above the warning threshold
- Example messages:
  - `Fuel critical, 0.6 laps left`
  - `Fuel tight`
- Recommended driver action: save fuel or box now

#### Rule: `box_this_lap`

- Purpose: turn fuel risk into a clear pit instruction
- Trigger logic:
  - `projected_fuel_to_finish_liters < 0`, or
  - `fuel_laps_remaining_estimate <= 1.0`
- Required normalized fields: `projected_fuel_to_finish_liters`, `fuel_laps_remaining_estimate`, `laps_remaining`
- Priority: `critical`
- Cooldown: 30s
- Suppression conditions:
  - suppress if the driver is already on an out-lap or pit lane state from another source
  - suppress if the pit recommendation is unsupported and no explicit pit state exists
- Example messages:
  - `Box this lap`
  - `Pit this lap`
- Recommended driver action: pit this lap

### 2. Laps Remaining / Race Phase

#### Rule: `laps_remaining_notice`

- Purpose: keep the driver aware of race phase without chattering every lap
- Trigger logic: `laps_remaining == 2`
- Required normalized fields: `laps_remaining`, `lap_number`, `laps_total`
- Priority: `info`
- Cooldown: 30s
- Suppression conditions:
  - suppress if `final_lap` is active
  - suppress if race distance is not lap-based
- Example messages:
  - `2 laps remaining`
  - `Two laps to go`
- Recommended driver action: plan the final stint

#### Rule: `final_lap`

- Purpose: announce the last lap
- Trigger logic: `laps_remaining == 1`
- Required normalized fields: `laps_remaining`, `lap_number`, `laps_total`
- Priority: `warning`
- Cooldown: 60s
- Suppression conditions:
  - suppress if the session is not a lap-counted race
  - suppress if a higher-priority pit instruction is already active and final-lap chatter would add no value
- Example messages:
  - `Final lap`
  - `Last lap`
- Recommended driver action: finish the race cleanly, avoid unnecessary risk

### 3. Tire Temperature and Grip Management

#### Rule: `tire_temp_hot`

- Purpose: warn when tire temperatures are drifting outside the usable window
- Trigger logic: any active tire temperature above the configured hot threshold
- Required normalized fields: `tire_temps_c`, `tire_temp_source`
- Priority: `warning`
- Cooldown: 20s
- Suppression conditions:
  - suppress if temps are hot but stable and not worsening
  - suppress if direct tire wear is already critical and further temperature chatter is redundant
- Example messages:
  - `Front left hot`
  - `Rear tires overheating`
- Recommended driver action: reduce slip, smooth inputs, manage corner entry speed

#### Rule: `tire_temp_cold`

- Purpose: warn when tires are below the usable grip window
- Trigger logic: any active tire temperature below the configured cold threshold
- Required normalized fields: `tire_temps_c`, `tire_temp_source`
- Priority: `warning`
- Cooldown: 20s
- Suppression conditions:
  - suppress during out-lap if other warm-up guidance is active
  - suppress if track phase or weather already explains the cold state
- Example messages:
  - `Tires cold`
  - `Build grip`
- Recommended driver action: warm the tires with controlled load and braking

#### Rule: `grip_building`

- Purpose: indicate when grip is improving after warm-up or stabilization
- Trigger logic: tire temp trend or slip trend is moving toward target window
- Required normalized fields: `tire_temps_c`, `slip_ratio`, `throttle_pct`, `brake_pct`
- Priority: `info`
- Cooldown: 30s
- Suppression conditions:
  - suppress if the car is mid-lap and grip is already adequate
  - suppress if no trend data exists
- Example messages:
  - `Grip coming in`
  - `Tires waking up`
- Recommended driver action: gradually increase push as tires come into the window

### 4. Slip / Traction Coaching

#### Rule: `exit_wheelspin`

- Purpose: coach throttle application when driven wheel speed exceeds vehicle speed
- Trigger logic: sustained positive driven-wheel slip ratio above threshold on throttle application
- Required normalized fields: `speed_mps`, `wheel_speeds_mps`, `slip_ratio_by_wheel`, `throttle_pct`
- Priority: `warning`
- Cooldown: 15s
- Suppression conditions:
  - suppress if the throttle is already low
  - suppress if a wet-track/rain adapter takes over later
- Example messages:
  - `Throttle too sharp`
  - `Reduce wheelspin`
- Recommended driver action: roll into throttle more progressively

#### Rule: `brake_lockup`

- Purpose: coach braking when wheel speed collapses relative to vehicle speed
- Trigger logic: sustained negative slip ratio or lockup signature during braking
- Required normalized fields: `speed_mps`, `wheel_speeds_mps`, `slip_ratio_by_wheel`, `brake_pct`
- Priority: `warning`
- Cooldown: 15s
- Suppression conditions:
  - suppress if threshold evidence is noisy or insufficient
  - suppress if a tire temperature warning already explains the lockup pattern
- Example messages:
  - `Brake too hard`
  - `Front lockup`
- Recommended driver action: brake a little earlier and release more smoothly

#### Rule: `traction_loss`

- Purpose: warn when the car is repeatedly exceeding the available grip
- Trigger logic: repeated high slip events or high yaw/traction instability signature
- Required normalized fields: `slip_ratio_by_wheel`, `speed_mps`, `throttle_pct`, `brake_pct`, `steering_angle_deg` if available
- Priority: `warning`
- Cooldown: 20s
- Suppression conditions:
  - suppress if slip events are isolated and not repeated
  - suppress if another specific coaching rule already explains the issue
- Example messages:
  - `Traction poor`
  - `Too much slip`
- Recommended driver action: reduce aggression and stabilize inputs

### 5. Pace / Performance Coaching

#### Rule: `best_lap`

- Purpose: announce a new best lap
- Trigger logic: `last_lap_time_ms` improves on `best_lap_time_ms` by the configured threshold
- Required normalized fields: `last_lap_time_ms`, `best_lap_time_ms`
- Priority: `info`
- Cooldown: 0s or minimal, but dedupe by lap
- Suppression conditions:
  - suppress repeated emission for the same lap
  - suppress if the improvement is below the configured meaningful threshold
- Example messages:
  - `New best lap`
  - `Best lap, 0.780s quicker`
- Recommended driver action: keep the rhythm, repeat the lap shape

#### Rule: `last_lap_degradation`

- Purpose: flag when the last lap is materially worse than the reference lap
- Trigger logic: `last_lap_time_ms` is slower than the comparison lap by threshold
- Required normalized fields: `last_lap_time_ms`, `best_lap_time_ms` or rolling lap baseline
- Priority: `info`
- Cooldown: 20s
- Suppression conditions:
  - suppress if degradation is explained by traffic or pit state from another source
  - suppress if the lap delta is within noise
- Example messages:
  - `Last lap slower`
  - `Lost pace`
- Recommended driver action: identify the corner or input pattern causing the loss

#### Rule: `pace_drop`

- Purpose: alert when lap pace is trending worse across multiple laps
- Trigger logic: rolling average lap time drifts slower by threshold over a small window
- Required normalized fields: `lap_time_ms`, `last_lap_time_ms`, `best_lap_time_ms`, history window
- Priority: `info`
- Cooldown: 30s
- Suppression conditions:
  - suppress if a one-off slow lap is clearly attributable to traffic or a mistake
  - suppress if fuel or tire strategy explains the drift and a more specific rule is active
- Example messages:
  - `Pace fading`
  - `Pick up the rhythm`
- Recommended driver action: reset driving rhythm and clean up the slowest sector

### 6. Tire Life / Wear Messaging

Tire wear must support two modes:

- `direct_tire_wear_enabled`
- `inferred_tire_life_enabled`

Only one mode should drive messaging at a time unless live validation shows both can be reconciled safely.

#### Rule: `direct_tire_wear_alert`

- Purpose: use direct wear telemetry when it is known and validated
- Trigger logic: direct wear exceeds configured wear threshold
- Required normalized fields: `tire_wear_pct`, `tire_wear_source=direct`
- Priority: `warning`
- Cooldown: 30s
- Suppression conditions:
  - suppress if direct wear is not validated on the current source
  - suppress if inferred tire life is the active fallback mode
- Example messages:
  - `Front left wearing`
  - `Tyres fading`
- Recommended driver action: reduce slip and protect the tires

#### Rule: `inferred_tire_life_alert`

- Purpose: estimate tire life when direct wear is unavailable or untrusted
- Trigger logic: inferred tire life drops below configured warning bands
- Required normalized fields: `tire_life_estimate_pct`, `slip_ratio`, `tire_temps_c`, `lap_time_ms`, `last_lap_time_ms`
- Priority: `warning`
- Cooldown: 30s
- Suppression conditions:
  - suppress if direct wear telemetry becomes validated and authoritative
  - suppress if the inference confidence is low
- Example messages:
  - `Tyres fading`
  - `Tires going off`
- Recommended driver action: lower slip, protect the stint, consider a pit window if applicable

### 7. Degradation Detection

#### Rule: `telemetry_stale`

- Purpose: detect stale or degraded telemetry delivery
- Trigger logic: telemetry age exceeds configured freshness threshold
- Required normalized fields: `timestamp_ms`, `ingest_timestamp_ms`, `connection_state`
- Priority: `warning`
- Cooldown: 10s
- Suppression conditions:
  - suppress if the stream recovers and freshness returns to normal
  - suppress duplicate stale warnings while the connection state is already degraded
- Example messages:
  - `Telemetry degraded`
  - `Signal stale`
- Recommended driver action: trust the last known callout state cautiously until telemetry recovers

#### Rule: `session_state_loss`

- Purpose: detect missing or inconsistent session state
- Trigger logic: lap, fuel, or pace fields disappear unexpectedly across consecutive snapshots
- Required normalized fields: session state fields and per-field presence history
- Priority: `warning`
- Cooldown: 15s
- Suppression conditions:
  - suppress if the missing field is expected during a known session transition
  - suppress if a reconnect or reload action is underway
- Example messages:
  - `Session data lost`
  - `Telemetry reset`
- Recommended driver action: hold the current plan and wait for state to stabilize

### 8. Message Suppression, Cooldowns, and Prioritization

#### Rule: `message_gate`

- Purpose: apply a final emission gate before output
- Trigger logic: any rule produces an event
- Required normalized fields: `event_id`, `timestamp_ms`, rule-specific state
- Priority: inherits from source rule
- Cooldown: rule-specific
- Suppression conditions:
  - identical event already emitted inside cooldown
  - lower-priority message conflicts with a higher-priority same-action message
  - duplicate lap-phase updates inside the same lap
- Example messages:
  - none, this is a gate rule
- Recommended driver action: none, this is internal control logic

#### Rule: `priority_collation`

- Purpose: order and merge competing messages deterministically
- Trigger logic: more than one event is ready for emission
- Required normalized fields: all active rule outputs
- Priority: critical > warning > info
- Cooldown: n/a
- Suppression conditions:
  - suppress lower-priority duplicates of the same action
  - suppress informational messages when they would hide an immediate action
- Example messages:
  - `Box this lap` should outrank `2 laps remaining`
- Recommended driver action: follow the most urgent actionable message first

## Extension Points

These are intentionally not implemented in phase 1:

- yellow flag detection
- opponent gaps
- pit intent of other cars
- rain / weather prediction
- voice output

TODO: validate which of these can be sourced directly from GT7 telemetry versus requiring OCR or another external source.

