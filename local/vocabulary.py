"""Custom vocabulary: Whisper biasing + context-aware homophone correction."""

from __future__ import annotations

import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    from rapidfuzz import fuzz
except ImportError:
    fuzz = None  # type: ignore[assignment]

_TOKEN_RE = re.compile(r"\S+")

_TECH_CONTEXT = re.compile(
    r"\b(?:"
    r"json|api|parse|parsing|file|files|data|format|object|objects|serialize|deserialize|"
    r"schema|endpoint|config|python|javascript|typescript|code|coding|programming|script|"
    r"function|variable|array|dictionary|backend|frontend|request|response|http|rest|"
    r"graphql|database|sql|import|export|debug|compile|build|deploy|repo|repository|"
    r"module|package|library|class|method|syntax|\.json|\.py|\.html|\.js|\.ts|\.css|"
    r"pip|npm|git|commit|branch|merge|docker|server|client|localhost|venv|async|await"
    r")\b",
    re.IGNORECASE,
)

_NAME_CONTEXT = re.compile(
    r"\b(?:"
    r"talk to|call|called|meet|met|with|he|she|him|her|his|hers|mr|mrs|ms|dr|"
    r"said|told|asked|hey|hi|thanks|thank|patient|doctor|assistant|team|everyone|"
    r"email|message|john|james|jackson|matthew|jason|michael|david|sarah|emily"
    r")\b",
    re.IGNORECASE,
)

_C_PLUS_CONTEXT = re.compile(
    r"\b(?:c\s+plus\s+plus|see\s+plus\s+plus|cplusplus|cpp)\b",
    re.IGNORECASE,
)

_DEPRECATED_ALIASES: dict[str, list[str]] = {
    "exe": ["executable file"],
    "c++": ["c plus"],
}

_BUNDLED_VOCAB_FILES = (
    "vocabulary.default.json",
    "vocabulary.names.json",
    "vocabulary.tech.json",
)


def _assets_dir() -> Path:
    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", ""))
        return meipass / "assets"
    return Path(__file__).resolve().parent / "assets"


def vocabulary_path(app_dir: Path) -> Path:
    return app_dir / "vocabulary.json"


def load_bundled_terms() -> list[dict]:
    terms: list[dict] = []
    seen: set[str] = set()
    for filename in _BUNDLED_VOCAB_FILES:
        path = _assets_dir() / filename
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for entry in data.get("terms", []):
            term = str(entry.get("term", "")).strip()
            if not term:
                continue
            key = term.lower()
            if key in seen:
                continue
            seen.add(key)
            terms.append(entry)
    return terms


def merge_bundled_terms_into_user_file(app_dir: Path) -> None:
    """Add bundled names/tech terms missing from the user's vocabulary.json."""
    dest = vocabulary_path(app_dir)
    bundled = load_bundled_terms()
    if not bundled:
        return

    if not dest.is_file():
        shutil.copy2(_assets_dir() / "vocabulary.default.json", dest)
        if not dest.is_file():
            dest.write_text(
                json.dumps({"version": "2.0", "terms": bundled}, indent=2) + "\n",
                encoding="utf-8",
            )
            return

    try:
        data = json.loads(dest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {"version": "2.0", "terms": []}

    user_terms: list[dict] = list(data.get("terms", []))
    by_key = {str(t.get("term", "")).strip().lower(): t for t in user_terms if t.get("term")}

    changed = False
    for entry in bundled:
        key = str(entry.get("term", "")).strip().lower()
        if not key:
            continue
        existing = by_key.get(key)
        if existing is None:
            user_terms.append(entry)
            by_key[key] = entry
            changed = True
            continue
        if entry.get("category") and not existing.get("category"):
            existing["category"] = entry["category"]
            changed = True
        if entry.get("conflicts") and not existing.get("conflicts"):
            existing["conflicts"] = entry["conflicts"]
            changed = True
        deprecated = _DEPRECATED_ALIASES.get(key, [])
        if deprecated and existing.get("aliases"):
            before = list(existing["aliases"])
            existing["aliases"] = [
                a for a in existing["aliases"] if _normalize_phrase(str(a)) not in {
                    _normalize_phrase(d) for d in deprecated
                }
            ]
            if existing["aliases"] != before:
                changed = True
        bundled_aliases = {_normalize_phrase(str(a)) for a in entry.get("aliases", [])}
        aliases = existing.setdefault("aliases", [])
        existing_aliases = {_normalize_phrase(str(a)) for a in aliases}
        for alias in entry.get("aliases", []):
            norm = _normalize_phrase(str(alias))
            if norm and norm not in existing_aliases:
                aliases.append(alias)
                existing_aliases.add(norm)
                changed = True

    if changed:
        data["version"] = data.get("version", "2.0")
        data["terms"] = user_terms
        dest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def ensure_vocabulary_file(app_dir: Path) -> Path:
    """Create or upgrade user vocabulary.json from bundled defaults."""
    dest = vocabulary_path(app_dir)
    if not dest.is_file():
        default = _assets_dir() / "vocabulary.default.json"
        if default.is_file():
            shutil.copy2(default, dest)
        else:
            dest.write_text(
                json.dumps({"version": "2.0", "terms": load_bundled_terms()}, indent=2) + "\n",
                encoding="utf-8",
            )
    merge_bundled_terms_into_user_file(app_dir)
    return dest


def _normalize_phrase(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9'\s.+#]+", " ", text)
    return " ".join(text.split())


@dataclass
class _TermMeta:
    term: str
    category: str = "general"
    conflicts: list[str] = field(default_factory=list)


class VocabularyStore:
    """Editable glossary used to bias Whisper and fix homophones after transcription."""

    def __init__(self, app_dir: Path, fuzzy_threshold: int = 82):
        self.app_dir = app_dir
        self.fuzzy_threshold = fuzzy_threshold
        self.path = ensure_vocabulary_file(app_dir)
        self._mtime: float | None = None
        self._terms: list[dict] = []
        self._term_meta: dict[str, _TermMeta] = {}
        self._alias_patterns: list[tuple[str, str]] = []
        self._fuzzy_patterns: list[tuple[str, str, str]] = []
        self.reload()

    def reload(self) -> None:
        merge_bundled_terms_into_user_file(self.app_dir)
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {"terms": []}
        self._mtime = self.path.stat().st_mtime if self.path.exists() else None
        self._terms = list(data.get("terms", []))
        self._term_meta = {}
        self._alias_patterns = []
        self._fuzzy_patterns = []
        seen: set[str] = set()

        for entry in self._terms:
            term = str(entry.get("term", "")).strip()
            if not term:
                continue
            category = str(entry.get("category", "general")).strip().lower() or "general"
            conflicts = [str(c).strip() for c in entry.get("conflicts", []) if str(c).strip()]
            self._term_meta[term.lower()] = _TermMeta(
                term=term,
                category=category,
                conflicts=conflicts,
            )
            canonical = term
            norm_term = _normalize_phrase(term)
            if norm_term and norm_term not in seen:
                self._fuzzy_patterns.append((norm_term, canonical, category))
                seen.add(norm_term)
            for alias in entry.get("aliases", []):
                alias_text = str(alias).strip()
                if not alias_text:
                    continue
                norm_alias = _normalize_phrase(alias_text)
                if not norm_alias or norm_alias in seen:
                    continue
                self._alias_patterns.append((alias_text, canonical))
                self._fuzzy_patterns.append((norm_alias, canonical, category))
                seen.add(norm_alias)

        self._alias_patterns.sort(key=lambda item: len(item[0]), reverse=True)
        self._fuzzy_patterns.sort(key=lambda item: len(item[0]), reverse=True)

    def _maybe_reload(self) -> None:
        if not self.path.exists():
            return
        mtime = self.path.stat().st_mtime
        if self._mtime != mtime:
            self.reload()

    def whisper_prompt(self, max_terms: int = 120) -> str:
        """Comma-separated terms to nudge Whisper — names and tech prioritized."""
        self._maybe_reload()
        priority: list[str] = []
        general: list[str] = []
        for entry in self._terms:
            term = str(entry.get("term", "")).strip()
            if not term:
                continue
            category = str(entry.get("category", "general")).lower()
            if category in ("name", "tech"):
                priority.append(term)
            else:
                general.append(term)
        names = (priority + general)[:max_terms]
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
        return re.sub(r"^[^\w'+#]+|[^\w'+#]+$", "", token).lower()

    def _context_window(self, text: str, start: int, end: int, radius: int = 80) -> str:
        return text[max(0, start - radius) : min(len(text), end + radius)]

    def _context_scores(self, context: str) -> tuple[int, int]:
        return len(_TECH_CONTEXT.findall(context)), len(_NAME_CONTEXT.findall(context))

    def _looks_like_name_token(self, phrase: str) -> bool:
        return phrase.isalpha() and len(phrase) >= 3

    def _meta_for(self, canonical: str) -> _TermMeta:
        return self._term_meta.get(
            canonical.lower(),
            _TermMeta(term=canonical, category="general"),
        )

    def _conflict_options(self, canonical: str) -> list[str]:
        meta = self._meta_for(canonical)
        options = [meta.term]
        options.extend(meta.conflicts)
        return options

    def _choose_with_context(
        self,
        phrase: str,
        candidates: list[tuple[str, int]],
        context: str,
    ) -> str | None:
        if not candidates:
            return None

        scored: list[tuple[str, int, str, int]] = []
        for canonical, match_score in candidates:
            meta = self._meta_for(canonical)
            scored.append((canonical, match_score, meta.category, 0))

        tech_hits, name_hits = self._context_scores(context)

        if len(candidates) == 1:
            canonical, match_score, category, _ = scored[0]
            meta = self._meta_for(canonical)
            if meta.conflicts:
                pool = [(c, match_score if c == canonical else self.fuzzy_threshold) for c in self._conflict_options(canonical)]
                return self._choose_with_context(phrase, pool, context)
            if category == "tech" and self._looks_like_name_token(phrase) and tech_hits <= name_hits:
                return None
            if category == "name" and tech_hits > name_hits and not name_hits:
                return None
            return canonical

        best: str | None = None
        best_score = -1
        for canonical, match_score, category, _ in scored:
            context_bonus = 0
            if category == "tech":
                context_bonus = tech_hits * 5
            elif category == "name":
                context_bonus = name_hits * 5
            total = match_score + context_bonus
            if total > best_score:
                best_score = total
                best = canonical

        if best is None:
            return None

        winner_meta = self._meta_for(best)
        if tech_hits == name_hits == 0 and winner_meta.conflicts:
            return None
        if (
            winner_meta.category == "tech"
            and self._looks_like_name_token(phrase)
            and tech_hits <= name_hits
        ):
            name_candidate = next(
                (c for c, _, cat, _ in scored if cat == "name"),
                None,
            )
            if name_candidate and name_hits > 0:
                return name_candidate
            if tech_hits == 0:
                return None
        return best

    def _score_fuzzy_match(self, phrase: str, pattern: str) -> int:
        if not phrase or not pattern:
            return 0
        score = int(fuzz.ratio(phrase, pattern))
        phrase_words = phrase.split()
        pattern_words = pattern.split()
        if len(pattern_words) != len(phrase_words):
            score -= 12 * abs(len(pattern_words) - len(phrase_words))
        if len(phrase) <= 1:
            return score if phrase == pattern else 0
        if len(phrase) == 2 and score < 95:
            return 0
        if phrase in {"c", "see"} and pattern in {
            "c++",
            "cpp",
            "c#",
            "c plus",
            "c plus plus",
        }:
            return 0
        if phrase in {"txt", "text"} and "exe" in pattern:
            return 0
        if phrase == "text file" and "executable" in pattern:
            return 0
        if phrase == "faster whisper" and pattern == "faster wisper":
            return score
        if score < self.fuzzy_threshold:
            return 0
        return score

    def _choose_c_family(
        self,
        phrase: str,
        candidates: list[tuple[str, int]],
        context: str,
    ) -> str | None:
        labels = {canonical for canonical, _ in candidates}
        if not labels.intersection({"C", "C++", "C#"}):
            return None
        if _C_PLUS_CONTEXT.search(context) or phrase in {"c plus plus", "cpp", "see plus plus"}:
            return "C++" if "C++" in labels else None
        if phrase in {"c", "see"} and "plus" not in context.lower():
            if "C" in labels:
                return "C"
        if phrase in {"c", "see"} and "C" in labels and "C++" not in labels:
            return "C"
        return None

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

                candidates: list[tuple[str, int]] = []
                for pattern, canonical, _category in self._fuzzy_patterns:
                    if abs(len(pattern.split()) - n) > 1 and n > 1:
                        continue
                    score = self._score_fuzzy_match(phrase, pattern)
                    if score > 0:
                        candidates.append((canonical, score))

                if not candidates:
                    continue

                candidates.sort(key=lambda item: item[1], reverse=True)
                top_score = candidates[0][1]
                close = [c for c in candidates if c[1] >= top_score - 3]
                first = matches[i]
                last = matches[i + n - 1]
                context = self._context_window(text, first.start(), last.end())
                c_family = self._choose_c_family(phrase, close, context)
                if c_family:
                    chosen = c_family
                else:
                    chosen = self._choose_with_context(phrase, close, context)
                if not chosen:
                    continue

                replacements.append((i, i + n, chosen))
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
            data = {"version": "2.0"}
        data["terms"] = self._terms
        self.path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        self._mtime = self.path.stat().st_mtime
