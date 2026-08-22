"""Startup splash and duplicate-launch tray feedback."""

from __future__ import annotations

import sys
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen, QSystemTrayIcon

APP_TITLE = "Dictate Lite"

_SPLASH_BG = QColor("#FFFFFF")
_SPLASH_TEXT = QColor("#09090B")
_SPLASH_MUTED = QColor("#71717B")
_ACCENT = QColor("#2B7FFF")


def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def _splash_pixmap(size: int = 128) -> QPixmap:
    icon_candidates = [
        _app_dir() / "assets" / "dictate.ico",
        Path(__file__).resolve().parent / "assets" / "dictate.ico",
    ]
    for path in icon_candidates:
        if path.is_file():
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                return pixmap.scaled(
                    size,
                    size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(_ACCENT)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(0, 0, size, size, 24, 24)
    painter.setPen(QColor("#FFFFFF"))
    font = QFont("Segoe UI", int(size * 0.42), QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "DL")
    painter.end()
    return pixmap


def show_startup_splash(message: str = "Starting Dictate Lite…") -> QSplashScreen:
    pixmap = _splash_pixmap()
    splash = QSplashScreen(pixmap)
    splash.setWindowFlags(
        Qt.WindowType.SplashScreen | Qt.WindowType.WindowStaysOnTopHint
    )
    font = QFont("Segoe UI", 10)
    splash.setFont(font)
    splash.showMessage(
        message,
        Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
        _SPLASH_MUTED,
    )
    splash.show()
    QApplication.processEvents()
    return splash


def update_startup_splash(splash: QSplashScreen | None, message: str) -> None:
    if splash is None:
        return
    splash.showMessage(
        message,
        Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
        _SPLASH_MUTED,
    )
    QApplication.processEvents()


def finish_startup_splash(splash: QSplashScreen | None, widget=None) -> None:
    if splash is None:
        return
    splash.finish(widget)
    QApplication.processEvents()


def _tray_icon() -> QSystemTrayIcon:
    from icon_loader import render_logo
    from ui_qt import _pil_icon

    tray = QSystemTrayIcon(_pil_icon(render_logo(64)))
    tray.setToolTip(APP_TITLE)
    return tray


def _activate_existing_window() -> bool:
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


def notify_already_running(*, try_raise_window: bool = True) -> None:
    """Show tray balloon when user launches Dictate Lite while it is already running."""
    if try_raise_window:
        _activate_existing_window()

    if not QSystemTrayIcon.isSystemTrayAvailable():
        return

    app = QApplication.instance() or QApplication(sys.argv)
    tray = _tray_icon()
    tray.show()
    tray.showMessage(
        APP_TITLE,
        "Dictate Lite is already running. Check the system tray.",
        QSystemTrayIcon.MessageIcon.Information,
        4000,
    )
    QTimer.singleShot(4500, app.quit)
    app.exec()
