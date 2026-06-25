"""Resolve bundled punctuation ONNX assets for dev and frozen (PyInstaller) runs."""

from __future__ import annotations

import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

MODEL_ARCHIVE_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/punctuation-models/"
    "sherpa-onnx-online-punct-en-2024-08-06.tar.bz2"
)
MODEL_FILES = ("model.int8.onnx", "model.onnx")
VOCAB_FILE = "bpe.vocab"
MIN_MODEL_BYTES = 100_000


def _project_assets_dir() -> Path:
    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", ""))
        return meipass / "assets" / "punctuation"
    return Path(__file__).resolve().parent / "assets" / "punctuation"


def _runtime_dir() -> Path:
    runtime = Path(tempfile.gettempdir()) / "Dictate" / "punctuation"
    runtime.mkdir(parents=True, exist_ok=True)
    return runtime


def _copy_if_needed(src: Path, dest: Path) -> None:
    if not src.is_file():
        raise FileNotFoundError(f"Missing punctuation asset: {src}")
    if not dest.exists() or dest.stat().st_size != src.stat().st_size:
        shutil.copy2(src, dest)


def _model_file(asset_dir: Path) -> Path | None:
    for name in MODEL_FILES:
        path = asset_dir / name
        if path.is_file() and path.stat().st_size >= MIN_MODEL_BYTES:
            return path
    return None


def _clear_partial_assets(asset_dir: Path) -> None:
    for name in (*MODEL_FILES, VOCAB_FILE, "_punct_download.tar.bz2"):
        path = asset_dir / name
        if path.is_file():
            path.unlink()


def _assets_complete(asset_dir: Path) -> bool:
    return _model_file(asset_dir) is not None and (asset_dir / VOCAB_FILE).is_file()


def ensure_punctuation_assets() -> Path:
    """Return a directory containing an ONNX model and bpe.vocab."""
    bundled = _project_assets_dir()
    if not _assets_complete(bundled) and not getattr(sys, "frozen", False):
        download_punctuation_model(bundled)

    if not _assets_complete(bundled):
        raise FileNotFoundError(
            "Punctuation model files missing. Rebuild with build.bat or run: "
            "python scripts/download_punctuation_model.py"
        )

    runtime = _runtime_dir()
    model = _model_file(bundled)
    assert model is not None
    _copy_if_needed(model, runtime / model.name)
    _copy_if_needed(bundled / VOCAB_FILE, runtime / VOCAB_FILE)
    return runtime


def download_punctuation_model(dest_dir: Path | None = None) -> Path:
    """Download and extract the English punctuation ONNX model into dest_dir."""
    dest_dir = dest_dir or _project_assets_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)

    if _assets_complete(dest_dir):
        return dest_dir

    _clear_partial_assets(dest_dir)
    archive_path = dest_dir / "_punct_download.tar.bz2"
    print(f"Downloading punctuation model to {dest_dir} …")
    urllib.request.urlretrieve(MODEL_ARCHIVE_URL, archive_path)

    wanted = {*MODEL_FILES, VOCAB_FILE}
    with tarfile.open(archive_path, "r:bz2") as tar:
        members = {
            member.name.split("/")[-1]: member
            for member in tar.getmembers()
            if member.isfile() and member.name.split("/")[-1] in wanted
        }
        if VOCAB_FILE not in members or not any(name in members for name in MODEL_FILES):
            raise RuntimeError(
                "Punctuation archive did not contain bpe.vocab and a model.onnx file"
            )
        for name, member in members.items():
            extracted = tar.extractfile(member)
            if extracted is None:
                raise RuntimeError(f"Failed to extract {name} from archive")
            (dest_dir / name).write_bytes(extracted.read())

    archive_path.unlink(missing_ok=True)
    if not _assets_complete(dest_dir):
        found = [p.name for p in dest_dir.iterdir() if p.is_file()]
        raise RuntimeError(
            "Punctuation model download incomplete. "
            f"Expected ONNX model + {VOCAB_FILE}; found: {found}"
        )
    model = _model_file(dest_dir)
    print(f"Punctuation model ready ({model.name}, {model.stat().st_size // 1024} KB).")
    return dest_dir
