"""Dictate UI — Flowstep-inspired dashboard."""

from __future__ import annotations

import os
import tkinter as tk
from datetime import date, datetime, timedelta
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING, Callable

import pyperclip
from PIL import Image, ImageTk

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
RED_LIGHT = "#FEF2F2"
RED_BORDER = "#FECACA"
SUCCESS = "#16A34A"
WARNING = "#D97706"
STATUS_BG = "#1C1C1E"
STATUS_FG = "#FFFFFF"
FOOTER_BG = "#F4F4F5"

FONT = ("Segoe UI", 10)
FONT_SM = ("Segoe UI", 9)
FONT_XS = ("Segoe UI", 8)
FONT_MD = ("Segoe UI", 11)
FONT_TITLE = ("Segoe UI", 20, "bold")
FONT_STAT = ("Segoe UI", 22, "bold")
FONT_CARD = ("Segoe UI", 12, "bold")


class AppAssets:
    def __init__(self):
        self._pil_cache: dict[str, Image.Image] = {}
        self._photo_cache: dict[str, ImageTk.PhotoImage] = {}
        self._master: tk.Misc | None = None

    def bind(self, master: tk.Misc) -> None:
        self._master = master
        self._photo_cache.clear()

    def get(self, name: str) -> ImageTk.PhotoImage:
        if self._master is None:
            raise RuntimeError("Call ASSETS.bind(root) first.")
        if name not in self._photo_cache:
            self._photo_cache[name] = ImageTk.PhotoImage(
                self._get_pil(name), master=self._master
            )
        return self._photo_cache[name]

    def pil_logo(self, size: int) -> Image.Image:
        return render_logo(size)

    def _get_pil(self, name: str) -> Image.Image:
        if name not in self._pil_cache:
            builders = {
                "logo_48": lambda: render_logo(48),
                "logo_40": lambda: render_logo(40),
                "settings": lambda: render_lucide("settings", 20, MUTED),
                "settings_hover": lambda: render_lucide("settings", 20, TEXT),
                "copy": lambda: render_lucide("copy", 14, MUTED),
                "trash": lambda: render_lucide("trash-2", 14, MUTED),
                "doc": lambda: render_lucide("file-text", 20, MUTED),
                "clock": lambda: render_lucide("clock", 16, ACCENT),
                "type": lambda: render_lucide("type", 16, ACCENT),
                "mic": lambda: render_lucide("mic", 16, ACCENT),
                "gauge": lambda: render_lucide("gauge", 16, ACCENT),
                "shield": lambda: render_lucide("shield-check", 20, ACCENT),
                "wifi": lambda: render_lucide("wifi", 16, ACCENT),
                "cpu": lambda: render_lucide("cpu", 14, MUTED),
                "hard-drive": lambda: render_lucide("hard-drive", 14, MUTED),
                "keyboard": lambda: render_lucide("keyboard", 14, MUTED),
                "square_red": lambda: _filled_square(14, RED_TEXT),
                "mic_lg": lambda: render_lucide("mic", 28, "#FFFFFF"),
                "mic_idle": lambda: render_lucide("mic", 28, ACCENT),
            }
            self._pil_cache[name] = builders[name]()
        return self._pil_cache[name]


ASSETS = AppAssets()


def _filled_square(size: int, color: str) -> Image.Image:
    from PIL import ImageDraw

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = max(2, size // 5)
    rgb = tuple(int(color.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)) + (255,)
    draw.rounded_rectangle((pad, pad, size - pad, size - pad), radius=max(2, size // 8), fill=rgb)
    return img


def setup_ttk_styles(master: tk.Misc) -> None:
    try:
        ttk.Style(master).theme_use("vista")
    except tk.TclError:
        pass


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


class IconButton(tk.Label):
    def __init__(self, parent, image, command, hover_image=None, bg=SURFACE):
        super().__init__(parent, image=image, bg=bg, cursor="hand2", padx=8, pady=6)
        self._cmd = command
        self._img = image
        self._hover = hover_image or image
        self._bg = bg
        self.bind("<Button-1>", lambda _e: command())
        self.bind("<Enter>", lambda _e: self.configure(image=self._hover))
        self.bind("<Leave>", lambda _e: self.configure(image=self._img))


class BorderedCard(tk.Frame):
    def __init__(self, parent, card_bg=SURFACE):
        super().__init__(parent, bg=BORDER, padx=1, pady=1)
        self.body = tk.Frame(self, bg=card_bg)
        self.body.pack(fill="both", expand=True)


class TranscriptRow(tk.Frame):
    def __init__(self, parent, entry: dict, on_copy, on_delete):
        super().__init__(parent, bg=ENTRY_BG, highlightbackground=BORDER, highlightthickness=1)
        inner = tk.Frame(self, bg=ENTRY_BG)
        inner.pack(fill="x", padx=14, pady=12)
        top = tk.Frame(inner, bg=ENTRY_BG)
        top.pack(fill="x")
        tk.Label(top, text=format_entry_timestamp(entry["timestamp"]), bg=ENTRY_BG, fg=MUTED, font=("Segoe UI", 9, "bold")).pack(side="left")
        actions = tk.Frame(top, bg=ENTRY_BG)
        actions.pack(side="right")
        IconButton(actions, ASSETS.get("copy"), lambda: on_copy(entry["text"]), bg=ENTRY_BG).pack(side="left")
        IconButton(actions, ASSETS.get("trash"), lambda: on_delete(entry["id"]), bg=ENTRY_BG).pack(side="left", padx=(2, 0))
        tk.Label(inner, text=entry["text"], bg=ENTRY_BG, fg=TEXT, font=FONT, wraplength=480, justify="left", anchor="w").pack(fill="x", pady=(8, 0))


class SettingsPage(tk.Frame):
    def __init__(self, parent, app: "DictationApp", on_back: Callable[[], None], save_config_fn):
        super().__init__(parent, bg=BG)
        self.app = app
        self._on_back = on_back
        self._save_config_fn = save_config_fn
        outer = tk.Frame(self, bg=BG)
        outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        scroll = tk.Frame(canvas, bg=BG)
        scroll.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        win = canvas.create_window((0, 0), window=scroll, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win, width=e.width))
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        top = tk.Frame(scroll, bg=BG)
        top.pack(fill="x", pady=(0, 20))
        tk.Button(top, text="← Back", command=on_back, relief="flat", bg=BG, fg=MUTED, font=FONT, cursor="hand2").pack(side="left")
        tk.Label(top, text="Settings", bg=BG, fg=TEXT, font=FONT_TITLE).pack(side="left", padx=(12, 0))

        card = BorderedCard(scroll)
        card.pack(fill="x")
        body = card.body
        body.configure(padx=24, pady=24)

        tk.Label(body, text="Quick Dictate", bg=SURFACE, fg=TEXT, font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 8))
        tk.Label(body, text="Hotkey", bg=SURFACE, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.hotkey_var = tk.StringVar(value=app.config["hotkey"])
        tk.Entry(body, textvariable=self.hotkey_var, font=FONT_MD, relief="flat", bg=ENTRY_BG).pack(fill="x", ipady=8, pady=(8, 16))
        tk.Label(body, text="Whisper model size", bg=SURFACE, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.model_var = tk.StringVar(value=app.config["model_size"])
        ttk.Combobox(body, textvariable=self.model_var, values=["tiny", "base", "small", "medium"], state="readonly").pack(fill="x", pady=(8, 16))
        self.restore_var = tk.BooleanVar(value=app.config.get("restore_clipboard_after_paste", False))
        tk.Checkbutton(body, text="Restore clipboard after paste", variable=self.restore_var, bg=SURFACE, fg=TEXT, font=FONT).pack(anchor="w", pady=(0, 8))
        self.cleanup_var = tk.BooleanVar(value=app.config.get("dictation_cleanup", True))
        tk.Checkbutton(
            body,
            text="Clean up dictation (remove fillers, add punctuation)",
            variable=self.cleanup_var,
            bg=SURFACE,
            fg=TEXT,
            font=FONT,
        ).pack(anchor="w", pady=(0, 8))
        self.vocabulary_var = tk.BooleanVar(value=app.config.get("vocabulary_correction", True))
        tk.Checkbutton(
            body,
            text="Use custom vocabulary (company names, file types, software)",
            variable=self.vocabulary_var,
            bg=SURFACE,
            fg=TEXT,
            font=FONT,
        ).pack(anchor="w", pady=(0, 8))
        tk.Button(
            body,
            text="Edit vocabulary.json",
            command=self._open_vocabulary,
            font=FONT,
            relief="flat",
            bg=ENTRY_BG,
            fg=TEXT,
            padx=12,
            pady=6,
            cursor="hand2",
        ).pack(anchor="w", pady=(0, 20))

        tk.Label(body, text="Clinical Session", bg=SURFACE, fg=TEXT, font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 8))
        tk.Label(body, text="Clinical stop hotkey", bg=SURFACE, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.clinical_hotkey_var = tk.StringVar(value=app.config.get("clinical_hotkey", "<ctrl>+<alt>+r"))
        tk.Entry(body, textvariable=self.clinical_hotkey_var, font=FONT_MD, relief="flat", bg=ENTRY_BG).pack(fill="x", ipady=8, pady=(8, 16))
        tk.Label(body, text="OpenAI API key (clinical only)", bg=SURFACE, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.openai_key_var = tk.StringVar(value=app.clinical.get_openai_api_key())
        tk.Entry(body, textvariable=self.openai_key_var, font=FONT_MD, relief="flat", bg=ENTRY_BG, show="•").pack(fill="x", ipady=8, pady=(8, 16))
        tk.Label(body, text="OpenAI model", bg=SURFACE, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.openai_model_var = tk.StringVar(value=app.config.get("openai_model", "gpt-4o-mini"))
        ttk.Combobox(body, textvariable=self.openai_model_var, values=["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1"], state="readonly").pack(fill="x", pady=(8, 16))
        tk.Label(body, text="Max recording duration (hours)", bg=SURFACE, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.max_hours_var = tk.StringVar(value=str(app.config.get("clinical_max_duration_hours", 2)))
        ttk.Combobox(body, textvariable=self.max_hours_var, values=["1", "2", "3", "4"], state="readonly").pack(fill="x", pady=(8, 16))
        tk.Label(body, text="Session retention", bg=SURFACE, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.retention_var = tk.StringVar(value=str(app.config.get("clinical_retention_days", "7")))
        ttk.Combobox(body, textvariable=self.retention_var, values=["1", "7", "30", "manual"], state="readonly").pack(fill="x", pady=(8, 0))

        tk.Button(scroll, text="Save changes", command=self._save, font=("Segoe UI", 10, "bold"), relief="flat", bg=ACCENT, fg="white", padx=18, pady=10, cursor="hand2").pack(anchor="w", pady=(20, 0))

    def reload(self):
        self.hotkey_var.set(self.app.config["hotkey"])
        self.model_var.set(self.app.config["model_size"])
        self.restore_var.set(self.app.config.get("restore_clipboard_after_paste", False))
        self.cleanup_var.set(self.app.config.get("dictation_cleanup", True))
        self.vocabulary_var.set(self.app.config.get("vocabulary_correction", True))
        self.clinical_hotkey_var.set(self.app.config.get("clinical_hotkey", "<ctrl>+<alt>+r"))
        self.openai_key_var.set(self.app.clinical.get_openai_api_key())
        self.openai_model_var.set(self.app.config.get("openai_model", "gpt-4o-mini"))
        self.max_hours_var.set(str(self.app.config.get("clinical_max_duration_hours", 2)))
        self.retention_var.set(str(self.app.config.get("clinical_retention_days", "7")))

    def _save(self):
        hotkey = self.hotkey_var.get().strip()
        if not hotkey:
            messagebox.showerror("Settings", "Hotkey cannot be empty.")
            return
        clinical_hotkey = self.clinical_hotkey_var.get().strip()
        if not clinical_hotkey:
            messagebox.showerror("Settings", "Clinical hotkey cannot be empty.")
            return
        config = self.app.config.copy()
        config["hotkey"] = hotkey
        config["clinical_hotkey"] = clinical_hotkey
        config["model_size"] = self.model_var.get()
        config["restore_clipboard_after_paste"] = self.restore_var.get()
        config["dictation_cleanup"] = self.cleanup_var.get()
        config["vocabulary_correction"] = self.vocabulary_var.get()
        config["openai_model"] = self.openai_model_var.get()
        try:
            config["clinical_max_duration_hours"] = int(self.max_hours_var.get())
        except ValueError:
            config["clinical_max_duration_hours"] = 2
        config["clinical_retention_days"] = self.retention_var.get()
        self._save_config_fn(config)
        self.app.clinical.set_openai_api_key(self.openai_key_var.get().strip())
        self.app.apply_settings(config)
        self._on_back()

    def _open_vocabulary(self):
        path = self.app.vocabulary.path
        try:
            os.startfile(path)
            self.app.vocabulary.reload()
        except OSError as exc:
            messagebox.showerror("Settings", f"Could not open vocabulary file:\n{exc}")


class StatusOverlay:

    PERSISTENT_STATES = frozenset({"loading", "recording", "working"})

    def __init__(self, parent: tk.Tk):
        self.root = tk.Toplevel(parent)
        self.root.transient(parent)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        try:
            self.root.attributes("-toolwindow", True)
        except tk.TclError:
            pass
        self.root.configure(bg=STATUS_BG)
        row = tk.Frame(self.root, bg=STATUS_BG)
        row.pack(padx=16, pady=12)
        self._dot = tk.Canvas(row, width=10, height=10, bg=STATUS_BG, highlightthickness=0)
        self._dot_id = self._dot.create_oval(1, 1, 9, 9, fill=ACCENT, outline="")
        self._dot.pack(side="left", padx=(0, 10))
        self._label = tk.Label(row, text="", bg=STATUS_BG, fg=STATUS_FG, font=("Segoe UI", 10))
        self._label.pack(side="left")
        self._hide_job = None
        self._current_state = "idle"
        self.root.withdraw()

    def hide(self):
        def _hide():
            if self._hide_job:
                self.root.after_cancel(self._hide_job)
                self._hide_job = None
            self.root.withdraw()

        self.root.after(0, _hide)

    def update_status(self, message: str, auto_hide_ms: int | None = None, state: str = "idle"):
        colors = {
            "idle": ACCENT,
            "recording": RED,
            "working": WARNING,
            "success": SUCCESS,
            "error": RED,
            "loading": WARNING,
        }

        def _apply():
            self._current_state = state
            self._dot.itemconfig(self._dot_id, fill=colors.get(state, ACCENT))
            self._label.config(text=message)
            sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
            self.root.update_idletasks()
            w = max(self.root.winfo_reqwidth(), 280)
            h = self.root.winfo_reqheight()
            self.root.geometry(f"{w}x{h}+{sw - w - 24}+{sh - h - 72}")
            self.root.deiconify()
            self.root.lift()
            if self._hide_job:
                self.root.after_cancel(self._hide_job)
                self._hide_job = None
            if auto_hide_ms and state not in self.PERSISTENT_STATES:
                self._hide_job = self.root.after(auto_hide_ms, self.root.withdraw)

        self.root.after(0, _apply)


class DashboardWindow:
    def __init__(self, app: "DictationApp"):
        self.app = app
        self._state = "loading"
        self._mode = "quick"
        self._view = "home"
        self.is_hidden = False
        self._left_col = None

        self.root = tk.Tk()
        self.root._dictate_app = app  # type: ignore[attr-defined]
        ASSETS.bind(self.root)
        setup_ttk_styles(self.root)
        self.root.title("Dictate")
        self.root.configure(bg=BG)
        self.root.minsize(1000, 700)
        self.root.geometry("1140x780")
        try:
            self.root.iconphoto(True, ASSETS.get("logo_48"))
        except tk.TclError:
            pass
        self._build_shell()
        self.refresh()
        self.set_app_state("loading")
        self.root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)

    def _build_shell(self):
        pad = tk.Frame(self.root, bg=BG)
        pad.pack(fill="both", expand=True, padx=32, pady=28)

        header = tk.Frame(pad, bg=BG)
        header.pack(fill="x", pady=(0, 24))
        brand = tk.Frame(header, bg=BG)
        brand.pack(side="left")
        tk.Label(brand, image=ASSETS.get("logo_48"), bg=BG).pack(side="left")
        titles = tk.Frame(brand, bg=BG)
        titles.pack(side="left", padx=(16, 0))
        tk.Label(titles, text="Dictate", bg=BG, fg=TEXT, font=FONT_TITLE).pack(anchor="w")
        self._subtitle = tk.Label(titles, text="Local voice typing assistant", bg=BG, fg=MUTED, font=FONT_SM)
        self._subtitle.pack(anchor="w")

        actions = tk.Frame(header, bg=BG)
        actions.pack(side="right")
        self._hotkey_pill = tk.Frame(actions, bg=ACCENT_LIGHT, highlightbackground=BORDER, highlightthickness=1)
        self._hotkey_pill.pack(side="left", padx=(0, 16))
        pill_inner = tk.Frame(self._hotkey_pill, bg=ACCENT_LIGHT)
        pill_inner.pack(padx=16, pady=8)
        self._hotkey_pill_inner = pill_inner
        self._hotkey_square = tk.Label(pill_inner, bg=ACCENT_LIGHT)
        self._hotkey_pill_label = tk.Label(
            pill_inner, text="", bg=ACCENT_LIGHT, fg=ACCENT, font=("Segoe UI", 10, "bold"),
        )
        settings_wrap = tk.Frame(actions, bg=BORDER, padx=1, pady=1)
        settings_wrap.pack(side="left")
        self._settings_btn = IconButton(
            settings_wrap, ASSETS.get("settings"), self._open_settings, ASSETS.get("settings_hover"), bg=SURFACE,
        )
        self._settings_btn.configure(padx=10, pady=10)
        self._settings_btn.pack()

        main_row = tk.Frame(pad, bg=BG)
        main_row.pack(fill="both", expand=True)
        main_row.columnconfigure(1, weight=1)
        main_row.rowconfigure(0, weight=1)

        sidebar = tk.Frame(main_row, bg=BG, width=200)
        sidebar.grid(row=0, column=0, sticky="ns", padx=(0, 20))
        sidebar.grid_propagate(False)
        tk.Label(sidebar, text="Modes", bg=BG, fg=MUTED, font=FONT_XS).pack(anchor="w", pady=(0, 8))
        self._nav_quick = self._nav_button(sidebar, "Quick Dictate", lambda: self._set_mode("quick"))
        self._nav_clinical = self._nav_button(sidebar, "Clinical Session", lambda: self._set_mode("clinical"))
        self._nav_quick.pack(fill="x", pady=(0, 8))
        self._nav_clinical.pack(fill="x")

        self._content = tk.Frame(main_row, bg=BG)
        self._content.grid(row=0, column=1, sticky="nsew")
        self._home_view = tk.Frame(self._content, bg=BG)
        self._home_view.pack(fill="both", expand=True)
        self._build_home()
        from clinical_ui import ClinicalPage  # noqa: PLC0415
        from main import CONFIG_PATH, save_config  # noqa: PLC0415

        self._clinical_view = ClinicalPage(
            self._content,
            self.app.clinical,
            on_notify=lambda msg, state="idle", ms=None: self.app._notify(msg, state, ms),
        )
        self._settings_view = SettingsPage(
            self._content,
            self.app,
            self._show_current_mode,
            lambda config: save_config(CONFIG_PATH, config),
        )

        self._footer = tk.Frame(pad, bg=FOOTER_BG, highlightbackground=BORDER, highlightthickness=1)
        self._footer.pack(fill="x", pady=(20, 0))
        foot_in = tk.Frame(self._footer, bg=FOOTER_BG)
        foot_in.pack(fill="x", padx=16, pady=12)
        left = tk.Frame(foot_in, bg=FOOTER_BG)
        left.pack(side="left")
        self._foot_dot = tk.Canvas(left, width=10, height=10, bg=FOOTER_BG, highlightthickness=0)
        self._foot_dot_id = self._foot_dot.create_oval(1, 1, 9, 9, fill=WARNING, outline="")
        self._foot_dot.pack(side="left", padx=(0, 8))
        self._foot_status = tk.Label(left, text="Loading…", bg=FOOTER_BG, fg=TEXT, font=("Segoe UI", 10, "bold"))
        self._foot_status.pack(side="left")
        self._foot_meta = tk.Frame(foot_in, bg=FOOTER_BG)
        self._foot_meta.pack(side="right")
        self._foot_model = tk.Label(self._foot_meta, text="", bg=FOOTER_BG, fg=MUTED, font=FONT_XS)
        self._foot_offline = tk.Label(self._foot_meta, text="", bg=FOOTER_BG, fg=MUTED, font=FONT_XS)
        self._foot_hotkey = tk.Label(self._foot_meta, text="", bg=FOOTER_BG, fg=MUTED, font=FONT_XS)
        self._foot_model.pack(side="left")
        self._foot_offline.pack(side="left", padx=(16, 0))
        self._foot_hotkey.pack(side="left", padx=(16, 0))
        self._set_mode("quick")

    def _nav_button(self, parent, text: str, command):
        btn = tk.Label(
            parent,
            text=text,
            bg=ENTRY_BG,
            fg=TEXT,
            font=("Segoe UI", 10, "bold"),
            padx=14,
            pady=12,
            cursor="hand2",
        )
        btn.bind("<Button-1>", lambda _e: command())
        return btn

    def _style_nav(self):
        active, idle = ACCENT_LIGHT, ENTRY_BG
        fg_active, fg_idle = ACCENT, TEXT
        if self._mode == "quick":
            self._nav_quick.configure(bg=active, fg=fg_active)
            self._nav_clinical.configure(bg=idle, fg=fg_idle)
        else:
            self._nav_clinical.configure(bg=active, fg=fg_active)
            self._nav_quick.configure(bg=idle, fg=fg_idle)

    def _set_mode(self, mode: str):
        self._mode = mode
        self._settings_view.pack_forget()
        self._home_view.pack_forget()
        self._clinical_view.pack_forget()
        self._settings_btn.pack(side="left")
        if mode == "quick":
            self._home_view.pack(fill="both", expand=True)
            self._subtitle.config(text="Local voice typing assistant")
            self._hotkey_pill.pack(side="left", padx=(0, 16))
            self.refresh()
        else:
            self._clinical_view.pack(fill="both", expand=True)
            self._subtitle.config(text="Clinical appointment recording & answer sheets")
            self._hotkey_pill.pack_forget()
            self.refresh_clinical()
        self._style_nav()
        self._update_footer_meta()

    def refresh_clinical(self):
        if hasattr(self, "_clinical_view"):
            self._clinical_view.refresh()
        if self.app.clinical.is_recording():
            elapsed = int(self.app.clinical.recording_elapsed())
            self.update_clinical_recording_timer(elapsed)
        elif self._mode == "clinical":
            self._foot_status.config(text="Clinical Session", fg=TEXT)
            self._foot_dot.itemconfig(self._foot_dot_id, fill=SUCCESS)

    def update_clinical_recording_timer(self, elapsed: int):
        h = elapsed // 3600
        m = (elapsed % 3600) // 60
        s = elapsed % 60
        timer = f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
        self._foot_status.config(text=f"Clinical recording {timer}", fg=RED_TEXT)
        self._foot_dot.itemconfig(self._foot_dot_id, fill=RED)

    def _show_current_mode(self):
        self._set_mode(self._mode)

    def _build_home(self):
        body = tk.Frame(self._home_view, bg=BG)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=0, minsize=320)
        body.rowconfigure(0, weight=1)

        self._left_col = tk.Frame(body, bg=BG)
        self._left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 24))

        self._record_banner = tk.Frame(self._left_col, bg=RECORD_BG)
        inner = tk.Frame(self._record_banner, bg=RECORD_BG)
        inner.pack(fill="x", padx=20, pady=14)
        tk.Frame(self._record_banner, bg=RED, width=4).place(relx=0, rely=0, relheight=1)
        row = tk.Frame(inner, bg=RECORD_BG)
        row.pack(fill="x")
        self._rec_dot = tk.Canvas(row, width=20, height=20, bg=RECORD_BG, highlightthickness=0)
        self._rec_dot.create_oval(2, 2, 18, 18, fill=RED, outline="")
        self._rec_dot.pack(side="left", padx=(0, 12))
        tf = tk.Frame(row, bg=RECORD_BG)
        tf.pack(side="left", fill="x", expand=True)
        tk.Label(tf, text="Recording…", bg=RECORD_BG, fg=TEXT, font=("Segoe UI", 11, "bold")).pack(anchor="w")
        tk.Label(tf, text="Press your hotkey again to stop.", bg=RECORD_BG, fg=MUTED, font=FONT_SM).pack(anchor="w")
        self._wave = tk.Canvas(row, width=72, height=40, bg=RECORD_BG, highlightthickness=0)
        self._wave.pack(side="right")
        x = 4
        for h in (16, 32, 20, 40, 24, 36, 12, 28, 20):
            self._wave.create_rectangle(x, 40 - h, x + 4, 40, fill="#FCA5A5", outline="")
            x += 8

        tcard = BorderedCard(self._left_col)
        self._tcard = tcard
        tcard.pack(fill="both", expand=True, pady=(16, 0))
        tbody = tcard.body
        thead = tk.Frame(tbody, bg=SURFACE)
        thead.pack(fill="x", padx=20, pady=(20, 12))
        tk.Label(thead, image=ASSETS.get("doc"), bg=SURFACE).pack(side="left")
        tk.Label(thead, text="Transcriptions", bg=SURFACE, fg=TEXT, font=FONT_CARD).pack(side="left", padx=(8, 0))
        self._count_badge = tk.Label(thead, text="0 items", bg=ENTRY_BG, fg=TEXT, font=("Segoe UI", 9, "bold"), padx=10, pady=4)
        self._count_badge.pack(side="right")
        list_wrap = tk.Frame(tbody, bg=SURFACE)
        list_wrap.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        self._canvas = tk.Canvas(list_wrap, bg=SURFACE, highlightthickness=0)
        sb = ttk.Scrollbar(list_wrap, orient="vertical", command=self._canvas.yview)
        self._feed = tk.Frame(self._canvas, bg=SURFACE)
        self._feed.bind("<Configure>", lambda _e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._win_id = self._canvas.create_window((0, 0), window=self._feed, anchor="nw")
        self._canvas.configure(yscrollcommand=sb.set)
        self._canvas.bind("<Configure>", lambda e: self._canvas.itemconfig(self._win_id, width=e.width))
        self._canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._canvas.bind_all("<MouseWheel>", lambda e: self._canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        right = tk.Frame(body, bg=BG)
        right.grid(row=0, column=1, sticky="nsew")
        grid = tk.Frame(right, bg=BG)
        grid.pack(fill="x")
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        self._stat_widgets = {}
        specs = [("time", "clock", "Total Time"), ("words", "type", "Words"), ("sessions", "mic", "Sessions"), ("wpm", "gauge", "Avg WPM")]
        for i, (key, icon, label) in enumerate(specs):
            card = BorderedCard(grid)
            card.grid(row=i // 2, column=i % 2, sticky="nsew", padx=(0, 6) if i % 2 == 0 else (6, 0), pady=(0, 12))
            cbody = card.body
            cbody.configure(padx=14, pady=14)
            r = tk.Frame(cbody, bg=SURFACE)
            r.pack(fill="x")
            tk.Label(r, image=ASSETS.get(icon), bg=SURFACE).pack(side="left")
            tk.Label(r, text=label, bg=SURFACE, fg=MUTED, font=FONT_XS).pack(side="left", padx=(6, 0))
            val = tk.Label(cbody, text="0", bg=SURFACE, fg=TEXT, font=FONT_STAT)
            val.pack(anchor="w", pady=(10, 0))
            self._stat_widgets[key] = val

        local = BorderedCard(right)
        local.pack(fill="x", pady=(4, 12))
        lb = local.body
        lb.configure(padx=20, pady=20)
        lh = tk.Frame(lb, bg=SURFACE)
        lh.pack(fill="x")
        sbx = tk.Frame(lh, bg=ACCENT_LIGHT, width=40, height=40)
        sbx.pack(side="left")
        sbx.pack_propagate(False)
        tk.Label(sbx, image=ASSETS.get("shield"), bg=ACCENT_LIGHT).pack(expand=True)
        lt = tk.Frame(lh, bg=SURFACE)
        lt.pack(side="left", padx=(12, 0))
        tk.Label(lt, text="Local Mode", bg=SURFACE, fg=TEXT, font=("Segoe UI", 11, "bold")).pack(anchor="w")
        tk.Label(lt, text="On-device processing", bg=SURFACE, fg=MUTED, font=FONT_XS).pack(anchor="w")
        tk.Label(lb, text="All transcription happens on your machine. No audio ever leaves your device.", bg=SURFACE, fg=MUTED, font=FONT_SM, wraplength=260, justify="left").pack(anchor="w", pady=(14, 12))
        pill = tk.Frame(lb, bg=ACCENT_LIGHT)
        pill.pack(anchor="w")
        tk.Label(pill, image=ASSETS.get("wifi"), bg=ACCENT_LIGHT).pack(side="left", padx=(10, 4), pady=8)
        tk.Label(pill, text="No internet required", bg=ACCENT_LIGHT, fg=ACCENT, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 12), pady=8)

        listen = BorderedCard(right)
        listen.pack(fill="both", expand=True)
        l2 = listen.body
        l2.configure(padx=20, pady=28)
        self._mic_circle = tk.Canvas(l2, width=64, height=64, bg=SURFACE, highlightthickness=0)
        self._mic_circle.pack()
        self._mic_img_id = self._mic_circle.create_image(32, 32, image=ASSETS.get("mic_idle"))
        self._listen_title = tk.Label(l2, text="Ready", bg=SURFACE, fg=TEXT, font=("Segoe UI", 11, "bold"))
        self._listen_title.pack(pady=(16, 4))
        self._listen_sub = tk.Label(l2, text="Press your hotkey to start dictating.", bg=SURFACE, fg=MUTED, font=FONT_XS, wraplength=240, justify="center")
        self._listen_sub.pack()

    def _update_hotkey_pill(self):
        hk = format_hotkey_display(self.app.config["hotkey"])
        if self._state == "recording":
            self._hotkey_pill.configure(bg=RED_LIGHT, highlightbackground=RED_BORDER)
            pill_bg = RED_LIGHT
            self._hotkey_pill_inner.configure(bg=pill_bg)
            self._hotkey_square.configure(image=ASSETS.get("square_red"), bg=pill_bg)
            self._hotkey_square.pack(side="left", padx=(0, 8))
            self._hotkey_pill_label.configure(bg=pill_bg, fg=RED_TEXT, text=f"Press {hk} to Stop")
            self._hotkey_pill_label.pack(side="left")
        else:
            self._hotkey_pill.configure(bg=ACCENT_LIGHT, highlightbackground=BORDER)
            pill_bg = ACCENT_LIGHT
            self._hotkey_pill_inner.configure(bg=pill_bg)
            self._hotkey_square.pack_forget()
            self._hotkey_pill_label.configure(bg=pill_bg, fg=ACCENT, text=f"Press {hk}")
            self._hotkey_pill_label.pack(side="left")

    def _update_footer_meta(self):
        model = self.app.config.get("model_size", "base")
        hk = format_hotkey_display(self.app.config["hotkey"])
        chk = format_hotkey_display(self.app.config.get("clinical_hotkey", "<ctrl>+<alt>+r"))
        if self._mode == "clinical":
            self._foot_model.configure(image=ASSETS.get("cpu"), compound="left", text=f"  Model: {model}")
            self._foot_offline.configure(image=ASSETS.get("hard-drive"), compound="left", text="  Transcribe: Local")
            self._foot_hotkey.configure(image=ASSETS.get("keyboard"), compound="left", text=f"  Clinical stop: {chk}")
        else:
            self._foot_model.configure(image=ASSETS.get("cpu"), compound="left", text=f"  Model: {model}")
            self._foot_offline.configure(image=ASSETS.get("hard-drive"), compound="left", text="  Offline")
            self._foot_hotkey.configure(image=ASSETS.get("keyboard"), compound="left", text=f"  Hotkey: {hk}")

    def set_app_state(self, state: str):
        self._state = state
        if state == "recording":
            self._record_banner.pack(fill="x", pady=(0, 12), before=self._tcard)
        else:
            self._record_banner.pack_forget()
        self._update_hotkey_pill()
        self._update_footer_meta()

        if state == "recording":
            self._mic_circle.delete("all")
            self._mic_circle.create_oval(4, 4, 60, 60, fill=RED, outline="")
            self._mic_circle.create_image(32, 32, image=ASSETS.get("mic_lg"))
            self._listen_title.config(text="Listening")
            self._listen_sub.config(text="Speak naturally — text appears where your cursor is.")
            self._foot_dot.itemconfig(self._foot_dot_id, fill=RED)
            self._foot_status.config(text="Recording…", fg=RED_TEXT)
        elif state == "working":
            self._mic_circle.delete("all")
            self._mic_circle.create_image(32, 32, image=ASSETS.get("mic_idle"))
            self._listen_title.config(text="Transcribing…")
            self._listen_sub.config(text="Processing your speech locally.")
            self._foot_dot.itemconfig(self._foot_dot_id, fill=WARNING)
            self._foot_status.config(text="Transcribing…", fg=TEXT)
        elif state == "loading":
            self._listen_title.config(text="Loading model…")
            self._listen_sub.config(text="")
            self._foot_dot.itemconfig(self._foot_dot_id, fill=WARNING)
            self._foot_status.config(text="Loading…", fg=TEXT)
        else:
            self._mic_circle.delete("all")
            self._mic_circle.create_image(32, 32, image=ASSETS.get("mic_idle"))
            self._listen_title.config(text="Ready")
            self._listen_sub.config(text="Press your hotkey to start dictating.")
            self._foot_dot.itemconfig(self._foot_dot_id, fill=SUCCESS)
            self._foot_status.config(text="Ready", fg=TEXT)

    def set_status(self, message: str, auto_clear_ms: int | None = None, state: str = "idle"):
        self.set_app_state(state)
        if message:
            self._foot_status.config(text=message)
        if auto_clear_ms:
            self.root.after(auto_clear_ms, lambda: self.set_app_state("idle"))

    def _delete_entry(self, entry_id: str):
        self.app.history.delete(entry_id)
        self.refresh()

    def _copy_text(self, text: str):
        pyperclip.copy(text)
        self.set_status("Copied to clipboard.", auto_clear_ms=2000, state="success")

    def refresh(self):
        for child in self._feed.winfo_children():
            child.destroy()
        entries = self.app.history.get_entries()
        n = len(entries)
        self._count_badge.config(text=f"{n} item" if n == 1 else f"{n} items")
        if not entries:
            tk.Label(self._feed, text="No transcriptions yet", bg=SURFACE, fg=MUTED, font=FONT).pack(pady=40)
        else:
            for entry in entries:
                TranscriptRow(self._feed, entry, self._copy_text, self._delete_entry).pack(fill="x", pady=(0, 10))
        stats = self.app.history.get_stats()
        self._stat_widgets["time"].config(text=format_total_time(stats["total_seconds"]))
        self._stat_widgets["words"].config(text=f"{stats['total_words']:,}")
        self._stat_widgets["sessions"].config(text=str(stats["sessions"]))
        self._stat_widgets["wpm"].config(text=str(stats["wpm"]))
        self._update_hotkey_pill()
        self._update_footer_meta()

    def _show_home(self):
        self._set_mode("quick")

    def _show_settings(self):
        self._settings_view.reload()
        self._home_view.pack_forget()
        self._clinical_view.pack_forget()
        self._settings_btn.pack_forget()
        self._settings_view.pack(fill="both", expand=True)

    def _open_settings(self):
        self._show_settings()

    def show(self):
        self.is_hidden = False
        self.root.deiconify()
        self.root.lift()

    def hide_to_tray(self):
        self.is_hidden = True
        self.root.withdraw()
        if self.app._tray is not None:
            self.app._tray.title = "Dictate"

    def run(self):
        self.root.mainloop()

    def destroy(self):
        self.root.after(0, self.root.destroy)
