"""Focused tests for Time Saved KPI helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ui_qt import (  # noqa: E402
    NORMAL_TYPING_WPM,
    calculate_time_saved,
    format_time_saved,
)


class TestCalculateTimeSaved(unittest.TestCase):
    def test_zero_data(self):
        self.assertEqual(calculate_time_saved(0, 0), 0)

    def test_required_example_five_minutes(self):
        # 400 words / 40 WPM = 10 typing minutes; 300s = 5 dictation minutes → 5
        self.assertEqual(calculate_time_saved(400, 300), 5)

    def test_required_example_four_hours_twenty(self):
        # 12000 / 40 = 300; 2400s = 40 → 260 minutes
        self.assertEqual(calculate_time_saved(12_000, 2_400), 260)

    def test_never_negative(self):
        # Slow dictation relative to typing should clamp to 0
        self.assertEqual(calculate_time_saved(40, 3600), 0)

    def test_invalid_inputs(self):
        self.assertEqual(calculate_time_saved(None, 10), 0)
        self.assertEqual(calculate_time_saved(100, None), 0)
        self.assertEqual(calculate_time_saved("x", 10), 0)
        self.assertEqual(calculate_time_saved(100, 10, 0), 0)
        self.assertEqual(calculate_time_saved(100, 10, -5), 0)
        self.assertEqual(calculate_time_saved(float("nan"), 10), 0)
        self.assertEqual(calculate_time_saved(100, float("inf")), 0)

    def test_default_wpm_constant(self):
        self.assertEqual(NORMAL_TYPING_WPM, 40)


class TestFormatTimeSaved(unittest.TestCase):
    def test_zero_and_invalid(self):
        self.assertEqual(format_time_saved(0), "No time saved yet")
        self.assertEqual(format_time_saved(-1), "No time saved yet")
        self.assertEqual(format_time_saved(None), "No time saved yet")
        self.assertEqual(format_time_saved("bad"), "No time saved yet")

    def test_minutes_only(self):
        self.assertEqual(format_time_saved(1), "You saved 1 minute")
        self.assertEqual(format_time_saved(18), "You saved 18 minutes")

    def test_hours_only(self):
        self.assertEqual(format_time_saved(60), "You saved 1 hour")
        self.assertEqual(format_time_saved(120), "You saved 2 hours")

    def test_hours_and_minutes(self):
        self.assertEqual(format_time_saved(61), "You saved 1 hour, 1 minute")
        self.assertEqual(format_time_saved(65), "You saved 1 hour, 5 minutes")
        self.assertEqual(format_time_saved(260), "You saved 4 hours, 20 minutes")


if __name__ == "__main__":
    unittest.main()
