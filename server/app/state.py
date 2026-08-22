"""Mutable runtime metrics for health and observability."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class RuntimeState:
    start_time: float = field(default_factory=time.time)
    model_loaded: bool = False
    transcribe_count: int = 0
    last_transcribe_seconds: float | None = None
    last_error: str | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record_transcribe(self, elapsed_seconds: float) -> None:
        with self._lock:
            self.transcribe_count += 1
            self.last_transcribe_seconds = elapsed_seconds

    def record_error(self, message: str) -> None:
        with self._lock:
            self.last_error = message[:500]

    def uptime_seconds(self) -> float:
        return max(0.0, time.time() - self.start_time)

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "uptime_seconds": round(self.uptime_seconds(), 2),
                "model_loaded": self.model_loaded,
                "transcribe_count": self.transcribe_count,
                "last_transcribe_seconds": self.last_transcribe_seconds,
                "last_error": self.last_error,
            }


runtime_state = RuntimeState()
