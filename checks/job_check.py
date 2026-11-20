"""Pass/fail check for burner jobs, run inside the job's worktree. Exit 0 = pass.

  python job_check.py [--min-new-tests N] [--only-paths PREFIX] -- <test command...>

Always: the test command must pass, and no line may be deleted from an existing test file
(so an AI can't make tests pass by weakening them).
--min-new-tests N: at least N more `def test_` than the last commit (so doing nothing fails).
--only-paths PREFIX: every changed file must start with PREFIX (read-only jobs, e.g. reviews/).
"""
import re
import subprocess
import sys
from pathlib import Path

NOTES = {"JOB.md", "FIX.md"}  # the burner's instructions, removed before commit


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8").stdout


def count_tests_on_disk():
    return sum(len(re.findall(r"^\s*def test_", p.read_text(encoding="utf-8", errors="replace"), re.M))
               for p in Path("tests").rglob("*.py")) if Path("tests").exists() else 0


def count_tests_at_head():
    total = 0
    for line in git("grep", "-c", r"^\s*def test_", "HEAD", "--", "tests").splitlines():
        total += int(line.rsplit(":", 1)[1])
    return total


def main(argv):
    sep = argv.index("--")
    opts, test_cmd = argv[:sep], argv[sep + 1:]
    problems = []

    tests = subprocess.run(test_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(tests.stdout[-2000:], tests.stderr[-1000:])
    if tests.returncode:
        problems.append("tests fail")

    for line in git("diff", "HEAD", "--numstat", "--", "tests").splitlines():
        added, deleted, path = line.split("\t")
        if deleted not in ("0", "-"):
            problems.append(f"{path}: {deleted} line(s) deleted from an existing test file")

    if "--min-new-tests" in opts:
        need = int(opts[opts.index("--min-new-tests") + 1])
        new = count_tests_on_disk() - count_tests_at_head()
        if new < need:
            problems.append(f"only {new} new test(s), need {need}")

    if "--only-paths" in opts:
        prefix = opts[opts.index("--only-paths") + 1]
        changed = [l[3:].strip().strip('"') for l in git("status", "--porcelain", "-uall").splitlines()]
        cache = ("__pycache__", ".pytest_cache", ".pyc")  # created by running the tests themselves
        outside = [p for p in changed if p not in NOTES and not p.startswith(prefix)
                   and not any(c in p for c in cache)]
        if outside:
            problems.append(f"changed files outside {prefix}: {', '.join(outside)}")
        if not any(p.startswith(prefix) for p in changed):
            problems.append(f"nothing written under {prefix}")

    print("CHECK " + ("PASSED" if not problems else "FAILED: " + "; ".join(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
