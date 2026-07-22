"""macOS global hotkey via Carbon RegisterEventHotKey (main-thread safe).

Why this exists: pynput's keyboard listener queries the Text Input Source APIs
(TSMGetInputSourceProperty) from a background thread. On modern macOS that trips
dispatch_assert_queue and hard-crashes the whole process (EXC_BREAKPOINT).

RegisterEventHotKey instead delivers hotkey events through the application's
main Carbon event loop (which Qt/Cocoa pumps on the main thread). It never
touches input sources and needs neither Accessibility nor Input-Monitoring
permission. We only use ctypes + the always-present Carbon framework.
"""

from __future__ import annotations

import ctypes
from ctypes import (
    CFUNCTYPE,
    POINTER,
    Structure,
    byref,
    c_int32,
    c_uint32,
    c_void_p,
)

# Carbon modifier masks (NOT the same values as Win32 / Cocoa).
cmdKey = 0x0100
shiftKey = 0x0200
optionKey = 0x0800
controlKey = 0x1000

kEventClassKeyboard = 0x6B657962  # 'keyb'
kEventHotKeyPressed = 6

# US ANSI virtual key codes.
_VK = {
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8,
    "v": 9, "b": 11, "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17,
    "1": 18, "2": 19, "3": 20, "4": 21, "6": 22, "5": 23, "=": 24, "9": 25,
    "7": 26, "-": 27, "8": 28, "0": 29, "]": 30, "o": 31, "u": 32, "[": 33,
    "i": 34, "p": 35, "l": 37, "j": 38, "k": 40, "n": 45, "m": 46,
    "space": 49, "return": 36, "enter": 36, "tab": 48, "esc": 53, "escape": 53,
    "delete": 51, "home": 115, "end": 119, "pageup": 116, "pagedown": 121,
    "left": 123, "right": 124, "down": 125, "up": 126,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97, "f7": 98,
    "f8": 100, "f9": 101, "f10": 109, "f11": 103, "f12": 111,
}

_MODS = {
    "cmd": cmdKey, "command": cmdKey, "win": cmdKey, "super": cmdKey,
    "shift": shiftKey,
    "alt": optionKey, "option": optionKey, "opt": optionKey,
    "ctrl": controlKey, "control": controlKey,
}


class _EventTypeSpec(Structure):
    _fields_ = [("eventClass", c_uint32), ("eventKind", c_uint32)]


class _EventHotKeyID(Structure):
    _fields_ = [("signature", c_uint32), ("id", c_uint32)]


_HANDLER = CFUNCTYPE(c_int32, c_void_p, c_void_p, c_void_p)


def parse_hotkey(spec: str) -> tuple[int, int]:
    """Parse a pynput-style spec ('<ctrl>+<alt>+d') into (carbon_mods, keycode)."""
    parts = [
        p.strip().lower()
        for p in spec.replace("<", "").replace(">", "").split("+")
        if p.strip()
    ]
    mods = 0
    key: int | None = None
    for p in parts:
        if p in _MODS:
            mods |= _MODS[p]
        elif p in _VK:
            key = _VK[p]
        else:
            raise ValueError(f"Unsupported hotkey part: {p}")
    if key is None:
        raise ValueError(f"Unsupported hotkey: {spec}")
    return mods, key


class MacHotKey:
    """Single global hotkey backed by Carbon RegisterEventHotKey."""

    def __init__(self) -> None:
        self.available = False
        self._carbon = None
        self._handler_ref: c_void_p | None = None
        self._hotkey_ref: c_void_p | None = None
        self._cb = None            # user callback
        self._handler_cb = None    # CFUNCTYPE instance — MUST stay referenced
        try:
            carbon = ctypes.cdll.LoadLibrary(
                "/System/Library/Frameworks/Carbon.framework/Carbon"
            )
        except OSError:
            return
        try:
            carbon.GetApplicationEventTarget.restype = c_void_p
            carbon.InstallEventHandler.argtypes = [
                c_void_p, _HANDLER, c_uint32, POINTER(_EventTypeSpec),
                c_void_p, POINTER(c_void_p),
            ]
            carbon.InstallEventHandler.restype = c_int32
            carbon.RegisterEventHotKey.argtypes = [
                c_uint32, c_uint32, _EventHotKeyID, c_void_p, c_uint32,
                POINTER(c_void_p),
            ]
            carbon.RegisterEventHotKey.restype = c_int32
            carbon.UnregisterEventHotKey.argtypes = [c_void_p]
            carbon.UnregisterEventHotKey.restype = c_int32
        except AttributeError:
            return
        self._carbon = carbon
        self.available = True

    def register(self, spec: str, callback) -> bool:
        """Register `spec`; `callback` is invoked (on the main thread) on press."""
        if not self.available or self._carbon is None:
            return False
        try:
            mods, key = parse_hotkey(spec)
        except ValueError:
            return False

        self.unregister()
        self._cb = callback
        target = self._carbon.GetApplicationEventTarget()

        if self._handler_ref is None:
            def _handler(_next, _event, _user):
                try:
                    if self._cb:
                        self._cb()
                except Exception:
                    pass
                return 0

            self._handler_cb = _HANDLER(_handler)
            spec_t = _EventTypeSpec(kEventClassKeyboard, kEventHotKeyPressed)
            href = c_void_p()
            if self._carbon.InstallEventHandler(
                target, self._handler_cb, 1, byref(spec_t), None, byref(href)
            ) != 0:
                return False
            self._handler_ref = href

        hk_id = _EventHotKeyID(0x44435458, 1)  # 'DCTX'
        ref = c_void_p()
        if self._carbon.RegisterEventHotKey(key, mods, hk_id, target, 0, byref(ref)) != 0:
            return False
        self._hotkey_ref = ref
        return True

    def unregister(self) -> None:
        if self._carbon is not None and self._hotkey_ref is not None:
            try:
                self._carbon.UnregisterEventHotKey(self._hotkey_ref)
            except Exception:
                pass
            self._hotkey_ref = None
