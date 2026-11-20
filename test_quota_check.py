from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import quota_check


class TestQuotaCheck(unittest.TestCase):
    def test_codex_uses_last_rate_limits_and_parses_weekly(self) -> None:
        now = datetime(2026, 11, 8, 20, 0, tzinfo=timezone.utc).astimezone()
        reset_5h = int(datetime(2026, 11, 8, 23, 0, tzinfo=timezone.utc).timestamp())
        reset_week = int(datetime(2026, 11, 11, 16, 51, tzinfo=timezone.utc).timestamp())

        line1 = json.dumps({
            "timestamp": "2026-11-08T18:00:00Z",
            "payload": {
                "rate_limits": {
                    "plan_type": "plus",
                    "primary": {"used_percent": 3.0, "resets_at": reset_5h},
                    "secondary": {"used_percent": 5.0, "resets_at": reset_week},
                }
            },
        })
        line2 = json.dumps({
            "timestamp": "2026-11-08T20:04:00Z",
            "payload": {
                "rate_limits": {
                    "plan_type": "plus",
                    "primary": {"used_percent": 9.0, "resets_at": reset_5h},
                    "secondary": {"used_percent": 10.0, "resets_at": reset_week},
                }
            },
        })

        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "session.jsonl"
            p.write_text(f"{line1}\n{line2}\n", encoding="utf-8")
            out = quota_check.parse_codex(p, now=now)

        self.assertIn("Codex (plus)", out)
        self.assertIn("week: 10% used", out)
        self.assertIn("5h: 9% used", out)
        self.assertIn("in 68.8h", out)

    def test_missing_claude_file_returns_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "does_not_exist.jsonl"
            out = quota_check.parse_claude(missing)
        self.assertIn("unknown", out)

    def test_malformed_json_line_in_codex_is_skipped(self) -> None:
        now = datetime(2026, 11, 8, 20, 0, tzinfo=timezone.utc).astimezone()
        reset_ts = int(datetime(2026, 11, 9, 20, 0, tzinfo=timezone.utc).timestamp())
        valid = json.dumps({
            "timestamp": "2026-11-08T20:00:00Z",
            "payload": {
                "rate_limits": {
                    "plan_type": "pro",
                    "primary": {"used_percent": 12.5, "resets_at": reset_ts},
                    "secondary": {"used_percent": 25.0, "resets_at": reset_ts},
                }
            },
        })
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "session.jsonl"
            p.write_text(f"{{not-valid-json\n{valid}\n{{{{\"broken\": true\n", encoding="utf-8")
            out = quota_check.parse_codex(p, now=now)

        self.assertIn("Codex (pro)", out)
        self.assertIn("week: 25% used", out)
        self.assertIn("5h: 12.5% used", out)

    def test_gemini_counts_today_responses_from_chat_logs(self) -> None:
        tz = quota_check._pacific_tz()
        now_pt = datetime(2026, 11, 8, 10, 0, tzinfo=tz)
        yesterday = {"type": "gemini", "timestamp": "2026-11-07T23:59:59-08:00"}
        today_one = {"type": "gemini", "timestamp": "2026-11-08T00:00:00-08:00"}
        user = {"type": "user", "timestamp": "2026-11-08T04:00:00-08:00"}
        today_two = {"type": "gemini", "timestamp": "2026-11-08T05:30:00-08:00"}

        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "session" / "chats" / "chat.jsonl"
            p.parent.mkdir(parents=True)
            p.write_text(
                "\n".join((json.dumps(today_one), json.dumps(user), "not json", json.dumps(today_two), json.dumps(yesterday))) + "\n",
                encoding="utf-8",
            )
            os.utime(p, (now_pt.timestamp(), now_pt.timestamp()))
            out = quota_check.parse_gemini(Path(tmp), now=now_pt)

        self.assertIn("~2 / 1500 responses today", out)
        self.assertIn("resets in 14.0h", out)

    def test_gemini_missing_dir_returns_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = quota_check.parse_gemini(Path(tmp) / "missing")
        self.assertIn("unknown", out)

    def test_agy_usage_parses_windows_and_groups(self) -> None:
        text = "\n".join((
            "Gemini Models\tWeekly Limit Remaining\t100%\t2026-11-16T18:00:54Z",
            "Gemini Models\tFive Hour Limit Remaining\t100%\t2026-11-09T23:00:54Z",
            "Claude and GPT models\tWeekly Limit Remaining\t100%\t2026-11-16T18:00:54Z",
            "Claude and GPT models\tFive Hour Limit Remaining\t100%\t2026-11-09T23:00:54Z",
            "Gemini 4 Argon\tGemini 4 Argon Weekly Limit\t94%\t2026-11-15T06:06:59Z",
        ))
        now = datetime(2026, 11, 9, 18, 0, tzinfo=timezone.utc)
        lines = quota_check.parse_agy_usage(text, now=now)

        self.assertEqual(len(lines), 3)
        self.assertIn("week: 0% used", lines[0])
        self.assertIn("5h: 0% used", lines[0])
        self.assertIn("week: 6% used", lines[2])
        self.assertNotIn("5h:", lines[2])

    def test_agy_usage_skips_junk_and_bad_percentages(self) -> None:
        text = "\n".join((
            "junk line",
            "Gemini Models\tWeekly Limit Remaining\tabc%\t2026-11-16T18:00:54Z",
            "Gemini Models\tFive Hour Limit Remaining\t90%\t2026-11-09T23:00:54Z",
        ))
        lines = quota_check.parse_agy_usage(text, now=datetime(2026, 11, 9, 18, tzinfo=timezone.utc))
        self.assertEqual(len(lines), 1)
        self.assertIn("5h: 10% used", lines[0])

    def test_agy_usage_empty_returns_unknown(self) -> None:
        self.assertEqual(
            quota_check.parse_agy_usage(""),
            ["Antigravity    unknown (no quota lines in agy /usage output)"],
        )

    def test_antigravity_reports_runner_errors(self) -> None:
        def missing(*args: object, **kwargs: object) -> object:
            raise FileNotFoundError

        def timed_out(*args: object, **kwargs: object) -> object:
            raise quota_check.subprocess.TimeoutExpired("agy", 90)

        self.assertIn("agy not found", quota_check.parse_antigravity(runner=missing)[0])
        self.assertIn("timed out", quota_check.parse_antigravity(runner=timed_out)[0])

    def test_codex_dir_skips_newer_file_without_rate_limits(self) -> None:
        now = datetime(2026, 11, 8, 20, 0, tzinfo=timezone.utc).astimezone()
        reset_ts = int(datetime(2026, 11, 9, 20, 0, tzinfo=timezone.utc).timestamp())
        older_line = json.dumps({
            "timestamp": "2026-11-08T18:00:00Z",
            "payload": {
                "rate_limits": {
                    "plan_type": "plus",
                    "primary": {"used_percent": 15.0, "resets_at": reset_ts},
                    "secondary": {"used_percent": 42.0, "resets_at": reset_ts},
                }
            },
        })
        newer_line = json.dumps({
            "timestamp": "2026-11-08T19:30:00Z",
            "payload": {"type": "session_meta"},
        })

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            older = tmp_path / "older.jsonl"
            newer = tmp_path / "newer.jsonl"
            older.write_text(f"{older_line}\n", encoding="utf-8")
            newer.write_text(f"{newer_line}\n", encoding="utf-8")
            os.utime(older, (1000, 1000))
            os.utime(newer, (2000, 2000))
            out = quota_check.parse_codex(tmp_path, now=now)

        self.assertIn("week: 42% used", out)


if __name__ == "__main__":
    unittest.main()
