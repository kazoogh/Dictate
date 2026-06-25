"""ctypes bridge to dictate_native.dll (Win32 hotkey, paste, audio)."""

from __future__ import annotations

import ctypes
import sys
import tempfile
from ctypes import WINFUNCTYPE, c_int, c_void_p, c_wchar_p
from pathlib import Path

HotkeyCallback = WINFUNCTYPE(None, c_int, c_void_p)

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008

VK_SPECIAL = {
    "space": 0x20,
    "end": 0x23,
    "home": 0x24,
    "pageup": 0x21,
    "pagedown": 0x22,
    "insert": 0x2D,
    "delete": 0x2E,
    "tab": 0x09,
    "enter": 0x0D,
    "esc": 0x1B,
    "escape": 0x1B,
}


def _dll_path(app_dir: Path) -> Path | None:
    candidates = [
        app_dir / "dictate_native.dll",
        app_dir / "native" / "dictate_native.dll",
        Path(__file__).resolve().parent / "native" / "build" / "bin" / "dictate_native.dll",
        Path(__file__).resolve().parent / "native" / "build" / "Release" / "dictate_native.dll",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def parse_hotkey(spec: str) -> tuple[int, int]:
    """Parse pynput-style hotkey into Win32 modifiers and virtual-key code."""
    parts = [p.strip().lower() for p in spec.replace("<", "").replace(">", "").split("+") if p.strip()]
    mods = 0
    vk: int | None = None
    mod_map = {
        "ctrl": MOD_CONTROL,
        "control": MOD_CONTROL,
        "alt": MOD_ALT,
        "shift": MOD_SHIFT,
        "win": MOD_WIN,
    }
    for part in parts:
        if part in mod_map:
            mods |= mod_map[part]
        elif part in VK_SPECIAL:
            vk = VK_SPECIAL[part]
        elif part.startswith("f") and part[1:].isdigit():
            n = int(part[1:])
            if 1 <= n <= 24:
                vk = 0x70 + (n - 1)
        elif len(part) == 1:
            vk = ord(part.upper())
        else:
            raise ValueError(f"Unsupported hotkey part: {part}")
    if vk is None:
        raise ValueError(f"Unsupported hotkey: {spec}")
    return mods, vk


class NativeShell:
    """Win32 integration via dictate_native.dll with safe Python fallbacks."""

    HOTKEY_QUICK = 1
    HOTKEY_CLINICAL = 2

    def __init__(self, app_dir: Path):
        self.app_dir = app_dir
        self.available = False
        self._lib = None
        self._cb_ref = None
        self._wav_path: str | None = None
        path = _dll_path(app_dir)
        if path is None:
            return
        try:
            lib = ctypes.CDLL(str(path))
        except OSError:
            return
        lib.dictate_initialize.restype = c_int
        lib.dictate_register_hotkey.argtypes = [ctypes.c_uint, ctypes.c_uint, c_int]
        lib.dictate_register_hotkey.restype = c_int
        lib.dictate_unregister_hotkey.argtypes = [c_int]
        lib.dictate_unregister_hotkey.restype = c_int
        lib.dictate_set_hotkey_callback.argtypes = [HotkeyCallback, c_void_p]
        lib.dictate_set_hotkey_callback.restype = c_int
        lib.dictate_paste_text.argtypes = [c_wchar_p, c_int]
        lib.dictate_paste_text.restype = c_int
        lib.dictate_audio_begin.argtypes = [c_wchar_p, c_int]
        lib.dictate_audio_begin.restype = c_int
        lib.dictate_audio_end.restype = c_int
        if not lib.dictate_initialize():
            return
        self._lib = lib
        self.available = True

    def set_hotkey_callback(self, callback) -> None:
        if not self._lib:
            return
        self._cb_ref = HotkeyCallback(callback)
        self._lib.dictate_set_hotkey_callback(self._cb_ref, None)

    def register_hotkey(self, spec: str, hotkey_id: int) -> bool:
        if not self._lib:
            return False
        mods, vk = parse_hotkey(spec)
        return bool(self._lib.dictate_register_hotkey(mods, vk, hotkey_id))

    def unregister_hotkey(self, hotkey_id: int) -> None:
        if self._lib:
            self._lib.dictate_unregister_hotkey(hotkey_id)

    def paste(self, text: str, restore_clipboard: bool = False) -> bool:
        if self._lib and self._lib.dictate_paste_text(text, int(restore_clipboard)):
            return True
        return False

    def audio_start(self, sample_rate: int = 16000) -> bool:
        if not self._lib:
            return False
        fd, path = tempfile.mkstemp(suffix=".wav")
        import os

        os.close(fd)
        self._wav_path = path
        return bool(self._lib.dictate_audio_begin(path, sample_rate))

    def audio_stop(self) -> str | None:
        if not self._lib or not self._wav_path:
            return None
        ok = bool(self._lib.dictate_audio_end())
        path = self._wav_path
        self._wav_path = None
        if not ok:
            return None
        if Path(path).stat().st_size <= 44:
            Path(path).unlink(missing_ok=True)
            return None
        return path

    def shutdown(self) -> None:
        if self._lib:
            self._lib.dictate_shutdown()
            self._lib = None
        self.available = False
