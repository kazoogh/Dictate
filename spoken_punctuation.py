"""Convert spoken punctuation and symbol commands into real characters.

Used for Quick Dictate when the user says things like ``comma``, ``period``,
``at symbol``, or ``dot com`` instead of typing punctuation.
"""

from __future__ import annotations

import re

# Multi-word phrases — longest / most specific first.
_SPOKEN_PHRASES: list[tuple[re.Pattern[str], str]] = [
  (re.compile(r"\bdot\s+com\b", re.I), ".com"),
  (re.compile(r"\bdot\s+org\b", re.I), ".org"),
  (re.compile(r"\bdot\s+net\b", re.I), ".net"),
  (re.compile(r"\bdot\s+edu\b", re.I), ".edu"),
  (re.compile(r"\bdot\s+gov\b", re.I), ".gov"),
  (re.compile(r"\bdot\s+io\b", re.I), ".io"),
  (re.compile(r"\bdot\s+co\b", re.I), ".co"),
  (re.compile(r"\bat\s+symbol\b", re.I), "@"),
  (re.compile(r"\bat\s+sign\b", re.I), "@"),
  (re.compile(r"\bexclamation\s+(?:mark|point)\b", re.I), "!"),
  (re.compile(r"\bquestion\s+mark\b", re.I), "?"),
  (re.compile(r"\bquotation\s+marks?\b", re.I), '"'),
  (re.compile(r"\bdouble\s+quotes?\b", re.I), '"'),
  (re.compile(r"\bopen\s+(?:quotation\s+)?quote\b", re.I), '"'),
  (re.compile(r"\bclose\s+(?:quotation\s+)?quote\b", re.I), '"'),
  (re.compile(r"\bleft\s+(?:quotation\s+)?quote\b", re.I), '"'),
  (re.compile(r"\bright\s+(?:quotation\s+)?quote\b", re.I), '"'),
  (re.compile(r"\bopen\s+parenthesis\b", re.I), "("),
  (re.compile(r"\bclose\s+parenthesis\b", re.I), ")"),
  (re.compile(r"\bleft\s+parenthesis\b", re.I), "("),
  (re.compile(r"\bright\s+parenthesis\b", re.I), ")"),
  (re.compile(r"\bopen\s+bracket\b", re.I), "["),
  (re.compile(r"\bclose\s+bracket\b", re.I), "]"),
  (re.compile(r"\bleft\s+bracket\b", re.I), "["),
  (re.compile(r"\bright\s+bracket\b", re.I), "]"),
  (re.compile(r"\bopen\s+brace\b", re.I), "{"),
  (re.compile(r"\bclose\s+brace\b", re.I), "}"),
  (re.compile(r"\bleft\s+brace\b", re.I), "{"),
  (re.compile(r"\bright\s+brace\b", re.I), "}"),
  (re.compile(r"\bnew\s*-?\s*line\b", re.I), "\n"),
  (re.compile(r"\bline\s+break\b", re.I), "\n"),
  (re.compile(r"\bcarriage\s+return\b", re.I), "\n"),
  (re.compile(r"\bforward\s+slash\b", re.I), "/"),
  (re.compile(r"\bback\s+slash\b", re.I), "\\"),
  (re.compile(r"\bfull\s+stop\b", re.I), "."),
  (re.compile(r"\bequal\s+sign\b", re.I), "="),
  (re.compile(r"\bequals\s+sign\b", re.I), "="),
  (re.compile(r"\bplus\s+sign\b", re.I), "+"),
  (re.compile(r"\bminus\s+sign\b", re.I), "-"),
  (re.compile(r"\bpercent\s+sign\b", re.I), "%"),
  (re.compile(r"\bdollar\s+sign\b", re.I), "$"),
  (re.compile(r"\bpound\s+sign\b", re.I), "#"),
  (re.compile(r"\bnumber\s+sign\b", re.I), "#"),
  (re.compile(r"\bhash\s+sign\b", re.I), "#"),
  (re.compile(r"\bampersand\s+sign\b", re.I), "&"),
  (re.compile(r"\bellipsis\b", re.I), "..."),
  (re.compile(r"\bellipses\b", re.I), "..."),
  (re.compile(r"\bem\s+dash\b", re.I), "—"),
  (re.compile(r"\ben\s+dash\b", re.I), "–"),
]

# Single-word commands — longer keys first when building the alternation.
_SPOKEN_WORDS: dict[str, str] = {
  "underscore": "_",
  "asterisk": "*",
  "ampersand": "&",
  "backtick": "`",
  "comma": ",",
  "period": ".",
  "semicolon": ";",
  "apostrophe": "'",
  "backslash": "\\",
  "newline": "\n",
  "enter": "\n",
  "return": "\n",
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

_SPOKEN_WORD_PATTERN = re.compile(
  r"\b(?:"
  + "|".join(re.escape(word) for word in sorted(_SPOKEN_WORDS, key=len, reverse=True))
  + r")\b",
  re.IGNORECASE,
)


def _normalize_symbol_spacing(text: str) -> str:
  """Collapse extra spaces around inserted punctuation and symbols."""
  text = re.sub(r"[ \t]+", " ", text)

  # Contractions: don ' t -> don't
  text = re.sub(r"(\w)\s+'\s+(\w)", r"\1'\2", text, flags=re.IGNORECASE)

  # Email / domain tightening: user @ gmail .com -> user@gmail.com
  text = re.sub(r"(\w)\s+@", r"\1@", text)
  text = re.sub(r"@\s+(\w)", r"@\1", text)
  text = re.sub(
    r"(\w)\s+\.(com|org|net|edu|gov|io|co)\b",
    r"\1.\2",
    text,
    flags=re.IGNORECASE,
  )

  # Windows paths: C : \ Users \ test -> C:\Users\test
  text = re.sub(r"(\w)\s*:\s*(?=\\)", r"\1:", text)
  text = re.sub(r"\\\s*(\w)", r"\\\1", text)

  # Forward slashes between words: home / user -> home/user
  text = re.sub(r"(?<=\w)\s*/\s*(?=\w)", "/", text)

  # Standard punctuation spacing
  text = re.sub(r"\s+([,.;:!?])", r"\1", text)
  text = re.sub(r"([,.;:!?])\s+", r"\1 ", text)
  text = re.sub(r"\s+([)\]}])", r"\1", text)
  text = re.sub(r"([(\[{])\s+", r"\1", text)

  # Quotes — trim spaces inside paired straight double quotes
  text = re.sub(r'"\s+([^"]+?)\s*"', r'"\1"', text)

  # Path slashes: https: / / example
  text = re.sub(r"/\s+/", "//", text)
  text = re.sub(r":\s+/", ":/", text)

  # Newlines / tabs
  text = re.sub(r" *\n *", "\n", text)
  text = re.sub(r" *\t *", "\t", text)

  # Collapse duplicate spaces (but keep newlines)
  text = re.sub(r"[^\S\n]+", " ", text)
  return text.strip()


def apply_spoken_punctuation(text: str) -> str:
  """Replace spoken punctuation commands with real symbols."""
  if not text or not text.strip():
    return text

  text = re.sub(r"\s+", " ", text.strip())

  for pattern, replacement in _SPOKEN_PHRASES:
    text = pattern.sub(lambda _m, r=replacement: f" {r} ", text)

  def _word_replacer(match: re.Match[str]) -> str:
    word = match.group(0).lower()
    symbol = _SPOKEN_WORDS[word]
    return f" {symbol} "

  text = _SPOKEN_WORD_PATTERN.sub(_word_replacer, text)
  return _normalize_symbol_spacing(text)
