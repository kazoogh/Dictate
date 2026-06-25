"""Regression tests for dictation cleanup using real user samples."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from transcript_cleanup import TranscriptCleaner  # noqa: E402

SAMPLES = [
    (
        "Hello, , this is just a test to determine the punctuation and removal of filler words like a",
        "no double commas, no trailing dangling like a",
    ),
    (
        "HI, , my name is JASON, , and we're gonna be describing clinical notes today,. "
        "So yeah, , I. Don't know Anyway,. The clinical notes templates each have like "
        "quick picks, blah, blah, blah,",
        "no double commas, reasonable casing, no today,.",
    ),
    (
        "Anyway, I'm using the dictate app right now.. I'm just testing to see how it "
        "transcribes and how it does punctuation. Clearly. It's having a little bit of "
        "issues. But in the Future, I, Think it will be pretty good. Local open source "
        "version of whisper Flow.",
        "no double periods, no random mid-word caps",
    ),
]


def _bad(text: str) -> list[str]:
    issues = []
    if ", ," in text or ",," in text:
        issues.append("double comma")
    if ",." in text or ".," in text:
        issues.append("comma-period")
    if ".." in text:
        issues.append("double period")
    if re.search(r"\b[A-Z]{2,}\b", text):
        issues.append("ALL CAPS word")
    if re.search(r",\s+I,\s+", text):
        issues.append("spurious comma around I")
    return issues


import re  # noqa: E402


def main() -> None:
    cleaner = TranscriptCleaner()
    cleaner.preload_punctuation()
    if not cleaner.wait_for_punctuation(timeout=120):
        print("Model unavailable:", cleaner.punctuation_error())
        sys.exit(1)

    failed = 0
    for i, (raw, note) in enumerate(SAMPLES, 1):
        out = cleaner.clean(raw)
        issues = _bad(out)
        print(f"--- Sample {i} ({note}) ---")
        print(f"IN:  {raw}")
        print(f"OUT: {out}")
        if issues:
            print(f"FAIL: {', '.join(issues)}")
            failed += 1
        print()
    sys.exit(failed)


def write_report(path: Path) -> int:
    cleaner = TranscriptCleaner()
    cleaner.preload_punctuation()
    if not cleaner.wait_for_punctuation(timeout=120):
        path.write_text(f"Model unavailable: {cleaner.punctuation_error()}\n", encoding="utf-8")
        return 1
    lines = []
    failed = 0
    for i, (raw, note) in enumerate(SAMPLES, 1):
        out = cleaner.clean(raw)
        issues = _bad(out)
        lines.append(f"--- Sample {i} ({note}) ---")
        lines.append(f"IN:  {raw}")
        lines.append(f"OUT: {out}")
        if issues:
            lines.append(f"FAIL: {', '.join(issues)}")
            failed += 1
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return failed


if __name__ == "__main__":
    report = ROOT / "_user_samples_out.txt"
    code = write_report(report)
    print(report.read_text(encoding="utf-8"))
    sys.exit(code)
