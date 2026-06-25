"""Dictate — local Wispr Flow-style dictation for Windows."""

import json
import os
import sys
import tempfile
import threading
import time

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import numpy as np
import pyautogui
import pyperclip
import sounddevice as sd
from pynput import keyboard
from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import QApplication, QMessageBox
from scipy.io import wavfile

from clinical.service import ClinicalManager
from native_bridge import HotkeyCallback, NativeShell
from transcript_cleanup import TranscriptCleaner
from ui_qt import DashboardWindow, StatusOverlay, format_hotkey_display
from focus_text import get_focused_text
from paste_learner import PasteLearner
from vocabulary import VocabularyStore

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.05


def get_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


CONFIG_PATH = get_app_dir() / "config.json"
HISTORY_PATH = get_app_dir() / "history.json"

DEFAULT_CONFIG = {
    "hotkey": "<end>",
    "clinical_hotkey": "<ctrl>+<alt>+r",
    "model_size": "base",
    "device": "cpu",
    "compute_type": "int8",
    "language": "en",
    "sample_rate": 16000,
    "channels": 1,
    "restore_clipboard_after_paste": False,
    "max_history_entries": 500,
    "dictation_cleanup": True,
    "vocabulary_correction": True,
    "vocabulary_auto_learn": True,
    "vocabulary_fuzzy_threshold": 82,
    "openai_model": "gpt-4o-mini",
    "clinical_retention_days": "7",
    "clinical_max_duration_hours": 2,
}


def load_config(path: Path) -> dict:
    config = DEFAULT_CONFIG.copy()
    if path.exists():
        with open(path, encoding="utf-8") as f:
            config.update(json.load(f))
    return config


def save_config(path: Path, config: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
        f.write("\n")


def format_mic_error(exc: Exception) -> str:
    msg = str(exc).lower()
    if "device -1" in msg or "no input" in msg or "invalid device" in msg:
        return "No microphone found. Plug one in or set a default input device."
    if "unanticipated host error" in msg or "access" in msg or "permission" in msg:
        return "Microphone blocked. Check Windows privacy settings."
    text = str(exc).strip()
    return text[:60] if text else "Microphone unavailable."


def configure_frozen_vad() -> None:
    if not getattr(sys, "frozen", False):
        return

    import shutil

    import faster_whisper.utils as fw_utils
    import faster_whisper.vad as fw_vad

    meipass = Path(getattr(sys, "_MEIPASS", ""))
    src_candidates = [
        meipass / "faster_whisper" / "assets" / "silero_vad_v6.onnx",
        meipass / "assets" / "silero_vad_v6.onnx",
    ]
    src = next((p for p in src_candidates if p.is_file()), None)
    if src is None:
        raise FileNotFoundError(
            "VAD model missing from packaged app. Rebuild with build.bat."
        )

    dest_dir = Path(tempfile.gettempdir()) / "Dictate"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "silero_vad_v6.onnx"
    if not dest.exists() or dest.stat().st_size != src.stat().st_size:
        shutil.copy2(src, dest)

    assets_path = str(dest_dir)
    fw_utils.get_assets_path = lambda _path=assets_path: _path
    fw_vad.get_vad_model.cache_clear()


SINGLE_INSTANCE_MUTEX = "Global\\DictateAppMutex"


def activate_existing_window() -> bool:
    try:
        import ctypes

        user32 = ctypes.windll.user32
        found = False

        def callback(hwnd, _lparam):
            nonlocal found
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            if buff.value == "Dictate":
                user32.ShowWindow(hwnd, 9)
                user32.SetForegroundWindow(hwnd)
                found = True
            return True

        enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(
            callback
        )
        user32.EnumWindows(enum_proc, 0)
        return found
    except Exception:
        return False


def ensure_single_instance() -> bool:
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW(None, True, SINGLE_INSTANCE_MUTEX)
        if kernel32.GetLastError() == 183:
            activate_existing_window()
            return False
        return True
    except Exception:
        return True


def count_words(text: str) -> int:
    return len(text.split())


class HotkeyEmitter(QObject):
    pressed = Signal(int)


class UiInvoker(QObject):
    """Marshal callables onto the Qt main thread."""

    invoke = Signal(object)

    def __init__(self):
        super().__init__()
        self.invoke.connect(self._dispatch, Qt.ConnectionType.QueuedConnection)

    def _dispatch(self, fn):
        try:
            fn()
        except Exception:
            import traceback

            traceback.print_exc()


_hotkey_target: "DictationApp | None" = None


@HotkeyCallback
def _native_hotkey_trampoline(hotkey_id: int, _userdata) -> None:
    if _hotkey_target is not None:
        _hotkey_target._hotkey_emitter.pressed.emit(hotkey_id)


class HistoryStore:
    def __init__(self, path: Path = HISTORY_PATH, max_entries: int = 500):
        self.path = Path(path).resolve()
        self.max_entries = max_entries
        self._lock = threading.Lock()
        self._data = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            try:
                with open(self.path, encoding="utf-8") as f:
                    data = json.load(f)
                if "entries" in data:
                    return data
            except (json.JSONDecodeError, OSError):
                pass
        return {"entries": []}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.path)
        except OSError:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            raise

    def add(self, text: str, duration_sec: float) -> dict:
        entry = {
            "id": uuid4().hex,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "text": text,
            "word_count": count_words(text),
            "duration_sec": round(max(duration_sec, 0.1), 2),
        }
        with self._lock:
            self._data["entries"].insert(0, entry)
            self._data["entries"] = self._data["entries"][: self.max_entries]
            self._save()
        return entry

    def get_entries(self) -> list[dict]:
        with self._lock:
            return list(self._data["entries"])

    def delete(self, entry_id: str) -> None:
        with self._lock:
            self._data["entries"] = [
                e for e in self._data["entries"] if e.get("id") != entry_id
            ]
            self._save()

    def get_stats(self) -> dict:
        with self._lock:
            entries = self._data["entries"]
        total_words = sum(e.get("word_count", 0) for e in entries)
        total_duration = sum(e.get("duration_sec", 0) for e in entries)
        wpm = int(total_words / (total_duration / 60)) if total_duration > 0 else 0
        sessions = len(entries)
        return {
            "total_words": total_words,
            "wpm": wpm,
            "sessions": sessions,
            "total_seconds": total_duration,
        }


class _PythonAudioRecorder:
    def __init__(self, sample_rate: int = 16000, channels: int = 1):
        self.sample_rate = sample_rate
        self.channels = channels
        self._chunks: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._recording = False
        self._lock = threading.Lock()

    def _callback(self, indata, frames, time_info, status):
        if status:
            print(f"Audio status: {status}", file=sys.stderr)
        with self._lock:
            if self._recording:
                self._chunks.append(indata.copy())

    def start(self):
        with self._lock:
            self._chunks = []
            self._recording = True
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> str | None:
        with self._lock:
            self._recording = False
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        with self._lock:
            if not self._chunks:
                return None
            audio = np.concatenate(self._chunks, axis=0)
        audio = audio.flatten()
        if len(audio) == 0:
            return None
        audio_int16 = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
        fd, temp_path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        wavfile.write(temp_path, self.sample_rate, audio_int16)
        return temp_path


class AudioRecorder:
    """Native WASAPI recorder when DLL is available; otherwise sounddevice."""

    def __init__(self, native: NativeShell, sample_rate: int = 16000, channels: int = 1):
        self.native = native
        self.sample_rate = sample_rate
        self.channels = channels
        self._use_native = native.available
        self._fallback = _PythonAudioRecorder(sample_rate, channels)

    def start(self):
        if self._use_native:
            if self.native.audio_start(self.sample_rate):
                return
            self._use_native = False
        self._fallback.start()

    def stop(self) -> str | None:
        if self._use_native:
            path = self.native.audio_stop()
            if path:
                return path
            self._use_native = False
        return self._fallback.stop()


class Transcriber:
    def __init__(self, config: dict, vocabulary: VocabularyStore | None = None):
        self.config = config
        self.vocabulary = vocabulary
        self.model = None

    def load_model(self):
        from faster_whisper import WhisperModel

        self.model = WhisperModel(
            self.config["model_size"],
            device=self.config["device"],
            compute_type=self.config["compute_type"],
        )

    def transcribe(self, wav_path: str) -> str:
        if self.model is None:
            raise RuntimeError("Model not loaded")
        transcribe_kwargs: dict = {
            "language": self.config["language"],
            "vad_filter": True,
        }
        if self.vocabulary and self.config.get("vocabulary_correction", True):
            prompt = self.vocabulary.whisper_prompt()
            punct_hints = (
                "exclamation mark, question mark, colon, semicolon, comma, period, "
                "apostrophe, Telegram, Microsoft"
            )
            if prompt:
                transcribe_kwargs["initial_prompt"] = f"{prompt}, {punct_hints}"
            else:
                transcribe_kwargs["initial_prompt"] = punct_hints
        segments, _info = self.model.transcribe(wav_path, **transcribe_kwargs)
        segments = list(segments)
        text = " ".join(seg.text.strip() for seg in segments)
        text = " ".join(text.split())
        if self.vocabulary and self.config.get("vocabulary_correction", True):
            text = self.vocabulary.correct(text)
        return text


class PasteManager:
    def __init__(self, native: NativeShell, restore_clipboard: bool = False):
        self.native = native
        self.restore_clipboard = restore_clipboard

    def paste(self, text: str) -> bool:
        if self.native.paste(text, self.restore_clipboard):
            return True
        old_clipboard = None
        if self.restore_clipboard:
            try:
                old_clipboard = pyperclip.paste()
            except pyperclip.PyperclipException:
                pass
        pyperclip.copy(text)
        time.sleep(0.1)
        try:
            pyautogui.hotkey("ctrl", "v")
            if self.restore_clipboard and old_clipboard is not None:
                time.sleep(0.5)
                pyperclip.copy(old_clipboard)
            return True
        except Exception:
            return False


class DictationApp:
    def __init__(self, config: dict):
        self.config = config
        self.hotkey_display = format_hotkey_display(config["hotkey"])
        self.clinical_hotkey_display = format_hotkey_display(
            config.get("clinical_hotkey", "<ctrl>+<alt>+r")
        )
        self.state = "loading"
        self._lock = threading.Lock()
        self._hotkey_listener = None
        self._recording_started_at: float | None = None
        self._hotkey_emitter = HotkeyEmitter()
        self._hotkey_emitter.pressed.connect(
            self._on_native_hotkey, Qt.ConnectionType.QueuedConnection
        )
        self._ui_invoker = UiInvoker()
        self._alive = True

        self.native = NativeShell(get_app_dir())
        self.hotkey_backend = "none"
        self.history = HistoryStore(
            get_app_dir() / "history.json",
            max_entries=config.get("max_history_entries", 500),
        )
        self.vocabulary = VocabularyStore(
            get_app_dir(),
            fuzzy_threshold=int(config.get("vocabulary_fuzzy_threshold", 82)),
        )
        self.paste_learner = PasteLearner(self.vocabulary)
        self.recorder = AudioRecorder(
            self.native,
            sample_rate=config["sample_rate"],
            channels=config["channels"],
        )
        self.transcriber = Transcriber(config, vocabulary=self.vocabulary)
        self.transcript_cleaner = TranscriptCleaner()
        self.paste_manager = PasteManager(
            self.native,
            restore_clipboard=config.get("restore_clipboard_after_paste", False),
        )
        self.clinical = ClinicalManager(
            get_app_dir(),
            config,
            self.transcriber,
            on_update=self._clinical_updated,
            on_status=self._notify,
        )
        self.dashboard = DashboardWindow(self)
        self.status_overlay = StatusOverlay()

        self.dashboard.set_app_state("loading")
        threading.Thread(target=self._load_model, daemon=True).start()
        self._setup_hotkey()
        self.clinical.run_cleanup()
        self._schedule_clinical_cleanup()

    def _ui(self, fn):
        if self._alive:
            self._ui_invoker.invoke.emit(fn)

    def _clinical_updated(self):
        self._ui(self.dashboard.refresh_clinical)

    def _schedule_clinical_cleanup(self):
        self._ui(lambda: QTimer.singleShot(3600_000, self._run_hourly_cleanup))

    def _run_hourly_cleanup(self):
        self.clinical.run_cleanup()
        self._schedule_clinical_cleanup()

    def _notify(self, message: str, state: str = "idle", auto_hide_ms: int | None = None):
        self._ui(lambda: self._apply_notify(message, state, auto_hide_ms))

    def _apply_notify(self, message: str, state: str = "idle", auto_hide_ms: int | None = None):
        persistent = state in StatusOverlay.PERSISTENT_STATES
        clear = None if persistent else auto_hide_ms
        self.dashboard.set_status(message, auto_clear_ms=clear, state=state)

        overlay_state = state
        if state == "idle" and auto_hide_ms and message.lower() in ("ready", "pasted.", "copied, paste manually."):
            overlay_state = "success"
        if message.startswith("Learned vocabulary"):
            overlay_state = "success"

        if persistent:
            self.status_overlay.update_status(message, auto_hide_ms=None, state=state)
        elif auto_hide_ms or state in ("success", "error"):
            hide_ms = auto_hide_ms or (4000 if state == "error" else 2500)
            self.status_overlay.update_status(
                message, auto_hide_ms=hide_ms, state=overlay_state
            )
        elif state == "idle" and not self.dashboard.is_hidden:
            self.status_overlay.hide()
        elif self.dashboard.is_hidden:
            self.status_overlay.update_status(
                message, auto_hide_ms=auto_hide_ms or 3000, state=overlay_state
            )

    def _load_model(self):
        try:
            cleanup = self.config.get("dictation_cleanup", True)
            if cleanup:
                self.transcript_cleaner.preload_punctuation()
            self.transcriber.load_model()
            with self._lock:
                self.state = "idle"
            self._ui(lambda: self.dashboard.set_app_state("idle"))
            self._notify("Ready", state="success", auto_hide_ms=2500)
            if cleanup:
                self.transcript_cleaner.wait_for_punctuation(timeout=120)
                if not self.transcript_cleaner.punctuation_available():
                    err = self.transcript_cleaner.punctuation_error() or "unknown error"
                    self._notify(
                        f"Punctuation unavailable: {err[:40]}",
                        state="idle",
                        auto_hide_ms=5000,
                    )
        except Exception as exc:
            with self._lock:
                self.state = "error"
            msg = str(exc)[:60] if str(exc) else "load failed"
            self._ui(lambda: self.dashboard.set_app_state("error"))
            self._notify(f"Error: {msg}", state="error")

    def apply_settings(self, new_config: dict):
        model_changed = new_config["model_size"] != self.config["model_size"]
        self.config = new_config
        self.hotkey_display = format_hotkey_display(new_config["hotkey"])
        self.clinical_hotkey_display = format_hotkey_display(
            new_config.get("clinical_hotkey", "<ctrl>+<alt>+r")
        )
        self.clinical.config = new_config
        self.vocabulary.fuzzy_threshold = int(new_config.get("vocabulary_fuzzy_threshold", 82))
        self.vocabulary.reload()
        self.paste_manager.restore_clipboard = new_config.get(
            "restore_clipboard_after_paste", False
        )
        if self.config.get("dictation_cleanup", True) and not self.transcript_cleaner._preload_started:
            self.transcript_cleaner.preload_punctuation()
        self._reload_hotkey()
        self.dashboard.refresh()
        if model_changed:
            QMessageBox.information(
                self.dashboard,
                "Settings saved",
                "Model size changed. Please restart Dictate for it to take effect.",
            )
        else:
            self.dashboard.set_status("Settings saved.", 2500, "success")

    def _sync_app_state(self):
        self._ui(lambda: self.dashboard.set_app_state(self.state))

    def _on_native_hotkey(self, hotkey_id: int):
        self._ui(lambda: self._dispatch_hotkey(hotkey_id))

    def _dispatch_hotkey(self, hotkey_id: int):
        if hotkey_id == NativeShell.HOTKEY_QUICK:
            self._handle_quick_hotkey()
        elif hotkey_id == NativeShell.HOTKEY_CLINICAL:
            self._handle_clinical_hotkey()

    def _reload_hotkey(self):
        if self._hotkey_listener is not None:
            self._hotkey_listener.stop()
            self._hotkey_listener = None
        if self.native.available:
            self.native.unregister_hotkey(NativeShell.HOTKEY_QUICK)
            self.native.unregister_hotkey(NativeShell.HOTKEY_CLINICAL)
        self._setup_hotkey()

    def _setup_hotkey(self):
        quick = self.config["hotkey"]
        clinical = self.config.get("clinical_hotkey", "<ctrl>+<alt>+r")
        self.hotkey_backend = "none"
        self.native.hotkeys_registered = False

        if self.native.available:
            global _hotkey_target
            _hotkey_target = self
            self.native.set_hotkey_callback(_native_hotkey_trampoline)
            quick_ok = self.native.register_hotkey(quick, NativeShell.HOTKEY_QUICK)
            clinical_ok = True
            if clinical != quick:
                clinical_ok = self.native.register_hotkey(clinical, NativeShell.HOTKEY_CLINICAL)
            if quick_ok and clinical_ok:
                if self._hotkey_listener is not None:
                    self._hotkey_listener.stop()
                    self._hotkey_listener = None
                self.hotkey_backend = "native"
                self.native.hotkeys_registered = True
                self._ui(self.dashboard.refresh_footer)
                return
            self.native.unregister_hotkey(NativeShell.HOTKEY_QUICK)
            self.native.unregister_hotkey(NativeShell.HOTKEY_CLINICAL)

        self._start_pynput_hotkeys(quick, clinical)

    def _start_pynput_hotkeys(self, quick: str, clinical: str) -> None:
        if self._hotkey_listener is not None:
            self._hotkey_listener.stop()
            self._hotkey_listener = None

        def on_quick():
            self.on_quick_hotkey()

        def on_clinical():
            self.on_clinical_hotkey()

        bindings = {quick: on_quick}
        if clinical != quick:
            bindings[clinical] = on_clinical
        self._hotkey_listener = keyboard.GlobalHotKeys(bindings)
        self._hotkey_listener.start()
        self.hotkey_backend = "pynput"
        self._ui(self.dashboard.refresh_footer)
        if self.native.available:
            self._notify(
                "Using Python hotkey listener (native hotkey registration failed).",
                state="idle",
                auto_hide_ms=4500,
            )

    def on_clinical_hotkey(self):
        self._ui(self._handle_clinical_hotkey)

    def on_quick_hotkey(self):
        self._ui(self._handle_quick_hotkey)

    def _handle_clinical_hotkey(self):
        if self.clinical.is_recording():
            session = self.clinical.stop_session()
            if session:
                self._apply_notify("Processing clinical session…", state="working")
        else:
            self._apply_notify(
                "Open Clinical Session in Dictate to start an appointment recording.",
                state="idle",
                auto_hide_ms=3000,
            )

    def _handle_quick_hotkey(self):
        if self.clinical.is_recording():
            self._apply_notify(
                "Clinical session recording — stop it first or use the clinical hotkey.",
                state="recording",
                auto_hide_ms=4000,
            )
            return
        self.on_hotkey()

    def on_hotkey(self):
        action = None
        with self._lock:
            if self.state == "loading":
                self._apply_notify("Still loading models…", state="loading", auto_hide_ms=2500)
                return
            if self.state == "error":
                self._apply_notify("Model failed to load. Restart Dictate.", state="error", auto_hide_ms=4000)
                return
            if self.state == "transcribing":
                self._apply_notify("Still transcribing…", state="working", auto_hide_ms=2000)
                return
            if self.state == "idle":
                self.state = "recording"
                action = "start"
            elif self.state == "recording":
                self.state = "transcribing"
                action = "stop"
        if action == "start":
            self._maybe_learn_vocabulary()
            self._start_recording()
        elif action == "stop":
            self._stop_and_transcribe()

    def _maybe_learn_vocabulary(self):
        if not self.config.get("vocabulary_auto_learn", True):
            return
        if not self.config.get("vocabulary_correction", True):
            return
        try:
            current = get_focused_text()
            learned = self.paste_learner.check_and_learn(current)
            for term, alias in learned:
                self._notify(
                    f"Learned vocabulary: {term} (from {alias})",
                    state="success",
                    auto_hide_ms=3500,
                )
        except Exception:
            pass

    def _start_recording(self):
        try:
            self._recording_started_at = time.time()
            self.recorder.start()
            self._sync_app_state()
            self._notify(f"Recording… Press {self.hotkey_display} to stop.", state="recording")
        except Exception as exc:
            with self._lock:
                self.state = "idle"
            self._sync_app_state()
            msg = f"Error: {format_mic_error(exc)}"
            self._notify(msg, state="error", auto_hide_ms=6000)

    def _stop_and_transcribe(self):
        self._sync_app_state()
        self._notify("Transcribing…", state="working")
        threading.Thread(target=self._transcribe_worker, daemon=True).start()

    def _transcribe_worker(self):
        temp_path = None
        duration = 0.0
        if self._recording_started_at is not None:
            duration = time.time() - self._recording_started_at
        try:
            temp_path = self.recorder.stop()
            if temp_path is None:
                self._notify("No speech detected.", state="idle", auto_hide_ms=3000)
                return
            text = self.transcriber.transcribe(temp_path)
            if not text.strip():
                self._notify("No speech detected.", state="idle", auto_hide_ms=3000)
                return
            cleanup = self.config.get("dictation_cleanup", True)
            if cleanup:
                self._notify("Cleaning up…", state="working")
            text = self.transcript_cleaner.clean(
                text,
                remove_fillers_enabled=cleanup,
                add_punctuation=cleanup,
            )
            self.history.add(text, duration)
            self._ui(self.dashboard.refresh)
            if self.paste_manager.paste(text):
                if self.config.get("vocabulary_auto_learn", True):
                    self.paste_learner.remember(text)
                self._notify("Pasted.", state="success", auto_hide_ms=2000)
            else:
                self._notify("Copied, paste manually.", state="working", auto_hide_ms=4000)
        except Exception as exc:
            msg = str(exc)[:60] if str(exc) else "transcription failed"
            self._notify(f"Error: {msg}", state="error", auto_hide_ms=4000)
        finally:
            self._recording_started_at = None
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            with self._lock:
                if self.state == "transcribing":
                    self.state = "idle"
            self._ui(self._sync_app_state)

    def quit(self):
        self._alive = False
        if self.clinical.is_recording():
            if (
                QMessageBox.question(
                    self.dashboard,
                    "Dictate",
                    "A clinical session is still recording. Quit anyway?",
                )
                != QMessageBox.StandardButton.Yes
            ):
                return
        if self._hotkey_listener is not None:
            self._hotkey_listener.stop()
        self.native.shutdown()
        self.dashboard.destroy()

    def run(self):
        self.dashboard.run()


def main():
    if not ensure_single_instance():
        print(
            "Dictate is already running. Check the system tray or close the other instance.",
            file=sys.stderr,
        )
        return

    qt_app = QApplication(sys.argv)
    qt_app.setQuitOnLastWindowClosed(False)
    try:
        configure_frozen_vad()
    except Exception as exc:
        if getattr(sys, "frozen", False):
            QMessageBox.critical(
                None,
                "Dictate",
                f"Speech model setup failed:\n{exc}\n\nTry rebuilding with .\\build.bat",
            )
            return
        print(f"Failed to prepare VAD model: {exc}", file=sys.stderr)

    config = load_config(CONFIG_PATH)
    if config.get("dictation_cleanup", True):
        try:
            from punctuation_assets import ensure_punctuation_assets

            ensure_punctuation_assets()
        except Exception as exc:
            if getattr(sys, "frozen", False):
                QMessageBox.critical(
                    None,
                    "Dictate",
                    f"Punctuation model setup failed:\n{exc}\n\n"
                    "Rebuild with .\\build.bat so the model is bundled in Dictate.exe.",
                )
                return
            print(f"Failed to prepare punctuation model: {exc}", file=sys.stderr)

    try:
        app = DictationApp(config)
        app.run()
    except Exception as exc:
        QMessageBox.critical(
            None,
            "Dictate",
            f"Failed to start:\n{exc}",
        )
        raise

    sys.exit(qt_app.exec())


if __name__ == "__main__":
    main()
