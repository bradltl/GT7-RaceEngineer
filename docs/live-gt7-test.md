# Direct GT7 Test Setup

This is the shortest path to test the assistant against a real GT7 session on PS5.

## Assumptions

- GT7 telemetry is enabled in the game settings.
- The PS5 and the Linux host are on the same network.
- The capture service listens on UDP port `33740`.
- The capture service sends GT7 heartbeat packets to the PS5 on UDP port `33739`.
- The current live decoder assumes the standard packet type `A`.
- TODO(gt7-field-validation): confirm the packet `A` offsets and the current fuel / lap semantics against your actual console build.

## What The Live Path Does

- Sends heartbeat packets to keep GT7 streaming telemetry.
- Receives encrypted GT7 UDP packets.
- Decrypts packets with the community-documented Salsa20 key.
- Normalizes the packet into the shared telemetry snapshot contract.
- Forwards snapshots to the engineer service.
- Falls back to raw packet recording if decode validation fails.

## Live Test Checklist

1. In GT7, enable telemetry output in the game options.
2. Set the PS5 console IP in `config/default.json` under `telemetry_capture.playstation_ip`.
3. Set `telemetry_capture.source_mode` to `live`.
4. Start the engineer service on port `8000`.
5. Start the telemetry capture service.
6. Watch `GET /healthz` on the capture service and the engineer dashboard for incoming updates.

## Direct Test Notes

- If no heartbeat is sent, GT7 will stop streaming telemetry after a short period.
- If the packet decode fails, the service records the raw UDP payload to `recordings/raw-packets.jsonl`.
- If the packet decode succeeds but any field mapping is uncertain, the snapshot includes validation warnings instead of silently inventing values.
