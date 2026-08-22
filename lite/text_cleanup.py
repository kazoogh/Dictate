"""Transcript cleanup that runs entirely on this machine.

Server mode gets its cleanup from the Dictate API (which can call OpenAI).
Local mode has no server to ask, so it cleans up here instead:

  basic   fast regex rules — fillers, spacing, casing, terminal punctuation
  ollama  hand the text to a local LLM served by Ollama, falling back to
          ``basic`` if Ollama isn't running or the request fails

Nothing in this module talks to the internet. Ollama is expected on
127.0.0.1:11434, which is where ``ollama serve`` listens by default.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

logger = logging.getLogger("dictate.cleanup")

CLEANUP_SYSTEM_PROMPT = (
    "You are polishing a voice dictation transcript.\n"
    "Remove speech fillers and disfluencies (um, uh, like, you know, I mean) when they are "
    "filler rather than meaningful content.\n"
    "Collapse accidentally repeated words and obvious false starts.\n"
    "Fix grammar, punctuation, casing, and paragraph structure.\n"
    "Preserve the speaker's meaning.\n"
    "Do not add new facts.\n"
    "Do not remove important details.\n"
    "Keep names, dates, numbers, phone numbers, emails, addresses, codes, and dollar amounts "
    "unchanged unless clearly misheard.\n"
    "Return only the corrected text, with no preamble and no commentary."
)

_FILLER_WORDS = frozenset(
    {
        "um", "uh", "uhh", "umm", "uhm", "hmm", "hm",
        "er", "ah", "ahh", "eh", "mmm", "mm", "mhm",
    }
)

_FILLER_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in sorted(_FILLER_WORDS, key=len, reverse=True)) + r")\b[,.]?\s*",
    re.IGNORECASE,
)

# "the the patient" -> "the patient". Only collapses an immediate repeat of the
# same word, which is a stutter artifact rather than real English.
_REPEATED_WORD = re.compile(r"\b(\w+)(\s+\1\b)+", re.IGNORECASE)

_MULTI_SPACE = re.compile(r"[ \t]+")
_MULTI_NEWLINE = re.compile(r"\n{3,}")
_SENTENCE_END = re.compile(r"([.!?])\s+([a-z])")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.;:!?])")
# Whisper writes the pronoun as "i" often enough to be worth fixing. Only a
# standalone lowercase "i" is touched, so "i.e." and identifiers survive.
_LONE_I = re.compile(r"(?<![\w.])i(?![\w.])")


@dataclass
class CleanupResult:
    text: str
    mode_used: str
    cleanup_error: str | None = None


def simple_cleanup(text: str) -> str:
    """Rule-based cleanup. No model, no network, effectively instant."""
    cleaned = text.strip()
    if not cleaned:
        return ""

    cleaned = _FILLER_PATTERN.sub("", cleaned)
    cleaned = _REPEATED_WORD.sub(r"\1", cleaned)
    cleaned = _LONE_I.sub("I", cleaned)
    cleaned = _SPACE_BEFORE_PUNCT.sub(r"\1", cleaned)
    cleaned = _MULTI_SPACE.sub(" ", cleaned)
    cleaned = _MULTI_NEWLINE.sub("\n\n", cleaned)

    paragraphs: list[str] = []
    for paragraph in cleaned.split("\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        paragraph = paragraph[0].upper() + paragraph[1:]
        paragraph = _SENTENCE_END.sub(lambda m: f"{m.group(1)} {m.group(2).upper()}", paragraph)
        if paragraph[-1] not in ".!?":
            paragraph += "."
        paragraphs.append(paragraph)

    return "\n\n".join(paragraphs).strip()


def ollama_polish(
    text: str,
    *,
    model: str,
    base_url: str = "http://127.0.0.1:11434",
    timeout: float = 30.0,
) -> str:
    """Polish the transcript with a local Ollama model. Raises on any failure."""
    url = f"{base_url.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "stream": False,
        "options": {"temperature": 0.2},
        "messages": [
            {"role": "system", "content": CLEANUP_SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama HTTP {exc.code}: {body[:200]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Could not reach Ollama at {base_url} ({exc.reason}). Is `ollama serve` running?"
        ) from exc

    data = json.loads(raw)
    content = str((data.get("message") or {}).get("content", "")).strip()
    if not content:
        raise RuntimeError("Ollama returned empty content")
    return content


def polish_text(
    text: str,
    *,
    mode: str = "basic",
    ollama_model: str = "",
    ollama_url: str = "http://127.0.0.1:11434",
    ollama_timeout: float = 30.0,
) -> CleanupResult:
    """Clean up a transcript, degrading to ``basic`` whenever ``ollama`` can't run."""
    raw = text.strip()
    if not raw:
        return CleanupResult(text="", mode_used="basic")

    if mode != "ollama":
        return CleanupResult(text=simple_cleanup(raw), mode_used="basic")

    if not ollama_model:
        return CleanupResult(
            text=simple_cleanup(raw),
            mode_used="basic",
            cleanup_error="No Ollama model configured",
        )

    try:
        polished = ollama_polish(
            raw, model=ollama_model, base_url=ollama_url, timeout=ollama_timeout
        )
        return CleanupResult(text=polished, mode_used="ollama")
    except Exception as exc:
        logger.warning("Ollama cleanup failed, falling back to basic rules: %s", exc)
        return CleanupResult(
            text=simple_cleanup(raw),
            mode_used="basic",
            cleanup_error=str(exc)[:300],
        )
