"""Dictate Lite — server-backed quick dictation for Windows."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import wave

from ctypes import wintypes
from datetime import datetime
from pathlib import Path
from typing import Callable
from uuid import uuid4

import numpy as np
import pyautogui
import pyperclip
import sounddevice as sd
from pynput import keyboard
from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import QApplication, QMessageBox

from audio_devices import (
    count_input_devices,
    input_device_signature,
    open_input_stream,
    refresh_audio_devices,
)
from native_bridge import HotkeyCallback, NativeShell
from server_client import DictateServerClient, DictateServerError
from startup import sync_startup_registration
from startup_ui import (
    finish_startup_splash,
    notify_already_running,
    show_startup_splash,
    update_startup_splash,
)
from ui_qt import DashboardWindow, StatusOverlay, format_hotkey_display

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.05

APP_TITLE = "Dictate Lite"

# Paste keystroke differs by OS: macOS uses Cmd+V, everything else Ctrl+V.
PASTE_MODIFIER = "command" if sys.platform == "darwin" else "ctrl"


def get_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def get_data_dir() -> Path:
    """Writable location for config.json / history.json.

    A frozen macOS .app keeps its executable inside a read-only bundle, so user
    data must live in Application Support instead. Everywhere else (source runs,
    the Windows .exe) we keep writing next to the app, so existing installs are
    completely unchanged.
    """
    if getattr(sys, "frozen", False) and sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / APP_TITLE
        try:
            base.mkdir(parents=True, exist_ok=True)
            return base
        except OSError:
            return Path(sys.executable).parent
    return get_app_dir()


CONFIG_PATH = get_data_dir() / "config.json"
HISTORY_PATH = get_data_dir() / "history.json"

__version__ = "1.0.0"

AUDIO_SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1
SERVER_UNAVAILABLE_MESSAGE = "Dictate server unavailable. Please notify IT."

# Default trigger key. Full desktop keyboards (and all Windows PCs here) have a
# dedicated End key, so Windows keeps "<end>". Mac laptops have no End key
# (it's Fn+Right Arrow, which cannot be captured as a global hotkey), so macOS
# defaults to a modifier combo that works on every Mac keyboard. Users can change
# it any time in Settings. This only affects a *fresh* install with no config.json.
_DEFAULT_HOTKEY = "<ctrl>+<alt>+d" if sys.platform == "darwin" else "<end>"

DEFAULT_CONFIG = {
    "hotkey": _DEFAULT_HOTKEY,
    "dictate_server_url": "http://10.159.0.31:8765",
    "dictate_server_api_key": "",
    "server_timeout_seconds": 60,
    "restore_clipboard_after_paste": False,
    "max_history_entries": 500,
    "launch_at_startup": True,
    "client_name": "",
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


_IS_MAC = sys.platform == "darwin"


def format_mic_error(exc: Exception) -> str:
    msg = str(exc).lower()
    if "device -1" in msg or "no input" in msg or "invalid device" in msg:
        where = (
            "set a default input device in System Settings → Sound"
            if _IS_MAC
            else "set a default input device in Windows"
        )
        return (
            f"No microphone found. Plug one in or {where}. "
            "Dictate Lite will retry automatically — no need to restart."
        )
    if "unanticipated host error" in msg or "access" in msg or "permission" in msg:
        if _IS_MAC:
            return (
                "Microphone blocked. Allow Dictate Lite under System Settings → "
                "Privacy & Security → Microphone."
            )
        return "Microphone blocked. Check Windows privacy settings for microphone access."
    text = str(exc).strip()
    return text[:80] if text else "Microphone unavailable."


SINGLE_INSTANCE_MUTEX = "Global\\DictateLiteAppMutex"


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
            if buff.value == APP_TITLE:
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


# Held for the whole process lifetime so the OS keeps the lock. Never closed
# explicitly — it is released when the process exits.
_SINGLE_INSTANCE_HANDLE = None


def ensure_single_instance() -> bool:
    """Return True if this is the only running Dictate Lite, False otherwise.

    Windows uses a named mutex; macOS/Linux use an advisory lock on a file in
    the data dir. On any unexpected error we fail open (return True) so the app
    still launches rather than being wrongly blocked.
    """
    global _SINGLE_INSTANCE_HANDLE
    if sys.platform.startswith("win"):
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            kernel32.CreateMutexW(None, True, SINGLE_INSTANCE_MUTEX)
            if kernel32.GetLastError() == 183:
                return False
            return True
        except Exception:
            return True

    # macOS / Linux: exclusive flock on a lock file. If another instance holds
    # it, flock raises and we report "already running".
    try:
        import fcntl

        lock_path = get_data_dir() / "dictate_lite.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(lock_path, "w")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return False
        _SINGLE_INSTANCE_HANDLE = handle  # keep the lock for the process lifetime
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

    def _close_stream(self) -> None:
        if self._stream is None:
            return
        try:
            self._stream.stop()
            self._stream.close()
        except Exception:
            pass
        self._stream = None

    def start(self):
        self._close_stream()
        with self._lock:
            self._chunks = []
            self._recording = True
        self._stream, _device = open_input_stream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
            callback=self._callback,
        )

    def stop(self) -> str | None:
        with self._lock:
            self._recording = False
        self._close_stream()
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
        with wave.open(temp_path, "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(audio_int16.tobytes())
        return temp_path


class AudioRecorder:
    """Native WASAPI recorder when DLL is available; otherwise sounddevice."""

    def __init__(self, native: NativeShell, sample_rate: int = 16000, channels: int = 1):
        self.native = native
        self.sample_rate = sample_rate
        self.channels = channels
        self._use_native = native.available
        self._fallback = _PythonAudioRecorder(sample_rate, channels)

    def reset_devices(self, *, refresh_portaudio: bool = True) -> None:
        """Re-enable native audio and refresh PortAudio after plug/unplug."""
        self._use_native = self.native.available
        self._fallback._close_stream()
        if refresh_portaudio:
            try:
                refresh_audio_devices()
            except Exception:
                pass

    def start(self):
        last_exc: Exception | None = None
        for attempt in range(4):
            # Always refresh on first try too — newly plugged headsets often miss PortAudio's cache.
            self.reset_devices(refresh_portaudio=True)
            if self._use_native:
                if self.native.audio_start(self.sample_rate):
                    return
                self._use_native = False
            try:
                self._fallback.start()
                return
            except Exception as exc:
                last_exc = exc
                self._fallback._close_stream()
                time.sleep(0.35 * (attempt + 1))
        if last_exc is not None:
            raise last_exc
        raise OSError("No microphone input device available")

    def stop(self) -> str | None:
        if self._use_native:
            path = self.native.audio_stop()
            if path:
                return path
            self._use_native = False
        return self._fallback.stop()


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
            pyautogui.hotkey(PASTE_MODIFIER, "v")
            if self.restore_clipboard and old_clipboard is not None:
                time.sleep(0.5)
                pyperclip.copy(old_clipboard)
            return True
        except Exception:
            return False


class DictationApp:
    def __init__(self, config: dict, *, start_minimized: bool = False):
        self.config = config
        self.start_minimized = start_minimized
        self.hotkey_display = format_hotkey_display(config["hotkey"])
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
        self._mac_hotkey = None
        self.history = HistoryStore(
            get_data_dir() / "history.json",
            max_entries=config.get("max_history_entries", 500),
        )
        self.recorder = AudioRecorder(
            self.native,
            sample_rate=int(config.get("sample_rate", AUDIO_SAMPLE_RATE)),
            channels=int(config.get("channels", AUDIO_CHANNELS)),
        )
        self.paste_manager = PasteManager(
            self.native,
            restore_clipboard=config.get("restore_clipboard_after_paste", False),
        )
        self.dashboard = DashboardWindow(self)
        self.status_overlay = StatusOverlay()

        self.dashboard.set_app_state("loading")
        threading.Thread(target=self._initialize, daemon=True).start()
        self._setup_hotkey()
        self._recording_start_in_progress = False
        self._mic_signature = input_device_signature()
        self._mic_device_count = count_input_devices()
        self._mic_monitor_stop = threading.Event()
        threading.Thread(target=self._mic_monitor_loop, daemon=True).start()
        # Always warm up briefly — Windows audio is often late at sign-in / USB plug.
        threading.Thread(target=self._warmup_mic_probe, daemon=True).start()

    def _warmup_mic_probe(self) -> None:
        """After launch, Windows audio / USB headsets may not be ready yet."""
        for i in range(24):
            if not self._alive or self._mic_monitor_stop.is_set():
                return
            time.sleep(1.25)
            # Skip while actively recording/transcribing to avoid PortAudio races.
            with self._lock:
                busy = self.state in ("recording", "transcribing") or self._recording_start_in_progress
            if busy:
                continue
            try:
                if i in (0, 2, 5, 10):
                    refresh_audio_devices()
                signature = input_device_signature()
                count = len(signature[2]) if len(signature) > 2 else count_input_devices()
            except Exception:
                continue
            if signature != self._mic_signature:
                previous_count = self._mic_device_count
                self._mic_signature = signature
                self._mic_device_count = count
                self.recorder.reset_devices(refresh_portaudio=True)
                if count > 0 and previous_count == 0:
                    self._notify(
                        "Microphone connected — ready to dictate.",
                        state="success",
                        auto_hide_ms=3500,
                    )
                elif count > 0:
                    self._notify(
                        "Microphone updated — ready to dictate.",
                        state="success",
                        auto_hide_ms=2500,
                    )
                return
            if count > 0 and i >= 2:
                return

    def _mic_monitor_loop(self) -> None:
        """Detect microphone hot-plug without restarting Dictate Lite."""
        while self._alive and not self._mic_monitor_stop.wait(2.0):
            with self._lock:
                busy = self.state in ("recording", "transcribing") or self._recording_start_in_progress
            if busy:
                continue
            try:
                # Cheap check first; only reinitialize PortAudio when something changed.
                signature = input_device_signature()
            except Exception:
                continue
            if signature == self._mic_signature:
                continue
            previous_count = self._mic_device_count
            try:
                self.recorder.reset_devices(refresh_portaudio=True)
                signature = input_device_signature()
            except Exception:
                continue
            count = len(signature[2]) if len(signature) > 2 else 0
            self._mic_signature = signature
            self._mic_device_count = count
            if count > 0 and previous_count == 0:
                self._notify(
                    "Microphone connected — ready to dictate.",
                    state="success",
                    auto_hide_ms=3500,
                )
            elif count == 0 and previous_count > 0:
                self._notify(
                    "Microphone disconnected.",
                    state="idle",
                    auto_hide_ms=4000,
                )
            elif count > 0:
                self._notify(
                    "Microphone updated — ready to dictate.",
                    state="success",
                    auto_hide_ms=2500,
                )

    def _ui(self, fn):
        if self._alive:
            self._ui_invoker.invoke.emit(fn)

    def _notify(self, message: str, state: str = "idle", auto_hide_ms: int | None = None):
        self._ui(lambda: self._apply_notify(message, state, auto_hide_ms))

    def _apply_notify(self, message: str, state: str = "idle", auto_hide_ms: int | None = None):
        persistent = state in StatusOverlay.PERSISTENT_STATES
        clear = None if persistent else auto_hide_ms
        self.dashboard.set_status(message, auto_clear_ms=clear, state=state)

        overlay_state = state
        if state == "idle" and auto_hide_ms and message.lower() in (
            "ready",
            "pasted.",
            "copied, paste manually.",
        ):
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

    def _initialize(self):
        with self._lock:
            self.state = "idle"
        self._ui(lambda: self.dashboard.set_app_state("idle"))
        self._notify("Ready", state="success", auto_hide_ms=2500)

    def _client_name(self) -> str:
        configured = str(self.config.get("client_name", "")).strip()
        if configured:
            return configured
        name = os.environ.get("COMPUTERNAME", "").strip()
        if name:
            return name
        try:
            import socket

            return socket.gethostname().strip()
        except OSError:
            return ""

    def _make_server_client(self) -> DictateServerClient:
        server_url = str(self.config.get("dictate_server_url", "")).strip().rstrip("/")
        return DictateServerClient(
            server_url,
            api_key=str(self.config.get("dictate_server_api_key", "")),
            timeout=float(self.config.get("server_timeout_seconds", 60)),
            client_name=self._client_name(),
            client_version=__version__,
        )

    def apply_settings(self, new_config: dict):
        self.config = new_config
        self.hotkey_display = format_hotkey_display(new_config["hotkey"])
        self.history.max_entries = int(new_config.get("max_history_entries", 500))
        self.paste_manager.restore_clipboard = new_config.get(
            "restore_clipboard_after_paste", False
        )
        try:
            sync_startup_registration(self.config.get("launch_at_startup", True))
        except OSError as exc:
            QMessageBox.warning(
                self.dashboard,
                APP_TITLE,
                f"Could not update Windows startup setting:\n{exc}",
            )
        self._reload_hotkey()
        self.dashboard.refresh()
        self.dashboard.set_status("Settings saved.", 2500, "success")

    def _sync_app_state(self):
        self._ui(lambda: self.dashboard.set_app_state(self.state))

    def _on_native_hotkey(self, hotkey_id: int):
        self._ui(lambda: self._dispatch_hotkey(hotkey_id))

    def _dispatch_hotkey(self, hotkey_id: int):
        if hotkey_id == NativeShell.HOTKEY_QUICK:
            self.on_hotkey()

    def _reload_hotkey(self):
        if self._hotkey_listener is not None:
            self._hotkey_listener.stop()
            self._hotkey_listener = None
        if self.native.available:
            self.native.unregister_hotkey(NativeShell.HOTKEY_QUICK)
        if self._mac_hotkey is not None:
            self._mac_hotkey.unregister()
        self._setup_hotkey()

    def _setup_hotkey(self):
        quick = self.config["hotkey"]
        self.hotkey_backend = "none"
        self.native.hotkeys_registered = False

        if self.native.available:
            global _hotkey_target
            _hotkey_target = self
            self.native.set_hotkey_callback(_native_hotkey_trampoline)
            if self.native.register_hotkey(quick, NativeShell.HOTKEY_QUICK):
                if self._hotkey_listener is not None:
                    self._hotkey_listener.stop()
                    self._hotkey_listener = None
                self.hotkey_backend = "native"
                self.native.hotkeys_registered = True
                self._ui(self.dashboard.refresh_footer)
                return
            self.native.unregister_hotkey(NativeShell.HOTKEY_QUICK)

        # macOS: use Carbon RegisterEventHotKey. NEVER fall back to pynput here —
        # pynput's listener queries Text Input Source APIs off the main thread,
        # which hard-crashes modern macOS. If Carbon fails, run without a hotkey.
        if sys.platform == "darwin":
            if self._setup_mac_hotkey(quick):
                return
            self._notify(
                "Could not register the global hotkey on macOS.",
                state="error",
                auto_hide_ms=6000,
            )
            return

        self._start_pynput_hotkey(quick)

    def _setup_mac_hotkey(self, quick: str) -> bool:
        try:
            from mac_hotkey import MacHotKey
        except Exception:
            return False
        if self._mac_hotkey is None:
            self._mac_hotkey = MacHotKey()
        if not self._mac_hotkey.available:
            return False

        def _fire():
            # Carbon delivers this on the main thread; hop through the emitter
            # so dictation logic runs exactly like the Windows native path.
            self._hotkey_emitter.pressed.emit(NativeShell.HOTKEY_QUICK)

        if self._mac_hotkey.register(quick, _fire):
            self.hotkey_backend = "mac"
            self._ui(self.dashboard.refresh_footer)
            return True
        return False

    def _start_pynput_hotkey(self, quick: str) -> None:
        if self._hotkey_listener is not None:
            self._hotkey_listener.stop()
            self._hotkey_listener = None

        def on_quick():
            self.on_quick_hotkey()

        self._hotkey_listener = keyboard.GlobalHotKeys({quick: on_quick})
        self._hotkey_listener.start()
        self.hotkey_backend = "pynput"
        self._ui(self.dashboard.refresh_footer)
        if self.native.available:
            self._notify(
                "Using Python hotkey listener (native hotkey registration failed).",
                state="idle",
                auto_hide_ms=4500,
            )

    def on_quick_hotkey(self):
        self._ui(self.on_hotkey)

    def on_hotkey(self):
        action = None
        with self._lock:
            if self.state == "loading":
                self._apply_notify("Still starting…", state="loading", auto_hide_ms=2500)
                return
            if self.state == "error":
                self._apply_notify(
                    "Startup failed. Restart Dictate Lite.", state="error", auto_hide_ms=4000
                )
                return
            if self.state == "transcribing":
                self._apply_notify("Still transcribing…", state="working", auto_hide_ms=2000)
                return
            if self.state == "recording" and self._recording_start_in_progress:
                # Second press while mic is still opening cancels cleanly.
                self.state = "idle"
                action = "cancel_start"
            elif self.state == "idle":
                self.state = "recording"
                self._recording_start_in_progress = True
                action = "start"
            elif self.state == "recording":
                self.state = "transcribing"
                action = "stop"
        if action == "cancel_start":
            self._sync_app_state()
            self._notify("Microphone open cancelled.", state="idle", auto_hide_ms=2000)
            return
        if action == "start":
            self._start_recording()
        elif action == "stop":
            self._stop_and_transcribe()

    def _start_recording(self):
        # Must not block the Qt UI thread — PortAudio open/retries freeze the window.
        self._sync_app_state()
        self._notify(f"Opening microphone… Press {self.hotkey_display} to stop.", state="recording")
        threading.Thread(target=self._start_recording_worker, daemon=True).start()

    def _start_recording_worker(self):
        try:
            self._recording_started_at = time.time()
            self.recorder.start()
            with self._lock:
                still_recording = self.state == "recording"
            if not still_recording:
                # User already stopped (or quit) while mic was opening.
                try:
                    self.recorder.stop()
                except Exception:
                    pass
                return
            self._notify(
                f"Recording… Press {self.hotkey_display} to stop.",
                state="recording",
            )
        except Exception as exc:
            with self._lock:
                self.state = "idle"
            self._sync_app_state()
            self._notify(f"Error: {format_mic_error(exc)}", state="error", auto_hide_ms=6000)
            # Recover device list after a failed open (common after headset plug).
            try:
                self.recorder.reset_devices(refresh_portaudio=True)
                self._mic_signature = input_device_signature()
                self._mic_device_count = count_input_devices()
            except Exception:
                pass
        finally:
            self._recording_start_in_progress = False

    def _stop_and_transcribe(self):
        self._sync_app_state()
        self._notify("Transcribing on server…", state="working")
        threading.Thread(target=self._transcribe_worker, daemon=True).start()

    def _transcribe_quick_dictate(self, wav_path: str) -> str:
        server_url = str(self.config.get("dictate_server_url", "")).strip().rstrip("/")
        if not server_url:
            raise DictateServerError("Dictate server URL is not configured")

        client = self._make_server_client()
        result = client.transcribe(wav_path)
        text = str(result.get("text", "")).strip()
        if not text:
            raise DictateServerError("Server returned empty text")
        return text

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
            text = self._transcribe_quick_dictate(temp_path)
            if not text.strip():
                self._notify("No speech detected.", state="idle", auto_hide_ms=3000)
                return
            self.history.add(text, duration)
            self._ui(self.dashboard.refresh)
            if self.paste_manager.paste(text):
                self._notify("Pasted.", state="success", auto_hide_ms=2000)
            else:
                self._notify("Copied, paste manually.", state="working", auto_hide_ms=4000)
        except (DictateServerError, OSError, TimeoutError, RuntimeError, ValueError) as exc:
            print(
                f"Dictate server transcription failed: {type(exc).__name__}",
                file=sys.stderr,
            )
            self._notify(SERVER_UNAVAILABLE_MESSAGE, state="error", auto_hide_ms=6000)
        except Exception as exc:
            print(
                f"Dictate transcription failed: {type(exc).__name__}",
                file=sys.stderr,
            )
            self._notify(SERVER_UNAVAILABLE_MESSAGE, state="error", auto_hide_ms=6000)
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
        if hasattr(self, "_mic_monitor_stop"):
            self._mic_monitor_stop.set()
        if self._hotkey_listener is not None:
            self._hotkey_listener.stop()
        if self._mac_hotkey is not None:
            self._mac_hotkey.unregister()
        self.native.shutdown()
        self.dashboard.destroy()

    def run(self):
        self.dashboard.run(start_minimized=self.start_minimized)


def main():
    if not ensure_single_instance():
        notify_already_running()
        return

    config = load_config(CONFIG_PATH)
    try:
        sync_startup_registration(config.get("launch_at_startup", True))
    except OSError as exc:
        print(f"Warning: could not sync Windows startup: {exc}", file=sys.stderr)

    qt_app = QApplication(sys.argv)
    qt_app.setQuitOnLastWindowClosed(False)
    splash = show_startup_splash("Starting Dictate Lite…")
    try:
        update_startup_splash(splash, "Loading interface…")
        start_minimized = "--startup" in sys.argv
        app = DictationApp(config, start_minimized=start_minimized)
        app.run()
        finish_startup_splash(splash, app.dashboard)
    except Exception as exc:
        finish_startup_splash(splash)
        QMessageBox.critical(
            None,
            APP_TITLE,
            f"Failed to start:\n{exc}",
        )
        raise

    sys.exit(qt_app.exec())


if __name__ == "__main__":
    main()
