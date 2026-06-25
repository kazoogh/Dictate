"""Benchmark filler + punctuation cleanup speed."""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from transcript_cleanup import TranscriptCleaner, remove_fillers  # noqa: E402

SAMPLE = (
    "can we use this dictate app for long recordings how long can it record work "
    "can it record like an hour or two hours what if I press the start button and "
    "I don't press stop for two hours will it transcribe the entire two hour conversation"
)

def main() -> None:
    t0 = time.perf_counter()
    fillers = remove_fillers(SAMPLE)
    t1 = time.perf_counter()

    cleaner = TranscriptCleaner()
    cleaner.preload_punctuation()
    if not cleaner.wait_for_punctuation(timeout=120):
        print("Punctuation model failed:", cleaner.punctuation_error())
        return

    t2 = time.perf_counter()
    result = cleaner.clean(SAMPLE)
    t3 = time.perf_counter()

    print(f"Fillers only: {(t1 - t0) * 1000:.1f} ms")
    print(f"Model load:   {(t2 - t0) * 1000:.0f} ms")
    print(f"Full cleanup: {(t3 - t2) * 1000:.1f} ms")
    print(f"Output: {result}")


if __name__ == "__main__":
    main()
