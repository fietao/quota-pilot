import os
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path

import reminders

BACKLOG = """
| # | Project | Job | Why | When |
|---|---|---|---|---|
| H1 | wl | send demo | out | |
| H2 | wl | ask excel | person | |
| H3 | wl | mockup | taste | |
| H4 | ai | essays | data | 2026-11-09 |
| H5 | gym | clips | body | 2026-12-01 |
| A1 | wl | not human | x | |
"""
TODAY = date(2026, 11, 9)


class TestReminders(unittest.TestCase):
    def test_five_jobs_shows_three_and_two_more(self):  # Jet's gate test
        msg = reminders.message(BACKLOG, [], TODAY)
        self.assertIn("(5 human jobs open)", msg)
        self.assertEqual(msg.count("• "), 3)
        self.assertIn("…and 2 more", msg)
        self.assertNotIn("not human", msg)

    def test_due_job_goes_first(self):
        msg = reminders.message(BACKLOG, [], TODAY)
        first = [l for l in msg.splitlines() if l.startswith("• ")][0]
        self.assertTrue(first.startswith("• H4"), first)
        self.assertIn("⏰ due", first)
        self.assertNotIn("H5", msg)  # future date, not in the top 3

    def test_no_jobs(self):
        self.assertIn("No human jobs open.", reminders.message("", [], TODAY))

    def test_stale_project_listed_fresh_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            old, new = Path(tmp, "oldproj"), Path(tmp, "newproj")
            for d in (old, new):
                d.mkdir()
                (d / "a.txt").write_text("x")
            month_ago = time.time() - 30 * 86400
            os.utime(old / "a.txt", (month_ago, month_ago))
            msg = reminders.message("", [old, new], date.today())
        self.assertIn("oldproj", msg)
        self.assertNotIn("newproj", msg)


if __name__ == "__main__":
    unittest.main()
