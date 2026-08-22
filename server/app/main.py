"""Dictate API — hardened transcription server for Quick Dictate."""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app import config
from app.auth import require_api_key
from app.cleanup import CleanupMode, polish_text, simple_cleanup
from app.state import runtime_state
from app.temp_files import (
    cleanup_stale_files,
    count_temp_files,
    delete_upload,
    ensure_temp_dir,
    free_disk_gb,
    save_upload_limited,
)
from app.transcription import load_model, transcribe_file

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("dictate.api")


async def _background_cleanup_loop() -> None:
    while True:
        await asyncio.sleep(config.BACKGROUND_CLEANUP_INTERVAL_SECONDS)
        try:
            cleanup_stale_files()
        except Exception as exc:
            logger.warning("Background temp cleanup failed: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_temp_dir()
    deleted = cleanup_stale_files()
    logger.info("Startup temp cleanup removed %d file(s)", deleted)
    try:
        load_model()
    except Exception as exc:
        runtime_state.record_error(f"Model load failed: {exc}")
        logger.error("Failed to load Whisper model: %s", exc)

    cleanup_task = asyncio.create_task(_background_cleanup_loop())
    logger.info(
        "Dictate API ready on %s:%s cleanup_mode=%s temp_dir=%s",
        config.HOST,
        config.PORT,
        config.CLEANUP_MODE,
        config.TEMP_UPLOAD_DIR,
    )
    yield
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Dictate API", version="2.0.0", lifespan=lifespan)


class CleanupRequest(BaseModel):
    text: str


class RewriteRequest(BaseModel):
    text: str
    mode: CleanupMode | None = Field(default=None)


class ClinicalGenerateRequest(BaseModel):
    transcript: str = ""
    context: str = ""


@app.get("/health")
def health() -> dict[str, object]:
    snapshot = runtime_state.snapshot()
    return {
        "ok": snapshot["model_loaded"],
        "service": config.SERVICE_NAME,
        "uptime_seconds": snapshot["uptime_seconds"],
        "model_loaded": snapshot["model_loaded"],
        "transcribe_count": snapshot["transcribe_count"],
        "last_transcribe_seconds": snapshot["last_transcribe_seconds"],
        "last_error": snapshot["last_error"],
        "temp_upload_dir": str(config.TEMP_UPLOAD_DIR),
        "temp_files_count": count_temp_files(),
        "free_disk_gb": free_disk_gb(),
        "cleanup_mode": config.CLEANUP_MODE,
    }


@app.post("/cleanup")
def cleanup_text(
    body: CleanupRequest,
    _: None = Depends(require_api_key),
) -> dict[str, str]:
    return {"text": simple_cleanup(body.text)}


@app.post("/rewrite")
def rewrite_text(
    body: RewriteRequest,
    _: None = Depends(require_api_key),
) -> dict[str, object]:
    mode: CleanupMode = body.mode or config.CLEANUP_MODE  # type: ignore[assignment]
    if mode not in {"basic", "openai"}:
        raise HTTPException(status_code=400, detail="mode must be 'basic' or 'openai'")
    result = polish_text(body.text, mode=mode)
    response: dict[str, object] = {
        "text": result.text,
        "raw_text": body.text,
        "mode": result.mode_used,
    }
    if result.cleanup_error:
        response["cleanup_error"] = result.cleanup_error
    return response


@app.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    _: None = Depends(require_api_key),
) -> dict[str, object]:
    temp_path: Path | None = None
    started = time.perf_counter()
    try:
        temp_path = await save_upload_limited(file, config.MAX_UPLOAD_BYTES)
        raw_text, transcribe_elapsed = transcribe_file(temp_path)
        cleanup_result = polish_text(raw_text)
        total_elapsed = time.perf_counter() - started
        runtime_state.record_transcribe(total_elapsed)

        response: dict[str, object] = {
            "text": cleanup_result.text,
            "raw_text": raw_text,
            "processing_time_seconds": round(total_elapsed, 2),
            "model": config.WHISPER_MODEL_SIZE,
            "device": config.WHISPER_DEVICE,
        }
        if cleanup_result.cleanup_error:
            response["cleanup_error"] = cleanup_result.cleanup_error
        logger.info(
            "Transcribe OK file=%s whisper=%.2fs total=%.2fs mode=%s",
            temp_path.name,
            transcribe_elapsed,
            total_elapsed,
            cleanup_result.mode_used,
        )
        return response
    except HTTPException:
        raise
    except Exception as exc:
        runtime_state.record_error(str(exc))
        logger.exception("Transcribe failed")
        raise HTTPException(status_code=500, detail="Transcription failed") from exc
    finally:
        delete_upload(temp_path)


@app.post("/clinical/generate")
def clinical_generate(
    body: ClinicalGenerateRequest,
    _: None = Depends(require_api_key),
) -> dict[str, str]:
    raise HTTPException(status_code=501, detail="Clinical generation is not enabled on this server")


def main() -> None:
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=config.HOST,
        port=config.PORT,
        log_level="info",
    )


if __name__ == "__main__":
    main()
