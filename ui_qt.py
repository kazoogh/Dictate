"""Dictate UI — PySide6 (Qt) dashboard."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Callable

import pyperclip
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QAction, QFont, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
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
QLineEdit, QComboBox {{
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
    """Label with no visible box/chrome — text only."""
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
        layout.addWidget(self._heading("Quick Dictate", small=True))
        layout.addWidget(QLabel("Hotkey"))
        self.hotkey_edit = QLineEdit()
        layout.addWidget(self.hotkey_edit)
        layout.addWidget(QLabel("Whisper model size"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(["tiny", "base", "small", "medium"])
        layout.addWidget(self.model_combo)
        self.restore_cb = QCheckBox("Restore clipboard after paste")
        layout.addWidget(self.restore_cb)
        self.cleanup_cb = QCheckBox("Clean up dictation (remove fillers, add punctuation)")
        layout.addWidget(self.cleanup_cb)
        self.vocabulary_cb = QCheckBox("Use custom vocabulary (company names, file types, software)")
        layout.addWidget(self.vocabulary_cb)
        self.vocabulary_learn_cb = QCheckBox("Learn vocabulary when I fix pasted text")
        layout.addWidget(self.vocabulary_learn_cb)
        vocab_btn = QPushButton("Edit vocabulary.json")
        vocab_btn.clicked.connect(self._open_vocabulary)
        layout.addWidget(vocab_btn)

        layout.addWidget(self._heading("Clinical Session", small=True))
        layout.addWidget(QLabel("Clinical stop hotkey"))
        self.clinical_hotkey_edit = QLineEdit()
        layout.addWidget(self.clinical_hotkey_edit)
        layout.addWidget(QLabel("OpenAI API key (clinical only)"))
        self.openai_key_edit = QLineEdit()
        self.openai_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.openai_key_edit)
        layout.addWidget(QLabel("OpenAI model"))
        self.openai_model_combo = QComboBox()
        self.openai_model_combo.addItems(["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1"])
        layout.addWidget(self.openai_model_combo)
        layout.addWidget(QLabel("Max recording duration (hours)"))
        self.max_hours_combo = QComboBox()
        self.max_hours_combo.addItems(["1", "2", "3", "4"])
        layout.addWidget(self.max_hours_combo)
        layout.addWidget(QLabel("Session retention"))
        self.retention_combo = QComboBox()
        self.retention_combo.addItems(["1", "7", "30", "manual"])
        layout.addWidget(self.retention_combo)

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
        self.model_combo.setCurrentText(self.app.config["model_size"])
        self.restore_cb.setChecked(self.app.config.get("restore_clipboard_after_paste", False))
        self.cleanup_cb.setChecked(self.app.config.get("dictation_cleanup", True))
        self.vocabulary_cb.setChecked(self.app.config.get("vocabulary_correction", True))
        self.vocabulary_learn_cb.setChecked(self.app.config.get("vocabulary_auto_learn", True))
        self.clinical_hotkey_edit.setText(self.app.config.get("clinical_hotkey", "<ctrl>+<alt>+r"))
        self.openai_key_edit.setText(self.app.clinical.get_openai_api_key())
        self.openai_model_combo.setCurrentText(self.app.config.get("openai_model", "gpt-4o-mini"))
        self.max_hours_combo.setCurrentText(str(self.app.config.get("clinical_max_duration_hours", 2)))
        self.retention_combo.setCurrentText(str(self.app.config.get("clinical_retention_days", "7")))

    def _open_vocabulary(self):
        path = self.app.vocabulary.path
        try:
            os.startfile(path)
            self.app.vocabulary.reload()
        except OSError as exc:
            QMessageBox.critical(self, "Settings", f"Could not open vocabulary file:\n{exc}")

    def _save(self):
        hotkey = self.hotkey_edit.text().strip()
        clinical_hotkey = self.clinical_hotkey_edit.text().strip()
        if not hotkey or not clinical_hotkey:
            QMessageBox.warning(self, "Settings", "Hotkeys cannot be empty.")
            return
        config = self.app.config.copy()
        config["hotkey"] = hotkey
        config["clinical_hotkey"] = clinical_hotkey
        config["model_size"] = self.model_combo.currentText()
        config["restore_clipboard_after_paste"] = self.restore_cb.isChecked()
        config["dictation_cleanup"] = self.cleanup_cb.isChecked()
        config["vocabulary_correction"] = self.vocabulary_cb.isChecked()
        config["vocabulary_auto_learn"] = self.vocabulary_learn_cb.isChecked()
        config["openai_model"] = self.openai_model_combo.currentText()
        try:
            config["clinical_max_duration_hours"] = int(self.max_hours_combo.currentText())
        except ValueError:
            config["clinical_max_duration_hours"] = 2
        config["clinical_retention_days"] = self.retention_combo.currentText()
        self._save_config_fn(config)
        self.app.clinical.set_openai_api_key(self.openai_key_edit.text().strip())
        self.app.apply_settings(config)
        self._on_back()


class DashboardWindow(QMainWindow):
    def __init__(self, app: "DictationApp"):
        super().__init__()
        self.app = app
        self._state = "loading"
        self._mode = "quick"
        self.is_hidden = False
        self.setWindowTitle("Dictate")
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
        self._title = QLabel("Dictate")
        self._title.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        self._subtitle = QLabel("Local voice typing assistant")
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

        body = QHBoxLayout()
        body.setSpacing(20)
        nav = QVBoxLayout()
        nav.setSpacing(6)
        modes_lbl = QLabel("Modes")
        modes_lbl.setStyleSheet(f"color: {MUTED}; font-size: 12px; font-weight: 600;")
        nav.addWidget(modes_lbl)
        self._nav_quick = QPushButton("Quick Dictate")
        self._nav_clinical = QPushButton("Clinical Session")
        for btn in (self._nav_quick, self._nav_clinical):
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                f"QPushButton {{ text-align: left; padding: 10px 14px; border-radius: 10px; "
                f"background: transparent; color: {TEXT}; font-size: 13px; }}"
                f"QPushButton:hover {{ background: {ENTRY_BG}; }}"
                f"QPushButton:checked {{ background: {ACCENT_LIGHT}; color: {ACCENT}; font-weight: 600; }}"
            )
        self._nav_quick.clicked.connect(lambda: self._set_mode("quick"))
        self._nav_clinical.clicked.connect(lambda: self._set_mode("clinical"))
        nav.addWidget(self._nav_quick)
        nav.addWidget(self._nav_clinical)
        nav.addStretch()
        nav_wrap = QWidget()
        nav_wrap.setFixedWidth(168)
        nav_wrap.setLayout(nav)
        body.addWidget(nav_wrap)

        self._stack = QStackedWidget()
        self._home = self._build_home()
        from clinical_ui_qt import ClinicalWidget  # noqa: PLC0415
        from main import CONFIG_PATH, save_config  # noqa: PLC0415

        self._clinical = ClinicalWidget(
            self.app.clinical,
            on_notify=lambda msg, state="idle", ms=None: self.app._notify(msg, state, ms),
        )
        self._settings = SettingsWidget(
            self.app,
            self._show_current_mode,
            lambda config: save_config(CONFIG_PATH, config),
        )
        self._stack.addWidget(self._home)
        self._stack.addWidget(self._clinical)
        self._stack.addWidget(self._settings)
        body.addWidget(self._stack, 1)
        root.addLayout(body, 1)

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

        self._set_mode("quick")
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
        show_action = QAction("Show Dictate", self)
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
        right.addLayout(grid)

        self._local_card = _card()
        lv = QVBoxLayout(self._local_card)
        lv.setContentsMargins(18, 18, 18, 18)
        lv.setSpacing(10)
        local_head = QHBoxLayout()
        shield_box = QFrame()
        shield_box.setFixedSize(40, 40)
        shield_box.setStyleSheet(f"background: {ACCENT_LIGHT}; border-radius: 10px;")
        sb = QVBoxLayout(shield_box)
        sb.setContentsMargins(0, 0, 0, 0)
        sh = QLabel()
        sh.setPixmap(_pil_icon(render_lucide("shield-check", 20, color=ACCENT)).pixmap(20, 20))
        sh.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sb.addWidget(sh)
        local_head.addWidget(shield_box)
        local_titles = QVBoxLayout()
        local_titles.setSpacing(0)
        lt = QLabel("Local Mode")
        lt.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        ls = QLabel("On-device processing")
        ls.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        local_titles.addWidget(lt)
        local_titles.addWidget(ls)
        local_head.addLayout(local_titles)
        lv.addLayout(local_head)
        local_desc = _muted_label(
            "All transcription happens on your machine. No audio ever leaves your device.",
            size=12,
        )
        local_desc.setWordWrap(True)
        lv.addWidget(local_desc)
        offline = QFrame()
        offline.setStyleSheet(f"background: {ACCENT_LIGHT}; border-radius: 8px;")
        off_l = QHBoxLayout(offline)
        off_l.setContentsMargins(10, 6, 10, 6)
        off_l.addWidget(_icon_label("wifi", 14, ACCENT))
        off_txt = QLabel("No internet required")
        off_txt.setStyleSheet(f"color: {ACCENT}; font-size: 11px; font-weight: 600;")
        off_l.addWidget(off_txt)
        off_l.addStretch()
        lv.addWidget(offline)
        right.addWidget(self._local_card)

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

    def _set_mode(self, mode: str):
        self._mode = mode
        self._nav_quick.setChecked(mode == "quick")
        self._nav_clinical.setChecked(mode == "clinical")
        if mode == "quick":
            self._stack.setCurrentWidget(self._home)
            self._subtitle.setText("Local voice typing assistant")
            self._hotkey_pill.show()
            self.refresh()
        elif mode == "clinical":
            self._stack.setCurrentWidget(self._clinical)
            self._subtitle.setText("Clinical appointment recording & answer sheets")
            self._hotkey_pill.hide()
            self.refresh_clinical()
        self._update_footer_meta()

    def _show_current_mode(self):
        self._set_mode(self._mode)

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
        model = self.app.config.get("model_size", "base")
        hk = format_hotkey_display(self.app.config["hotkey"])
        chk = format_hotkey_display(self.app.config.get("clinical_hotkey", "<ctrl>+<alt>+r"))
        backend = getattr(self.app, "hotkey_backend", "none")
        if backend == "native":
            shell = " · Native shell"
        elif backend == "pynput":
            shell = " · Python hotkeys"
        elif self.app.native.available:
            shell = " · Native (paste/audio)"
        else:
            shell = ""
        if self._mode == "clinical":
            self._foot_meta.setText(f"Model: {model} · Transcribe: Local · Clinical stop: {chk}{shell}")
        else:
            self._foot_meta.setText(f"Model: {model} · Offline · Hotkey: {hk}{shell}")

    def set_app_state(self, state: str):
        self._state = state
        if state == "recording":
            self._record_banner.show()
            self._local_card.hide()
            mic = _pil_icon(render_lucide("mic", 28, color="white"))
            self._listen_icon.setPixmap(mic.pixmap(56, 56))
            self._listen_icon.setStyleSheet(
                f"background: {RED}; border-radius: 28px; padding: 14px;"
            )
        else:
            self._record_banner.hide()
            self._local_card.show()
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
            self._listen_sub.setText("Processing your speech locally.")
            self._foot_status.setText("Transcribing…")
            self._foot_status.setStyleSheet(foot_text)
        elif state == "loading":
            self._listen_title.setText("Loading model…")
            self._listen_sub.setText("Downloading Whisper weights on first run.")
            self._foot_status.setText("Loading…")
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
            QTimer.singleShot(auto_clear_ms, lambda: self.set_app_state("idle"))

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
        copy_btn.clicked.connect(lambda: pyperclip.copy(entry["text"]))
        del_btn = _icon_button("trash-2", "Delete")
        del_btn.clicked.connect(lambda: self._delete_entry(entry["id"]))
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

    def refresh_clinical(self):
        self._clinical.refresh()
        if self.app.clinical.is_recording():
            self.update_clinical_recording_timer(int(self.app.clinical.recording_elapsed()))

    def update_clinical_recording_timer(self, elapsed: int):
        timer = format_total_time(elapsed).replace("m", ":")  # rough
        h = elapsed // 3600
        m = (elapsed % 3600) // 60
        s = elapsed % 60
        t = f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
        self._foot_status.setText(f"Clinical recording {t}")

    def show_window(self):
        self.is_hidden = False
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def hide_to_tray(self):
        self.is_hidden = True
        if self._tray is not None:
            self.hide()
        else:
            self.showMinimized()

    def run(self):
        self.show()
        # Populate after layout has real dimensions (avoids empty scroll viewport).
        QTimer.singleShot(0, self.refresh)
        self.app._notify("Loading Whisper model…", state="loading")

    def destroy(self):
        self.close()
        QApplication.instance().quit()
