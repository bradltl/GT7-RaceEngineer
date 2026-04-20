# Technical Architecture

## Overview

The system is split into three small services:

1. `telemetry-capture` ingests GT7 telemetry, normalizes it, and records it for replay
2. `engineer` consumes normalized telemetry and generates deterministic callouts
3. `web-ui` presents the current callout, recent history, and session metrics

The services communicate through a simple JSON contract so replay and live modes use the same data shape.

## Core Design Choices

- Deterministic rule engine first, no LLM in the critical path
- Replay file support is mandatory for development and testing
- Unknown GT7 fields stay behind explicit interface boundaries
- State is kept local to the device to reduce latency and complexity
- SQLite is used for lightweight history/config persistence

If a different stack is introduced later, it should only replace the implementation inside a service, not the contract between them.

## Service Responsibilities

### telemetry-capture

Responsibilities:

- connect to the GT7 UDP source
- manage heartbeat and source health
- decode or normalize input into `TelemetrySnapshot`
- persist replay recordings as JSONL
- forward normalized snapshots to the engineer service

Important note:

- The raw GT7 payload is not assumed to be directly decodable yet
- The live decoder is an interface with a documented TODO until packet validation is complete

### engineer

Responsibilities:

- consume normalized telemetry snapshots
- detect raw signals from telemetry
- reason about race state
- apply priorities, cooldowns, and deduplication
- generate short messages ready for display and later TTS
- expose websocket updates and REST endpoints for the UI

Processing layers:

1. raw signal detection
2. race-state reasoning
3. message formatting

### web-ui

Responsibilities:

- show the current engineer message
- show recent messages
- show connection health
- show basic session metrics
- subscribe over websocket for real-time updates

## Data Flow

1. GT7 emits telemetry
2. `telemetry-capture` ingests the data and normalizes it
3. The normalized snapshot is recorded to JSONL if recording is enabled
4. The snapshot is forwarded to `engineer`
5. `engineer` processes the snapshot into signals and messages
6. `engineer` publishes updates to the websocket
7. `web-ui` renders the current state

## Normalized Contract

The canonical payload is `TelemetrySnapshot`.

Sample fields:

- session identifiers
- lap number
- laps remaining
- last lap and best lap
- fuel level and projected fuel to finish
- connection state
- optional raw fields for validation and future parsing

Unknown or not-yet-validated values must be marked optional and documented in the schema.

## Replay Mode

Replay mode reads JSONL files containing normalized snapshots.

Use cases:

- development without a PS5
- regression testing of callout behavior
- performance checks on low-resource hardware

## Persistence

SQLite is used for:

- recent message history
- config overrides if needed later

Telemetry recordings are stored as files, not in SQLite.

## Open Technical Unknowns

- exact GT7 UDP packet layout
- encrypted packet decoding strategy
- authoritative field mapping for fuel and lap timing
- whether traction/slip can be derived reliably from available telemetry
- how much of opponent state is actually available from direct telemetry

## Extension Points

Phase 2 and later should add adapters for:

- screen/OCR based signal extraction
- richer community APIs
- additional race intelligence sources
- TTS/voice output

