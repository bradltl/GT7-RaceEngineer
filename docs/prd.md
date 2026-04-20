# Product Requirements Document

## Summary

Build a Gran Turismo 7 race engineer assistant that emits short, high-value, race-critical callouts in real time. The system should behave like a human race engineer, not a chat assistant.

## Goals

- Deliver concise, actionable callouts while the driver is racing
- Keep latency low and behavior deterministic
- Support a single-device deployment on low-resource Linux
- Provide replayable telemetry so engineer logic can be developed without a PS5
- Make unsupported features explicit behind clean interfaces

## Non-Goals

- No conversational chat interface in the core product
- No cloud-first architecture
- No distributed microservice mesh
- No assumption that every desired insight is directly exposed by GT7 telemetry

## Primary User

Sim racer driving GT7 on PS5, using a second device or local browser for race engineer guidance.

## Phase 1 Scope

Supported directly from normalized telemetry or simple derivation:

- lap count and laps remaining
- final lap detection
- fuel status and projected fuel to finish
- pit recommendation when fuel becomes critical
- best lap and last lap deltas
- connection health
- basic session metrics in the UI

## Phase 2+ Scope

Behind interfaces for later implementation:

- opponent gaps and gap changes
- pit entry detection for cars ahead
- yellow flag detection
- rain prediction and weather transition warnings
- traction/slip analysis if validated telemetry supports it
- voice output

## Product Principles

- Deterministic first, AI phrasing later
- Short messages only
- No repeated chatter unless the state materially changes
- Prefer reliable partial coverage over speculative completeness

## Success Criteria

- Replay data can drive the full dashboard without a live console
- Engineer output is consistent for the same telemetry input
- Unknown telemetry fields are isolated and documented
- New signal types can be added without refactoring the whole system

