"""Learn vocabulary corrections when the user edits pasted dictation."""

from __future__ import annotations

import difflib
import re
import time
from dataclasses import dataclass

from vocabulary import VocabularyStore

_STOPWORDS = frozenset(
    """
    a an the and or but if in on at to for of is are was were be been being
    i you he she it we they my your his her its our their this that these those
    not no yes so do does did done have has had will would can could should may
    might must am as by with from up down out about into over after before
    """.split()
)

_TOKEN_RE = re.compile(r"\S+")


@dataclass
class _LastPaste:
    text: str
    at: float


class PasteLearner:
    """Compare last pasted text to the focused field on the next dictate."""

    def __init__(self, vocabulary: VocabularyStore, max_age_seconds: float = 3600.0):
        self.vocabulary = vocabulary
        self.max_age_seconds = max_age_seconds
        self._last: _LastPaste | None = None

    def remember(self, text: str) -> None:
        cleaned = text.strip()
        if cleaned:
            self._last = _LastPaste(text=cleaned, at=time.time())

    def clear(self) -> None:
        self._last = None

    def check_and_learn(self, current_text: str) -> list[tuple[str, str]]:
        """Return learned (term, alias) pairs and update vocabulary."""
        if self._last is None:
            return []

        pasted = self._last.text
        pasted_at = self._last.at
        self._last = None

        if time.time() - pasted_at > self.max_age_seconds:
            return []

        current = (current_text or "").strip()
        if not current or pasted == current:
            return []

        pairs = extract_word_corrections(pasted, current)
        learned: list[tuple[str, str]] = []
        for alias, term in pairs:
            if self.vocabulary.add_learned_correction(term, alias):
                learned.append((term, alias))
        return learned


def _is_learnable(old: str, new: str) -> bool:
    old = old.strip()
    new = new.strip()
    if len(old) < 2 or len(new) < 2:
        return False
    if old.lower() == new.lower():
        return False
    if old.lower() in _STOPWORDS and new.lower() in _STOPWORDS:
        return False
    if not _TOKEN_RE.fullmatch(old) or not _TOKEN_RE.fullmatch(new):
        return False
    return True


def _word_replace_corrections(
    pasted_words: list[str], current_words: list[str]
) -> list[tuple[str, str]]:
    if not pasted_words or not current_words:
        return []
    if abs(len(pasted_words) - len(current_words)) > 4:
        return []

    sm = difflib.SequenceMatcher(None, pasted_words, current_words, autojunk=False)
    corrections: list[tuple[str, str]] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "replace":
            continue
        if (i2 - i1) != 1 or (j2 - j1) != 1:
            continue
        old_word = pasted_words[i1]
        new_word = current_words[j1]
        if _is_learnable(old_word, new_word):
            corrections.append((old_word, new_word))
    return corrections


def extract_word_corrections(pasted: str, current: str) -> list[tuple[str, str]]:
    """
    Find single-word substitutions between pasted and current text.
    Returns (alias, term) where alias was pasted and term is the user's fix.
    """
    if pasted == current or pasted in current:
        return []

    pasted_words = pasted.split()
    current_words = current.split()
    if not pasted_words or not current_words:
        return []

    ratio = difflib.SequenceMatcher(None, pasted, current, autojunk=False).ratio()
    if ratio < 0.25 and len(pasted_words) > 1:
        return []

    # Pasted snippet edited inside a larger field (e.g. "John" in "Dear Johnny").
    n = len(pasted_words)
    for i in range(0, len(current_words) - n + 1):
        window = current_words[i : i + n]
        window_ratio = difflib.SequenceMatcher(None, pasted_words, window, autojunk=False).ratio()
        if window_ratio < 0.55:
            continue
        corrections = _word_replace_corrections(pasted_words, window)
        if corrections:
            return corrections

    corrections = _word_replace_corrections(pasted_words, current_words)
    if corrections:
        return corrections

    if len(pasted_words) == 1 and len(current_words) == 1:
        if _is_learnable(pasted_words[0], current_words[0]):
            return [(pasted_words[0], current_words[0])]

    return []
