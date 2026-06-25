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
    (
        "Just a quick example here, Telegram? Microsoft! Google: Amazon.",
        "Just a quick example here, Telegram? Microsoft! Google: Amazon;",
    ),
]

failed = 0
cleaner = TranscriptCleaner()
for raw, expected in CASES:
    got = cleaner.clean(raw, remove_fillers_enabled=False, add_punctuation=True)
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
