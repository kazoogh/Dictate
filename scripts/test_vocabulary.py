"""Quick vocabulary correction checks."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vocabulary import VocabularyStore  # noqa: E402

CASES = [
    ("I use teddy graham for messaging", "Telegram"),
    ("save it as a doc x file", "DOCX"),
    ("export the pdf file", "PDF"),
    ("build the e x e", "EXE"),
    ("open dent tricks ascend", "Dentrix"),
]


def main() -> None:
    store = VocabularyStore(ROOT, fuzzy_threshold=82)
    failed = 0
    for raw, needle in CASES:
        out = store.correct(raw)
        ok = needle.lower() in out.lower()
        print(f"IN:  {raw}")
        print(f"OUT: {out}")
        print("OK" if ok else f"FAIL (expected {needle})")
        print()
        if not ok:
            failed += 1
    sys.exit(failed)


if __name__ == "__main__":
    main()
