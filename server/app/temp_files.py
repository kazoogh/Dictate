"""Temporary upload directory management."""

from __future__ import annotations

import logging
import shutil
import time
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app import config

logger = logging.getLogger("dictate.temp")


def ensure_temp_dir() -> Path:
    config.TEMP_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return config.TEMP_UPLOAD_DIR


def count_temp_files() -> int:
    directory = ensure_temp_dir()
    return sum(1 for path in directory.iterdir() if path.is_file())


def free_disk_gb() -> float:
    directory = ensure_temp_dir()
    usage = shutil.disk_usage(directory)
    return round(usage.free / (1024**3), 2)


def cleanup_stale_files() -> int:
    """Delete temp uploads older than max age. Returns number deleted."""
    directory = ensure_temp_dir()
    cutoff = time.time() - config.TEMP_FILE_MAX_AGE_SECONDS
    deleted = 0
    for path in directory.iterdir():
        if not path.is_file():
            continue
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
                deleted += 1
        except OSError as exc:
            logger.warning("Failed to delete stale upload %s: %s", path.name, exc)
    if deleted:
        logger.info("Deleted %d stale temp upload(s) from %s", deleted, directory)
    return deleted


def _safe_extension(filename: str | None) -> str:
    if not filename:
        return ".wav"
    suffix = Path(filename).suffix.lower()
    if suffix in {".wav", ".mp3", ".m4a", ".ogg", ".webm", ".flac"}:
        return suffix
    return ".wav"


async def save_upload_limited(upload: UploadFile, max_bytes: int) -> Path:
    """Stream upload into temp dir, enforcing max size. Caller must delete."""
    directory = ensure_temp_dir()
    suffix = _safe_extension(upload.filename)
    dest = directory / f"{uuid.uuid4().hex}{suffix}"

    content_length = upload.size
    if content_length is not None and content_length > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum size of {config.MAX_UPLOAD_MB} MB",
        )

    total = 0
    try:
        with dest.open("wb") as handle:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds maximum size of {config.MAX_UPLOAD_MB} MB",
                    )
                handle.write(chunk)
    except Exception:
        dest.unlink(missing_ok=True)
        raise

    logger.info("Saved temp upload %s (%d bytes)", dest.name, total)
    return dest


def delete_upload(path: Path | None) -> None:
    if path is None:
        return
    try:
        if path.exists():
            path.unlink()
            logger.info("Deleted temp upload %s", path.name)
    except OSError as exc:
        logger.warning("Failed to delete temp upload %s: %s", path.name, exc)
