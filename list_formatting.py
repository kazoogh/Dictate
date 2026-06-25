"""Detect dictated ordinal lists and format them as bullet points."""

from __future__ import annotations

import re

# "The first thing is", "second thing is", "number three", "1st thing is", etc.
_LIST_ITEM_START = re.compile(
    r"(?i)"
    r"(?:the\s+)?"
    r"(?:"
    r"(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|eleventh|twelfth)"
    r"(?:\s+thing)?\s+is"
    r"|"
    r"(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)ly"
    r"|"
    r"(?:1st|2nd|3rd|\d{1,2}th)(?:\s+thing)?(?:\s+is)?"
    r"|"
    r"number\s+(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d{1,2})"
    r"|"
    r"step\s+(?:one|two|three|four|five|six|seven|eight|nine|ten|\d{1,2})"
    r")"
)

_OUTRO_STARTERS = re.compile(
    r"(?i)^(?:so|and|also|finally|anyway|please|in conclusion|to wrap up|that's all|now)\b"
)

_MIN_LIST_ITEMS = 2


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
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

    bullets = [f"- {item}" for item in items if item]

    sections: list[str] = []
    if intro:
        sections.append(intro)
    sections.extend(bullets)
    if outro:
        sections.append(outro)

    return "\n".join(sections)
