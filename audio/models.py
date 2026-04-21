from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AudioPriority(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"

    @property
    def rank(self) -> int:
        return {
            AudioPriority.critical: 4,
            AudioPriority.high: 3,
            AudioPriority.medium: 2,
            AudioPriority.low: 1,
        }[self]


@dataclass(frozen=True)
class AudioRequest:
    intent: str
    priority: AudioPriority = AudioPriority.medium
    tone: str = "normal"
    data: dict[str, Any] = field(default_factory=dict)
    telemetry_state: Any | None = None


@dataclass(frozen=True)
class SelectedPhrase:
    intent: str
    tone: str
    text: str
    file: str
    priority: AudioPriority
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class QueuedAudioItem:
    intent: str
    priority: AudioPriority
    tone: str
    text: str
    file_path: str
    data: dict[str, Any] = field(default_factory=dict)
    created_at_ms: int = 0
    sequence: int = 0


@dataclass
class AudioConfig:
    volume: float = 0.85
    queue_size: int = 8
    player_backend: str = "auto"
    default_tone: str = "normal"
    dry_run_playback_ms: int = 500
    cooldowns_ms: dict[str, int] = field(default_factory=dict)
    timing_thresholds: dict[str, float] = field(default_factory=dict)

    def cooldown_for(self, intent: str, default: int = 0) -> int:
        return int(self.cooldowns_ms.get(intent, default))

    def threshold_for(self, key: str, default: float) -> float:
        return float(self.timing_thresholds.get(key, default))

