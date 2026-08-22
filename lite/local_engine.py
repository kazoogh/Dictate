"""On-device transcription: Whisper runs on this computer, nothing leaves it.

This is the local half of Dictate. It exposes the same two methods as
``DictateServerClient`` — ``health()`` and ``transcribe(path)`` — and returns
the same response shape, so the rest of the app doesn't care which one it got.

The model is loaded lazily and kept in memory. The first load downloads the
weights from Hugging Face (a few hundred MB for the default ``base.en``) and
caches them under the user's home directory; every run after that is offline.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any

from text_cleanup import polish_text

logger = logging.getLogger("dictate.local")

# Model sizes that ship a faster, more accurate English-only twin.
_EN_CAPABLE = {"tiny", "base", "small", "medium"}

# What the settings screen offers, smallest first. The trade is speed vs
# accuracy; base.en is the sweet spot on a typical office CPU.
MODEL_CHOICES = (
    "tiny.en",
    "base.en",
    "small.en",
    "medium.en",
    "large-v3-turbo",
    "large-v3",
)


class LocalEngineError(Exception):
    """Raised when local transcription cannot be performed."""


def resolve_model_name(model: str, language: str) -> str:
    """Prefer the ``.en`` build when dictating English — it's faster AND better."""
    name = (model or "base").strip()
    if (language or "").strip().lower() == "en" and name in _EN_CAPABLE and not name.endswith(".en"):
        return f"{name}.en"
    return name


class LocalDictateEngine:
    """Transcribes with faster-whisper in this process."""

    def __init__(
        self,
        *,
        model: str = "base.en",
        device: str = "cpu",
        compute_type: str = "int8",
        language: str = "en",
        beam_size: int = 1,
        batch_size: int = 8,
        cpu_threads: int = 0,
        cleanup_mode: str = "basic",
        ollama_model: str = "",
        ollama_url: str = "http://127.0.0.1:11434",
        ollama_timeout: float = 30.0,
    ):
        self.model_name = resolve_model_name(model, language)
        self.device = (device or "cpu").strip()
        self.compute_type = (compute_type or "int8").strip()
        self.language = (language or "").strip()
        self.beam_size = max(1, int(beam_size))
        self.batch_size = int(batch_size)
        self.cpu_threads = int(cpu_threads)
        self.cleanup_mode = (cleanup_mode or "basic").strip().lower()
        self.ollama_model = ollama_model.strip()
        self.ollama_url = ollama_url.strip() or "http://127.0.0.1:11434"
        self.ollama_timeout = float(ollama_timeout)

        self._model: Any = None
        self._batched: Any = None
        self._lock = threading.Lock()
        self._transcribe_count = 0
        self._last_seconds: float | None = None
        self._last_error: str | None = None

    # -- model ---------------------------------------------------------- #
    @property
    def model_loaded(self) -> bool:
        return self._model is not None

    def load_model(self) -> None:
        """Load (and on first run, download) the Whisper weights. Safe to call twice."""
        with self._lock:
            if self._model is not None:
                return
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise LocalEngineError(
                    "Local mode needs faster-whisper. Install it with:\n"
                    "    pip install -r requirements-local.txt"
                ) from exc

            logger.info(
                "Loading local Whisper model=%s device=%s compute=%s beam=%s batch=%s",
                self.model_name, self.device, self.compute_type, self.beam_size, self.batch_size,
            )
            kwargs: dict[str, Any] = {"device": self.device, "compute_type": self.compute_type}
            if self.cpu_threads > 0:
                kwargs["cpu_threads"] = self.cpu_threads
            try:
                self._model = WhisperModel(self.model_name, **kwargs)
            except Exception as exc:
                self._last_error = str(exc)[:300]
                raise LocalEngineError(f"Could not load model '{self.model_name}': {exc}") from exc

            # Batched inference transcribes VAD chunks in parallel — the big win
            # on CPU. Older faster-whisper builds lack it, so this stays optional.
            if self.batch_size and self.batch_size > 1:
                try:
                    from faster_whisper import BatchedInferencePipeline

                    self._batched = BatchedInferencePipeline(model=self._model)
                except Exception as exc:  # pragma: no cover - version dependent
                    self._batched = None
                    logger.warning(
                        "Batched inference unavailable (%s); using the serial pipeline. "
                        "Upgrade to faster-whisper>=1.1.0 for the speedup.", exc,
                    )
            logger.info("Local Whisper model ready")

    # -- interface shared with DictateServerClient ---------------------- #
    def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "service": "dictate-local",
            "model_loaded": self.model_loaded,
            "model": self.model_name,
            "device": self.device,
            "compute_type": self.compute_type,
            "cleanup_mode": self.cleanup_mode,
            "transcribe_count": self._transcribe_count,
            "last_transcribe_seconds": self._last_seconds,
            "last_error": self._last_error,
        }

    def transcribe(self, audio_path: str | Path) -> dict[str, Any]:
        path = Path(audio_path)
        if not path.is_file():
            raise LocalEngineError(f"Audio file not found: {path}")

        if self._model is None:
            self.load_model()

        started = time.perf_counter()
        language = self.language or None
        try:
            if self._batched is not None:
                segments, _info = self._batched.transcribe(
                    str(path),
                    language=language,
                    beam_size=self.beam_size,
                    batch_size=self.batch_size,
                )
            else:
                segments, _info = self._model.transcribe(
                    str(path),
                    language=language,
                    beam_size=self.beam_size,
                    vad_filter=True,
                )
            parts = [seg.text.strip() for seg in segments if seg.text.strip()]
        except Exception as exc:
            self._last_error = str(exc)[:300]
            raise LocalEngineError(f"Transcription failed: {exc}") from exc

        raw_text = " ".join(parts).strip()
        if not raw_text:
            # Silence isn't an error — the app shows "No speech detected".
            self._transcribe_count += 1
            self._last_seconds = time.perf_counter() - started
            return {
                "text": "",
                "raw_text": "",
                "processing_time_seconds": round(self._last_seconds, 2),
                "model": self.model_name,
                "device": self.device,
            }

        result = polish_text(
            raw_text,
            mode=self.cleanup_mode,
            ollama_model=self.ollama_model,
            ollama_url=self.ollama_url,
            ollama_timeout=self.ollama_timeout,
        )
        elapsed = time.perf_counter() - started
        self._transcribe_count += 1
        self._last_seconds = elapsed

        # Text is never logged — only how much of it there was.
        logger.info("Local transcribe OK in %.2fs (%d chars)", elapsed, len(result.text))

        payload: dict[str, Any] = {
            "text": result.text,
            "raw_text": raw_text,
            "processing_time_seconds": round(elapsed, 2),
            "model": self.model_name,
            "device": self.device,
            "cleanup_mode": result.mode_used,
        }
        if result.cleanup_error:
            payload["cleanup_error"] = result.cleanup_error
        return payload
