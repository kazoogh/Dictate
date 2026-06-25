"""Unit tests for spoken punctuation commands."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from spoken_punctuation import apply_spoken_punctuation, repair_whisper_punctuation_mishears
from transcript_cleanup import TranscriptCleaner, remove_fillers

CASES = [
    ("hello comma world", "hello, world"),
    ("hello period", "hello."),
    ("don apostrophe t", "don't"),
    ("see you at symbol gmail dot com", "see you@gmail.com"),
    ("visit example dot org", "visit example.org"),
    ("wow double exclamation mark", "wow!!"),
    ("really question mark", "really?"),
    ("end semicolon next", "end; next"),
    (
        "telegram, Microsoft, Or! Or? Or: Semi.",
        "Telegram, Microsoft! ? : ;",
    ),
]

failed = 0
for raw, expected in CASES:
    repaired = repair_whisper_punctuation_mishears(raw)
    got = apply_spoken_punctuation(repaired)
    if got != expected:
        # Full pipeline may capitalize via transcript cleaner
        cleaner = TranscriptCleaner()
        got = cleaner.clean(
            repaired,
            remove_fillers_enabled=False,
            add_punctuation=False,
        )
    if got != expected:
        failed += 1
        print(f"FAIL: {raw!r}")
        print(f"  expected: {expected!r}")
        print(f"  got:      {got!r}")
    else:
        print(f"OK: {raw!r}")

if failed:
    print(f"\n{failed} failed")
    sys.exit(1)
print(f"\nAll {len(CASES)} passed")
