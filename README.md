# GT7 Race Engineer

Real-time race engineer assistant for Gran Turismo 7 on PS5.

The first pass is a deterministic, low-latency scaffold built for a single low-resource Linux device:

- `telemetry-capture`: Go service for ingest, normalization, replay, and recording
- `engineer`: Python service for deterministic race callouts and websocket distribution
- `web-ui`: React + TypeScript dashboard for live engineer output and session metrics

The live GT7 UDP payload is treated as an unknown until validated. Phase 1 uses normalized replay/mock data so the engineer logic can be built and tested without a live console feed.

## Repository Layout

- `docs/` product and architecture documents
- `docs/install-linux.md` Linux installation guide
- `docs/todo.md` live todo/status list
- `contracts/` normalized telemetry schemas and sample recordings
- `config/` default thresholds and feature flags
- `services/telemetry-capture/` Go telemetry ingest and replay scaffold
- `services/engineer/` Python deterministic rule engine and websocket backend
- `services/web-ui/` React dashboard shell

## Local Run

Open three terminals from the repo root and run the services in parallel.

1. Start the engineer service:

```powershell
cd services/engineer
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.main --config ..\..\config\default.json
```

2. Start the telemetry capture service in replay mode:

```powershell
cd services\telemetry-capture
$env:GOTELEMETRY='off'
$env:GOCACHE=Join-Path $PWD '.gocache'
$env:GOMODCACHE=Join-Path $PWD '.gomodcache'
New-Item -ItemType Directory -Force -Path $env:GOCACHE,$env:GOMODCACHE | Out-Null
go run ./cmd/telemetry-capture -config ..\..\config\default.json
```

3. Start the web UI:

```powershell
cd services/web-ui
npm install
npm run dev
```

4. Optional fallback if you want to replay directly into the engineer service instead of using telemetry-capture:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/replay -ContentType application/json -Body '{"path":"..\..\contracts\sample_normalized_telemetry.jsonl"}'
```

5. Open the dashboard at the Vite URL shown in the terminal.

Optional:

- Point `telemetry-capture` at the engineer `/ingest` endpoint once the live UDP decoder is validated.
