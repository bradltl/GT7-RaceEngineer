from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

if __package__ is None or __package__ == "":  # pragma: no cover - script entrypoint support
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audio.audio_service import AudioService
from audio.models import AudioPriority, AudioRequest


def main() -> int:
    parser = argparse.ArgumentParser(description="GT7 race engineer audio test mode")
    parser.add_argument("--list", action="store_true", help="List available intents and phrase variants")
    parser.add_argument("--intent", help="Trigger one intent manually")
    parser.add_argument("--tone", default="normal", help="Tone to use for --intent")
    parser.add_argument("--priority", default="medium", choices=["critical", "high", "medium", "low"], help="Priority for --intent")
    parser.add_argument("--count", type=int, default=1, help="How many times to trigger the selected intent")
    parser.add_argument("--random-seed", type=int, default=7, help="Seed phrase selection for reproducible runs")
    parser.add_argument("--sample", help="Sample random phrase selection without queueing")
    parser.add_argument("--sample-count", type=int, default=5, help="How many random samples to print for --sample")
    parser.add_argument("--conflict", action="store_true", help="Simulate a lower-priority clip being interrupted by a critical one")
    parser.add_argument("--smoke", action="store_true", help="Play one selection for each intent in the catalog")
    args = parser.parse_args()

    service = AudioService(rng=random.Random(args.random_seed), dry_run=True)

    if args.list:
        for intent in service.list_intents():
            print(intent)
            for tone, variants in service.phrase_map[intent].items():
                for variant in variants:
                    print(f"  [{tone}] {variant['text']} -> {variant['file']}")
        return 0

    if args.sample:
        for _ in range(max(1, args.sample_count)):
            phrase = service.select_phrase(args.sample, args.tone)
            print({"intent": phrase.intent, "tone": phrase.tone, "text": phrase.text, "file": phrase.file})
        return 0

    if args.conflict:
        print("Queueing medium-priority call, then critical interrupt...")
        service.submit(AudioRequest(intent="on_best_lap_pace", priority=AudioPriority.medium, tone="normal"))
        time.sleep(0.05)
        service.submit(AudioRequest(intent="fuel_critical", priority=AudioPriority.critical, tone="urgent"))
        service.wait_until_idle(timeout=5.0)
        print("Played:", service.playback_engine.play_history)
        print("Interrupts:", service.playback_engine.interrupt_history)
        return 0

    if args.smoke:
        for intent in service.list_intents():
            result = service.submit(AudioRequest(intent=intent, priority=AudioPriority.medium, tone="normal"))
            print(result)
        service.wait_until_idle(timeout=10.0)
        print("Played:", service.playback_engine.play_history)
        return 0

    if args.intent:
        for _ in range(max(1, args.count)):
            result = service.submit(
                AudioRequest(
                    intent=args.intent,
                    priority=AudioPriority(args.priority),
                    tone=args.tone,
                )
            )
            print(result)
        service.wait_until_idle(timeout=5.0)
        print("Played:", service.playback_engine.play_history)
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
