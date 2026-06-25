"""Dictate UI — PySide6 (Qt) dashboard."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Callable

import pyperclip
from PySide6.QtCore import Qt, QTimer
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
    QSizePolicy,
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
        self.setStyleSheet(f"QMainWindow {{ background: {BG}; }} QLabel {{ color: {TEXT}; }}")

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(32, 28, 32, 28)

        header = QHBoxLayout()
        brand = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(_pil_icon(render_logo(48)).pixmap(48, 48))
        brand.addWidget(logo)
        titles = QVBoxLayout()
        self._title = QLabel("Dictate")
        self._title.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        self._subtitle = QLabel("Local voice typing assistant")
        self._subtitle.setStyleSheet(f"color: {MUTED};")
        titles.addWidget(self._title)
        titles.addWidget(self._subtitle)
        brand.addLayout(titles)
        header.addLayout(brand)
        header.addStretch()
        self._hotkey_pill = QLabel()
        self._hotkey_pill.setStyleSheet(
            f"background: {ACCENT_LIGHT}; color: {ACCENT}; padding: 8px 14px; border-radius: 8px; font-weight: 600;"
        )
        header.addWidget(self._hotkey_pill)
        settings_btn = QPushButton("Settings")
        settings_btn.clicked.connect(self._open_settings)
        header.addWidget(settings_btn)
        root.addLayout(header)

        body = QHBoxLayout()
        nav = QVBoxLayout()
        nav.addWidget(QLabel("Modes"))
        self._nav_quick = QPushButton("Quick Dictate")
        self._nav_clinical = QPushButton("Clinical Session")
        for btn in (self._nav_quick, self._nav_clinical):
            btn.setCheckable(True)
            btn.setStyleSheet(
                f"QPushButton {{ text-align: left; padding: 12px; border-radius: 8px; background: {ENTRY_BG}; }}"
                f"QPushButton:checked {{ background: {ACCENT_LIGHT}; color: {ACCENT}; font-weight: 600; }}"
            )
        self._nav_quick.clicked.connect(lambda: self._set_mode("quick"))
        self._nav_clinical.clicked.connect(lambda: self._set_mode("clinical"))
        nav.addWidget(self._nav_quick)
        nav.addWidget(self._nav_clinical)
        nav.addStretch()
        body.addLayout(nav)

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
        footer.setStyleSheet(f"background: {FOOTER_BG}; border: 1px solid {BORDER}; border-radius: 10px;")
        foot = QHBoxLayout(footer)
        self._foot_status = QLabel("Loading…")
        self._foot_status.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        foot.addWidget(self._foot_status)
        foot.addStretch()
        self._foot_meta = QLabel("")
        self._foot_meta.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
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
        left = QVBoxLayout()
        self._record_banner = QFrame()
        self._record_banner.setStyleSheet(f"background: {RECORD_BG}; border-left: 4px solid {RED}; border-radius: 8px;")
        rb = QVBoxLayout(self._record_banner)
        rb.addWidget(QLabel("Recording…  Press your hotkey again to stop."))
        self._record_banner.hide()
        left.addWidget(self._record_banner)

        list_card = _card()
        lc = QVBoxLayout(list_card)
        head = QHBoxLayout()
        head.addWidget(QLabel("Transcriptions"))
        self._count_badge = QLabel("0 items")
        head.addStretch()
        head.addWidget(self._count_badge)
        lc.addLayout(head)
        self._history_area = QVBoxLayout()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        hist_body = QWidget()
        hist_body.setLayout(self._history_area)
        scroll.setWidget(hist_body)
        lc.addWidget(scroll)
        left.addWidget(list_card, 1)
        layout.addLayout(left, 2)

        right = QVBoxLayout()
        grid = QGridLayout()
        self._stat_labels: dict[str, QLabel] = {}
        for i, (key, title) in enumerate(
            [("time", "Total Time"), ("words", "Words"), ("sessions", "Sessions"), ("wpm", "Avg WPM")]
        ):
            card = _card()
            cv = QVBoxLayout(card)
            cv.addWidget(QLabel(title))
            val = QLabel("0")
            val.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
            self._stat_labels[key] = val
            cv.addWidget(val)
            grid.addWidget(card, i // 2, i % 2)
        right.addLayout(grid)

        listen_card = _card()
        lv = QVBoxLayout(listen_card)
        self._listen_title = QLabel("Ready")
        self._listen_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self._listen_sub = QLabel("Press your hotkey to start dictating.")
        self._listen_sub.setStyleSheet(f"color: {MUTED};")
        self._listen_sub.setWordWrap(True)
        lv.addWidget(self._listen_title, alignment=Qt.AlignmentFlag.AlignCenter)
        lv.addWidget(self._listen_sub, alignment=Qt.AlignmentFlag.AlignCenter)
        right.addWidget(listen_card, 1)
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
                f"background: #FEF2F2; color: {RED_TEXT}; padding: 8px 14px; border-radius: 8px; font-weight: 600;"
            )
        else:
            self._hotkey_pill.setText(f"Press {hk}")
            self._hotkey_pill.setStyleSheet(
                f"background: {ACCENT_LIGHT}; color: {ACCENT}; padding: 8px 14px; border-radius: 8px; font-weight: 600;"
            )

    def _update_footer_meta(self):
        model = self.app.config.get("model_size", "base")
        hk = format_hotkey_display(self.app.config["hotkey"])
        chk = format_hotkey_display(self.app.config.get("clinical_hotkey", "<ctrl>+<alt>+r"))
        native = " · Native shell" if self.app.native.available else ""
        if self._mode == "clinical":
            self._foot_meta.setText(f"Model: {model} · Transcribe: Local · Clinical stop: {chk}{native}")
        else:
            self._foot_meta.setText(f"Model: {model} · Offline · Hotkey: {hk}{native}")

    def set_app_state(self, state: str):
        self._state = state
        if state == "recording":
            self._record_banner.show()
        else:
            self._record_banner.hide()
        self._update_hotkey_pill()
        self._update_footer_meta()
        if state == "recording":
            self._listen_title.setText("Listening")
            self._listen_sub.setText("Speak naturally — text appears where your cursor is.")
            self._foot_status.setText("Recording…")
        elif state == "working":
            self._listen_title.setText("Transcribing…")
            self._listen_sub.setText("Processing your speech locally.")
            self._foot_status.setText("Transcribing…")
        elif state == "loading":
            self._listen_title.setText("Loading model…")
            self._listen_sub.setText("")
            self._foot_status.setText("Loading…")
        else:
            self._listen_title.setText("Ready")
            self._listen_sub.setText("Press your hotkey to start dictating.")
            self._foot_status.setText("Ready")

    def set_status(self, message: str, auto_clear_ms: int | None = None, state: str = "idle"):
        self.set_app_state(state)
        if message:
            self._foot_status.setText(message)
        if auto_clear_ms:
            QTimer.singleShot(auto_clear_ms, lambda: self.set_app_state("idle"))

    def refresh(self):
        while self._history_area.count():
            item = self._history_area.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        entries = self.app.history.get_entries()
        self._count_badge.setText(f"{len(entries)} item" if len(entries) == 1 else f"{len(entries)} items")
        if not entries:
            empty = QLabel("No transcriptions yet")
            empty.setStyleSheet(f"color: {MUTED}; padding: 24px;")
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
        row.setStyleSheet(f"background: {ENTRY_BG}; border: 1px solid {BORDER}; border-radius: 10px;")
        layout = QVBoxLayout(row)
        top = QHBoxLayout()
        top.addWidget(QLabel(format_entry_timestamp(entry["timestamp"])))
        top.addStretch()
        copy_btn = QPushButton("Copy")
        copy_btn.setFlat(True)
        copy_btn.clicked.connect(lambda: pyperclip.copy(entry["text"]))
        del_btn = QPushButton("Delete")
        del_btn.setFlat(True)
        del_btn.clicked.connect(lambda: self._delete_entry(entry["id"]))
        top.addWidget(copy_btn)
        top.addWidget(del_btn)
        layout.addLayout(top)
        text = QLabel(entry["text"])
        text.setWordWrap(True)
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

    def destroy(self):
        self.close()
        QApplication.instance().quit()
