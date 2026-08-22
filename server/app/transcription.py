"""faster-whisper transcription wrapper (batched + speed-tuned)."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any

from app import config
from app.state import runtime_state

logger = logging.getLogger("dictate.transcribe")

_model: Any = None
_batched_model: Any = None
_model_lock = threading.Lock()

# Multilingual sizes that have a faster/more-accurate English-only (.en) variant.
_EN_CAPABLE = {"tiny", "base", "small", "medium"}


def _resolve_model_name() -> str:
    """Prefer the English-only variant for English so it's faster AND better.

    large-v3 / large-v3-turbo / distil-* have no ``.en`` build, so they're left
    untouched. Only the small multilingual sizes gain a ``.en`` twin.
    """
    name = config.WHISPER_MODEL_SIZE
    lang = (config.WHISPER_LANGUAGE or "").lower()
    if lang == "en" and name in _EN_CAPABLE and not name.endswith(".en"):
        return f"{name}.en"
    return name


def load_model() -> None:
    global _model, _batched_model
    with _model_lock:
        if _model is not None:
            runtime_state.model_loaded = True
            return

        model_name = _resolve_model_name()
        logger.info(
            "Loading Whisper model=%s device=%s compute=%s beam=%s batch=%s threads=%s",
            model_name,
            config.WHISPER_DEVICE,
            config.WHISPER_COMPUTE_TYPE,
            config.WHISPER_BEAM_SIZE,
            config.WHISPER_BATCH_SIZE,
            config.WHISPER_CPU_THREADS,
        )
        from faster_whisper import WhisperModel

        model_kwargs: dict[str, Any] = {
            "device": config.WHISPER_DEVICE,
            "compute_type": config.WHISPER_COMPUTE_TYPE,
        }
        if config.WHISPER_CPU_THREADS > 0:
            model_kwargs["cpu_threads"] = config.WHISPER_CPU_THREADS

        _model = WhisperModel(model_name, **model_kwargs)

        # Batched pipeline parallelizes across VAD chunks — the big CPU/GPU win.
        # Guarded so an older faster-whisper without it still runs (serial).
        if config.WHISPER_BATCH_SIZE and config.WHISPER_BATCH_SIZE > 1:
            try:
                from faster_whisper import BatchedInferencePipeline

                _batched_model = BatchedInferencePipeline(model=_model)
                logger.info(
                    "Batched inference enabled (batch_size=%s)", config.WHISPER_BATCH_SIZE
                )
            except Exception as exc:  # pragma: no cover - depends on installed version
                _batched_model = None
                logger.warning(
                    "BatchedInferencePipeline unavailable (%s); using serial pipeline. "
                    "Upgrade faster-whisper>=1.1.0 for the batched speedup.",
                    exc,
                )

        runtime_state.model_loaded = True
        logger.info("Whisper model loaded")


def transcribe_file(audio_path: Path) -> tuple[str, float]:
    """Transcribe audio file. Returns (raw_text, elapsed_seconds). Does not log text."""
    if _model is None:
        load_model()

    language = config.WHISPER_LANGUAGE or None
    beam_size = max(1, config.WHISPER_BEAM_SIZE)

    started = time.perf_counter()
    if _batched_model is not None:
        # Batched pipeline runs VAD internally to form the batches.
        segments, _info = _batched_model.transcribe(
            str(audio_path),
            language=language,
            beam_size=beam_size,
            batch_size=config.WHISPER_BATCH_SIZE,
        )
    else:
        segments, _info = _model.transcribe(
            str(audio_path),
            language=language,
            beam_size=beam_size,
            vad_filter=True,
        )

    parts: list[str] = []
    for segment in segments:
        piece = segment.text.strip()
        if piece:
            parts.append(piece)
    raw_text = " ".join(parts).strip()
    elapsed = time.perf_counter() - started
    logger.info(
        "Transcribed %s in %.2fs (%d chars)",
        audio_path.name,
        elapsed,
        len(raw_text),
    )
    return raw_text, elapsed
