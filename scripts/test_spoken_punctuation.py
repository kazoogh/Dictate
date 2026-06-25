"""Unit tests for spoken punctuation commands."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from spoken_punctuation import apply_spoken_punctuation, iter_spoken_commands, merge_punctuated_pieces
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
]

failed = 0
for raw, expected in CASES:
    got = apply_spoken_punctuation(raw)
    if got != expected:
        failed += 1
        print(f"FAIL: {raw!r}")
        print(f"  expected: {expected!r}")
        print(f"  got:      {got!r}")
    else:
        print(f"OK: {raw!r}")

segments = list(iter_spoken_commands("hi comma there period"))
assert [s[0] for s in segments] == ["text", "punct", "text", "punct"]

cleaner = TranscriptCleaner()
merged = merge_punctuated_pieces(
    [
        cleaner._punctuate_chunk("hi", trailing_user_punct=","),
        ",",
        cleaner._punctuate_chunk("there", trailing_user_punct="."),
        ".",
    ]
)
print("segment merge:", merged)

if failed:
    print(f"\n{failed} failed")
    sys.exit(1)
print(f"\nAll {len(CASES)} passed")
