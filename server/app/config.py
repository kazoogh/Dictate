"""Environment configuration for Dictate API."""

from __future__ import annotations

import os
from pathlib import Path


def _env_str(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    return int(raw)


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    return float(raw)


SERVICE_NAME = "dictate-api"
TEMP_UPLOAD_DIR = Path(_env_str("DICTATE_TEMP_UPLOAD_DIR", "/tmp/dictate-api-uploads"))
TEMP_FILE_MAX_AGE_SECONDS = 3600
BACKGROUND_CLEANUP_INTERVAL_SECONDS = 30 * 60

API_KEY = _env_str("DICTATE_API_KEY")
HOST = _env_str("DICTATE_HOST", "0.0.0.0")
PORT = _env_int("DICTATE_PORT", 8765)

MAX_UPLOAD_MB = _env_int("DICTATE_MAX_UPLOAD_MB", 50)
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

CLEANUP_MODE = _env_str("DICTATE_CLEANUP_MODE", "basic").lower()
if CLEANUP_MODE not in {"basic", "openai"}:
    CLEANUP_MODE = "basic"

OPENAI_API_KEY = _env_str("OPENAI_API_KEY")
OPENAI_CLEANUP_MODEL = _env_str("OPENAI_CLEANUP_MODEL", "gpt-5.4-mini")
OPENAI_CLEANUP_TIMEOUT = _env_float("OPENAI_CLEANUP_TIMEOUT", 20.0)

# 0 = no explicit cap. Otherwise bounds the polish response so a bad model can't
# run away and stall the paste. Dictation cleanup output ~= input length, so a
# few hundred tokens covers normal use.
OPENAI_MAX_TOKENS = _env_int("DICTATE_OPENAI_MAX_TOKENS", 0)

WHISPER_MODEL_SIZE = _env_str("DICTATE_WHISPER_MODEL", "base")
WHISPER_DEVICE = _env_str("DICTATE_WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = _env_str("DICTATE_WHISPER_COMPUTE_TYPE", "int8")
WHISPER_LANGUAGE = _env_str("DICTATE_WHISPER_LANGUAGE", "en")

# --- Speed knobs -----------------------------------------------------------
# beam_size=1 (greedy) is markedly faster than the faster-whisper default of 5,
# with only a small accuracy cost on clean dictation. Raise to 5 if you notice
# accuracy regressions.
WHISPER_BEAM_SIZE = _env_int("DICTATE_WHISPER_BEAM_SIZE", 1)

# BatchedInferencePipeline transcribes VAD-detected chunks in parallel. A batch
# size > 1 gives a 3-5x speedup on CPU and even more on GPU. Set to 0/1 to fall
# back to the classic serial pipeline.
WHISPER_BATCH_SIZE = _env_int("DICTATE_WHISPER_BATCH_SIZE", 8)

# 0 = let CTranslate2 pick (uses all physical cores). Set explicitly if the VM
# shares the host with other services and you want to cap CPU usage.
WHISPER_CPU_THREADS = _env_int("DICTATE_WHISPER_CPU_THREADS", 0)
