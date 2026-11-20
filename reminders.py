"""Morning reminders: HUMAN jobs from backlog.md + projects not touched in a while. No AI."""
from __future__ import annotations

import subprocess
from datetime import date, datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
BACKLOG = BASE_DIR / "backlog.md"
PER_DAY = 3
STALE_DAYS = 14
PROJECTS = [p for p in Path("C:/dev/projects").iterdir() if p.is_dir()] if Path("C:/dev/projects").exists() else []
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "data", "tmp", "output"}


def human_jobs(text: str) -> list[dict]:
    """Rows of the HUMAN table: | H1 | project | job | why | when |"""
    jobs = []
    for line in text.splitlines():
        cols = [c.strip() for c in line.strip().strip("|").split("|")]
        if cols and cols[0].startswith("H") and cols[0][1:].isdigit() and len(cols) >= 3:
            jobs.append({"id": cols[0], "project": cols[1], "job": cols[2],
                         "when": cols[4] if len(cols) > 4 else ""})
    return jobs


def pick(jobs: list[dict], today: date) -> tuple[list[dict], int]:
    """Jobs dated today or earlier go first, then the rest in backlog order."""
    due = [j for j in jobs if j["when"] and j["when"] <= today.isoformat()]
    rest = [j for j in jobs if j not in due]
    ordered = due + rest
    return ordered[:PER_DAY], max(0, len(ordered) - PER_DAY)


def last_change(folder: Path) -> date:
    """Last git commit date, or newest file within 2 levels if there is no git."""
    if (folder / ".git").exists():
        out = subprocess.run(["git", "log", "-1", "--format=%cs"], cwd=folder,
                             capture_output=True, text=True)
        if out.stdout.strip():
            return date.fromisoformat(out.stdout.strip())
    newest = 0.0
    for f in list(folder.glob("*")) + list(folder.glob("*/*")):
        if not SKIP_DIRS.intersection(f.parts) and f.is_file():
            newest = max(newest, f.stat().st_mtime)
    return datetime.fromtimestamp(newest).date() if newest else date.min


def stale_projects(folders: list[Path], today: date) -> list[str]:
    return sorted(f.name for f in folders if (today - last_change(f)).days >= STALE_DAYS)


def message(backlog_text: str, folders: list[Path], today: date) -> str:
    jobs = human_jobs(backlog_text)
    shown, more = pick(jobs, today)
    lines = [f"**Your jobs today** ({len(jobs)} human jobs open)"]
    for j in shown:
        due = " ⏰ due" if j["when"] and j["when"] <= today.isoformat() else ""
        lines.append(f"• {j['id']} {j['project']}: {j['job']}{due}")
    if more:
        lines.append(f"…and {more} more in quota-pilot/backlog.md")
    if not jobs:
        lines.append("No human jobs open.")
    stale = stale_projects(folders, today)
    if stale:
        lines.append(f"Not touched in {STALE_DAYS}+ days: {', '.join(stale)}")
    lines.append("Done one? Delete its row in backlog.md (or tell any AI \"H1 done\").")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print(message(BACKLOG.read_text(encoding="utf-8"), PROJECTS, date.today()))
