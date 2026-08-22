"""Dictate Lite UI — PySide6 (Qt) dashboard."""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Callable

import pyperclip
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QAction, QFont, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from icon_loader import render_logo, render_lucide

if TYPE_CHECKING:
    from main import DictationApp

APP_TITLE = "Dictate Lite"

BG = "#FFFFFF"
SURFACE = "#FFFFFF"
ENTRY_BG = "#F4F4F5"
BORDER = "#E4E4E7"
TEXT = "#09090B"
MUTED = "#71717B"
ACCENT = "#2B7FFF"
ACCENT_LIGHT = "#EBF3FF"
RECORD_BG = "#FFF5F5"
RED = "#EF4444"
RED_TEXT = "#DC2626"
SUCCESS = "#16A34A"
WARNING = "#D97706"
STATUS_BG = "#1C1C1E"
STATUS_FG = "#FFFFFF"
FOOTER_BG = "#F4F4F5"

GLOBAL_STYLE = f"""
QMainWindow, QWidget {{
    background: {BG};
    color: {TEXT};
    font-family: "Segoe UI", sans-serif;
}}
QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollBar:vertical {{
    width: 8px;
    background: {BG};
    margin: 0;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: #D4D4D8;
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: #A1A1AA;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
    border: none;
    background: none;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: {BG};
    border: none;
}}
QScrollBar:horizontal {{
    height: 8px;
    background: {BG};
    margin: 0;
    border: none;
}}
QScrollBar::handle:horizontal {{
    background: #D4D4D8;
    border-radius: 4px;
    min-width: 24px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
    border: none;
    background: none;
}}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: {BG};
    border: none;
}}
QPushButton {{
    border: none;
}}
QLabel {{
    border: none;
    background: transparent;
    padding: 0;
    margin: 0;
}}
QLineEdit {{
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 8px 10px;
    background: white;
}}
"""


def _icon_label(name: str, size: int = 16, color: str = ACCENT) -> QLabel:
    label = QLabel()
    label.setPixmap(_pil_icon(render_lucide(name, size, color=color), size).pixmap(size, size))
    label.setFixedSize(size, size)
    return label


def _icon_button(name: str, tooltip: str = "", size: int = 28) -> QPushButton:
    btn = QPushButton()
    btn.setFixedSize(size, size)
    btn.setIcon(_pil_icon(render_lucide(name, 14, color=MUTED)))
    btn.setIconSize(QSize(14, 14))
    btn.setToolTip(tooltip)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setStyleSheet(
        "QPushButton { background: transparent; border-radius: 8px; }"
        "QPushButton:hover { background: #E4E4E7; }"
    )
    return btn


def _plain_label(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    label.setFrameShape(QFrame.Shape.NoFrame)
    label.setStyleSheet("border: none; background: transparent; padding: 0; margin: 0;")
    return label


def _muted_label(text: str, *, size: int = 11, bold: bool = False) -> QLabel:
    label = _plain_label(text)
    weight = "font-weight: 600;" if bold else ""
    label.setStyleSheet(
        f"color: {MUTED}; font-size: {size}px; {weight} border: none; background: transparent; padding: 0;"
    )
    return label


def format_hotkey_display(hotkey: str) -> str:
    parts = hotkey.replace("<", "").replace(">", "").split("+")
    return "+".join(p.capitalize() if p != "space" else "Space" for p in parts)


def format_entry_timestamp(iso_timestamp: str) -> str:
    dt = datetime.fromisoformat(iso_timestamp)
    d = dt.date()
    today = date.today()
    time_str = dt.strftime("%I:%M %p").lstrip("0")
    if d == today:
        return f"Today · {time_str}"
    if d == today - timedelta(days=1):
        return f"Yesterday · {time_str}"
    return f"{d.strftime('%b %d')} · {time_str}"


def format_total_time(seconds: float) -> str:
    total = int(seconds)
    if total < 60:
        return f"{total}s"
    minutes = total // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    rem = minutes % 60
    return f"{hours}h {rem}m" if rem else f"{hours}h"


# Assumed normal typing speed used to estimate "time saved" vs dictation.
NORMAL_TYPING_WPM = 40


def calculate_time_saved(
    total_words,
    total_dictation_seconds,
    normal_typing_wpm: float = NORMAL_TYPING_WPM,
) -> int:
    """Return estimated minutes saved by dictating instead of typing.

    Uses raw word count and raw dictation duration. Never returns a negative value.
    Returns 0 for missing/invalid inputs.
    """
    try:
        words = float(total_words)
        seconds = float(total_dictation_seconds)
        wpm = float(normal_typing_wpm)
    except (TypeError, ValueError):
        return 0
    if words <= 0 or seconds < 0 or wpm <= 0:
        return 0
    if not (words == words and seconds == seconds and wpm == wpm):  # NaN check
        return 0
    if abs(words) == float("inf") or abs(seconds) == float("inf") or abs(wpm) == float("inf"):
        return 0

    estimated_typing_minutes = words / wpm
    actual_dictation_minutes = seconds / 60.0
    time_saved_minutes = estimated_typing_minutes - actual_dictation_minutes
    return max(0, int(round(time_saved_minutes)))


def format_time_saved(time_saved_minutes) -> str:
    """Format saved minutes as natural language for the Time Saved KPI."""
    try:
        minutes = int(time_saved_minutes)
    except (TypeError, ValueError):
        return "No time saved yet"
    if minutes <= 0:
        return "No time saved yet"

    hours, rem = divmod(minutes, 60)
    parts: list[str] = []
    if hours:
        parts.append(f"{hours} hour" if hours == 1 else f"{hours} hours")
    if rem:
        parts.append(f"{rem} minute" if rem == 1 else f"{rem} minutes")
    if not parts:
        return "No time saved yet"
    return f"You saved {', '.join(parts)}"


def _pil_icon(pil_image, size: int | None = None) -> QIcon:
    if size:
        pil_image = pil_image.resize((size, size))
    if pil_image.mode != "RGBA":
        pil_image = pil_image.convert("RGBA")
    data = pil_image.tobytes("raw", "RGBA")
    qimg = QImage(data, pil_image.width, pil_image.height, QImage.Format.Format_RGBA8888)
    return QIcon(QPixmap.fromImage(qimg))


def _card() -> QFrame:
    frame = QFrame()
    frame.setObjectName("card")
    frame.setStyleSheet(
        f"#card {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 12px; }}"
    )
    return frame


class StatusOverlay(QWidget):
    PERSISTENT_STATES = frozenset({"loading", "recording", "working"})

    def __init__(self):
        super().__init__(None, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet(
            f"background: {STATUS_BG}; color: {STATUS_FG}; border-radius: 10px; padding: 12px 16px;"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 10, 12, 10)
        self._dot = QLabel("●")
        self._label = QLabel("")
        self._label.setFont(QFont("Segoe UI", 10))
        row.addWidget(self._dot)
        row.addWidget(self._label)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)
        self.hide()

    def update_status(self, message: str, auto_hide_ms: int | None = None, state: str = "idle"):
        colors = {
            "idle": ACCENT,
            "recording": RED,
            "working": WARNING,
            "success": SUCCESS,
            "error": RED,
            "loading": WARNING,
        }
        self._dot.setStyleSheet(f"color: {colors.get(state, ACCENT)}; font-size: 14px;")
        self._label.setText(message)
        self.adjustSize()
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - self.width() - 24, screen.bottom() - self.height() - 72)
        self.show()
        self._hide_timer.stop()
        if auto_hide_ms and state not in self.PERSISTENT_STATES:
            self._hide_timer.start(auto_hide_ms)

    def hide_overlay(self):
        self.hide()


class SettingsWidget(QWidget):
    def __init__(self, app: "DictationApp", on_back: Callable[[], None], save_config_fn):
        super().__init__()
        self.app = app
        self._on_back = on_back
        self._save_config_fn = save_config_fn
        self._build()
        self.reload()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setSpacing(12)

        back = QPushButton("← Back")
        back.setFlat(True)
        back.clicked.connect(self._on_back)
        layout.addWidget(back)
        layout.addWidget(self._heading("Settings"))
        layout.addWidget(QLabel("Hotkey"))
        self.hotkey_edit = QLineEdit()
        layout.addWidget(self.hotkey_edit)
        layout.addWidget(QLabel("Dictate server URL"))
        self.dictate_server_url_edit = QLineEdit()
        self.dictate_server_url_edit.setPlaceholderText("http://10.159.0.31:8765")
        layout.addWidget(self.dictate_server_url_edit)
        layout.addWidget(QLabel("Dictate server API key"))
        self.dictate_server_api_key_edit = QLineEdit()
        self.dictate_server_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.dictate_server_api_key_edit)
        layout.addWidget(QLabel("Server timeout (seconds)"))
        self.server_timeout_edit = QLineEdit()
        self.server_timeout_edit.setPlaceholderText("60")
        layout.addWidget(self.server_timeout_edit)
        test_server_btn = QPushButton("Test server connection")
        test_server_btn.clicked.connect(self._test_server)
        layout.addWidget(test_server_btn)
        self.restore_cb = QCheckBox("Restore clipboard after paste")
        layout.addWidget(self.restore_cb)
        layout.addWidget(QLabel("Max history entries"))
        self.max_history_edit = QLineEdit()
        self.max_history_edit.setPlaceholderText("500")
        layout.addWidget(self.max_history_edit)
        _startup_label = (
            "Launch Dictate Lite at login (start in the menu bar)"
            if sys.platform == "darwin"
            else "Launch Dictate Lite at Windows sign-in (start in system tray)"
        )
        self.startup_cb = QCheckBox(_startup_label)
        layout.addWidget(self.startup_cb)

        save = QPushButton("Save changes")
        save.setStyleSheet(f"background: {ACCENT}; color: white; padding: 10px 18px; border-radius: 8px;")
        save.clicked.connect(self._save)
        layout.addWidget(save)
        layout.addStretch()
        scroll.setWidget(body)
        outer.addWidget(scroll)

    def _heading(self, text: str, small: bool = False) -> QLabel:
        label = QLabel(text)
        label.setFont(QFont("Segoe UI", 12 if small else 20, QFont.Weight.Bold if not small else QFont.Weight.DemiBold))
        return label

    def reload(self):
        self.hotkey_edit.setText(self.app.config["hotkey"])
        self.dictate_server_url_edit.setText(self.app.config.get("dictate_server_url", ""))
        self.dictate_server_api_key_edit.setText(
            self.app.config.get("dictate_server_api_key", "")
        )
        self.server_timeout_edit.setText(
            str(self.app.config.get("server_timeout_seconds", 60))
        )
        self.restore_cb.setChecked(self.app.config.get("restore_clipboard_after_paste", False))
        self.max_history_edit.setText(str(self.app.config.get("max_history_entries", 500)))
        self.startup_cb.setChecked(self.app.config.get("launch_at_startup", True))

    def _test_server(self):
        from main import __version__
        from server_client import DictateServerClient, DictateServerError

        url = self.dictate_server_url_edit.text().strip().rstrip("/")
        if not url:
            QMessageBox.warning(self, "Test server", "Enter a Dictate server URL first.")
            return
        client = DictateServerClient(
            url,
            api_key=self.dictate_server_api_key_edit.text().strip(),
            timeout=float(self.server_timeout_edit.text().strip() or "60"),
            client_name=self.app.config.get("client_name", ""),
            client_version=__version__,
        )
        try:
            health = client.health()
        except DictateServerError as exc:
            QMessageBox.critical(self, "Test server", f"Could not reach server:\n{exc}")
            return
        ok = health.get("ok")
        service = health.get("service", "dictate-api")
        model_loaded = health.get("model_loaded")
        cleanup_mode = health.get("cleanup_mode", "unknown")
        transcribe_count = health.get("transcribe_count", "—")
        QMessageBox.information(
            self,
            "Test server",
            (
                f"Connected to {url}\n\n"
                f"Service: {service}\n"
                f"Healthy: {ok}\n"
                f"Model loaded: {model_loaded}\n"
                f"Cleanup mode: {cleanup_mode}\n"
                f"Transcribe count: {transcribe_count}"
            ),
        )

    def _save(self):
        hotkey = self.hotkey_edit.text().strip()
        if not hotkey:
            QMessageBox.warning(self, "Settings", "Hotkey cannot be empty.")
            return
        config = self.app.config.copy()
        config["hotkey"] = hotkey
        config["dictate_server_url"] = self.dictate_server_url_edit.text().strip().rstrip("/")
        config["dictate_server_api_key"] = self.dictate_server_api_key_edit.text().strip()
        try:
            config["server_timeout_seconds"] = int(self.server_timeout_edit.text().strip() or "60")
        except ValueError:
            config["server_timeout_seconds"] = 60
        try:
            config["max_history_entries"] = int(self.max_history_edit.text().strip() or "500")
        except ValueError:
            config["max_history_entries"] = 500
        config["restore_clipboard_after_paste"] = self.restore_cb.isChecked()
        config["launch_at_startup"] = self.startup_cb.isChecked()
        self._save_config_fn(config)
        self.app.apply_settings(config)
        self._on_back()


class DashboardWindow(QMainWindow):
    def __init__(self, app: "DictationApp"):
        super().__init__()
        self.app = app
        self._state = "loading"
        self.is_hidden = False
        self.setWindowTitle(APP_TITLE)
        self.setMinimumSize(1000, 700)
        self.resize(1140, 780)
        self.setWindowIcon(_pil_icon(render_logo(48)))
        self.setStyleSheet(GLOBAL_STYLE)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(32, 28, 32, 24)
        root.setSpacing(20)

        header = QHBoxLayout()
        brand = QHBoxLayout()
        logo_box = QFrame()
        logo_box.setFixedSize(48, 48)
        logo_box.setStyleSheet(
            f"background: {ACCENT}; border-radius: 12px;"
        )
        lb = QVBoxLayout(logo_box)
        lb.setContentsMargins(0, 0, 0, 0)
        logo = QLabel()
        logo.setPixmap(_pil_icon(render_lucide("audio-lines", 24, color="#EFF6FF")).pixmap(24, 24))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lb.addWidget(logo)
        brand.addWidget(logo_box)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self._title = QLabel(APP_TITLE)
        self._title.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        self._subtitle = QLabel("Server-backed voice typing")
        self._subtitle.setStyleSheet(f"color: {MUTED}; font-size: 13px;")
        titles.addWidget(self._title)
        titles.addWidget(self._subtitle)
        brand.addLayout(titles)
        header.addLayout(brand)
        header.addStretch()
        self._hotkey_pill = QLabel()
        self._hotkey_pill.setStyleSheet(
            f"background: {ACCENT_LIGHT}; color: {ACCENT}; padding: 8px 16px; "
            "border-radius: 20px; font-weight: 600; font-size: 13px;"
        )
        header.addWidget(self._hotkey_pill)
        settings_btn = QPushButton()
        settings_btn.setFixedSize(40, 40)
        settings_btn.setIcon(_pil_icon(render_lucide("settings", 20, color=TEXT)))
        settings_btn.setStyleSheet(
            f"QPushButton {{ border: 1px solid {BORDER}; border-radius: 12px; background: white; }}"
            "QPushButton:hover { background: #F4F4F5; }"
        )
        settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        settings_btn.clicked.connect(self._open_settings)
        header.addWidget(settings_btn)
        root.addLayout(header)

        self._stack = QStackedWidget()
        self._home = self._build_home()
        from main import CONFIG_PATH, save_config  # noqa: PLC0415

        self._settings = SettingsWidget(
            self.app,
            self._show_home,
            lambda config: save_config(CONFIG_PATH, config),
        )
        self._stack.addWidget(self._home)
        self._stack.addWidget(self._settings)
        root.addWidget(self._stack, 1)

        footer = QFrame()
        footer.setStyleSheet(
            f"background: {FOOTER_BG}; border: 1px solid {BORDER}; border-radius: 12px;"
        )
        foot = QHBoxLayout(footer)
        foot.setContentsMargins(16, 10, 16, 10)
        self._foot_dot = _plain_label("●")
        self._foot_dot.setStyleSheet(f"color: {ACCENT}; font-size: 10px; border: none; background: transparent;")
        self._foot_status = _plain_label("Loading…")
        self._foot_status.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        foot.addWidget(self._foot_dot)
        foot.addWidget(self._foot_status)
        foot.addStretch()
        self._foot_meta = _plain_label("")
        self._foot_meta.setStyleSheet(
            f"color: {MUTED}; font-size: 11px; border: none; background: transparent;"
        )
        foot.addWidget(self._foot_meta)
        root.addWidget(footer)

        self._show_home()
        self._setup_tray()

    def closeEvent(self, event):
        if QSystemTrayIcon.isSystemTrayAvailable():
            event.ignore()
            self.hide_to_tray()
            return
        super().closeEvent(event)

    def _setup_tray(self):
        self._tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._tray = QSystemTrayIcon(_pil_icon(render_logo(64)), self)
        menu = self._tray.contextMenu()
        if menu is None:
            from PySide6.QtWidgets import QMenu

            menu = QMenu()
        show_action = QAction(f"Show {APP_TITLE}", self)
        show_action.triggered.connect(self.show_window)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.app.quit)
        menu.addAction(show_action)
        menu.addAction(quit_action)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._tray_activated)
        self._tray.show()

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_window()

    def _build_home(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setSpacing(20)
        layout.setContentsMargins(0, 0, 0, 0)
        left = QVBoxLayout()
        left.setSpacing(12)

        self._record_banner = QFrame()
        self._record_banner.setStyleSheet(
            f"background: {RECORD_BG}; border-left: 4px solid {RED}; border-radius: 12px;"
        )
        rb = QHBoxLayout(self._record_banner)
        rb.setContentsMargins(16, 14, 16, 14)
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {RED}; font-size: 18px;")
        rb.addWidget(dot)
        rb_text = QVBoxLayout()
        rb_title = QLabel("Recording…")
        rb_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        rb_sub = QLabel("Press your hotkey again to stop.")
        rb_sub.setStyleSheet(f"color: {MUTED}; font-size: 12px;")
        rb_text.addWidget(rb_title)
        rb_text.addWidget(rb_sub)
        rb.addLayout(rb_text, 1)
        self._record_banner.hide()
        left.addWidget(self._record_banner)

        list_card = _card()
        lc = QVBoxLayout(list_card)
        lc.setContentsMargins(20, 20, 8, 20)
        lc.setSpacing(12)
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 12, 0)
        head.addWidget(_icon_label("file-text", 18, MUTED))
        title = QLabel("Transcriptions")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.DemiBold))
        head.addWidget(title)
        head.addStretch()
        self._count_badge = QLabel("0 items")
        self._count_badge.setStyleSheet(
            f"background: {ENTRY_BG}; color: {TEXT}; padding: 4px 10px; "
            "border-radius: 12px; font-size: 11px; font-weight: 600;"
        )
        head.addWidget(self._count_badge)
        lc.addLayout(head)
        self._history_scroll = QScrollArea()
        self._history_scroll.setWidgetResizable(True)
        self._history_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._history_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._history_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._history_scroll.setStyleSheet(
            "QScrollArea { border: none; background: white; }"
        )
        self._history_body = QWidget()
        self._history_area = QVBoxLayout(self._history_body)
        self._history_area.setSpacing(10)
        self._history_area.setContentsMargins(0, 0, 4, 0)
        self._history_area.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._history_scroll.setWidget(self._history_body)
        lc.addWidget(self._history_scroll, 1)
        left.addWidget(list_card, 1)
        layout.addLayout(left, 2)

        right = QVBoxLayout()
        right.setSpacing(12)
        grid = QGridLayout()
        grid.setSpacing(12)
        self._stat_labels: dict[str, QLabel] = {}
        stat_icons = {"time": "clock", "words": "type", "sessions": "mic", "wpm": "gauge"}
        for i, (key, title_text) in enumerate(
            [("time", "Total Time"), ("words", "Words"), ("sessions", "Sessions"), ("wpm", "Avg WPM")]
        ):
            card = _card()
            cv = QVBoxLayout(card)
            cv.setContentsMargins(14, 14, 14, 14)
            cv.setSpacing(6)
            row = QHBoxLayout()
            row.addWidget(_icon_label(stat_icons[key], 14, ACCENT))
            lbl = _muted_label(title_text, size=11)
            row.addWidget(lbl)
            row.addStretch()
            cv.addLayout(row)
            val = _plain_label("0")
            val.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
            self._stat_labels[key] = val
            cv.addWidget(val)
            grid.addWidget(card, i // 2, i % 2)

        # Time Saved spans both KPI columns beneath the two-by-two grid.
        saved_card = _card()
        saved_layout = QVBoxLayout(saved_card)
        saved_layout.setContentsMargins(14, 14, 14, 14)
        saved_layout.setSpacing(6)
        saved_head = QHBoxLayout()
        saved_head.addWidget(_icon_label("clock", 14, ACCENT))
        saved_head.addWidget(_muted_label("Time Saved", size=11))
        saved_head.addStretch()
        saved_layout.addLayout(saved_head)
        self._stat_labels["time_saved"] = _plain_label("No time saved yet")
        self._stat_labels["time_saved"].setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        self._stat_labels["time_saved"].setWordWrap(True)
        saved_layout.addWidget(self._stat_labels["time_saved"])
        grid.addWidget(saved_card, 2, 0, 1, 2)
        right.addLayout(grid)

        self._server_card = _card()
        sv_card = QVBoxLayout(self._server_card)
        sv_card.setContentsMargins(18, 18, 18, 18)
        sv_card.setSpacing(10)
        server_head = QHBoxLayout()
        shield_box = QFrame()
        shield_box.setFixedSize(40, 40)
        shield_box.setStyleSheet(f"background: {ACCENT_LIGHT}; border-radius: 10px;")
        sb = QVBoxLayout(shield_box)
        sb.setContentsMargins(0, 0, 0, 0)
        sh = QLabel()
        sh.setPixmap(_pil_icon(render_lucide("wifi", 20, color=ACCENT)).pixmap(20, 20))
        sh.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sb.addWidget(sh)
        server_head.addWidget(shield_box)
        server_titles = QVBoxLayout()
        server_titles.setSpacing(0)
        st = QLabel("Server Mode")
        st.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        ss = QLabel("Transcription on Proxmox server")
        ss.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        server_titles.addWidget(st)
        server_titles.addWidget(ss)
        server_head.addLayout(server_titles)
        sv_card.addLayout(server_head)
        server_desc = _muted_label(
            "Audio is sent to the Dictate API server for transcription and OpenAI cleanup. "
            "No local AI runs on this workstation.",
            size=12,
        )
        server_desc.setWordWrap(True)
        sv_card.addWidget(server_desc)
        right.addWidget(self._server_card)

        self._status_card = _card()
        sv = QVBoxLayout(self._status_card)
        sv.setContentsMargins(18, 18, 18, 18)
        sv.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._listen_icon = QLabel()
        self._listen_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._listen_icon.setFixedHeight(72)
        sv.addWidget(self._listen_icon)
        self._listen_title = _plain_label("Ready")
        self._listen_title.setFont(QFont("Segoe UI", 12, QFont.Weight.DemiBold))
        self._listen_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._listen_sub = _muted_label("Press your hotkey to start dictating.", size=11)
        self._listen_sub.setWordWrap(True)
        self._listen_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sv.addWidget(self._listen_title)
        sv.addWidget(self._listen_sub)
        right.addWidget(self._status_card, 1)
        layout.addLayout(right, 1)
        return page

    def _show_home(self):
        self._stack.setCurrentWidget(self._home)
        self.refresh()
        self._update_footer_meta()

    def _open_settings(self):
        self._settings.reload()
        self._stack.setCurrentWidget(self._settings)

    def _update_hotkey_pill(self):
        hk = format_hotkey_display(self.app.config["hotkey"])
        if self._state == "recording":
            self._hotkey_pill.setText(f"Press {hk} to Stop")
            self._hotkey_pill.setStyleSheet(
                f"background: #FEF2F2; color: {RED_TEXT}; padding: 8px 16px; "
                "border-radius: 20px; font-weight: 600; font-size: 13px; border: 1px solid #FECACA;"
            )
        else:
            self._hotkey_pill.setText(f"Press {hk}")
            self._hotkey_pill.setStyleSheet(
                f"background: {ACCENT_LIGHT}; color: {ACCENT}; padding: 8px 16px; "
                "border-radius: 20px; font-weight: 600; font-size: 13px;"
            )

    def refresh_footer(self):
        self._update_footer_meta()

    def _update_footer_meta(self):
        from main import __version__

        hk = format_hotkey_display(self.app.config["hotkey"])
        server = self.app.config.get("dictate_server_url", "").rstrip("/") or "not configured"
        backend = getattr(self.app, "hotkey_backend", "none")
        if backend == "native":
            shell = " · Native shell"
        elif backend == "pynput":
            shell = " · Python hotkeys"
        elif self.app.native.available:
            shell = " · Native (paste/audio)"
        else:
            shell = ""
        self._foot_meta.setText(f"Server: {server} · Hotkey: {hk} · v{__version__}{shell}")

    def set_app_state(self, state: str):
        self._state = state
        if state == "recording":
            self._record_banner.show()
            self._server_card.hide()
            mic = _pil_icon(render_lucide("mic", 28, color="white"))
            self._listen_icon.setPixmap(mic.pixmap(56, 56))
            self._listen_icon.setStyleSheet(
                f"background: {RED}; border-radius: 28px; padding: 14px;"
            )
        else:
            self._record_banner.hide()
            self._server_card.show()
            self._listen_icon.setStyleSheet("background: transparent;")
            if state in ("working", "loading"):
                self._listen_icon.setPixmap(
                    _pil_icon(render_lucide("gauge", 32, color=ACCENT)).pixmap(48, 48)
                )
            else:
                self._listen_icon.setPixmap(
                    _pil_icon(render_lucide("mic", 28, color=ACCENT)).pixmap(48, 48)
                )
        self._update_hotkey_pill()
        self._update_footer_meta()
        dot_color = {
            "recording": RED,
            "working": WARNING,
            "loading": WARNING,
            "error": RED,
        }.get(state, ACCENT)
        self._foot_dot.setStyleSheet(
            f"color: {dot_color}; font-size: 10px; border: none; background: transparent;"
        )
        foot_text = f"color: {TEXT}; border: none; background: transparent;"
        foot_muted = f"color: {RED_TEXT}; border: none; background: transparent;"
        if state == "recording":
            self._listen_title.setText("Listening")
            self._listen_sub.setText("Speak naturally — text appears where your cursor is.")
            self._foot_status.setText("Recording…")
            self._foot_status.setStyleSheet(foot_muted)
        elif state == "working":
            self._listen_title.setText("Transcribing…")
            self._listen_sub.setText("Sending audio to the Dictate server.")
            self._foot_status.setText("Transcribing…")
            self._foot_status.setStyleSheet(foot_text)
        elif state == "loading":
            self._listen_title.setText("Starting…")
            self._listen_sub.setText("Connecting to the Dictate server.")
            self._foot_status.setText("Starting…")
            self._foot_status.setStyleSheet(foot_text)
        else:
            self._listen_title.setText("Ready")
            self._listen_sub.setText("Press your hotkey to start dictating.")
            self._foot_status.setText("Ready")
            self._foot_status.setStyleSheet(foot_text)

    def set_status(self, message: str, auto_clear_ms: int | None = None, state: str = "idle"):
        self.set_app_state(state)
        if message:
            self._foot_status.setText(message)
        if auto_clear_ms:
            # Only clear if we are still showing this same state (avoid wiping "recording").
            token = getattr(self, "_status_token", 0) + 1
            self._status_token = token

            def _clear():
                if getattr(self, "_status_token", 0) != token:
                    return
                if self._state in ("recording", "working", "loading"):
                    return
                self.set_app_state("idle")

            QTimer.singleShot(auto_clear_ms, _clear)

    def refresh(self):
        while self._history_area.count():
            item = self._history_area.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        entries = self.app.history.get_entries()
        self._count_badge.setText(f"{len(entries)} item" if len(entries) == 1 else f"{len(entries)} items")
        if not entries:
            empty = _muted_label("No transcriptions yet", size=13)
            empty.setStyleSheet(f"color: {MUTED}; padding: 24px; border: none; background: transparent;")
            self._history_area.addWidget(empty)
        else:
            for entry in entries:
                self._history_area.addWidget(self._history_row(entry))
        stats = self.app.history.get_stats()
        self._stat_labels["time"].setText(format_total_time(stats["total_seconds"]))
        self._stat_labels["words"].setText(f"{stats['total_words']:,}")
        self._stat_labels["sessions"].setText(str(stats["sessions"]))
        self._stat_labels["wpm"].setText(str(stats["wpm"]))
        saved_minutes = calculate_time_saved(
            stats.get("total_words", 0),
            stats.get("total_seconds", 0),
            NORMAL_TYPING_WPM,
        )
        self._stat_labels["time_saved"].setText(format_time_saved(saved_minutes))

    def _history_row(self, entry: dict) -> QWidget:
        row = QFrame()
        row.setStyleSheet(
            f"background: rgba(244,244,245,0.85); border: 1px solid {BORDER}; border-radius: 12px;"
        )
        layout = QVBoxLayout(row)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        top = QHBoxLayout()
        ts = _muted_label(format_entry_timestamp(entry["timestamp"]), bold=True)
        top.addWidget(ts)
        top.addStretch()
        copy_btn = _icon_button("copy", "Copy")
        copy_btn.clicked.connect(lambda _checked=False, t=entry["text"]: pyperclip.copy(t))
        del_btn = _icon_button("trash-2", "Delete")
        del_btn.clicked.connect(lambda _checked=False, eid=entry["id"]: self._delete_entry(eid))
        top.addWidget(copy_btn)
        top.addWidget(del_btn)
        layout.addLayout(top)
        text = _plain_label(entry["text"])
        text.setWordWrap(True)
        text.setStyleSheet(
            f"color: {TEXT}; font-size: 13px; border: none; background: transparent; padding: 0;"
        )
        layout.addWidget(text)
        return row

    def _delete_entry(self, entry_id: str):
        self.app.history.delete(entry_id)
        self.refresh()

    def show_window(self):
        self.is_hidden = False
        self.showNormal()
        self.raise_()
        self.activateWindow()
        # Defer paint/refresh so tray restore does not race a PortAudio probe.
        QTimer.singleShot(0, self._after_show)

    def _after_show(self):
        try:
            self.set_app_state(self.app.state if self.app.state != "loading" else self._state)
            self.refresh()
            self._update_footer_meta()
        except Exception:
            pass
        QApplication.processEvents()

    def hide_to_tray(self):
        self.is_hidden = True
        if self._tray is not None:
            self.hide()
        else:
            self.showMinimized()

    def run(self, *, start_minimized: bool = False):
        if start_minimized:
            self.hide_to_tray()
        else:
            self.show()
        QTimer.singleShot(0, self.refresh)

    def destroy(self):
        self.close()
        QApplication.instance().quit()
