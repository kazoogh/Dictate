"""Clinical Session UI for Dictate."""

from __future__ import annotations

import os
import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING, Callable

import pyperclip

from ui import (
    ACCENT,
    ACCENT_LIGHT,
    BG,
    BORDER,
    BorderedCard,
    ENTRY_BG,
    FONT,
    FONT_CARD,
    FONT_MD,
    FONT_SM,
    FONT_TITLE,
    FONT_XS,
    MUTED,
    RED,
    RED_TEXT,
    SUCCESS,
    SURFACE,
    TEXT,
    WARNING,
)

if TYPE_CHECKING:
    from clinical.service import ClinicalManager


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


class ClinicalPage(tk.Frame):
    def __init__(self, parent, manager: "ClinicalManager", on_notify: Callable):
        super().__init__(parent, bg=BG)
        self.manager = manager
        self.on_notify = on_notify
        self._selected_id: str | None = None
        self._timer_job = None
        self._build()
        self.refresh()

    def _build(self):
        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", pady=(0, 16))
        tk.Label(top, text="Clinical Session", bg=BG, fg=TEXT, font=FONT_TITLE).pack(side="left")
        tk.Label(
            top,
            text="Record appointments · transcribe locally · AI answer sheets",
            bg=BG,
            fg=MUTED,
            font=FONT_SM,
        ).pack(side="left", padx=(12, 0))

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        left = BorderedCard(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        left.configure(width=300)
        left.grid_propagate(False)
        lb = left.body
        lb.configure(padx=12, pady=12)
        tk.Label(lb, text="Sessions", bg=SURFACE, fg=TEXT, font=FONT_CARD).pack(anchor="w")

        start_card = tk.Frame(lb, bg=ENTRY_BG)
        start_card.pack(fill="x", pady=(12, 12))
        inner = tk.Frame(start_card, bg=ENTRY_BG)
        inner.pack(fill="x", padx=12, pady=12)
        tk.Label(inner, text="Procedure type", bg=ENTRY_BG, fg=MUTED, font=FONT_XS).pack(anchor="w")
        from clinical.paths import PROCEDURE_TYPES

        self._procedure_var = tk.StringVar(value=PROCEDURE_TYPES[0])
        ttk.Combobox(
            inner,
            textvariable=self._procedure_var,
            values=PROCEDURE_TYPES,
            state="readonly",
        ).pack(fill="x", pady=(4, 8))
        self._start_btn = tk.Button(
            inner,
            text="Start Recording",
            command=self._start_recording,
            bg=ACCENT,
            fg="white",
            relief="flat",
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
            padx=12,
            pady=8,
        )
        self._start_btn.pack(fill="x")
        self._stop_btn = tk.Button(
            inner,
            text="Stop & Generate Answer Sheet",
            command=self._stop_recording,
            bg=RED,
            fg="white",
            relief="flat",
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
            padx=12,
            pady=8,
        )
        self._recording_banner = tk.Label(
            inner,
            text="",
            bg=ENTRY_BG,
            fg=RED_TEXT,
            font=("Segoe UI", 10, "bold"),
        )

        list_wrap = tk.Frame(lb, bg=SURFACE)
        list_wrap.pack(fill="both", expand=True)
        self._session_canvas = tk.Canvas(list_wrap, bg=SURFACE, highlightthickness=0)
        sb = ttk.Scrollbar(list_wrap, orient="vertical", command=self._session_canvas.yview)
        self._session_list = tk.Frame(self._session_canvas, bg=SURFACE)
        self._session_list.bind(
            "<Configure>",
            lambda _e: self._session_canvas.configure(scrollregion=self._session_canvas.bbox("all")),
        )
        self._list_win = self._session_canvas.create_window((0, 0), window=self._session_list, anchor="nw")
        self._session_canvas.configure(yscrollcommand=sb.set)
        self._session_canvas.bind(
            "<Configure>", lambda e: self._session_canvas.itemconfig(self._list_win, width=e.width)
        )
        self._session_canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        right = BorderedCard(body)
        right.grid(row=0, column=1, sticky="nsew")
        self._detail_body = right.body
        self._detail_body.configure(padx=20, pady=20)
        self._detail_placeholder = tk.Label(
            self._detail_body,
            text="Select a session or start a new recording.",
            bg=SURFACE,
            fg=MUTED,
            font=FONT_MD,
        )
        self._detail_placeholder.pack(expand=True)

    def _start_recording(self):
        if self.manager.is_recording():
            return
        self._start_btn.config(state="disabled", text="Starting…")
        procedure = self._procedure_var.get()

        def _work():
            err = None
            session = None
            try:
                session = self.manager.start_session(procedure)
            except Exception as exc:
                err = exc

            def _done():
                self._start_btn.config(state="normal", text="Start Recording")
                if err is not None:
                    messagebox.showerror("Clinical Session", str(err))
                    return
                if session is not None:
                    self._selected_id = session["id"]
                self.on_notify("Clinical recording started…", "recording")
                self._update_recording_ui()
                self.refresh_sessions_list()
                self._show_recording_detail()

            self.after(0, _done)

        threading.Thread(target=_work, daemon=True).start()

    def _stop_recording(self):
        if not self.manager.is_recording():
            return
        self._stop_btn.config(state="disabled", text="Stopping…")

        def _work():
            session = self.manager.stop_session()

            def _done():
                self._stop_btn.config(state="normal", text="Stop & Generate Answer Sheet")
                self._update_recording_ui()
                if session:
                    self._selected_id = session["id"]
                    self.on_notify("Processing clinical session…", "working")
                self.refresh()

            self.after(0, _done)

        threading.Thread(target=_work, daemon=True).start()

    def _update_recording_ui(self):
        if self._timer_job:
            self.after_cancel(self._timer_job)
            self._timer_job = None
        if self.manager.is_recording():
            self._start_btn.pack_forget()
            self._stop_btn.pack(fill="x", pady=(0, 6))
            self._recording_banner.pack(fill="x")
            self._tick_timer()
        else:
            self._stop_btn.pack_forget()
            self._recording_banner.pack_forget()
            self._start_btn.pack(fill="x")

    def _tick_timer(self):
        if not self.manager.is_recording():
            return
        elapsed = int(self.manager.recording_elapsed())
        self._recording_banner.config(text=f"● Recording {format_duration(elapsed)}")
        self._update_footer_timer(elapsed)
        self._timer_job = self.after(1000, self._tick_timer)

    def _update_footer_timer(self, elapsed: int):
        try:
            root = self.winfo_toplevel()
            app = getattr(root, "_dictate_app", None)
            if app is not None:
                app.dashboard.update_clinical_recording_timer(elapsed)
        except Exception:
            pass

    def refresh_sessions_list(self):
        for child in self._session_list.winfo_children():
            child.destroy()
        sessions = self.manager.list_sessions()
        if not sessions:
            tk.Label(self._session_list, text="No sessions yet", bg=SURFACE, fg=MUTED, font=FONT).pack(
                pady=20
            )
        else:
            for session in sessions:
                SessionListItem(
                    self._session_list,
                    session,
                    session["id"] == self._selected_id,
                    self._select_session,
                ).pack(fill="x", pady=(0, 8))

    def _show_recording_detail(self):
        for child in self._detail_body.winfo_children():
            child.destroy()
        tk.Label(
            self._detail_body,
            text="Recording in progress…",
            bg=SURFACE,
            fg=RED_TEXT,
            font=FONT_MD,
        ).pack(expand=True)

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

    def _select_session(self, session_id: str):
        self._selected_id = session_id
        self.refresh()

    def _show_detail(self, session_id: str):
        for child in self._detail_body.winfo_children():
            child.destroy()
        session = self.manager.get_session(session_id)
        if not session:
            self._detail_placeholder = tk.Label(
                self._detail_body, text="Session not found.", bg=SURFACE, fg=MUTED, font=FONT_MD
            )
            self._detail_placeholder.pack(expand=True)
            return
        SessionDetailView(self._detail_body, self.manager, session, self.refresh).pack(
            fill="both", expand=True
        )


class SessionListItem(tk.Frame):
    def __init__(self, parent, session: dict, selected: bool, on_select):
        bg = ACCENT_LIGHT if selected else ENTRY_BG
        super().__init__(parent, bg=bg, cursor="hand2")
        self._session = session
        self._on_select = on_select
        inner = tk.Frame(self, bg=bg)
        inner.pack(fill="x", padx=10, pady=10)
        top = tk.Frame(inner, bg=bg)
        top.pack(fill="x")
        tk.Label(
            top,
            text=session["procedure_type"],
            bg=bg,
            fg=TEXT,
            font=("Segoe UI", 10, "bold"),
        ).pack(side="left")
        status_color = STATUS_COLORS.get(session["status"], MUTED)
        tk.Label(top, text=session["status"], bg=bg, fg=status_color, font=FONT_XS).pack(side="right")
        tk.Label(
            inner,
            text=format_session_time(session["started_at"]),
            bg=bg,
            fg=MUTED,
            font=FONT_XS,
        ).pack(anchor="w", pady=(4, 0))
        tk.Label(
            inner,
            text=format_duration(session.get("duration_seconds", 0)),
            bg=bg,
            fg=MUTED,
            font=FONT_XS,
        ).pack(anchor="w")
        for w in (self, inner, top):
            w.bind("<Button-1>", self._click)

    def _click(self, _event=None):
        self._on_select(self._session["id"])


class SessionDetailView(tk.Frame):
    def __init__(self, parent, manager: "ClinicalManager", session: dict, on_change: Callable):
        super().__init__(parent, bg=SURFACE)
        self.manager = manager
        self.session = session
        self.on_change = on_change

        header = tk.Frame(self, bg=SURFACE)
        header.pack(fill="x", pady=(0, 12))
        tk.Label(
            header,
            text=f"{session['procedure_type']} — {session['status']}",
            bg=SURFACE,
            fg=TEXT,
            font=FONT_CARD,
        ).pack(side="left")
        actions = tk.Frame(header, bg=SURFACE)
        actions.pack(side="right")
        if session.get("pdf_path") and os.path.exists(session.get("pdf_path", "")):
            tk.Button(
                actions,
                text="Open PDF",
                command=self._open_pdf,
                relief="flat",
                bg=ACCENT_LIGHT,
                fg=ACCENT,
                cursor="hand2",
            ).pack(side="left", padx=4)
        if session["status"] in ("Needs Review", "Ready for Dentrix"):
            tk.Button(
                actions,
                text="Mark Entered in Dentrix",
                command=self._mark_entered,
                relief="flat",
                bg=SUCCESS,
                fg="white",
                cursor="hand2",
            ).pack(side="left", padx=4)
        tk.Button(
            actions,
            text="Delete",
            command=self._delete,
            relief="flat",
            bg=ENTRY_BG,
            fg=RED_TEXT,
            cursor="hand2",
        ).pack(side="left", padx=4)

        meta = tk.Label(
            self,
            text=f"Started {format_session_time(session['started_at'])} · "
            f"Duration {format_duration(session.get('duration_seconds', 0))}",
            bg=SURFACE,
            fg=MUTED,
            font=FONT_SM,
        )
        meta.pack(anchor="w", pady=(0, 8))
        if session.get("error_message"):
            tk.Label(
                self,
                text=session["error_message"],
                bg=SURFACE,
                fg=RED_TEXT,
                font=FONT_SM,
                wraplength=560,
                justify="left",
            ).pack(anchor="w", pady=(0, 8))

        canvas = tk.Canvas(self, bg=SURFACE, highlightthickness=0)
        sb = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        content = tk.Frame(canvas, bg=SURFACE)
        content.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        win_id = canvas.create_window((0, 0), window=content, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win_id, width=e.width))
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        sheet = self.manager.read_answer_sheet(session)
        if sheet:
            self._render_answer_sheet(content, sheet)
        else:
            transcript = self.manager.read_transcript(session)
            if transcript:
                tk.Label(content, text="Transcript", bg=SURFACE, fg=TEXT, font=FONT_CARD).pack(
                    anchor="w", pady=(0, 8)
                )
                tk.Label(
                    content,
                    text=transcript,
                    bg=ENTRY_BG,
                    fg=TEXT,
                    font=FONT,
                    wraplength=520,
                    justify="left",
                    padx=12,
                    pady=12,
                ).pack(fill="x")
                tk.Button(
                    content,
                    text="Copy Transcript",
                    command=lambda: pyperclip.copy(transcript),
                    relief="flat",
                    bg=ACCENT_LIGHT,
                    fg=ACCENT,
                    cursor="hand2",
                ).pack(anchor="w", pady=8)
            elif session["status"] == "Processing":
                tk.Label(content, text="Processing…", bg=SURFACE, fg=MUTED, font=FONT_MD).pack(pady=40)
            elif session["status"] == "Recording":
                tk.Label(content, text="Recording in progress…", bg=SURFACE, fg=RED_TEXT, font=FONT_MD).pack(
                    pady=40
                )

    def _render_answer_sheet(self, parent, sheet: dict):
        d = sheet.get("detected_details", {})
        tk.Label(parent, text="Detected Details", bg=SURFACE, fg=TEXT, font=FONT_CARD).pack(
            anchor="w", pady=(0, 8)
        )
        for label, key in (
            ("Provider", "provider"),
            ("Assistant", "assistant"),
            ("Operatory", "operatory"),
            ("Tooth/Teeth", "tooth_number"),
        ):
            tk.Label(
                parent,
                text=f"{label}: {d.get(key, '')}",
                bg=SURFACE,
                fg=MUTED,
                font=FONT_SM,
                wraplength=520,
                justify="left",
            ).pack(anchor="w")

        tk.Label(parent, text="Template Answers", bg=SURFACE, fg=TEXT, font=FONT_CARD).pack(
            anchor="w", pady=(16, 8)
        )
        for field in sheet.get("template_answers", []):
            card = tk.Frame(parent, bg=ENTRY_BG, highlightbackground=BORDER, highlightthickness=1)
            card.pack(fill="x", pady=(0, 8))
            inner = tk.Frame(card, bg=ENTRY_BG)
            inner.pack(fill="x", padx=12, pady=10)
            row = tk.Frame(inner, bg=ENTRY_BG)
            row.pack(fill="x")
            tk.Label(row, text=field.get("label", ""), bg=ENTRY_BG, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(
                side="left"
            )
            tk.Button(
                row,
                text="Copy",
                command=lambda f=field: pyperclip.copy(f.get("suggested_answer", "")),
                relief="flat",
                bg=ENTRY_BG,
                fg=ACCENT,
                cursor="hand2",
                font=FONT_XS,
            ).pack(side="right")
            tk.Label(
                inner,
                text=f"Answer: {field.get('suggested_answer', '')}",
                bg=ENTRY_BG,
                fg=TEXT,
                font=FONT_SM,
                wraplength=500,
                justify="left",
            ).pack(anchor="w", pady=(6, 2))
            tk.Label(
                inner,
                text=f"Evidence: {field.get('evidence', '')}",
                bg=ENTRY_BG,
                fg=MUTED,
                font=FONT_XS,
                wraplength=500,
                justify="left",
            ).pack(anchor="w")
            tk.Label(
                inner,
                text=f"Confidence: {field.get('confidence', '')}",
                bg=ENTRY_BG,
                fg=MUTED,
                font=FONT_XS,
            ).pack(anchor="w", pady=(2, 0))

        if sheet.get("warnings"):
            tk.Label(parent, text="Warnings", bg=SURFACE, fg=RED_TEXT, font=FONT_CARD).pack(
                anchor="w", pady=(12, 6)
            )
            for w in sheet["warnings"]:
                tk.Label(
                    parent,
                    text=f"• [{w.get('type', '')}] {w.get('message', '')}",
                    bg=SURFACE,
                    fg=RED_TEXT,
                    font=FONT_XS,
                    wraplength=520,
                    justify="left",
                ).pack(anchor="w")

        all_answers = "\n".join(
            f"{f.get('label')}: {f.get('suggested_answer')}" for f in sheet.get("template_answers", [])
        )
        tk.Button(
            parent,
            text="Copy All Answers",
            command=lambda: pyperclip.copy(all_answers),
            relief="flat",
            bg=ACCENT,
            fg="white",
            cursor="hand2",
            padx=12,
            pady=8,
        ).pack(anchor="w", pady=(12, 0))

    def _open_pdf(self):
        path = self.manager.export_pdf(self.session["id"])
        if path and path.exists():
            os.startfile(str(path))
        else:
            messagebox.showerror("PDF", "Could not open PDF.")

    def _mark_entered(self):
        self.manager.mark_entered(self.session["id"])
        self.on_change()

    def _delete(self):
        if messagebox.askyesno("Delete Session", "Delete this session and all files?"):
            self.manager.delete_session(self.session["id"])
            self.on_change()
