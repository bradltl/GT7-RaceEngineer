from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class EngineerConfig:
    db_path: str = "data/engineer.sqlite3"
    history_limit: int = 50
    stale_telemetry_ms: int = 2500
    connection_health_ms: int = 2000
    cooldowns_ms: dict[str, int] = field(default_factory=dict)
    thresholds: dict[str, float] = field(default_factory=dict)
    enabled_callouts: dict[str, bool] = field(default_factory=dict)

    def cooldown(self, key: str, default: int) -> int:
        return int(self.cooldowns_ms.get(key, default))

    def threshold(self, key: str, default: float) -> float:
        value = self.thresholds.get(key, default)
        return float(value)


@dataclass
class AppConfig:
    engineer: EngineerConfig
    web_ui: dict[str, Any] = field(default_factory=dict)


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    data = json.loads(config_path.read_text(encoding="utf-8"))
    engineer = data.get("engineer", {})
    return AppConfig(
        engineer=EngineerConfig(
            db_path=engineer.get("db_path", "data/engineer.sqlite3"),
            history_limit=int(engineer.get("history_limit", 50)),
            stale_telemetry_ms=int(engineer.get("stale_telemetry_ms", 2500)),
            connection_health_ms=int(engineer.get("connection_health_ms", 2000)),
            cooldowns_ms=dict(engineer.get("cooldowns_ms", {})),
            thresholds=dict(engineer.get("thresholds", {})),
            enabled_callouts=dict(engineer.get("enabled_callouts", {})),
        ),
        web_ui=data.get("web_ui", {}),
    )
