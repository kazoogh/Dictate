"""Read text from the currently focused control on Windows."""

from __future__ import annotations

import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E
EM_GETLINE = 0x00C4


def _get_focus_hwnd() -> int:
    fg = user32.GetForegroundWindow()
    if not fg:
        return 0

    tid = user32.GetWindowThreadProcessId(fg, None)
    current_tid = kernel32.GetCurrentThreadId()
    attached = False
    if tid != current_tid:
        attached = bool(user32.AttachThreadInput(current_tid, tid, True))

    try:
        focus = user32.GetFocus()
        if focus:
            return focus
        return fg
    finally:
        if attached:
            user32.AttachThreadInput(current_tid, tid, False)


def _read_hwnd_text(hwnd: int, max_chars: int = 200_000) -> str:
    if not hwnd:
        return ""

    length = user32.SendMessageW(hwnd, WM_GETTEXTLENGTH, 0, 0)
    if length <= 0:
        length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""

    size = min(int(length) + 2, max_chars)
    buf = ctypes.create_unicode_buffer(size)
    copied = user32.SendMessageW(hwnd, WM_GETTEXT, size, buf)
    if copied > 0 and buf.value:
        return buf.value

    if user32.GetWindowTextW(hwnd, buf, size) > 0:
        return buf.value
    return ""


def _try_uia_value() -> str:
    try:
        import uiautomation as auto
    except ImportError:
        return ""

    try:
        ctrl = auto.GetFocusedControl()
        if ctrl is None:
            return ""
        for getter in (
            lambda: ctrl.GetValuePattern().Value if ctrl.GetValuePattern() else "",
            lambda: ctrl.GetTextPattern().DocumentRange.GetText(-1) if ctrl.GetTextPattern() else "",
            lambda: ctrl.Name or "",
        ):
            try:
                value = getter()
            except Exception:
                value = ""
            if value and value.strip():
                return value
    except Exception:
        return ""
    return ""


def _try_win32(hwnd: int) -> str:
    text = _read_hwnd_text(hwnd)
    if text.strip():
        return text

    # Walk direct children for embedded edit controls.
    child = wintypes.HWND(0)
    while True:
        child = user32.FindWindowExW(hwnd, child, None, None)
        if not child:
            break
        text = _read_hwnd_text(child)
        if text.strip():
            return text
    return ""


def get_focused_text() -> str:
    """Best-effort text from the focused control (UIA, then Win32)."""
    text = _try_uia_value()
    if text.strip():
        return text
    return _try_win32(_get_focus_hwnd())
