"""Retention and file cleanup for clinical sessions."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path


def delete_file(path: Path | str | None) -> bool:
    if not path:
        return True
    p = Path(path)
    if not p.exists():
        return True
    try:
        p.unlink()
        return True
    except OSError:
        return False


def delete_session_files(session: dict) -> None:
    for key in ("audio_path", "transcript_path", "answer_sheet_path", "pdf_path"):
        delete_file(session.get(key))


def retention_cutoff_iso(retention_days: str) -> str | None:
    if retention_days == "manual":
        return None
    try:
        days = int(retention_days)
    except ValueError:
        days = 7
    cutoff = datetime.now() - timedelta(days=days)
    return cutoff.isoformat(timespec="seconds")


def run_retention_cleanup(storage, retention_days: str) -> int:
    cutoff = retention_cutoff_iso(retention_days)
    if cutoff is None:
        return 0
    removed = 0
    for session in storage.get_sessions_older_than(cutoff):
        delete_session_files(session)
        storage.delete_session(session["id"])
        removed += 1
    return removed
