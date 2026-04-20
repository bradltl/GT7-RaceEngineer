from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
import uvicorn

from .config import load_config
from .engine.engine import RuleEngine
from .models import EngineerMessage, IngestResponse, SessionMetrics, TelemetrySnapshot
from .storage import HistoryStore


app = FastAPI(title="GT7 Race Engineer")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
engine: RuleEngine | None = None
store: HistoryStore | None = None
latest_metrics = SessionMetrics()
latest_message: EngineerMessage | None = None
recent_messages: list[EngineerMessage] = []
websockets: set[WebSocket] = set()


@app.on_event("startup")
def _startup() -> None:
    global engine, store
    if engine is None:
        raise RuntimeError("engine not configured")
    if store is None:
        raise RuntimeError("storage not configured")


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    return {"status": "ok", "messages": len(recent_messages)}


@app.get("/api/state")
def api_state() -> dict[str, Any]:
    return {
        "latest_message": latest_message.model_dump() if latest_message else None,
        "recent_messages": [message.model_dump() for message in recent_messages[-50:]],
        "metrics": latest_metrics.model_dump(),
    }


@app.get("/api/messages")
def api_messages() -> list[dict[str, Any]]:
    return [message.model_dump() for message in recent_messages[-50:]]


@app.post("/ingest")
def ingest(snapshot: TelemetrySnapshot) -> IngestResponse:
    assert engine is not None
    assert store is not None
    messages, metrics = engine.process(snapshot)
    _update_state(metrics, messages)
    for message in messages:
        store.add_message(message)
    return IngestResponse(accepted=True, messages=messages)


@app.post("/api/replay")
async def api_replay(payload: dict[str, Any]) -> dict[str, Any]:
    path = Path(payload["path"])
    speed_ms = int(payload.get("speed_ms", 100))
    asyncio.create_task(_replay_file(path, speed_ms))
    return {"status": "started", "path": str(path)}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    websockets.add(ws)
    try:
        await ws.send_json(await _snapshot_payload())
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        websockets.discard(ws)


def _update_state(metrics: SessionMetrics, messages: list[EngineerMessage]) -> None:
    global latest_metrics, latest_message, recent_messages
    latest_metrics = metrics
    recent_messages.extend(messages)
    if len(recent_messages) > 200:
        recent_messages = recent_messages[-200:]
    if messages:
        latest_message = messages[-1]
    asyncio.create_task(_broadcast())


async def _broadcast() -> None:
    payload = await _snapshot_payload()
    dead: set[WebSocket] = set()
    for ws in websockets:
        try:
            await ws.send_json(payload)
        except Exception:
            dead.add(ws)
    for ws in dead:
        websockets.discard(ws)


async def _snapshot_payload() -> dict[str, Any]:
    return {
        "latest_message": latest_message.model_dump() if latest_message else None,
        "recent_messages": [message.model_dump() for message in recent_messages[-50:]],
        "metrics": latest_metrics.model_dump(),
    }


async def _replay_file(path: Path, speed_ms: int) -> None:
    assert engine is not None
    if not path.exists():
        raise FileNotFoundError(path)
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            snapshot = TelemetrySnapshot.model_validate_json(line)
        except ValidationError as exc:
            print(f"replay validation error: {exc}")
            continue
        messages, metrics = engine.process(snapshot)
        _update_state(metrics, messages)
        for message in messages:
            store.add_message(message)  # type: ignore[union-attr]
        await asyncio.sleep(speed_ms / 1000)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="../../config/default.json")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    config = load_config(args.config)
    global engine, store
    engine = RuleEngine(config.engineer)
    store = HistoryStore(config.engineer.db_path)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
