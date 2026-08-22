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
- And then blah, blah, blah.
- Blah, blah, blah.
- Blah, blah blah.
- Blah, blah, blah.
So please get to work on that everybody!"""

USER_SAMPLE = (
    "Yo so just a couple things, blah, blah, blah, that we need to work on this week. "
    "The first thing is Json has to finish dictate. "
    "The second thing is we have a weekly it meeting this Friday. "
    "The third thing is talk to chat Gbt and transfer that account. "
    "The fourth thing is get access to Google Drive. "
    "Number five is talk to John"
)

USER_EXPECTED = """Yo so just a couple things, blah, blah, blah, that we need to work on this week.
- Json has to finish dictate.
- We have a weekly it meeting this Friday.
- Talk to chat Gbt and transfer that account.
- Get access to Google Drive.
- Talk to John"""

for label, raw, expected in (
    ("basic", SAMPLE, EXPECTED),
    ("user", USER_SAMPLE, USER_EXPECTED),
):
    got = format_dictated_lists(raw)
    if got != expected:
        print(f"FAIL: {label}")
        print("expected:")
        print(expected)
        print("got:")
        print(got)
        sys.exit(1)
    print(f"OK: {label}")

single = "The first thing is we only have one item here."
if format_dictated_lists(single) != single:
    print("FAIL: single item should stay unchanged")
    sys.exit(1)

print("OK: all list formatting tests passed")
