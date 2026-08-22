"""Unit tests for paste vocabulary learning."""

import sys
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from paste_learner import PasteLearner, extract_word_corrections
from vocabulary import VocabularyStore


class ExtractCorrectionsTest(unittest.TestCase):
    def test_single_word_fix(self):
        self.assertEqual(
            extract_word_corrections("John went home", "Johnny went home"),
            [("John", "Johnny")],
        )

    def test_fix_inside_larger_field(self):
        self.assertEqual(
            extract_word_corrections("John", "Dear Johnny"),
            [("John", "Johnny")],
        )

    def test_no_change(self):
        self.assertEqual(extract_word_corrections("hello world", "hello world"), [])

    def test_too_different(self):
        self.assertEqual(
            extract_word_corrections("short", "completely unrelated long paragraph here"),
            [],
        )


class PasteLearnerTest(unittest.TestCase):
    def test_learns_into_vocabulary(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = Path(tmp)
            vocab = VocabularyStore(app_dir)
            learner = PasteLearner(vocab)
            learner.remember("John went home")
            learned = learner.check_and_learn("Johnny went home")
            self.assertEqual(learned, [("Johnny", "John")])
            vocab.reload()
            entry = next(e for e in vocab._terms if e["term"] == "Johnny")
            self.assertIn("John", entry["aliases"])


if __name__ == "__main__":
    unittest.main()
