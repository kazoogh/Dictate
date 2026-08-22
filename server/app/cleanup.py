"""Text cleanup: basic rules and optional OpenAI polish."""

from __future__ import annotations

import json
import logging
import re
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Literal

from app import config

logger = logging.getLogger("dictate.cleanup")

CleanupMode = Literal["basic", "openai"]

CLEANUP_SYSTEM_PROMPT = (
    "You are polishing a voice dictation transcript.\n"
    "Fix grammar, punctuation, casing, paragraph structure, and obvious speech-to-text errors.\n"
    "Preserve the speaker's meaning.\n"
    "Do not add new facts.\n"
    "Do not remove important details.\n"
    "Keep names, dates, numbers, phone numbers, emails, addresses, codes, and dollar amounts "
    "unchanged unless clearly misheard.\n"
    "Do not make clinical, legal, billing, insurance, or HR conclusions.\n"
    "Return only the corrected text."
)

_FILLER_WORDS = frozenset(
    {
        "um",
        "uh",
        "uhh",
        "umm",
        "uhm",
        "hmm",
        "hm",
        "er",
        "ah",
        "ahh",
        "eh",
        "mmm",
        "mm",
        "mhm",
    }
)

_FILLER_PATTERN = re.compile(
    r"\b(?:"
    + "|".join(re.escape(word) for word in sorted(_FILLER_WORDS, key=len, reverse=True))
    + r")\b[,.]?\s*",
    re.IGNORECASE,
)

_MULTI_SPACE = re.compile(r"[ \t]+")
_MULTI_NEWLINE = re.compile(r"\n{3,}")
_SENTENCE_END = re.compile(r"([.!?])\s+([a-z])")


@dataclass
class CleanupResult:
    text: str
    mode_used: CleanupMode
    cleanup_error: str | None = None


def simple_cleanup(text: str) -> str:
    """Lightweight local cleanup without external APIs."""
    cleaned = text.strip()
    if not cleaned:
        return ""

    cleaned = _FILLER_PATTERN.sub("", cleaned)
    cleaned = _MULTI_SPACE.sub(" ", cleaned)
    cleaned = _MULTI_NEWLINE.sub("\n\n", cleaned)

    paragraphs = []
    for paragraph in cleaned.split("\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        paragraph = paragraph[0].upper() + paragraph[1:] if paragraph else paragraph
        paragraph = _SENTENCE_END.sub(lambda m: f"{m.group(1)} {m.group(2).upper()}", paragraph)
        if paragraph and paragraph[-1] not in ".!?":
            paragraph += "."
        paragraphs.append(paragraph)

    return "\n\n".join(paragraphs).strip()


def _openai_cleanup(text: str) -> str:
    if not config.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    payload: dict = {
        "model": config.OPENAI_CLEANUP_MODEL,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": CLEANUP_SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
    }
    if config.OPENAI_MAX_TOKENS and config.OPENAI_MAX_TOKENS > 0:
        payload["max_tokens"] = config.OPENAI_MAX_TOKENS
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {config.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
    )
    context = ssl.create_default_context()
    try:
        with urllib.request.urlopen(
            request, timeout=config.OPENAI_CLEANUP_TIMEOUT, context=context
        ) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI HTTP {exc.code}: {err_body[:200]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"OpenAI request failed: {exc.reason}") from exc

    data = json.loads(raw)
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("OpenAI returned no choices")
    message = choices[0].get("message") or {}
    content = str(message.get("content", "")).strip()
    if not content:
        raise RuntimeError("OpenAI returned empty content")
    return content


def polish_text(text: str, mode: CleanupMode | None = None) -> CleanupResult:
    """Apply cleanup using requested mode, with OpenAI fallback to basic."""
    raw = text.strip()
    if not raw:
        return CleanupResult(text="", mode_used="basic")

    selected: CleanupMode = mode or config.CLEANUP_MODE  # type: ignore[assignment]
    if selected not in {"basic", "openai"}:
        selected = "basic"

    if selected == "basic":
        return CleanupResult(text=simple_cleanup(raw), mode_used="basic")

    try:
        polished = _openai_cleanup(raw)
        return CleanupResult(text=polished, mode_used="openai")
    except Exception as exc:
        logger.warning("OpenAI cleanup failed, falling back to basic: %s", exc)
        return CleanupResult(
            text=simple_cleanup(raw),
            mode_used="basic",
            cleanup_error=str(exc)[:300],
        )
