# Installation Guide

This guide covers installing the project on:

- CachyOS
- Ubuntu and Ubuntu-based systems

The current codebase is a local-first development scaffold. The recommended deployment model is a single Linux machine running the engineer backend, telemetry capture service, and browser UI locally.

## Requirements

- Git
- Go 1.22 or newer
- Python 3.11 or newer
- Node.js 20 or newer
- npm

## CachyOS Install

CachyOS is Arch-based, so install packages with `pacman`.

```bash
sudo pacman -Syu
sudo pacman -S git go python nodejs npm
```

If your CachyOS install uses a different Node package set, install a current LTS Node release instead of the distro default.

## Ubuntu Install

On Ubuntu and Ubuntu-based systems, install packages with `apt`.

```bash
sudo apt update
sudo apt install -y git golang python3 python3-venv python3-pip nodejs npm
```

If the distro Node version is too old for Vite or your local workflow, install a current LTS Node version separately and make sure it is first on `PATH`.

## Clone The Repo

```bash
git clone <repo-url>
cd GT7-RaceEngineer
```

Replace `<repo-url>` with the actual remote URL for this project.

## Engineer Service Setup

The engineer service hosts the API and websocket backend.

```bash
cd services/engineer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.main --config ../../config/default.json
```

If you are using a shell that does not support `source`, activate the virtual environment with the equivalent command for that shell.

## Telemetry Capture Setup

The capture service is written in Go.

```bash
cd services/telemetry-capture
export GOTELEMETRY=off
export GOCACHE="$PWD/.gocache"
export GOMODCACHE="$PWD/.gomodcache"
mkdir -p "$GOCACHE" "$GOMODCACHE"
go run ./cmd/telemetry-capture -config ../../config/default.json
```

Current default mode is replay. That lets you validate the engineer layer without a live PS5 feed.

## Web UI Setup

```bash
cd services/web-ui
npm install
npm run dev
```

Open the Vite URL shown in the terminal after the dev server starts.

## Local Replay Workflow

1. Start the engineer service.
2. Start the telemetry capture service.
3. Start the web UI.
4. Load the sample telemetry replay or post a replay file to the engineer API.

Replay sample:

```bash
curl -X POST http://127.0.0.1:8000/api/replay \
  -H "Content-Type: application/json" \
  -d '{"path":"../../contracts/sample_normalized_telemetry.jsonl"}'
```

## Live GT7 Mode

Live GT7 UDP capture is not fully validated yet.

Before using live mode:

- confirm the packet decoder against real GT7 telemetry
- validate fuel and lap field mappings
- verify the engineer output on replay data first

## Notes For Future Packaging

This repo is not yet packaged as a single installable system service.
If you want a systemd-based install later, the likely next step is:

- one unit for `engineer`
- one unit for `telemetry-capture`
- one optional unit or static file server for `web-ui`

