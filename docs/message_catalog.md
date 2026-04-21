# Message Catalog

Short, actionable engineer callouts grouped by state, impact, and action.

Messages must be concise enough to be useful while driving.

## Fuel / Pit

### State: fuel risk

- Impact: immediate race finish risk
- Action: pit or conserve now

Messages:

- `Fuel critical`
- `Fuel critical, box this lap`
- `Fuel to finish: deficit 0.1 L`
- `Fuel tight`
- `Pit this lap`

### State: projected fuel shortfall

- Impact: likely finish deficit
- Action: reduce consumption or pit

Messages:

- `Fuel to finish: deficit 1.4 L`
- `Fuel margin gone`
- `Projected fuel short`
- `Need fuel save`

### State: fuel management

- Impact: strategy adjustment required
- Action: lift, short-shift, smooth throttle

Messages:

- `Fuel saving`
- `Manage fuel`
- `Lift and coast`
- `Short shift`

## Lap Phase

### State: race end approaching

- Impact: phase awareness
- Action: plan execution

Messages:

- `2 laps remaining`
- `Final lap`
- `Last lap`
- `One lap to go`

## Pace / Performance

### State: improving

- Impact: positive pace signal
- Action: repeat the same approach

Messages:

- `New best lap`
- `Best lap, 0.780s quicker`
- `Strong lap`
- `Keep that rhythm`

### State: slower pace

- Impact: pace loss
- Action: identify and clean up the slow segment

Messages:

- `Last lap slower`
- `Pace fading`
- `Lost time`
- `Pick up the rhythm`

## Tires / Grip

### State: tire temperatures too high

- Impact: reduced grip, wear, and stability
- Action: reduce slip and smooth inputs

Messages:

- `Front left hot`
- `Rear tires overheating`
- `Tires too hot`
- `Protect the tires`

### State: tire temperatures too low

- Impact: low grip
- Action: build temperature progressively

Messages:

- `Tires cold`
- `Build grip`
- `Warm them up`
- `Tires waking up`

### State: tire life falling off

- Impact: degraded stint performance
- Action: reduce aggression, manage the stint

Messages:

- `Tyres fading`
- `Tires going off`
- `Wear increasing`
- `Protect the stint`

## Traction / Slip

### State: wheelspin

- Impact: lost acceleration
- Action: feed throttle more gradually

Messages:

- `Reduce wheelspin`
- `Throttle too sharp`
- `Too much slip`
- `Be smoother on exit`

### State: braking lockup

- Impact: lost braking efficiency
- Action: brake earlier and release more smoothly

Messages:

- `Front lockup`
- `Brake too hard`
- `Ease the pedal`
- `Brake release`

### State: grip instability

- Impact: inconsistent lap time
- Action: stabilize inputs

Messages:

- `Traction poor`
- `Car moving around`
- `Calm the inputs`
- `Stabilize the car`

## Degradation / Health

### State: telemetry stale or degraded

- Impact: message confidence reduced
- Action: trust the last known instruction cautiously

Messages:

- `Telemetry degraded`
- `Signal stale`
- `Data stale`
- `Stand by`

## General Suppression Guidance

- Do not repeat the same callout every frame
- Prefer one message per actionable change
- Suppress low-value info when a critical instruction is active
- Merge duplicate messages that imply the same driver action

TODO: refine this catalog after live race sessions confirm which messages are actually useful under pressure.

