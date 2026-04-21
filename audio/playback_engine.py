from __future__ import annotations

import logging
import shutil
import subprocess
import threading
import time
from pathlib import Path

from .models import AudioConfig, AudioPriority, QueuedAudioItem
from .queue_manager import AudioQueueManager


class AudioPlaybackEngine:
    def __init__(self, queue_manager: AudioQueueManager, config: AudioConfig, *, dry_run: bool | None = None):
        self.queue_manager = queue_manager
        self.config = config
        self.logger = logging.getLogger(__name__)
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._playback_stop_event = threading.Event()
        self._lock = threading.Lock()
        self._current_item: QueuedAudioItem | None = None
        self._current_process: subprocess.Popen[str] | None = None
        self.play_history: list[str] = []
        self.interrupt_history: list[str] = []
        self._dry_run = bool(dry_run) if dry_run is not None else self._detect_backend() is None
        self._backend = self._detect_backend() if not self._dry_run else None

    @property
    def current_item(self) -> QueuedAudioItem | None:
        with self._lock:
            return self._current_item

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._worker, name="audio-playback", daemon=True)
        self._thread.start()

    def shutdown(self) -> None:
        self._stop_event.set()
        self.stop()
        self.queue_manager.clear()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def play(self, file_path: str) -> bool:
        if self._dry_run:
            # Dry-run mode keeps the control flow identical but skips real audio.
            end_time = time.time() + (self.config.dry_run_playback_ms / 1000.0)
            while time.time() < end_time:
                if self._playback_stop_event.is_set() or self._stop_event.is_set():
                    return False
                time.sleep(0.02)
            return True

        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {path}")

        command = self._command_for(path)
        self.logger.debug("Playing audio via %s: %s", self._backend, path)
        proc = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with self._lock:
            self._current_process = proc
        try:
            while proc.poll() is None:
                if self._playback_stop_event.is_set() or self._stop_event.is_set():
                    self._terminate_process(proc)
                    return False
                time.sleep(0.02)
            return True
        finally:
            with self._lock:
                self._current_process = None

    def stop(self) -> None:
        self._playback_stop_event.set()
        with self._lock:
            proc = self._current_process
        if proc is not None:
            self._terminate_process(proc)

    def interrupt(self) -> None:
        # Interrupt means stop the current clip immediately so the higher-priority item can run next.
        self.interrupt_history.append(self._current_item.intent if self._current_item else "unknown")
        self.stop()

    def consider_interrupt(self, incoming_priority: AudioPriority) -> None:
        current = self.current_item
        if current is None:
            return
        if incoming_priority.rank <= current.priority.rank:
            return
        if current.priority == AudioPriority.critical:
            return
        self.interrupt()

    def wait_until_idle(self, timeout: float | None = None) -> bool:
        deadline = None if timeout is None else time.time() + timeout
        while True:
            if self.queue_manager.size() == 0 and self.current_item is None:
                return True
            if deadline is not None and time.time() >= deadline:
                return False
            time.sleep(0.05)

    def _worker(self) -> None:
        while not self._stop_event.is_set():
            item = self.queue_manager.pop_next(timeout=0.1)
            if item is None:
                continue
            with self._lock:
                self._current_item = item
                self._playback_stop_event.clear()
            played = self.play(item.file_path)
            if played:
                self.play_history.append(item.intent)
                self.queue_manager.mark_played(item)
            with self._lock:
                self._current_item = None
                self._current_process = None

    def _detect_backend(self) -> str | None:
        if self.config.player_backend and self.config.player_backend != "auto":
            return self.config.player_backend
        for candidate in ("ffplay", "mpg123", "cvlc"):
            if shutil.which(candidate):
                return candidate
        return None

    def _command_for(self, file_path: Path) -> list[str]:
        volume_percent = max(0, min(100, int(self.config.volume * 100)))
        if self._backend == "ffplay":
            return [
                "ffplay",
                "-nodisp",
                "-autoexit",
                "-loglevel",
                "quiet",
                "-volume",
                str(volume_percent),
                str(file_path),
            ]
        if self._backend == "mpg123":
            return [
                "mpg123",
                "-q",
                "--scale",
                str(volume_percent),
                str(file_path),
            ]
        if self._backend == "cvlc":
            return [
                "cvlc",
                "--play-and-exit",
                "--quiet",
                "--gain",
                str(self.config.volume),
                str(file_path),
            ]
        raise RuntimeError("No supported audio backend detected")

    def _terminate_process(self, proc: subprocess.Popen[str]) -> None:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=0.5)
