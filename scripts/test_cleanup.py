"""Quick test for transcript cleanup (filler rules + ONNX punctuation)."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from transcript_cleanup import TranscriptCleaner, remove_fillers

SAMPLE = (
    "Um, can we use this dictate app for long recordings? Like how long can it record work? "
    "Can it record like an hour or two hours? Like, what if I press the start button and I "
    "don't press stop for two hours? Will it transcribe the entire two hour conversation? "
    "Because six days ago, we were working on a clinical note app. Basically, that was built "
    "to record a patient two hours, like, or one hour or 30 minute. Basically, just like an "
    "appointment, right? It'll record the whole appointment. And then at the end, it will "
    "match up and transcribe with the clinical note tablet. You know what I mean? So could we, "
    "like, is it possible for us to build this into a dictate? So it's all just one app inside "
    "dictate. What do you think? Don't build it yet. Let's think about it first."
)

cleaner = TranscriptCleaner()
result = cleaner.clean(SAMPLE)
out = f"=== FILLERS ONLY ===\n{remove_fillers(SAMPLE)}\n\n=== FULL CLEANUP ===\n{result}\n"
print(out)
Path(__file__).resolve().parents[1].joinpath("_test_cleanup_out.txt").write_text(out, encoding="utf-8")
