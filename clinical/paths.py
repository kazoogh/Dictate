"""Clinical data paths and template resolution."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

PROCEDURE_TYPES = [
    "Extraction",
    "Filling",
    "Crown",
    "Denture",
    "New Patient Exam",
    "Other",
]

PROCEDURE_TEMPLATE_MAP = {
    "Extraction": "extraction.json",
    "Filling": "filling.json",
    "Crown": "crown.json",
    "Denture": "denture.json",
    "New Patient Exam": "new_patient_exam.json",
    "Other": "other.json",
}


def _bundle_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def get_clinical_dirs(app_dir: Path) -> dict[str, Path]:
    base = app_dir / "clinical_data"
    return {
        "base": base,
        "temp_audio": base / "temp_audio",
        "transcripts": base / "transcripts",
        "answer_sheets": base / "answer_sheets",
        "templates": base / "templates",
        "db": base / "db",
        "db_file": base / "db" / "clinical.db",
    }


def ensure_clinical_dirs(app_dir: Path) -> dict[str, Path]:
    paths = get_clinical_dirs(app_dir)
    for key, path in paths.items():
        if key in ("db_file",):
            continue
        path.mkdir(parents=True, exist_ok=True)
    paths["db"].mkdir(parents=True, exist_ok=True)
    seed_templates(paths["templates"])
    return paths


def bundled_templates_dir() -> Path:
    return _bundle_root() / "clinical" / "templates"


def seed_templates(dest_dir: Path) -> None:
    bundled = bundled_templates_dir()
    if not bundled.is_dir():
        return
    for src in bundled.glob("*.json"):
        dest = dest_dir / src.name
        if not dest.exists():
            shutil.copy2(src, dest)
            continue
        try:
            bundled_meta = json.loads(src.read_text(encoding="utf-8"))
            dest_meta = json.loads(dest.read_text(encoding="utf-8"))
            bundled_ver = str(bundled_meta.get("version", "0"))
            dest_ver = str(dest_meta.get("version", "0"))
            if bundled_ver > dest_ver:
                shutil.copy2(src, dest)
        except (json.JSONDecodeError, OSError):
            pass


def template_path_for_procedure(templates_dir: Path, procedure_type: str) -> Path:
    name = PROCEDURE_TEMPLATE_MAP.get(procedure_type, "other.json")
    return templates_dir / name
