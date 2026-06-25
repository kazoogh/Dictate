"""Vocabulary correction and Jason/JSON disambiguation tests."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vocabulary import VocabularyStore  # noqa: E402

CASES = [
    ("I use teddy graham for messaging", "Telegram"),
    ("save it as a doc x file", "DOCX"),
    ("talk to jason about the schedule", "Jason"),
    ("parse the json file and export it", "JSON"),
    ("john and james need to review this", "John"),
    ("write a python script for the api", "Python"),
    ("save it as dot py", ".py"),
]

AMBIGUOUS = [
  ("jason said he would call back", "Jason"),
  ("serialize this object to json", "JSON"),
]


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        app_dir = Path(tmp)
        # Seed minimal file so merge pulls bundled names/tech from repo assets.
        (app_dir / "vocabulary.json").write_text(
            json.dumps({"version": "2.0", "terms": []}) + "\n",
            encoding="utf-8",
        )
        store = VocabularyStore(app_dir, fuzzy_threshold=82)
        failed = 0

        for raw, needle in CASES + AMBIGUOUS:
            out = store.correct(raw)
            ok = needle.lower() in out.lower()
            print(f"IN:  {raw}")
            print(f"OUT: {out}")
            print("OK" if ok else f"FAIL (expected {needle})")
            print()
            if not ok:
                failed += 1

        # Ambiguous with no context should not force JSON for a name-like token.
        neutral = store.correct("jason")
        if neutral.lower() == "json":
            print("FAIL: neutral 'jason' became JSON")
            failed += 1
        else:
            print(f"OK: neutral jason -> {neutral!r}")

    sys.exit(failed)


if __name__ == "__main__":
    main()
