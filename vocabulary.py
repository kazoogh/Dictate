"""Custom vocabulary: Whisper biasing + fuzzy homophone correction."""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

try:
    from rapidfuzz import fuzz
except ImportError:
    fuzz = None  # type: ignore[assignment]

_TOKEN_RE = re.compile(r"\S+")


def _bundled_default_path() -> Path:
    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", ""))
        return meipass / "assets" / "vocabulary.default.json"
    return Path(__file__).resolve().parent / "assets" / "vocabulary.default.json"


def vocabulary_path(app_dir: Path) -> Path:
    return app_dir / "vocabulary.json"


def ensure_vocabulary_file(app_dir: Path) -> Path:
    """Create user vocabulary.json from bundled defaults if missing."""
    dest = vocabulary_path(app_dir)
    if dest.is_file():
        return dest
    src = _bundled_default_path()
    if not src.is_file():
        dest.write_text(
            json.dumps({"version": "1.0", "terms": []}, indent=2),
            encoding="utf-8",
        )
        return dest
    shutil.copy2(src, dest)
    return dest


def _normalize_phrase(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9'\s]+", " ", text)
    return " ".join(text.split())


class VocabularyStore:
    """Editable glossary used to bias Whisper and fix homophones after transcription."""

    def __init__(self, app_dir: Path, fuzzy_threshold: int = 82):
        self.app_dir = app_dir
        self.fuzzy_threshold = fuzzy_threshold
        self.path = ensure_vocabulary_file(app_dir)
        self._mtime: float | None = None
        self._terms: list[dict] = []
        self._alias_patterns: list[tuple[str, str]] = []
        self._fuzzy_patterns: list[tuple[str, str]] = []
        self.reload()

    def reload(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {"terms": []}
        self._mtime = self.path.stat().st_mtime if self.path.exists() else None
        self._terms = list(data.get("terms", []))
        self._alias_patterns = []
        self._fuzzy_patterns = []
        seen: set[str] = set()
        for entry in self._terms:
            term = str(entry.get("term", "")).strip()
            if not term:
                continue
            canonical = term
            norm_term = _normalize_phrase(term)
            if norm_term and norm_term not in seen:
                self._fuzzy_patterns.append((norm_term, canonical))
                seen.add(norm_term)
            for alias in entry.get("aliases", []):
                alias_text = str(alias).strip()
                if not alias_text:
                    continue
                norm_alias = _normalize_phrase(alias_text)
                if not norm_alias or norm_alias in seen:
                    continue
                self._alias_patterns.append((alias_text, canonical))
                self._fuzzy_patterns.append((norm_alias, canonical))
                seen.add(norm_alias)
        self._alias_patterns.sort(key=lambda item: len(item[0]), reverse=True)
        self._fuzzy_patterns.sort(key=lambda item: len(item[0]), reverse=True)

    def _maybe_reload(self) -> None:
        if not self.path.exists():
            return
        mtime = self.path.stat().st_mtime
        if self._mtime != mtime:
            self.reload()

    def whisper_prompt(self, max_terms: int = 80) -> str:
        """Comma-separated terms to nudge Whisper toward correct spellings."""
        self._maybe_reload()
        names: list[str] = []
        for entry in self._terms:
            term = str(entry.get("term", "")).strip()
            if term:
                names.append(term)
            if len(names) >= max_terms:
                break
        return ", ".join(names)

    def _apply_alias_pass(self, text: str) -> str:
        result = text
        for pattern, canonical in self._alias_patterns:
            result = re.sub(
                rf"(?i)\b{re.escape(pattern)}\b",
                canonical,
                result,
            )
        return result

    def _word_core(self, token: str) -> str:
        return re.sub(r"^[^\w']+|[^\w']+$", "", token).lower()

    def _apply_fuzzy_pass(self, text: str) -> str:
        if not fuzz or not self._fuzzy_patterns:
            return text

        matches = list(_TOKEN_RE.finditer(text))
        if not matches:
            return text

        cores = [self._word_core(m.group(0)) for m in matches]
        used = [False] * len(cores)
        replacements: list[tuple[int, int, str]] = []

        max_n = min(4, len(cores))
        for n in range(max_n, 0, -1):
            for i in range(0, len(cores) - n + 1):
                if any(used[i : i + n]):
                    continue
                phrase = " ".join(c for c in cores[i : i + n] if c)
                if not phrase:
                    continue
                best_term: str | None = None
                best_score = 0
                for pattern, canonical in self._fuzzy_patterns:
                    if abs(len(pattern.split()) - n) > 1 and n > 1:
                        continue
                    score = int(fuzz.ratio(phrase, pattern))
                    if score > best_score:
                        best_score = score
                        best_term = canonical
                if best_term and best_score >= self.fuzzy_threshold:
                    replacements.append((i, i + n, best_term))
                    for j in range(i, i + n):
                        used[j] = True

        if not replacements:
            return text

        replacements.sort(key=lambda item: item[0])
        merged: list[tuple[int, int, str]] = []
        for start, end, canonical in replacements:
            if merged and start < merged[-1][1]:
                continue
            merged.append((start, end, canonical))

        parts: list[str] = []
        cursor = 0
        for start, end, canonical in merged:
            first = matches[start]
            last = matches[end - 1]
            parts.append(text[cursor : first.start()])
            parts.append(canonical)
            cursor = last.end()
        parts.append(text[cursor:])
        return "".join(parts)

    def correct(self, text: str) -> str:
        self._maybe_reload()
        if not text.strip() or not self._terms:
            return text
        text = self._apply_alias_pass(text)
        text = self._apply_fuzzy_pass(text)
        return text

    def add_learned_correction(self, term: str, alias: str) -> bool:
        """Add canonical term with alias (what Whisper pasted). Returns True if updated."""
        term = str(term).strip()
        alias = str(alias).strip()
        if not term or not alias or term.lower() == alias.lower():
            return False

        self._maybe_reload()
        norm_alias = _normalize_phrase(alias)

        for entry in self._terms:
            canonical = str(entry.get("term", "")).strip()
            if not canonical:
                continue
            if canonical.lower() != term.lower():
                continue
            aliases = entry.setdefault("aliases", [])
            existing = {_normalize_phrase(str(a)) for a in aliases}
            if norm_alias in existing:
                return False
            aliases.append(alias)
            self._save()
            self.reload()
            return True

        for entry in self._terms:
            canonical = str(entry.get("term", "")).strip()
            if canonical and _normalize_phrase(canonical) == norm_alias:
                return False

        self._terms.append({"term": term, "aliases": [alias]})
        self._save()
        self.reload()
        return True

    def _save(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {"version": "1.0"}
        data["terms"] = self._terms
        self.path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        self._mtime = self.path.stat().st_mtime
