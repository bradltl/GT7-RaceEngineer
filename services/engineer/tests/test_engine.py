from __future__ import annotations

from pathlib import Path
import unittest

from app.config import EngineerConfig
from app.engine.engine import RuleEngine
from app.models import ConnectionState, SourceMode, TelemetrySnapshot


class RuleEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = EngineerConfig(
            cooldowns_ms={
                "final_lap": 60000,
                "laps_remaining": 30000,
                "fuel_critical": 30000,
                "projected_fuel_to_finish": 30000,
                "box_this_lap": 30000,
                "best_lap": 0,
            },
            thresholds={
                "fuel_critical_laps": 1.0,
                "fuel_to_finish_margin_liters": 0.5,
                "best_lap_improvement_ms": 250,
            },
            enabled_callouts={
                "laps_remaining": True,
                "final_lap": True,
                "fuel_status": True,
                "projected_fuel_to_finish": True,
                "box_this_lap": True,
                "best_lap": True,
            },
        )
        self.engine = RuleEngine(self.config)

    def test_sample_replay_frames_emit_expected_messages(self) -> None:
        frames = self._load_sample_frames()
        outputs = []
        for frame in frames:
            messages, _ = self.engine.process(frame)
            outputs.append([message.text for message in messages])

        self.assertEqual(outputs[0], [])
        self.assertEqual(outputs[1], [])
        self.assertEqual(outputs[2], [])
        self.assertEqual(
            outputs[3],
            [
                "Box this lap",
                "Fuel to finish: deficit 0.1 L",
                "2 laps remaining",
            ],
        )
        self.assertEqual(
            outputs[4],
            [
                "Fuel critical, 0.6 laps left",
                "Box this lap",
                "Fuel to finish: deficit 1.4 L",
                "Final lap",
            ],
        )

    def test_repeat_snapshot_is_suppressed_by_cooldown(self) -> None:
        snapshot = TelemetrySnapshot(
            event_id="evt-2",
            timestamp_ms=1000,
            session_id="session-1",
            source="replay",
            source_mode=SourceMode.replay,
            connection_state=ConnectionState.connected,
            laps_remaining=2,
        )
        first_messages, _ = self.engine.process(snapshot)
        second_messages, _ = self.engine.process(snapshot.model_copy(update={"event_id": "evt-3", "timestamp_ms": 2000}))

        self.assertEqual([message.text for message in first_messages], ["2 laps remaining"])
        self.assertEqual(second_messages, [])

    def test_best_lap_improvement_emits_callout(self) -> None:
        frame = self._load_sample_frames()[2].model_copy(
            update={"event_id": "evt-best", "last_lap_time_ms": 90000}
        )

        messages, _ = self.engine.process(frame)

        self.assertEqual(messages[0].text, "New best lap, 0.780s quicker")

    def _load_sample_frames(self) -> list[TelemetrySnapshot]:
        path = Path(__file__).resolve().parents[3] / "contracts" / "sample_normalized_telemetry.jsonl"
        frames: list[TelemetrySnapshot] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            frames.append(TelemetrySnapshot.model_validate_json(line))
        return frames


if __name__ == "__main__":
    unittest.main()
