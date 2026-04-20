# Phased Roadmap

## Phase 1

Foundation and deterministic engineer:

- scaffold all three services
- define and validate normalized telemetry schema
- implement replay and recording
- implement laps remaining, final lap, fuel, and lap delta callouts
- add websocket dashboard shell
- persist message history in SQLite

## Phase 2

Expanded telemetry-derived intelligence:

- improve fuel projection models
- refine pit timing guidance
- add session-level trend summaries
- add optional traction/slip warnings if validated fields exist
- add configurable callout suppression rules

## Phase 3

External signal adapters:

- opponent gap estimation
- pit-entry detection ahead
- yellow flag integration
- rain and weather prediction
- screen analysis / OCR adapters

## Phase 4

Voice and operational polish:

- TTS output
- voice profile selection
- callout prioritization tuned for audio
- pre-race configuration and live session presets

## Delivery Rule

Each phase should remain usable on its own. Do not block a working replay-driven engineer on unknown telemetry fields.

