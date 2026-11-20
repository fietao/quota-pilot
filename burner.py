"""Burner: spend unused Codex/agy quota on approved jobs, one job per run.

Safety: only projects in ALLOWED; each job runs on its own local branch (burn/<id>) in a worktree;
never merges, pushes or sends anything. Keeps RESERVE % of each week for Jet and skips a tool
Jet used in the last IDLE_MIN minutes.
Usage: python burner.py [--dry-run | --summary]
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
JOBS_DIR = BASE / "jobs"
STATUS_FILE = BASE / "data" / "quota-status.md"
RUNS_LOG = BASE / "data" / "burner_runs.jsonl"
WORK_DIR = BASE / "data" / "worktrees"
LOCKS = BASE / "data"  # burner-<tool>.lock: one job per tool at a time, so Codex and agy can run side by side
PROJECTS_ROOT = Path("C:/dev/projects")
ALLOWED = {"ai-detector", "gym", "quota-pilot"}  # Jet's choice 2026-11-09
RESERVE = 20          # % of each week left for Jet
IDLE_MIN = 60         # skip a tool Jet used this recently
AUTO_HOURS = 24       # no approval needed only if the weekly reset is this close...
AUTO_MAX_USED = 50    # ...and less than this % of the week is used
JOB_TIMEOUT = 45 * 60
CHECK_TIMEOUT = 10 * 60
PROMPT = "Read JOB.md in the current directory and follow it exactly. Do not run git commit."
FIX_PROMPT = "Read FIX.md in the current directory and follow it exactly. JOB.md has the original job."
LOG_DIRS = {
    "codex": (Path.home() / ".codex" / "sessions", "*/*/*/*.jsonl"),
    "agy": (Path.home() / ".gemini" / "antigravity-cli" / "brain", "*/.system_generated/logs/transcript.jsonl"),
}


# --- deciding -------------------------------------------------------------------------

def read_status(text: str) -> dict[str, dict]:
    """quota-status.md lines -> {"codex": {"week_used", "week_hours", "five_used"}, "agy": {...}}"""
    status = {}
    for line in text.splitlines():
        name = line[:14].strip()
        key = "codex" if name.startswith("Codex") else "agy" if name == "agy Gemini" else None
        week = re.search(r"week: ([\d.]+)% used.*?\(in ([\d.]+)h\)", line)
        if key and week:
            five = re.search(r"5h: ([\d.]+)% used", line)
            status[key] = {"week_used": float(week.group(1)), "week_hours": float(week.group(2)),
                           "five_used": float(five.group(1)) if five else 0.0}
    return status


def pick_provider(status: dict, wanted: str, active: set[str]) -> str | None:
    """Closest weekly reset first, among tools with quota above the reserve that Jet isn't using."""
    ok = [p for p, s in status.items()
          if wanted in ("any", p) and p not in active
          and s["week_used"] <= 100 - RESERVE and s["five_used"] < 80]
    return min(ok, key=lambda p: status[p]["week_hours"]) if ok else None


def jet_active(provider: str, last_burner_end: datetime | None, now: datetime) -> bool:
    """True if the tool's newest log is from the last IDLE_MIN minutes and newer than the burner's last run."""
    folder, pattern = LOG_DIRS[provider]
    times = [f.stat().st_mtime for f in folder.glob(pattern)] if folder.exists() else []
    if not times:
        return False
    newest = datetime.fromtimestamp(max(times))
    mine = last_burner_end and newest <= last_burner_end + timedelta(minutes=2)
    return not mine and now - newest < timedelta(minutes=IDLE_MIN)


def auto_ok(s: dict) -> bool:
    """Run without asking only when quota is about to be wasted anyway (Jet's rule 2026-11-09):
    weekly reset in under 24 h AND more than half of the week still unused."""
    return s["week_hours"] < AUTO_HOURS and s["week_used"] < AUTO_MAX_USED


def allowed(job: dict) -> bool:
    project = Path(job["project"]).resolve()
    return project.parent == PROJECTS_ROOT.resolve() and project.name in ALLOWED


def ready_jobs() -> list[dict]:
    jobs = []
    for folder in sorted(JOBS_DIR.glob("*/")):
        meta = folder / "job.json"
        if meta.exists() and (folder / "JOB.md").exists():
            job = json.loads(meta.read_text(encoding="utf-8"))
            if job.get("status") in ("ready", "approved"):
                jobs.append({**job, "id": folder.name, "_folder": folder})
    return jobs


# --- running --------------------------------------------------------------------------

def ai_command(provider: str, prompt: str) -> list[str]:
    if provider == "codex":
        return [shutil.which("codex") or "codex", "exec", "-s", "workspace-write",
                "-c", "model_reasoning_effort=high", prompt]
    return [shutil.which("agy") or "agy", "--print", prompt, "--print-timeout", "45m"]


def run_job(job: dict, provider: str, runner=subprocess.run) -> dict:
    """Worktree on branch burn/<id> -> AI -> check -> (one fix round) -> commit on pass."""
    wt = WORK_DIR / job["id"]
    def call(cmd, cwd, timeout):
        try:
            r = runner(cmd, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
            return r.returncode, (r.stdout or "") + (r.stderr or "")
        except subprocess.TimeoutExpired:
            return 124, f"timed out after {timeout // 60} min"
        except OSError as exc:
            return 127, str(exc)

    code, out = call(["git", "worktree", "add", str(wt), "-b", f"burn/{job['id']}"], job["project"], 120)
    if code:
        return {"status": "failed", "reason": f"worktree: {out.strip()[-200:]}"}
    shutil.copy(job["_folder"] / "JOB.md", wt / "JOB.md")

    call(ai_command(provider, PROMPT), wt, JOB_TIMEOUT)
    code, out = call(job["check"], wt, CHECK_TIMEOUT)
    rounds = 1
    if code:
        (wt / "FIX.md").write_text("# Fix round\nThe check failed. Make it pass without editing or weakening "
                                   f"any test.\n\nCheck command: {' '.join(job['check'])}\n\nOutput (end):\n```\n"
                                   f"{out[-3000:]}\n```\n", encoding="utf-8")
        call(ai_command(provider, FIX_PROMPT), wt, JOB_TIMEOUT)
        code, out = call(job["check"], wt, CHECK_TIMEOUT)
        rounds = 2
    for note in ("JOB.md", "FIX.md"):
        (wt / note).unlink(missing_ok=True)
    if code:
        return {"status": "failed", "reason": f"check failed after {rounds} rounds: {out.strip()[-200:]}",
                "branch": f"burn/{job['id']}", "worktree": str(wt)}
    call(["git", "add", "-A"], wt, 60)
    call(["git", "commit", "-q", "-m", f"burn: {job['id']} ({provider}, {rounds} round(s); review before merge)"], wt, 60)
    return {"status": "passed", "branch": f"burn/{job['id']}", "worktree": str(wt), "rounds": rounds}


# --- log + entry point ----------------------------------------------------------------

def read_runs() -> list[dict]:
    if not RUNS_LOG.exists():
        return []
    return [json.loads(l) for l in RUNS_LOG.read_text(encoding="utf-8").splitlines() if l.strip()]


def lock(provider: str) -> Path:
    return LOCKS / f"burner-{provider}.lock"


def last_end_for(runs: list[dict], provider: str) -> datetime | None:
    """When the burner last finished a job on this tool (its own logs shouldn't look like Jet)."""
    ends = [r["end"] for r in runs if r["provider"] == provider]
    return datetime.fromisoformat(max(ends)) if ends else None


def set_status(job: dict, status: str) -> None:
    meta = job["_folder"] / "job.json"
    saved = json.loads(meta.read_text(encoding="utf-8"))
    meta.write_text(json.dumps({**saved, "status": status}, indent=2), encoding="utf-8")


def pending_message(status: dict, now: datetime) -> str:
    """Discord text asking Jet about jobs not asked yet; marks them asked so each is asked once."""
    lines = []
    for job in ready_jobs():
        if job["status"] != "ready" or job.get("asked") or not allowed(job):
            continue
        provider = pick_provider(status, job.get("ai", "any"), set())
        where = (f"{provider} ({status[provider]['week_used']:g}% used, reset in {status[provider]['week_hours']:g}h)"
                 if provider else "no tool free right now")
        title = (job["_folder"] / "JOB.md").read_text(encoding="utf-8").splitlines()[0].lstrip("# ")
        lines.append(f"• **{job['id'][:2]}** {title} → {where}")
        meta = job["_folder"] / "job.json"
        saved = json.loads(meta.read_text(encoding="utf-8"))
        meta.write_text(json.dumps({**saved, "asked": now.isoformat(timespec="minutes")}, indent=2), encoding="utf-8")
    if not lines:
        return ""
    return ("**Burner wants to run these** (reply `approve 03` or `skip 03`; nothing runs until you do):\n"
            + "\n".join(lines))


def decide(job_ref: str, decision: str) -> str:
    """Jet's answer from Discord: job_ref is the number ("03") or the full id."""
    matches = [f for f in JOBS_DIR.glob("*/") if f.name == job_ref or f.name.startswith(f"{job_ref}-")]
    if len(matches) != 1:
        return f"No single job matches '{job_ref}'. Jobs: {', '.join(f.name for f in sorted(JOBS_DIR.glob('*/')))}"
    meta = matches[0] / "job.json"
    saved = json.loads(meta.read_text(encoding="utf-8"))
    if saved.get("status") not in ("ready", "approved"):
        return f"{matches[0].name} is already {saved.get('status')}; nothing changed."
    meta.write_text(json.dumps({**saved, "status": decision}, indent=2), encoding="utf-8")
    if decision == "approved":
        start_detached()
        return f"Approved {matches[0].name}. Starting it now (it waits if that tool is busy or you're using it)."
    return f"Skipped {matches[0].name}. It won't run."


def start_detached() -> None:
    """Start a burner run in the background (a job can outlast Hermes's 1-hour script limit)."""
    log = open(BASE / "data" / "burner_last.log", "a", encoding="utf-8")
    subprocess.Popen([sys.executable, str(BASE / "burner.py")], cwd=BASE, stdout=log, stderr=log,
                     stdin=subprocess.DEVNULL,
                     creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))


def summary(runs: list[dict], now: datetime) -> str:
    """One block for the 9 AM Discord report: what ran in the last 24h."""
    recent = [r for r in runs if now - datetime.fromisoformat(r["end"]) < timedelta(hours=24)]
    if not recent:
        return ""
    passed = [r for r in recent if r["status"] == "passed"]
    lines = [f"**Burner, last 24h:** {len(passed)} passed, {len(recent) - len(passed)} failed"]
    for r in recent:
        mark = "✅" if r["status"] == "passed" else "❌"
        lines.append(f"{mark} {r['job']} on {r['provider']}: {r.get('branch') or r.get('reason', '')}")
    if passed:
        lines.append("Review + merge the ✅ branches when you're ready (nothing is merged for you).")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    now = datetime.now()
    runs = read_runs()
    if "--summary" in argv:
        print(summary(runs, now))
        return 0
    status = read_status(STATUS_FILE.read_text(encoding="utf-8")) if STATUS_FILE.exists() else {}
    if "--pending" in argv:
        print(pending_message(status, now))
        return 0
    for flag, decision in (("--approve", "approved"), ("--skip", "skipped")):
        if flag in argv:
            print(decide(argv[argv.index(flag) + 1], decision))
            return 0
    busy = {p for p in LOG_DIRS if lock(p).exists()
            and now - datetime.fromtimestamp(lock(p).stat().st_mtime) < timedelta(hours=3)}
    active = {p for p in LOG_DIRS if p not in busy and jet_active(p, last_end_for(runs, p), now)}
    for job in ready_jobs():
        if not allowed(job):
            print(f"skip {job['id']}: project {Path(job['project']).name} is not on the burner list")
            continue
        provider = pick_provider(status, job.get("ai", "any"), active | busy)
        if provider is None:
            print(f"wait {job['id']}: no tool free (busy: {sorted(busy) or 'none'}, Jet active: {sorted(active) or 'none'})")
            continue  # a later job may fit the other tool
        if job["status"] != "approved" and not auto_ok(status[provider]):
            print(f"wait {job['id']}: needs Jet's approval ({provider} {status[provider]['week_used']:g}% used, "
                  f"reset in {status[provider]['week_hours']:g}h)")
            continue
        if "--dry-run" in argv:
            print(f"would run {job['id']} ({Path(job['project']).name}) on {provider}")
            return 0
        lock(provider).parent.mkdir(exist_ok=True)
        lock(provider).write_text(job["id"])
        set_status(job, "running")  # so the next hourly tick doesn't pick the same job
        start = datetime.now()
        try:
            result = run_job(job, provider)
        finally:
            lock(provider).unlink(missing_ok=True)
        record = {"job": job["id"], "provider": provider, "start": start.isoformat(),
                  "end": datetime.now().isoformat(), **result}
        RUNS_LOG.parent.mkdir(exist_ok=True)
        with RUNS_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        set_status(job, result["status"])
        print(f"{result['status']}: {job['id']} on {provider} → {result.get('branch') or result.get('reason')}")
        return 0  # one job per run; Hermes calls again next hour
    print("idle: nothing to start")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
