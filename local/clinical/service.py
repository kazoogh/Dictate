"""Clinical session orchestration."""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from clinical.cleanup import delete_file, delete_session_files, run_retention_cleanup
from clinical.llm import generate_answer_sheet
from clinical.paths import ensure_clinical_dirs, template_path_for_procedure
from clinical.pdf_export import build_pdf_filename, export_answer_sheet_pdf
from clinical.recorder import StreamingDiskRecorder
from clinical.storage import ClinicalStorage


class ClinicalManager:
    def __init__(
        self,
        app_dir: Path,
        config: dict,
        transcriber,
        on_update: Callable[[], None],
        on_status: Callable[..., None] | None = None,
    ):
        self.app_dir = app_dir
        self.config = config
        self.transcriber = transcriber
        self.on_update = on_update
        self.on_status = on_status or (lambda *_a, **_k: None)
        self.paths = ensure_clinical_dirs(app_dir)
        self.storage = ClinicalStorage(self.paths["db_file"])
        self._recorder: StreamingDiskRecorder | None = None
        self._active_session: dict | None = None
        self._timer_thread: threading.Thread | None = None
        self._stop_timer = threading.Event()
        self._lock = threading.Lock()

    def get_openai_api_key(self) -> str:
        return self.storage.get_setting("openai_api_key") or ""

    def set_openai_api_key(self, key: str) -> None:
        self.storage.set_setting("openai_api_key", key.strip())

    def is_recording(self) -> bool:
        return self._recorder is not None and self._recorder.is_recording

    def active_session(self) -> dict | None:
        return self._active_session

    def list_sessions(self) -> list[dict]:
        return self.storage.get_all_sessions()

    def get_session(self, session_id: str) -> dict | None:
        return self.storage.get_session(session_id)

    def start_session(self, procedure_type: str) -> dict:
        with self._lock:
            if self.is_recording():
                raise RuntimeError("A clinical session is already recording.")
            existing = self.storage.get_recording_session()
            if existing:
                raise RuntimeError("Another recording session exists in the database.")
            session = self.storage.create_session(procedure_type)
            session_id = session["id"]
            audio_path = self.paths["temp_audio"] / f"{session_id}.wav"
            max_hours = float(self.config.get("clinical_max_duration_hours", 2))

        recorder = StreamingDiskRecorder(
            audio_path,
            sample_rate=self.config.get("sample_rate", 16000),
            channels=self.config.get("channels", 1),
            max_duration_sec=max_hours * 3600,
        )
        try:
            recorder.start()
        except Exception as exc:
            self.storage.update_session(
                session_id,
                status="Error",
                error_message=f"Microphone error: {exc}",
            )
            raise

        with self._lock:
            self._recorder = recorder
            session = self.storage.update_session(session_id, audio_path=str(audio_path))
            self._active_session = session
            self._stop_timer.clear()
            self._timer_thread = threading.Thread(target=self._duration_watch, daemon=True)
            self._timer_thread.start()

        self.on_update()
        return session

    def _duration_watch(self) -> None:
        while not self._stop_timer.wait(1.0):
            if self._recorder and self._recorder.is_over_limit():
                self.stop_session(auto=True)
                break

    def stop_session(self, auto: bool = False) -> dict | None:
        with self._lock:
            if not self._recorder or not self._active_session:
                return None
            session = self._active_session
            session_id = session["id"]
            duration = int(self._recorder.elapsed_seconds)
            recorder = self._recorder
            self._recorder = None
            self._active_session = None
            self._stop_timer.set()

        try:
            audio_path = recorder.stop()
        except Exception as exc:
            self.storage.update_session(
                session_id,
                status="Error",
                error_message=f"Failed to stop recording: {exc}",
            )
            self.on_update()
            return self.storage.get_session(session_id)

        ended = datetime.now().isoformat(timespec="seconds")
        session = self.storage.update_session(
            session_id,
            status="Processing",
            ended_at=ended,
            duration_seconds=duration,
            audio_path=audio_path,
            error_message="Auto-stopped: maximum duration reached." if auto else None,
        )
        self.on_update()
        threading.Thread(
            target=self._process_session,
            args=(session_id,),
            daemon=True,
        ).start()
        return session

    def _process_session(self, session_id: str) -> None:
        session = self.storage.get_session(session_id)
        if not session:
            return

        audio_path = session.get("audio_path")
        transcript_path = self.paths["transcripts"] / f"{session_id}.txt"
        notify_msg: str | None = None
        notify_state = "idle"
        notify_hide = 4000

        try:
            self.on_status("Transcribing appointment…", "working")
            if not audio_path or not os.path.exists(audio_path):
                raise RuntimeError("No audio file found for session.")
            text = self.transcriber.transcribe(audio_path)
            if not text.strip():
                raise RuntimeError("No speech detected in recording.")
            transcript_path.write_text(text, encoding="utf-8")
            session = self.storage.update_session(
                session_id,
                transcript_path=str(transcript_path),
            )
            self.on_update()

            api_key = self.get_openai_api_key()
            if not api_key:
                self.storage.update_session(
                    session_id,
                    status="Error",
                    error_message=(
                        "OpenAI API key not configured. Transcript saved — "
                        "add your key in Settings to generate the answer sheet."
                    ),
                )
                self._delete_audio(session)
                notify_msg = (
                    "Transcript saved. Add OpenAI API key in Settings "
                    "to generate the answer sheet."
                )
                notify_state = "error"
                notify_hide = 8000
                return

            self.on_status("Generating answer sheet…", "working")
            template_path = template_path_for_procedure(
                self.paths["templates"], session["procedure_type"]
            )
            template = json.loads(template_path.read_text(encoding="utf-8"))
            sheet = generate_answer_sheet(
                api_key=api_key,
                model=self.config.get("openai_model", "gpt-4o-mini"),
                transcript=text,
                template=template,
                procedure_type=session["procedure_type"],
                recording_datetime=session["started_at"],
                duration_seconds=session["duration_seconds"],
            )
            sheet["transcript_excerpt"] = text[:500]
            answer_path = self.paths["answer_sheets"] / f"{session_id}.json"
            self.storage.write_answer_sheet(answer_path, sheet)

            status = (
                "Ready for Dentrix"
                if sheet.get("final_note_status") == "Ready for Dentrix"
                else "Needs Review"
            )
            session = self.storage.update_session(
                session_id,
                answer_sheet_path=str(answer_path),
                status=status,
                error_message=None,
            )
            pdf_name = build_pdf_filename(session)
            pdf_path = self.paths["answer_sheets"] / pdf_name
            export_answer_sheet_pdf(session, sheet, pdf_path)
            self.storage.update_session(session_id, pdf_path=str(pdf_path))
            self._delete_audio(session)
            notify_msg = "Clinical answer sheet ready."
            notify_state = "success"
            notify_hide = 4000
        except Exception as exc:
            msg = str(exc)[:200] if str(exc) else "Processing failed"
            session = self.storage.get_session(session_id)
            if session and transcript_path.exists():
                self.storage.update_session(
                    session_id,
                    transcript_path=str(transcript_path),
                    status="Error",
                    error_message=msg,
                )
                self._delete_audio(session)
            else:
                self.storage.update_session(
                    session_id, status="Error", error_message=msg
                )
                if session:
                    self._delete_audio(session)
            notify_msg = f"Clinical error: {msg}"
            notify_state = "error"
            notify_hide = 6000
        finally:
            self.on_update()
            if notify_msg:
                self.on_status(notify_msg, notify_state, notify_hide)

    def _delete_audio(self, session: dict) -> None:
        if delete_file(session.get("audio_path")):
            self.storage.update_session(
                session["id"],
                audio_path=None,
                audio_deleted=True,
                audio_deletion_failed=False,
            )
        else:
            self.storage.update_session(
                session["id"],
                audio_deleted=False,
                audio_deletion_failed=True,
            )

    def read_transcript(self, session: dict) -> str:
        path = session.get("transcript_path")
        if not path or not os.path.exists(path):
            return ""
        return Path(path).read_text(encoding="utf-8")

    def read_answer_sheet(self, session: dict) -> dict | None:
        path = session.get("answer_sheet_path")
        if not path or not os.path.exists(path):
            return None
        return self.storage.read_answer_sheet(Path(path))

    def mark_entered(self, session_id: str) -> None:
        self.storage.update_session(session_id, status="Entered in Dentrix", error_message=None)
        self.on_update()

    def delete_session(self, session_id: str) -> None:
        session = self.storage.get_session(session_id)
        if session:
            delete_session_files(session)
        self.storage.delete_session(session_id)
        self.on_update()

    def export_pdf(self, session_id: str) -> Path | None:
        session = self.storage.get_session(session_id)
        if not session:
            return None
        sheet = self.read_answer_sheet(session)
        if not sheet:
            return None
        if session.get("pdf_path") and os.path.exists(session["pdf_path"]):
            return Path(session["pdf_path"])
        pdf_name = build_pdf_filename(session)
        pdf_path = self.paths["answer_sheets"] / pdf_name
        export_answer_sheet_pdf(session, sheet, pdf_path)
        self.storage.update_session(session_id, pdf_path=str(pdf_path))
        return pdf_path

    def run_cleanup(self) -> int:
        days = str(self.config.get("clinical_retention_days", "7"))
        return run_retention_cleanup(self.storage, days)

    def recording_elapsed(self) -> float:
        if self._recorder:
            return self._recorder.elapsed_seconds
        return 0.0
