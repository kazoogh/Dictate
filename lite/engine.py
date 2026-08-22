"""Picks the transcription engine the app should use.

Dictate can run two ways and this is the one place that decides which:

  local   faster-whisper runs on this computer; audio never leaves it
  server  audio is posted to a Dictate API server you (or your IT team) host
  auto    server when a server URL is configured, local otherwise

``auto`` is the default so an existing install with a server URL keeps
behaving exactly as it did, while a fresh install works offline out of the box.
"""

from __future__ import annotations

from typing import Any

from local_engine import LocalDictateEngine, LocalEngineError
from server_client import DictateServerClient, DictateServerError

MODES = ("auto", "local", "server")

# Everything an engine can raise that the app should treat as "this dictation
# failed" rather than as a bug.
ENGINE_ERRORS = (DictateServerError, LocalEngineError, OSError, TimeoutError, RuntimeError, ValueError)


def resolve_mode(config: dict) -> str:
    """Return the concrete mode — 'local' or 'server' — for this config."""
    mode = str(config.get("mode", "auto")).strip().lower()
    if mode not in MODES:
        mode = "auto"
    if mode != "auto":
        return mode
    return "server" if str(config.get("dictate_server_url", "")).strip() else "local"


# Config keys that change what an engine *is*. Anything else (hotkey, history
# size, clipboard behaviour) can be saved without rebuilding it — which in local
# mode would mean reloading the Whisper model.
_ENGINE_KEYS = (
    "mode",
    "dictate_server_url",
    "dictate_server_api_key",
    "server_timeout_seconds",
    "local_model",
    "local_device",
    "local_compute_type",
    "local_language",
    "local_beam_size",
    "local_batch_size",
    "local_cpu_threads",
    "local_cleanup_mode",
    "ollama_url",
    "ollama_model",
    "ollama_timeout_seconds",
)


def engine_signature(config: dict) -> tuple:
    """Fingerprint of the settings an engine is built from."""
    return tuple(str(config.get(key, "")) for key in _ENGINE_KEYS)


def make_local_engine(config: dict) -> LocalDictateEngine:
    return LocalDictateEngine(
        model=str(config.get("local_model", "base.en")),
        device=str(config.get("local_device", "cpu")),
        compute_type=str(config.get("local_compute_type", "int8")),
        language=str(config.get("local_language", "en")),
        beam_size=int(config.get("local_beam_size", 1)),
        batch_size=int(config.get("local_batch_size", 8)),
        cpu_threads=int(config.get("local_cpu_threads", 0)),
        cleanup_mode=str(config.get("local_cleanup_mode", "basic")),
        ollama_model=str(config.get("ollama_model", "")),
        ollama_url=str(config.get("ollama_url", "http://127.0.0.1:11434")),
        ollama_timeout=float(config.get("ollama_timeout_seconds", 30)),
    )


def make_server_client(
    config: dict, *, client_name: str = "", client_version: str = ""
) -> DictateServerClient:
    return DictateServerClient(
        str(config.get("dictate_server_url", "")).strip().rstrip("/"),
        api_key=str(config.get("dictate_server_api_key", "")),
        timeout=float(config.get("server_timeout_seconds", 60)),
        client_name=client_name,
        client_version=client_version,
    )


def make_engine(
    config: dict, *, client_name: str = "", client_version: str = ""
) -> tuple[Any, str]:
    """Return ``(engine, mode)`` where mode is the resolved 'local' or 'server'."""
    mode = resolve_mode(config)
    if mode == "local":
        return make_local_engine(config), "local"
    client = make_server_client(config, client_name=client_name, client_version=client_version)
    if not client.base_url:
        raise DictateServerError(
            "Server mode is selected but no Dictate server URL is configured. "
            "Add one in Settings, or switch the mode to Local."
        )
    return client, "server"
