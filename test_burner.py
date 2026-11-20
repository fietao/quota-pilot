import json
import os
import subprocess
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

import burner

STATUS = """short: x
```
Codex (plus)   week: 17% used, resets Wed Nov 11 10:51 (in 44.9h) | 5h: 25% used, resets Mon Nov 09 18:36 (in 4.6h) | data from 2026-11-09 13:58
Claude         week: 18% used, resets Sat Nov 14 14:00 (in 120.6h) | 5h: 13% used, resets Mon Nov 09 15:40 (in 2.3h)
agy Gemini     week: 0% used, resets Mon Nov 16 13:22 (in 168.0h) | 5h: 0% used, resets Mon Nov 09 18:22 (in 5.0h)
agy Argon      week: 6% used, resets Sun Nov 15 00:06 (in 130.7h)
```"""


class TestDeciding(unittest.TestCase):
    def test_read_status_codex_and_agy_gemini_only(self):
        s = burner.read_status(STATUS)
        self.assertEqual(set(s), {"codex", "agy"})  # Claude is never burned; Argon is not the agy default
        self.assertEqual(s["codex"], {"week_used": 17.0, "week_hours": 44.9, "five_used": 25.0})
        self.assertEqual(s["agy"]["week_hours"], 168.0)

    def test_closest_reset_wins(self):
        self.assertEqual(burner.pick_provider(burner.read_status(STATUS), "any", set()), "codex")

    def test_jet_using_codex_moves_job_to_agy(self):  # the gate's test idea
        self.assertEqual(burner.pick_provider(burner.read_status(STATUS), "any", {"codex"}), "agy")

    def test_reserve_is_kept(self):
        s = {"codex": {"week_used": 81, "week_hours": 5, "five_used": 0}}
        self.assertIsNone(burner.pick_provider(s, "any", set()))

    def test_five_hour_window_nearly_full_is_skipped(self):
        s = {"codex": {"week_used": 10, "week_hours": 5, "five_used": 85}}
        self.assertIsNone(burner.pick_provider(s, "any", set()))

    def test_job_can_ask_for_one_tool(self):
        self.assertEqual(burner.pick_provider(burner.read_status(STATUS), "agy", set()), "agy")

    def test_allowed_list(self):
        self.assertTrue(burner.allowed({"project": "C:/dev/projects/gym"}))
        self.assertFalse(burner.allowed({"project": "C:/dev/projects/workflow-layer"}))
        self.assertFalse(burner.allowed({"project": "C:/dev/aftersell"}))
        self.assertFalse(burner.allowed({"project": "C:/dev/projects/gym/../workflow-layer"}))


class TestJetActive(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.log = root / "2026" / "11" / "09" / "s.jsonl"
        self.log.parent.mkdir(parents=True)
        self.log.write_text("x")
        self.patch = mock.patch.dict(burner.LOG_DIRS, {"codex": (root, "*/*/*/*.jsonl")})
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_recent_log_means_active(self):
        self.assertTrue(burner.jet_active("codex", None, datetime.now()))

    def test_old_log_means_idle(self):
        old = time.time() - 2 * 3600
        os.utime(self.log, (old, old))
        self.assertFalse(burner.jet_active("codex", None, datetime.now()))

    def test_burners_own_run_does_not_count_as_jet(self):
        self.assertFalse(burner.jet_active("codex", datetime.now(), datetime.now()))


class FakeRunner:
    """Pretends to be git/codex/check. check_results: return codes for each check call, in order."""
    def __init__(self, check_results):
        self.check_results = list(check_results)
        self.calls = []

    def __call__(self, cmd, cwd, **kw):
        self.calls.append(cmd)
        if cmd[:3] == ["git", "worktree", "add"]:
            Path(cmd[3]).mkdir(parents=True)
        code = self.check_results.pop(0) if cmd == ["check"] else 0
        return subprocess.CompletedProcess(cmd, code, stdout="check output", stderr="")


class TestRunJob(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.job_folder = root / "jobs" / "j1"
        self.job_folder.mkdir(parents=True)
        (self.job_folder / "JOB.md").write_text("do it")
        self.job = {"id": "j1", "project": str(root), "check": ["check"], "_folder": self.job_folder}
        self.patch = mock.patch.object(burner, "WORK_DIR", root / "work")
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def ai_calls(self, runner):
        return [c for c in runner.calls if "exec" in c or "--print" in c]

    def test_pass_first_time_commits_on_burn_branch(self):
        runner = FakeRunner([0])
        res = burner.run_job(self.job, "codex", runner)
        self.assertEqual(res["status"], "passed")
        self.assertEqual(res["branch"], "burn/j1")
        self.assertEqual(len(self.ai_calls(runner)), 1)
        self.assertTrue(any(c[:2] == ["git", "commit"] for c in runner.calls))
        self.assertFalse(any("push" in c or "merge" in c for c in runner.calls))
        self.assertFalse((burner.WORK_DIR / "j1" / "JOB.md").exists())  # notes not committed

    def test_fail_then_fix_round_then_pass(self):
        runner = FakeRunner([1, 0])
        res = burner.run_job(self.job, "agy", runner)
        self.assertEqual(res["status"], "passed")
        self.assertEqual(res["rounds"], 2)
        self.assertEqual(len(self.ai_calls(runner)), 2)

    def test_fail_twice_is_failed_and_not_committed(self):
        runner = FakeRunner([1, 1])
        res = burner.run_job(self.job, "codex", runner)
        self.assertEqual(res["status"], "failed")
        self.assertFalse(any(c[:2] == ["git", "commit"] for c in runner.calls))

    def test_timeout_counts_as_failure(self):
        def runner(cmd, cwd, **kw):
            if cmd[:3] == ["git", "worktree", "add"]:
                Path(cmd[3]).mkdir(parents=True)
                return subprocess.CompletedProcess(cmd, 0, "", "")
            raise subprocess.TimeoutExpired(cmd, 1)
        self.assertEqual(burner.run_job(self.job, "codex", runner)["status"], "failed")


class TestSummary(unittest.TestCase):
    def test_summary_counts_last_24h_only(self):
        now = datetime(2026, 11, 10, 9, 0)
        runs = [
            {"job": "a", "provider": "codex", "status": "passed", "branch": "burn/a", "end": "2026-11-10T03:00:00"},
            {"job": "b", "provider": "agy", "status": "failed", "reason": "check failed", "end": "2026-11-09T20:00:00"},
            {"job": "old", "provider": "codex", "status": "passed", "branch": "burn/old", "end": "2026-11-08T01:00:00"},
        ]
        out = burner.summary(runs, now)
        self.assertIn("1 passed, 1 failed", out)
        self.assertNotIn("old", out)
        self.assertEqual(burner.summary([], now), "")


if __name__ == "__main__":
    unittest.main()


class TestMainLoop(unittest.TestCase):
    """Two hourly ticks: Codex busy with job a → the next tick starts job b on agy, never job a again."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "data").mkdir()
        (root / "data" / "quota-status.md").write_text(STATUS, encoding="utf-8")
        for name in ("a", "b"):
            (root / "jobs" / name).mkdir(parents=True)
            (root / "jobs" / name / "JOB.md").write_text("x")
            (root / "jobs" / name / "job.json").write_text(json.dumps(
                {"project": "C:/dev/projects/gym", "ai": "any", "status": "approved", "check": ["c"]}))
        self.root = root
        self.patches = [mock.patch.object(burner, k, v) for k, v in {
            "JOBS_DIR": root / "jobs", "STATUS_FILE": root / "data" / "quota-status.md",
            "RUNS_LOG": root / "data" / "runs.jsonl", "LOCKS": root / "data"}.items()]
        self.patches.append(mock.patch.object(burner, "jet_active", return_value=False))
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def status_of(self, name):
        return json.loads((self.root / "jobs" / name / "job.json").read_text())["status"]

    def test_second_tick_runs_next_job_on_other_tool(self):
        seen = []

        def first_run(job, provider):
            seen.append((job["id"], provider))
            self.assertEqual(self.status_of("a"), "running")      # marked before the work starts
            self.assertTrue(burner.lock("codex").exists())
            # while job a is still going, the next hourly tick happens:
            with mock.patch.object(burner, "run_job", side_effect=lambda j, p: seen.append((j["id"], p)) or {"status": "passed", "branch": "x"}):
                burner.main([])
            return {"status": "passed", "branch": "burn/a"}

        with mock.patch.object(burner, "run_job", side_effect=first_run):
            burner.main([])
        self.assertEqual(seen, [("a", "codex"), ("b", "agy")])
        self.assertEqual(self.status_of("a"), "passed")
        self.assertFalse(burner.lock("codex").exists())

    def test_job_not_on_list_is_skipped(self):
        meta = self.root / "jobs" / "a" / "job.json"
        meta.write_text(json.dumps({"project": "C:/dev/projects/workflow-layer", "ai": "any",
                                    "status": "approved", "check": ["c"]}))
        with mock.patch.object(burner, "run_job", return_value={"status": "passed", "branch": "x"}) as run:
            burner.main([])
        self.assertEqual(run.call_args[0][0]["id"], "b")
        self.assertEqual(self.status_of("a"), "approved")


class TestApproval(TestMainLoop):
    """Jet's rule: ask first, unless the reset is <24h away and >50% is unused."""
    def set_status(self, name, status):
        meta = self.root / "jobs" / name / "job.json"
        meta.write_text(json.dumps({**json.loads(meta.read_text()), "status": status}))

    def test_ready_job_waits_when_reset_is_far(self):  # Codex reset in 44.9h -> must ask
        self.set_status("a", "ready")
        self.set_status("b", "ready")
        with mock.patch.object(burner, "run_job") as run:
            burner.main([])
        run.assert_not_called()

    def test_ready_job_runs_alone_when_quota_would_be_wasted(self):
        self.set_status("a", "ready")
        (self.root / "data" / "quota-status.md").write_text(
            "Codex (plus)   week: 30% used, resets Wed (in 10.0h) | 5h: 5% used\n", encoding="utf-8")
        with mock.patch.object(burner, "run_job", return_value={"status": "passed", "branch": "x"}) as run:
            burner.main([])
        self.assertEqual(run.call_args[0][0]["id"], "a")

    def test_more_than_half_used_still_asks_even_near_reset(self):
        self.set_status("a", "ready")
        self.set_status("b", "ready")
        (self.root / "data" / "quota-status.md").write_text(
            "Codex (plus)   week: 60% used, resets Wed (in 10.0h) | 5h: 5% used\n", encoding="utf-8")
        with mock.patch.object(burner, "run_job") as run:
            burner.main([])
        run.assert_not_called()

    def test_pending_asks_once_per_job(self):
        self.set_status("a", "ready")
        self.set_status("b", "passed")
        status = burner.read_status(STATUS)
        first = burner.pending_message(status, datetime.now())
        self.assertIn("approve", first)
        self.assertIn("a", first)
        self.assertEqual(burner.pending_message(status, datetime.now()), "")  # not asked twice

    def test_approve_and_skip_by_number(self):
        for name in ("a", "b"):
            (self.root / "jobs" / name).rename(self.root / "jobs" / f"0{'1' if name == 'a' else '2'}-{name}")
        for d in (self.root / "jobs").glob("*/"):
            meta = d / "job.json"
            meta.write_text(json.dumps({**json.loads(meta.read_text()), "status": "ready"}))
        with mock.patch.object(burner, "start_detached") as start:
            self.assertIn("Approved 01-a", burner.decide("01", "approved"))
            start.assert_called_once()
        self.assertIn("Skipped 02-b", burner.decide("02", "skipped"))
        self.assertIn("already skipped", burner.decide("02", "approved"))
        self.assertIn("No single job", burner.decide("99", "approved"))
        st = {d.name: json.loads((d / "job.json").read_text())["status"] for d in (self.root / "jobs").glob("*/")}
        self.assertEqual(st, {"01-a": "approved", "02-b": "skipped"})
