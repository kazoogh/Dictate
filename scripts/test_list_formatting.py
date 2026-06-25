"""Tests for dictated list -> bullet formatting."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from list_formatting import format_dictated_lists

SAMPLE = (
    "Yeah, so we have a couple things we need to get done. "
    "The first thing is, and then blah, blah, blah. "
    "The second thing is, blah, blah, blah. "
    "The third thing is blah, blah blah. "
    "The fourth thing is blah, blah, blah. "
    "So please get to work on that everybody!"
)

EXPECTED = """Yeah, so we have a couple things we need to get done.
- The first thing is, and then blah, blah, blah.
- The second thing is, blah, blah, blah.
- The third thing is blah, blah blah.
- The fourth thing is blah, blah, blah.
So please get to work on that everybody!"""

got = format_dictated_lists(SAMPLE)
if got != EXPECTED:
    print("FAIL")
    print("expected:")
    print(EXPECTED)
    print("got:")
    print(got)
    sys.exit(1)

# Single ordinal should not bullet
single = "The first thing is we only have one item here."
if format_dictated_lists(single) != single:
    print("FAIL: single item should stay unchanged")
    sys.exit(1)

print("OK: list formatting tests passed")
