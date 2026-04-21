from __future__ import annotations

import json
import random
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    yaml = None

from .models import AudioConfig, AudioPriority, AudioRequest, QueuedAudioItem, SelectedPhrase
from .playback_engine import AudioPlaybackEngine
from .queue_manager import AudioQueueManager


def can_play_audio(telemetry_state: Any | None, *, priority: str | AudioPriority = "normal", config: AudioConfig | None = None) -> bool:
    """Gate audio so short race calls only land when the driver can actually hear them."""

    if priority == AudioPriority.critical or priority == "critical":
        return True
    if telemetry_state is None:
        return True

    config = config or AudioConfig()
    brake_threshold = config.threshold_for("brake_threshold_pct", 30.0)
    throttle_threshold = config.threshold_for("throttle_threshold_pct", 35.0)
    steering_threshold = config.threshold_for("steering_angle_threshold_deg", 12.0)

    brake_pct = _value_from_state(telemetry_state, ("brake_pct",), default=None)
    throttle_pct = _value_from_state(telemetry_state, ("throttle_pct",), default=None)
    steering_angle = _value_from_state(telemetry_state, ("steering_angle_deg", "steering_angle", "steering_pct"), default=None)

    # Critical calls bypass timing. Otherwise we prefer to speak only when the driver is not hard on the brake.
    if throttle_pct is not None and float(throttle_pct) >= throttle_threshold:
        return True
    if brake_pct is not None and float(brake_pct) >= brake_threshold:
        return False
    if steering_angle is not None and abs(float(steering_angle)) > steering_threshold:
        return False
    return True


class AudioService:
    def __init__(
        self,
        *,
        audio_root: str | Path | None = None,
        phrase_map_path: str | Path | None = None,
        config_path: str | Path | None = None,
        rng: random.Random | None = None,
        dry_run: bool | None = None,
        auto_start: bool = True,
    ):
        self.audio_root = Path(audio_root or Path(__file__).resolve().parent)
        self.phrase_map_path = Path(phrase_map_path or self.audio_root / "phrase_map.json")
        self.config_path = Path(config_path or self.audio_root / "config.yaml")
        self._rng = rng or random.Random()
        self.config = load_audio_config(self.config_path)
        self.phrase_map = load_phrase_map(self.phrase_map_path)
        self.queue_manager = AudioQueueManager(self.config)
        self.playback_engine = AudioPlaybackEngine(self.queue_manager, self.config, dry_run=dry_run)
        if auto_start:
            self.playback_engine.start()

    def list_intents(self) -> list[str]:
        return sorted(self.phrase_map.keys())

    def select_phrase(self, intent: str, tone: str | None = None, *, priority: AudioPriority = AudioPriority.medium) -> SelectedPhrase:
        intent_map = self._intent_entry(intent)
        tone_key = self._resolve_tone(intent_map, tone or self.config.default_tone)
        variations = intent_map[tone_key]
        selected = self._rng.choice(variations)
        # Phrase selection is intentionally random within a curated tone bucket so the audio stays natural.
        return SelectedPhrase(
            intent=intent,
            tone=tone_key,
            text=selected["text"],
            file=selected["file"],
            priority=priority,
            data={},
        )

    def submit(self, payload: AudioRequest | Mapping[str, Any] | Any, telemetry_state: Any | None = None) -> dict[str, Any]:
        request = self._coerce_request(payload)
        if request.intent not in self.phrase_map:
            raise ValueError(f"Unknown audio intent: {request.intent}")

        effective_telemetry = telemetry_state if telemetry_state is not None else request.telemetry_state
        if not can_play_audio(effective_telemetry, priority=request.priority, config=self.config):
            if request.priority != AudioPriority.critical:
                return {"accepted": False, "reason": "timing_gate"}

        selected = self.select_phrase(request.intent, request.tone, priority=request.priority)
        item = QueuedAudioItem(
            intent=request.intent,
            priority=request.priority,
            tone=selected.tone,
            text=selected.text,
            file_path=str(self.audio_root / "files" / selected.file),
            data=request.data,
            created_at_ms=int(time.time() * 1000),
        )
        accepted = self.queue_manager.enqueue(item)
        if accepted:
            self.playback_engine.consider_interrupt(request.priority)
        return {
            "accepted": accepted,
            "intent": request.intent,
            "tone": selected.tone,
            "priority": request.priority.value,
            "text": selected.text,
            "file": selected.file,
        }

    def submit_engineer_event(self, event: Any, telemetry_state: Any | None = None) -> dict[str, Any]:
        intent = getattr(event, "intent", None) or getattr(event, "rule_id", None)
        if not intent:
            raise ValueError("Engineer event does not contain an intent or rule_id")
        priority_value = getattr(event, "priority", AudioPriority.medium)
        if isinstance(priority_value, AudioPriority):
            priority = priority_value
        else:
            priority = AudioPriority(str(getattr(priority_value, "value", priority_value)))
        tone = getattr(event, "tone", None) or self._tone_for_priority(priority)
        data = getattr(event, "data", None) or {}
        return self.submit(AudioRequest(intent=intent, priority=priority, tone=tone, data=dict(data)), telemetry_state=telemetry_state)

    def interrupt(self) -> None:
        self.playback_engine.interrupt()

    def stop(self) -> None:
        self.playback_engine.stop()

    def shutdown(self) -> None:
        self.playback_engine.shutdown()

    def wait_until_idle(self, timeout: float | None = None) -> bool:
        return self.playback_engine.wait_until_idle(timeout=timeout)

    def _intent_entry(self, intent: str) -> dict[str, list[dict[str, str]]]:
        try:
            return self.phrase_map[intent]
        except KeyError as exc:
            raise ValueError(f"Unknown audio intent: {intent}") from exc

    def _resolve_tone(self, intent_map: dict[str, list[dict[str, str]]], tone: str) -> str:
        if tone in intent_map:
            return tone
        if self.config.default_tone in intent_map:
            return self.config.default_tone
        return next(iter(intent_map.keys()))

    def _tone_for_priority(self, priority: AudioPriority) -> str:
        if priority == AudioPriority.critical:
            return "urgent"
        if priority == AudioPriority.high:
            return "warning"
        return self.config.default_tone

    def _coerce_request(self, payload: AudioRequest | Mapping[str, Any] | Any) -> AudioRequest:
        if isinstance(payload, AudioRequest):
            return payload
        if isinstance(payload, Mapping):
            return AudioRequest(
                intent=str(payload["intent"]),
                priority=_coerce_priority(payload.get("priority", AudioPriority.medium)),
                tone=str(payload.get("tone", self.config.default_tone)),
                data=dict(payload.get("data", {}) or {}),
                telemetry_state=payload.get("telemetry_state"),
            )
        return AudioRequest(
            intent=str(getattr(payload, "intent")),
            priority=_coerce_priority(getattr(payload, "priority", AudioPriority.medium)),
            tone=str(getattr(payload, "tone", self.config.default_tone)),
            data=dict(getattr(payload, "data", {}) or {}),
            telemetry_state=getattr(payload, "telemetry_state", None),
        )


def load_phrase_map(path: str | Path) -> dict[str, dict[str, list[dict[str, str]]]]:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data


def load_audio_config(path: str | Path) -> AudioConfig:
    raw = Path(path).read_text(encoding="utf-8")
    if yaml is not None:
        data = yaml.safe_load(raw)
    else:
        data = _parse_simple_yaml(raw)
    audio = data.get("audio", data)
    return AudioConfig(
        volume=float(audio.get("volume", 0.85)),
        queue_size=int(audio.get("queue_size", 8)),
        player_backend=str(audio.get("player_backend", "auto")),
        default_tone=str(audio.get("default_tone", "normal")),
        dry_run_playback_ms=int(audio.get("dry_run_playback_ms", 500)),
        cooldowns_ms={key: int(value) for key, value in dict(audio.get("cooldowns_ms", {})).items()},
        timing_thresholds={key: float(value) for key, value in dict(audio.get("timing_thresholds", {})).items()},
    )


def _coerce_priority(value: Any) -> AudioPriority:
    if isinstance(value, AudioPriority):
        return value
    if hasattr(value, "value"):
        value = getattr(value, "value")
    return AudioPriority(str(value))


def _value_from_state(state: Any, names: tuple[str, ...], default: Any = None) -> Any:
    if isinstance(state, Mapping):
        for name in names:
            if name in state:
                return state[name]
        return default
    for name in names:
        if hasattr(state, name):
            return getattr(state, name)
    return default


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(0, root)]
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        key, _, value = line.strip().partition(":")
        value = value.strip()
        while stack and indent < stack[-1][0]:
            stack.pop()
        current = stack[-1][1]
        if not value:
            current[key] = {}
            stack.append((indent + 2, current[key]))
        else:
            current[key] = _parse_scalar(value)
    return root


def _parse_scalar(value: str) -> Any:
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value.strip('"')
