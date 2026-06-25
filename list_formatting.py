"""Detect dictated ordinal lists and format them as bullet points."""

from __future__ import annotations

import re

_ORDINAL_WORD = (
    r"(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|eleventh|twelfth)"
)
_NUMBER_WORD = r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d{1,2})"

# Detect where each list item begins in the transcript.
_LIST_ITEM_START = re.compile(
    r"(?i)"
    r"(?:the\s+)?"
    r"(?:"
    rf"{_ORDINAL_WORD}(?:\s+thing)?\s+is"
    r"|"
    rf"{_ORDINAL_WORD}ly"
    r"|"
    r"(?:1st|2nd|3rd|\d{1,2}th)(?:\s+thing)?(?:\s+is)?"
    r"|"
    rf"number\s+{_NUMBER_WORD}(?:\s+is)?"
    r"|"
    rf"step\s+{_NUMBER_WORD}(?:\s+is)?"
    r")"
)

# Strip the ordinal lead-in from each bullet (e.g. "The second thing is" -> "").
_LIST_ITEM_PREFIX = re.compile(
    r"(?i)^"
    r"(?:the\s+)?"
    r"(?:"
    rf"{_ORDINAL_WORD}(?:\s+thing)?\s+is"
    r"|"
    rf"{_ORDINAL_WORD}ly"
    r"|"
    r"(?:1st|2nd|3rd|\d{1,2}th)(?:\s+thing)?(?:\s+is)?"
    r"|"
    rf"number\s+{_NUMBER_WORD}(?:\s+is)?"
    r"|"
    rf"step\s+{_NUMBER_WORD}(?:\s+is)?"
    r")"
    r"\s*[,:-]?\s*"
)

_OUTRO_STARTERS = re.compile(
    r"(?i)^(?:so|and|also|finally|anyway|please|in conclusion|to wrap up|that's all|now)\b"
)

_MIN_LIST_ITEMS = 2


def looks_like_dictated_list(text: str) -> bool:
    """True when the transcript contains at least two dictated list markers."""
    return len(list(_LIST_ITEM_START.finditer(text))) >= _MIN_LIST_ITEMS


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"((?<=[.!?])\s+)", text.strip())
    return [part.strip() for part in parts if part.strip()]


def _peel_outro_from_last_item(last_item: str) -> tuple[str, str]:
    sentences = _split_sentences(last_item)
    if len(sentences) < 2:
        return last_item, ""

    outro = sentences[-1]
    if not _OUTRO_STARTERS.match(outro):
        return last_item, ""

    item_text = " ".join(sentences[:-1]).strip()
    return item_text, outro


def _strip_list_item_prefix(item: str) -> str:
    text = _LIST_ITEM_PREFIX.sub("", item.strip(), count=1)
    text = re.sub(r"^,\s*", "", text).strip()
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    return text


def format_dictated_lists(text: str) -> str:
    """Turn dictated 'first thing is / second thing is / …' sequences into bullets."""
    if not text or not text.strip():
        return text

    matches = list(_LIST_ITEM_START.finditer(text))
    if len(matches) < _MIN_LIST_ITEMS:
        return text

    intro = text[: matches[0].start()].strip()
    items: list[str] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        items.append(text[start:end].strip())

    outro = ""
    if items:
        items[-1], outro = _peel_outro_from_last_item(items[-1])

    bullets = [f"- {_strip_list_item_prefix(item)}" for item in items if item]

    sections: list[str] = []
    if intro:
        sections.append(intro)
    sections.extend(bullets)
    if outro:
        sections.append(outro)

    return "\n".join(sections)
