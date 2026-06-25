"""SQLite storage for clinical sessions."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


class ClinicalStorage:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._connect()
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    procedure_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    duration_seconds INTEGER DEFAULT 0,
                    audio_path TEXT,
                    audio_deleted INTEGER DEFAULT 0,
                    audio_deletion_failed INTEGER DEFAULT 0,
                    transcript_path TEXT,
                    answer_sheet_path TEXT,
                    pdf_path TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
                CREATE INDEX IF NOT EXISTS idx_sessions_started_at ON sessions(started_at);
                """
            )
            conn.commit()
            conn.close()

    def _row_to_session(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "procedure_type": row["procedure_type"],
            "status": row["status"],
            "started_at": row["started_at"],
            "ended_at": row["ended_at"],
            "duration_seconds": row["duration_seconds"] or 0,
            "audio_path": row["audio_path"],
            "audio_deleted": bool(row["audio_deleted"]),
            "audio_deletion_failed": bool(row["audio_deletion_failed"]),
            "transcript_path": row["transcript_path"],
            "answer_sheet_path": row["answer_sheet_path"],
            "pdf_path": row["pdf_path"],
            "error_message": row["error_message"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def create_session(self, procedure_type: str) -> dict[str, Any]:
        now = datetime.now().isoformat(timespec="seconds")
        session = {
            "id": uuid4().hex,
            "procedure_type": procedure_type,
            "status": "Recording",
            "started_at": now,
            "ended_at": None,
            "duration_seconds": 0,
            "audio_path": None,
            "audio_deleted": False,
            "audio_deletion_failed": False,
            "transcript_path": None,
            "answer_sheet_path": None,
            "pdf_path": None,
            "error_message": None,
            "created_at": now,
            "updated_at": now,
        }
        with self._lock:
            conn = self._connect()
            conn.execute(
                """
                INSERT INTO sessions (
                    id, procedure_type, status, started_at, ended_at, duration_seconds,
                    audio_path, audio_deleted, audio_deletion_failed, transcript_path,
                    answer_sheet_path, pdf_path, error_message, created_at, updated_at
                ) VALUES (
                    :id, :procedure_type, :status, :started_at, :ended_at, :duration_seconds,
                    :audio_path, :audio_deleted, :audio_deletion_failed, :transcript_path,
                    :answer_sheet_path, :pdf_path, :error_message, :created_at, :updated_at
                )
                """,
                {
                    **session,
                    "audio_deleted": int(session["audio_deleted"]),
                    "audio_deletion_failed": int(session["audio_deletion_failed"]),
                },
            )
            conn.commit()
            conn.close()
        return session

    def update_session(self, session_id: str, **updates: Any) -> dict[str, Any] | None:
        session = self.get_session(session_id)
        if not session:
            return None
        session.update(updates)
        session["updated_at"] = datetime.now().isoformat(timespec="seconds")
        with self._lock:
            conn = self._connect()
            conn.execute(
                """
                UPDATE sessions SET
                    procedure_type = :procedure_type, status = :status,
                    started_at = :started_at, ended_at = :ended_at,
                    duration_seconds = :duration_seconds, audio_path = :audio_path,
                    audio_deleted = :audio_deleted, audio_deletion_failed = :audio_deletion_failed,
                    transcript_path = :transcript_path, answer_sheet_path = :answer_sheet_path,
                    pdf_path = :pdf_path, error_message = :error_message, updated_at = :updated_at
                WHERE id = :id
                """,
                {
                    **session,
                    "audio_deleted": int(session["audio_deleted"]),
                    "audio_deletion_failed": int(session["audio_deletion_failed"]),
                },
            )
            conn.commit()
            conn.close()
        return session

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            conn = self._connect()
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            conn.close()
        return self._row_to_session(row) if row else None

    def get_all_sessions(self) -> list[dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            rows = conn.execute("SELECT * FROM sessions ORDER BY started_at DESC").fetchall()
            conn.close()
        return [self._row_to_session(r) for r in rows]

    def get_recording_session(self) -> dict[str, Any] | None:
        with self._lock:
            conn = self._connect()
            row = conn.execute(
                "SELECT * FROM sessions WHERE status = 'Recording' LIMIT 1"
            ).fetchone()
            conn.close()
        return self._row_to_session(row) if row else None

    def delete_session(self, session_id: str) -> None:
        with self._lock:
            conn = self._connect()
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            conn.commit()
            conn.close()

    def get_sessions_older_than(self, cutoff_iso: str) -> list[dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            rows = conn.execute(
                "SELECT * FROM sessions WHERE started_at < ? ORDER BY started_at ASC",
                (cutoff_iso,),
            ).fetchall()
            conn.close()
        return [self._row_to_session(r) for r in rows]

    def get_setting(self, key: str) -> str | None:
        with self._lock:
            conn = self._connect()
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            conn.close()
        return row["value"] if row else None

    def set_setting(self, key: str, value: str) -> None:
        with self._lock:
            conn = self._connect()
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            conn.commit()
            conn.close()

    def read_answer_sheet(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def write_answer_sheet(self, path: Path, sheet: dict[str, Any]) -> None:
        path.write_text(json.dumps(sheet, indent=2) + "\n", encoding="utf-8")
