# Contracts

This directory contains the canonical JSON shapes for normalized telemetry and engineer messages.

## Current Status

- `normalized_telemetry.schema.json` is the phase 1 contract for replay and live ingestion
- `engine_message.schema.json` describes the output sent to the dashboard
- `sample_normalized_telemetry.jsonl` is a replay file used for local development

## Validation Notes

The following areas still need live GT7 validation:

- UDP packet decoding
- exact fuel field semantics
- exact lap timing source fields
- flag and weather field availability
- traction/slip derivation feasibility

