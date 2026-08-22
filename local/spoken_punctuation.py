"""Convert spoken punctuation and symbol commands into real characters.

Quick Dictate uses :func:`iter_spoken_commands` to split a transcript into plain
speech and explicit dictation commands, then :func:`merge_punctuated_pieces` to
reassemble ONNX output with user-dictated symbols.
"""

from __future__ import annotations

import re
from typing import Iterator

# Multi-word phrases — longest / most specific first.
_SPOKEN_PHRASES: list[tuple[str, str]] = [
    (r"\bdot\s+com\b", ".com"),
    (r"\bdot\s+org\b", ".org"),
    (r"\bdot\s+net\b", ".net"),
    (r"\bdot\s+edu\b", ".edu"),
    (r"\bdot\s+gov\b", ".gov"),
    (r"\bdot\s+io\b", ".io"),
    (r"\bdot\s+co\b", ".co"),
    (r"\bat\s+symbol\b", "@"),
    (r"\bat\s+sign\b", "@"),
    (r"\bdouble\s+exclamations?\b", "!!"),
    (r"\bdouble\s+exclamation\s+(?:marks?|points?)\b", "!!"),
    (r"\bexclamation\s+(?:mark|point)\b", "!"),
    (r"\bquestion\s+mark\b", "?"),
    (r"\bquotation\s+marks?\b", '"'),
    (r"\bdouble\s+quotes?\b", '"'),
    (r"\bopen\s+(?:quotation\s+)?quote\b", '"'),
    (r"\bclose\s+(?:quotation\s+)?quote\b", '"'),
    (r"\bleft\s+(?:quotation\s+)?quote\b", '"'),
    (r"\bright\s+(?:quotation\s+)?quote\b", '"'),
    (r"\bopen\s+parenthesis\b", "("),
    (r"\bclose\s+parenthesis\b", ")"),
    (r"\bleft\s+parenthesis\b", "("),
    (r"\bright\s+parenthesis\b", ")"),
    (r"\bopen\s+bracket\b", "["),
    (r"\bclose\s+bracket\b", "]"),
    (r"\bleft\s+bracket\b", "["),
    (r"\bright\s+bracket\b", "]"),
    (r"\bopen\s+brace\b", "{"),
    (r"\bclose\s+brace\b", "}"),
    (r"\bleft\s+brace\b", "{"),
    (r"\bright\s+brace\b", "}"),
    (r"\bnew\s*-?\s*line\b", "\n"),
    (r"\bline\s+break\b", "\n"),
    (r"\bcarriage\s+return\b", "\n"),
    (r"\bforward\s+slash\b", "/"),
    (r"\bback\s+slash\b", "\\"),
    (r"\bsemi\s+colon\b", ";"),
    (r"\bfull\s+stop\b", "."),
    (r"\bequal\s+sign\b", "="),
    (r"\bequals\s+sign\b", "="),
    (r"\bplus\s+sign\b", "+"),
    (r"\bminus\s+sign\b", "-"),
    (r"\bpercent\s+sign\b", "%"),
    (r"\bdollar\s+sign\b", "$"),
    (r"\bpound\s+sign\b", "#"),
    (r"\bnumber\s+sign\b", "#"),
    (r"\bhash\s+sign\b", "#"),
    (r"\bampersand\s+sign\b", "&"),
    (r"\bellipsis\b", "..."),
    (r"\bellipses\b", "..."),
    (r"\bem\s+dash\b", "—"),
    (r"\ben\s+dash\b", "–"),
]

# Whisper often garbles spoken punctuation commands — map back before parsing.
_WHISPER_PUNCT_MISHEARS: list[tuple[str, str]] = [
    (r"\bOr\s*!\b", "exclamation mark"),
    (r"\bOr\s*\?\b", "question mark"),
    (r"\bOr\s*:\b", "colon"),
    (r"\bSemi\.?\b", "semicolon"),
    (r"\bsemi\b(?=\s*(?:colon|[,.!?;:]|$))", "semicolon"),
    (r"\bexclamation\s+point\b", "exclamation mark"),
    (r"\bquestion\s+point\b", "question mark"),
]

_WHISPER_MISHEAR_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(src, re.IGNORECASE), repl) for src, repl in _WHISPER_PUNCT_MISHEARS
]

_FINAL_PERIOD_AS_SEMICOLON = re.compile(r"(\w)\.(?=\s*$)")

_SPOKEN_WORDS: dict[str, str] = {
    "underscore": "_",
    "asterisk": "*",
    "ampersand": "&",
    "backtick": "`",
    "semicolon": ";",
    "apostrophe": "'",
    "backslash": "\\",
    "newline": "\n",
    "enter": "\n",
    "return": "\n",
    "comma": ",",
    "period": ".",
    "slash": "/",
    "dot": ".",
    "colon": ":",
    "hyphen": "-",
    "dash": "-",
    "hash": "#",
    "dollar": "$",
    "percent": "%",
    "plus": "+",
    "equals": "=",
    "equal": "=",
    "pipe": "|",
    "tilde": "~",
    "caret": "^",
    "star": "*",
    "bang": "!",
    "tab": "\t",
}

_COMMAND_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    *((re.compile(src, re.IGNORECASE), sym) for src, sym in _SPOKEN_PHRASES),
    *(
        (re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE), sym)
        for word, sym in sorted(_SPOKEN_WORDS.items(), key=lambda item: -len(item[0]))
    ),
]


def _repair_final_period_as_semicolon(text: str) -> str:
    """Whisper often turns a final dictated semicolon into a period on the last word."""
    if len(re.findall(r"[?!:;]", text)) < 2:
        return text
    return _FINAL_PERIOD_AS_SEMICOLON.sub(r"\1;", text)


def repair_whisper_punctuation_mishears(text: str) -> str:
    """Rewrite common Whisper mis-hearings of spoken punctuation commands."""
    text = re.sub(r"\b(\w+)\.\s+Semi\.?\b", r" \1 semicolon ", text, flags=re.IGNORECASE)
    for pattern, replacement in _WHISPER_MISHEAR_PATTERNS:
        text = pattern.sub(f" {replacement} ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return _repair_final_period_as_semicolon(text)


def _find_earliest_command(text: str, start: int) -> tuple[re.Match[str], str] | None:
    best: tuple[re.Match[str], str] | None = None
    for pattern, symbol in _COMMAND_PATTERNS:
        match = pattern.search(text, start)
        if match is None:
            continue
        if best is None:
            best = (match, symbol)
            continue
        bmatch, _ = best
        if match.start() < bmatch.start():
            best = (match, symbol)
        elif match.start() == bmatch.start() and match.end() > bmatch.end():
            best = (match, symbol)
    return best


def iter_spoken_commands(text: str) -> Iterator[tuple[str, str]]:
    """Yield alternating ``("text", chunk)`` and ``("punct", symbol)`` pieces."""
    if not text or not text.strip():
        return

    normalized = repair_whisper_punctuation_mishears(text)
    normalized = re.sub(r"\s+", " ", normalized.strip())
    pos = 0
    while pos < len(normalized):
        found = _find_earliest_command(normalized, pos)
        if found is None:
            tail = normalized[pos:].strip()
            if tail:
                yield ("text", tail)
            break
        match, symbol = found
        if match.start() > pos:
            chunk = normalized[pos : match.start()].strip()
            if chunk:
                yield ("text", chunk)
        yield ("punct", symbol)
        pos = match.end()


def merge_punctuated_pieces(pieces: list[str]) -> str:
    """Join processed text chunks and dictated symbols with sensible spacing."""
    if not pieces:
        return ""

    out: list[str] = []
    for piece in pieces:
        if not piece:
            continue
        if not out:
            out.append(piece)
            continue

        prev = out[-1]
        if piece in "\n\t":
            out.append(piece)
            continue
        if piece in ",;:!?":
            if prev and prev[-1] in ",;:!?":
                out[-1] = prev.rstrip() + " " + piece
            else:
                out[-1] = prev.rstrip() + piece
            continue
        if piece in ("...", "!!"):
            out[-1] = prev.rstrip() + piece
            continue
        if piece in "-—–":
            out[-1] = prev.rstrip() + piece
            continue
        if piece in "@#$/\\|~^%+=)]}\"'":
            if prev and prev[-1].isalnum() and piece in "@":
                out[-1] = prev.rstrip() + piece
            elif prev and prev[-1].isalnum() and piece in ".com":
                out[-1] = prev.rstrip() + piece
            elif piece.startswith(".") and len(piece) > 1:
                out[-1] = prev.rstrip() + piece
            else:
                out.append(piece)
            continue
        if piece in "([{\"'":
            if prev and not prev.endswith((" ", "\n")):
                out.append(" " + piece)
            else:
                out.append(piece)
            continue
        if prev.endswith(("\n", "\t")):
            out.append(piece)
        elif prev and prev[-1] in ",;:!?…":
            out.append(" " + piece.lstrip())
        elif prev and prev[-1] in "-—–":
            out.append(" " + piece.lstrip())
        elif prev and prev[-1] in "@(/[{\"'":
            out.append(piece)
        elif prev and prev[-1] in ")]}\"'":
            if piece[0] in ",;:.!?)]}\"'":
                out[-1] = prev.rstrip() + piece
            else:
                out.append(" " + piece.lstrip())
        else:
            out.append(" " + piece.lstrip())

    return normalize_symbol_spacing("".join(out))


def normalize_symbol_spacing(text: str) -> str:
    """Collapse extra spaces around inserted punctuation and symbols."""
    text = re.sub(r"[ \t]+", " ", text)

    text = re.sub(r"(\w)\s+'\s+(\w)", r"\1'\2", text, flags=re.IGNORECASE)
    text = re.sub(r"(\w)\s+@\s*(\w)", r"\1@\2", text)
    text = re.sub(
        r"(\w)\s+\.(com|org|net|edu|gov|io|co)\b",
        r"\1.\2",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"(\w)\s*:\s*(?=\\)", r"\1:", text)
    text = re.sub(r"\\\s*(\w)", r"\\\1", text)
    text = re.sub(r"(?<=\w)\s*/\s*(?=\w)", "/", text)

    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([,.;:!?])\s+", r"\1 ", text)
    text = re.sub(r"\s+([)\]}])", r"\1", text)
    text = re.sub(r"([(\[{])\s+", r"\1", text)
    text = re.sub(r'"\s+([^"]+?)\s*"', r'"\1"', text)
    text = re.sub(r"/\s+/", "//", text)
    text = re.sub(r":\s+/", ":/", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r" *\t *", "\t", text)
    text = re.sub(r"[^\S\n]+", " ", text)
    return text.strip()


def apply_spoken_punctuation(text: str) -> str:
    """Replace every spoken command in one pass (no ONNX cooperation)."""
    pieces: list[str] = []
    for kind, value in iter_spoken_commands(text):
        pieces.append(value)
    return merge_punctuated_pieces(pieces)
