"""Launch-at-login registration for Dictate Lite (cross-platform).

Windows  -> HKCU ...\\CurrentVersion\\Run registry value.
macOS    -> a per-user LaunchAgent plist in ~/Library/LaunchAgents.
Other    -> no-op (feature simply unavailable).

All public functions are safe to call on any OS: they never raise ImportError,
and only raise OSError on a genuine failure to read/write the relevant store
(the callers in main.py catch OSError).
"""

from __future__ import annotations

import sys
from pathlib import Path

APP_NAME = "Dictate Lite"
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

# macOS LaunchAgent
_LAUNCH_AGENT_LABEL = "care.franklindental.dictatelite"


def startup_args() -> list[str]:
    """Argument vector used to relaunch Dictate Lite at sign-in."""
    if getattr(sys, "frozen", False):
        exe = str(Path(sys.executable).resolve())
        return [exe, "--startup"]
    main_py = str(Path(__file__).resolve().parent / "main.py")
    python = str(Path(sys.executable).resolve())
    return [python, main_py, "--startup"]


def startup_command() -> str:
    """Command-line string (Windows Run key wants a single string)."""
    return " ".join(f'"{part}"' for part in startup_args())


# --------------------------------------------------------------------------- #
# Windows
# --------------------------------------------------------------------------- #
def _win_is_enabled() -> bool:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except OSError:
        return False


def _win_sync(enabled: bool) -> None:
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, startup_command())
            return
        try:
            winreg.DeleteValue(key, APP_NAME)
        except FileNotFoundError:
            pass


# --------------------------------------------------------------------------- #
# macOS
# --------------------------------------------------------------------------- #
def _mac_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{_LAUNCH_AGENT_LABEL}.plist"


def _mac_is_enabled() -> bool:
    return _mac_plist_path().is_file()


def _xml_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _mac_sync(enabled: bool) -> None:
    plist_path = _mac_plist_path()
    if not enabled:
        try:
            plist_path.unlink()
        except FileNotFoundError:
            pass
        return

    program_args = "".join(
        f"        <string>{_xml_escape(a)}</string>\n" for a in startup_args()
    )
    plist = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        "<dict>\n"
        "    <key>Label</key>\n"
        f"    <string>{_LAUNCH_AGENT_LABEL}</string>\n"
        "    <key>ProgramArguments</key>\n"
        "    <array>\n"
        f"{program_args}"
        "    </array>\n"
        "    <key>RunAtLoad</key>\n"
        "    <true/>\n"
        "    <key>ProcessType</key>\n"
        "    <string>Interactive</string>\n"
        "</dict>\n"
        "</plist>\n"
    )
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(plist, encoding="utf-8")


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def is_startup_enabled() -> bool:
    if sys.platform.startswith("win"):
        return _win_is_enabled()
    if sys.platform == "darwin":
        return _mac_is_enabled()
    return False


def sync_startup_registration(enabled: bool) -> None:
    """Register or remove Dictate Lite from the current user's login items."""
    if sys.platform.startswith("win"):
        _win_sync(enabled)
    elif sys.platform == "darwin":
        _mac_sync(enabled)
    # Other platforms: launch-at-login is unsupported; silently do nothing.
