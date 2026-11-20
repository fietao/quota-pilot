# quota-pilot

Use every AI subscription close to its limit before it resets, without ever blocking my own work.

I pay for Claude, Codex, Gemini and Antigravity. Each resets on its own schedule, and unused
quota is just lost. quota-pilot tracks all of them and spends the leftover on safe, checkable jobs.

## What it does
- **`quota_check.py`**: % used and hours to reset per AI. Reads local logs only: Codex session
  logs, Gemini chat logs, Claude Code status line, `agy /usage`. No browser cookies, no scraping.
- **`burner.py`**: hourly. Picks the AI with the closest reset that I'm not using, runs one
  approved job on a local `burn/<id>` branch. Never merges, pushes or sends. Keeps 20% of each
  week for me, and asks first on Discord unless the quota would be wasted anyway.
- **`checks/job_check.py`**: hard-to-fake pass checks. Tests must pass, no existing test line may
  be deleted, "write tests" jobs must add N new tests (doing nothing fails).
- **`reminders.py`**: morning Discord report: 3 human tasks + projects untouched for 14+ days.

## Design choices
- Show % left + hours to reset, not "sessions left" (that's fake precision).
- Measure first, automate second: shipped the forecast, watched a real week, then built the burner.
- Plain scripts, no AI, wherever no judgment is needed: free, fast, predictable.

Full reasoning: [`plans/quota-pilot.md`](plans/quota-pilot.md)

## Run
```
python quota_check.py
python -m unittest
```

Built for my own setup (Windows, Hermes on Discord), so paths and providers are mine.
