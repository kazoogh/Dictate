"""Clinical Session UI — PySide6."""

from __future__ import annotations

import os
import threading
from datetime import datetime
from typing import TYPE_CHECKING, Callable

import pyperclip
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from clinical.paths import PROCEDURE_TYPES

if TYPE_CHECKING:
    from clinical.service import ClinicalManager

ACCENT = "#2B7FFF"
ACCENT_LIGHT = "#EBF3FF"
ENTRY_BG = "#F4F4F5"
BORDER = "#E4E4E7"
MUTED = "#71717B"
RED = "#EF4444"
RED_TEXT = "#DC2626"
SUCCESS = "#16A34A"
SURFACE = "#FFFFFF"
TEXT = "#09090B"
WARNING = "#D97706"

STATUS_COLORS = {
    "Recording": RED_TEXT,
    "Processing": WARNING,
    "Needs Review": WARNING,
    "Ready for Dentrix": SUCCESS,
    "Entered in Dentrix": MUTED,
    "Error": RED_TEXT,
}


def format_duration(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def format_session_time(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%b %d · %I:%M %p")
    except ValueError:
        return iso


class ClinicalWidget(QWidget):
    def __init__(self, manager: "ClinicalManager", on_notify: Callable):
        super().__init__()
        self.manager = manager
        self.on_notify = on_notify
        self._selected_id: str | None = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick_timer)
        self._build()
        self.refresh()

    def _build(self):
        layout = QVBoxLayout(self)
        title = QLabel("Clinical Session")
        title.setStyleSheet("font-size: 20px; font-weight: 700;")
        layout.addWidget(title)
        layout.addWidget(QLabel("Record appointments · transcribe locally · AI answer sheets"))

        split = QSplitter(Qt.Orientation.Horizontal)
        left = QFrame()
        left.setStyleSheet(f"background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 12px;")
        ll = QVBoxLayout(left)
        ll.addWidget(QLabel("Sessions"))
        ll.addWidget(QLabel("Procedure type"))
        self._procedure = QComboBox()
        self._procedure.addItems(PROCEDURE_TYPES)
        ll.addWidget(self._procedure)
        self._start_btn = QPushButton("Start Recording")
        self._start_btn.setStyleSheet(f"background: {ACCENT}; color: white; padding: 10px; border-radius: 8px;")
        self._start_btn.clicked.connect(self._start_recording)
        ll.addWidget(self._start_btn)
        self._stop_btn = QPushButton("Stop & Generate Answer Sheet")
        self._stop_btn.setStyleSheet(f"background: {RED}; color: white; padding: 10px; border-radius: 8px;")
        self._stop_btn.clicked.connect(self._stop_recording)
        self._stop_btn.hide()
        self._recording_banner = QLabel("")
        self._recording_banner.setStyleSheet(f"color: {RED_TEXT}; font-weight: 600;")
        ll.addWidget(self._recording_banner)
        self._session_list = QVBoxLayout()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body.setLayout(self._session_list)
        scroll.setWidget(body)
        ll.addWidget(scroll, 1)
        split.addWidget(left)

        self._detail_host = QFrame()
        self._detail_host.setStyleSheet(f"background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 12px;")
        self._detail_layout = QVBoxLayout(self._detail_host)
        self._detail_layout.addWidget(QLabel("Select a session or start a new recording."))
        split.addWidget(self._detail_host)
        split.setSizes([320, 680])
        layout.addWidget(split, 1)

    def _start_recording(self):
        if self.manager.is_recording():
            return
        self._start_btn.setEnabled(False)
        procedure = self._procedure.currentText()

        def work():
            err = None
            session = None
            try:
                session = self.manager.start_session(procedure)
            except Exception as exc:
                err = exc

            def done():
                self._start_btn.setEnabled(True)
                if err:
                    QMessageBox.critical(self, "Clinical Session", str(err))
                    return
                if session:
                    self._selected_id = session["id"]
                self.on_notify("Clinical recording started…", "recording")
                self._update_recording_ui()
                self.refresh_sessions_list()
                self._show_recording_detail()

            QTimer.singleShot(0, done)

        threading.Thread(target=work, daemon=True).start()

    def _stop_recording(self):
        if not self.manager.is_recording():
            return
        self._stop_btn.setEnabled(False)

        def work():
            session = self.manager.stop_session()

            def done():
                self._stop_btn.setEnabled(True)
                self._update_recording_ui()
                if session:
                    self._selected_id = session["id"]
                    self.on_notify("Processing clinical session…", "working")
                self.refresh()

            QTimer.singleShot(0, done)

        threading.Thread(target=work, daemon=True).start()

    def _update_recording_ui(self):
        self._timer.stop()
        if self.manager.is_recording():
            self._start_btn.hide()
            self._stop_btn.show()
            self._recording_banner.show()
            self._tick_timer()
            self._timer.start(1000)
        else:
            self._stop_btn.hide()
            self._recording_banner.hide()
            self._start_btn.show()

    def _tick_timer(self):
        if not self.manager.is_recording():
            return
        elapsed = int(self.manager.recording_elapsed())
        self._recording_banner.setText(f"● Recording {format_duration(elapsed)}")

    def refresh_sessions_list(self):
        while self._session_list.count():
            item = self._session_list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        sessions = self.manager.list_sessions()
        if not sessions:
            self._session_list.addWidget(QLabel("No sessions yet"))
            return
        for session in sessions:
            btn = QPushButton(
                f"{session['procedure_type']}\n{session['status']} · "
                f"{format_session_time(session['started_at'])}"
            )
            btn.setStyleSheet(
                f"text-align: left; padding: 10px; background: "
                f"{'#EBF3FF' if session['id'] == self._selected_id else ENTRY_BG}; border-radius: 8px;"
            )
            btn.clicked.connect(lambda checked=False, sid=session["id"]: self._select_session(sid))
            self._session_list.addWidget(btn)

    def _select_session(self, session_id: str):
        self._selected_id = session_id
        self.refresh()

    def _clear_detail(self):
        while self._detail_layout.count():
            item = self._detail_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _show_recording_detail(self):
        self._clear_detail()
        self._detail_layout.addWidget(QLabel("Recording in progress…"))

    def refresh(self):
        self._update_recording_ui()
        self.refresh_sessions_list()
        active = self.manager.active_session()
        if self._selected_id:
            if self.manager.is_recording() and active and self._selected_id == active["id"]:
                self._show_recording_detail()
            else:
                self._show_detail(self._selected_id)
        elif self.manager.is_recording() and active:
            self._selected_id = active["id"]
            self._show_recording_detail()

    def _show_detail(self, session_id: str):
        self._clear_detail()
        session = self.manager.get_session(session_id)
        if not session:
            self._detail_layout.addWidget(QLabel("Session not found."))
            return
        header = QHBoxLayout()
        header_w = QWidget()
        header_w.setLayout(header)
        header.addWidget(QLabel(f"{session['procedure_type']} — {session['status']}"))
        header.addStretch()
        if session.get("pdf_path") and os.path.exists(session.get("pdf_path", "")):
            pdf_btn = QPushButton("Open PDF")
            pdf_btn.clicked.connect(lambda: self._open_pdf(session))
            header.addWidget(pdf_btn)
        if session["status"] in ("Needs Review", "Ready for Dentrix"):
            mark_btn = QPushButton("Mark Entered in Dentrix")
            mark_btn.clicked.connect(lambda: self._mark_entered(session_id))
            header.addWidget(mark_btn)
        del_btn = QPushButton("Delete")
        del_btn.clicked.connect(lambda: self._delete(session_id))
        header.addWidget(del_btn)
        self._detail_layout.addWidget(header_w)
        self._detail_layout.addWidget(
            QLabel(
                f"Started {format_session_time(session['started_at'])} · "
                f"Duration {format_duration(session.get('duration_seconds', 0))}"
            )
        )
        if session.get("error_message"):
            err = QLabel(session["error_message"])
            err.setStyleSheet(f"color: {RED_TEXT};")
            err.setWordWrap(True)
            self._detail_layout.addWidget(err)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        cv = QVBoxLayout(content)
        sheet = self.manager.read_answer_sheet(session)
        if sheet:
            self._render_answer_sheet(cv, sheet)
        else:
            transcript = self.manager.read_transcript(session)
            if transcript:
                cv.addWidget(QLabel("Transcript"))
                t = QLabel(transcript)
                t.setWordWrap(True)
                t.setStyleSheet(f"background: {ENTRY_BG}; padding: 12px; border-radius: 8px;")
                cv.addWidget(t)
                copy_btn = QPushButton("Copy Transcript")
                copy_btn.clicked.connect(lambda: pyperclip.copy(transcript))
                cv.addWidget(copy_btn)
            elif session["status"] == "Processing":
                cv.addWidget(QLabel("Processing…"))
            elif session["status"] == "Recording":
                cv.addWidget(QLabel("Recording in progress…"))
        scroll.setWidget(content)
        self._detail_layout.addWidget(scroll, 1)

    def _render_answer_sheet(self, parent: QVBoxLayout, sheet: dict):
        parent.addWidget(QLabel("Detected Details"))
        d = sheet.get("detected_details", {})
        for label, key in (
            ("Provider", "provider"),
            ("Assistant", "assistant"),
            ("Operatory", "operatory"),
            ("Tooth/Teeth", "tooth_number"),
        ):
            parent.addWidget(QLabel(f"{label}: {d.get(key, '')}"))
        parent.addWidget(QLabel("Template Answers"))
        for field in sheet.get("template_answers", []):
            card = QFrame()
            card.setStyleSheet(f"background: {ENTRY_BG}; border-radius: 8px; padding: 8px;")
            cl = QVBoxLayout(card)
            row = QHBoxLayout()
            row.addWidget(QLabel(field.get("label", "")))
            row.addStretch()
            copy = QPushButton("Copy")
            copy.clicked.connect(lambda checked=False, f=field: pyperclip.copy(f.get("suggested_answer", "")))
            row.addWidget(copy)
            cl.addLayout(row)
            cl.addWidget(QLabel(f"Answer: {field.get('suggested_answer', '')}"))
            cl.addWidget(QLabel(f"Evidence: {field.get('evidence', '')}"))
            parent.addWidget(card)
        all_answers = "\n".join(
            f"{f.get('label')}: {f.get('suggested_answer')}" for f in sheet.get("template_answers", [])
        )
        copy_all = QPushButton("Copy All Answers")
        copy_all.clicked.connect(lambda: pyperclip.copy(all_answers))
        parent.addWidget(copy_all)

    def _open_pdf(self, session: dict):
        path = self.manager.export_pdf(session["id"])
        if path and path.exists():
            os.startfile(str(path))
        else:
            QMessageBox.critical(self, "PDF", "Could not open PDF.")

    def _mark_entered(self, session_id: str):
        self.manager.mark_entered(session_id)
        self.refresh()

    def _delete(self, session_id: str):
        if QMessageBox.question(self, "Delete Session", "Delete this session and all files?") == QMessageBox.StandardButton.Yes:
            self.manager.delete_session(session_id)
            self.refresh()
