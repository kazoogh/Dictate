"""Checks for the local engine, the cleanup rules, and mode selection.

Runs without faster-whisper, without a GPU and without downloading a model:
faster-whisper is stubbed, and Ollama is stood up as a throwaway HTTP server.

    python scripts/test_local_engine.py
"""

from __future__ import annotations

import json
import sys
import threading
import types
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TRANSCRIPT = " um so i i need to call the patient"


class _Segment:
    def __init__(self, text: str):
        self.text = text


class _FakeModel:
    last: tuple | None = None

    def __init__(self, name, **kwargs):
        self.name, self.kwargs = name, kwargs

    def transcribe(self, path, **kwargs):
        _FakeModel.last = ("serial", kwargs)
        return [_Segment(TRANSCRIPT)], {}


class _FakeBatched:
    def __init__(self, model=None):
        self.model = model

    def transcribe(self, path, **kwargs):
        _FakeModel.last = ("batched", kwargs)
        return [_Segment(TRANSCRIPT), _Segment(" tomorrow")], {}


def _install_stub() -> types.ModuleType:
    stub = types.ModuleType("faster_whisper")
    stub.WhisperModel = _FakeModel
    stub.BatchedInferencePipeline = _FakeBatched
    sys.modules["faster_whisper"] = stub
    return stub


def _audio() -> str:
    path = Path(__file__).resolve().parent / "_fake_audio.wav"
    path.write_bytes(b"RIFF")
    return str(path)


def test_cleanup_rules():
    from text_cleanup import simple_cleanup

    assert simple_cleanup("um so this is a a test") == "So this is a test."
    assert simple_cleanup("uh i need to call the the patient") == "I need to call the patient."
    assert simple_cleanup("hello there. how are you") == "Hello there. How are you."
    assert simple_cleanup("   ") == ""
    print("ok  cleanup rules")


def test_model_naming():
    from local_engine import resolve_model_name

    assert resolve_model_name("base", "en") == "base.en"
    assert resolve_model_name("base.en", "en") == "base.en"
    assert resolve_model_name("base", "fr") == "base"
    assert resolve_model_name("large-v3", "en") == "large-v3"
    print("ok  english models get the .en variant")


def test_transcribe(stub, audio):
    from local_engine import LocalDictateEngine

    engine = LocalDictateEngine(model="base", language="en")
    result = engine.transcribe(audio)
    assert _FakeModel.last[0] == "batched"
    assert result["model"] == "base.en"
    assert result["text"] == "So I need to call the patient tomorrow."
    assert engine.health()["transcribe_count"] == 1
    assert engine.health()["model_loaded"]

    serial = LocalDictateEngine(model="small.en", batch_size=1)
    serial.transcribe(audio)
    assert _FakeModel.last[0] == "serial"
    assert _FakeModel.last[1]["vad_filter"] is True
    print("ok  transcription, batched and serial")


def test_silence_is_not_an_error(stub, audio):
    from local_engine import LocalDictateEngine

    class _Silent(_FakeModel):
        def transcribe(self, path, **kwargs):
            return [], {}

    stub.WhisperModel = _Silent
    try:
        result = LocalDictateEngine(model="tiny.en", batch_size=1).transcribe(audio)
        assert result["text"] == "" and result["raw_text"] == ""
    finally:
        stub.WhisperModel = _FakeModel
    print("ok  silence returns empty text rather than raising")


def test_model_load_failure(stub):
    from local_engine import LocalDictateEngine, LocalEngineError

    class _Boom(_FakeModel):
        def __init__(self, name, **kwargs):
            raise RuntimeError("out of memory")

    stub.WhisperModel = _Boom
    try:
        LocalDictateEngine(model="large-v3").load_model()
    except LocalEngineError as exc:
        assert "out of memory" in str(exc)
    else:
        raise AssertionError("expected LocalEngineError")
    finally:
        stub.WhisperModel = _FakeModel
    print("ok  a failed model load explains itself")


def test_ollama_polish(stub, audio):
    from local_engine import LocalDictateEngine

    seen: dict = {}

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.update(body)
            seen["path"] = self.path
            payload = json.dumps({"message": {"content": "Polished by Ollama."}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        engine = LocalDictateEngine(
            model="tiny.en",
            batch_size=1,
            cleanup_mode="ollama",
            ollama_model="llama3.2",
            ollama_url=f"http://127.0.0.1:{server.server_port}",
        )
        result = engine.transcribe(audio)
        assert result["text"] == "Polished by Ollama."
        assert result["cleanup_mode"] == "ollama"
        assert seen["path"] == "/api/chat"
        assert seen["model"] == "llama3.2" and seen["stream"] is False
    finally:
        server.shutdown()
    print("ok  ollama cleanup")


def test_ollama_fallback(stub, audio):
    from local_engine import LocalDictateEngine

    engine = LocalDictateEngine(
        model="tiny.en",
        batch_size=1,
        cleanup_mode="ollama",
        ollama_model="llama3.2",
        ollama_url="http://127.0.0.1:1",  # nothing is listening here
        ollama_timeout=2,
    )
    result = engine.transcribe(audio)
    assert result["cleanup_mode"] == "basic"
    assert result["cleanup_error"]
    assert result["text"] == "So I need to call the patient."
    print("ok  a missing ollama falls back to the rules")


def test_mode_selection():
    import engine as engine_module

    cases = [
        ({}, "local"),
        ({"dictate_server_url": "http://box:8765"}, "server"),
        ({"mode": "local", "dictate_server_url": "http://box:8765"}, "local"),
        ({"mode": "server"}, "server"),
        ({"mode": "nonsense", "dictate_server_url": "http://box:8765"}, "server"),
    ]
    for config, expected in cases:
        assert engine_module.resolve_mode(config) == expected, config

    built, mode = engine_module.make_engine({"mode": "local"})
    assert mode == "local" and built.model_name == "base.en"

    built, mode = engine_module.make_engine(
        {"dictate_server_url": "http://box:8765/"}, client_name="PC1", client_version="1.0.0"
    )
    assert mode == "server" and built.base_url == "http://box:8765"

    try:
        engine_module.make_engine({"mode": "server"})
    except Exception as exc:
        assert "no Dictate server URL" in str(exc)
    else:
        raise AssertionError("server mode without a URL should refuse")
    print("ok  mode selection")


def main() -> int:
    stub = _install_stub()
    audio = _audio()
    try:
        test_cleanup_rules()
        test_model_naming()
        test_transcribe(stub, audio)
        test_silence_is_not_an_error(stub, audio)
        test_model_load_failure(stub)
        test_ollama_polish(stub, audio)
        test_ollama_fallback(stub, audio)
        test_mode_selection()
    finally:
        Path(audio).unlink(missing_ok=True)
    print("\nAll local-engine checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
