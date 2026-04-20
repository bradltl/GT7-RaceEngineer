# Project Todo

This list is updated to reflect what is already done and what still needs validation or implementation.

## Completed

- [x] Repository scaffold created for `telemetry-capture`, `engineer`, and `web-ui`
- [x] Product, architecture, and roadmap docs added
- [x] Canonical normalized telemetry schema defined
- [x] Sample replay telemetry frames added
- [x] Deterministic engineer layer implemented for phase 1 signals
- [x] Cooldowns and deduplication added to engineer output
- [x] Replay-based tests added for deterministic callouts
- [x] GT7 field mapping assumptions documented
- [x] Live UDP capture path stubbed with raw packet recording
- [x] Basic websocket dashboard shell created

## In Progress / Needs Validation

- [ ] Validate live GT7 UDP packet format against real telemetry
- [ ] Confirm fuel field semantics from live packets
- [ ] Confirm lap timing field mappings from live packets
- [ ] Confirm whether `laps_remaining` is always explicit or sometimes derived
- [ ] Validate whether `projected_fuel_to_finish_liters` should remain a phase 1 field or be derived in a later adapter
- [ ] Verify replay path against additional sample frames from real sessions

## Next Implementation Priorities

- [ ] Add better fuel projection calibration
- [ ] Add pit recommendation rules once fuel validation is stronger
- [ ] Add connection health visibility to the engineer output if needed
- [ ] Add opponent gap / yellow flag / rain interfaces behind stubs only
- [ ] Add voice output formatting layer after deterministic text callouts are stable

## Later Phase Work

- [ ] Screen analysis / OCR adapters
- [ ] Weather and rain prediction sources
- [ ] Opponent state inference
- [ ] TTS / voice engine integration
- [ ] Session-level analytics and post-race summaries

