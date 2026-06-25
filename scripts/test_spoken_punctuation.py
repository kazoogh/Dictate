"""Unit tests for spoken punctuation commands."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from spoken_punctuation import apply_spoken_punctuation

CASES = [
    ("hello comma world", "hello, world"),
    ("hello period", "hello."),
    ("don apostrophe t", "don't"),
    ("see you at symbol gmail dot com", "see you@gmail.com"),
    ("visit example dot org", "visit example.org"),
    ("use slash home slash user", "use /home/user"),
    ("line one new line line two", "line one\nline two"),
    ("open quote hello close quote", '"hello"'),
    ("wow exclamation mark", "wow!"),
    ("really question mark", "really?"),
    ("C colon backslash Users backslash test", "C:\\Users\\test"),
    ("price dollar sign 50", "price $50"),
    ("one hundred percent sign", "one hundred%"),
]

failed = 0
for raw, expected in CASES:
    got = apply_spoken_punctuation(raw)
    ok = got == expected
    if not ok:
        failed += 1
        print(f"FAIL: {raw!r}")
        print(f"  expected: {expected!r}")
        print(f"  got:      {got!r}")
    else:
        print(f"OK: {raw!r} -> {got!r}")

if failed:
    print(f"\n{failed} failed")
    sys.exit(1)
print(f"\nAll {len(CASES)} passed")
