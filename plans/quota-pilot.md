# Quota Pilot — plan

Planned 2026-11-08 with plan-master. Status: not started.

## Goal
Use every AI subscription close to its limit before each reset, without ever blocking Jet's own work.
Single outcome that matters: no tool resets with lots unused while Jet still had nothing taken from him.

## Deliverable
1. `quota_check.py` — reads usage per provider, prints % used + hours to reset.
2. Claude Code statusline script — appends Claude 5h/7d `rate_limits` to a local log.
3. Hermes daily Discord report — forecast per provider + suggested days for Claude sessions.
4. (next week) Backlog file + idea scanner writing learning-brain proposals.
5. (next week) Burn runner — spends leftover Codex/Gemini/Antigravity on approved backlog jobs.

## Chosen Approach (+ rationale)
Forecast + reserve/burn queue + jobs on local branches; learn rhythm after 3 weeks of data.
- **Claude is suggest-only.** Pro OAuth is for Claude Code/claude.ai; headless `claude -p` billing reportedly changed in 2026 (unverified). Hermes only tells Jet when to use his own Claude sessions.
- **Auto-spend runs on Codex, Gemini, Antigravity**, which have no such restriction.
- **Own small script, not an existing tool**: no WSL, no browser-cookie access, Jet can explain every line.
- **Measure before automating** (advisor): ship forecast first, watch one real week, then build the burn runner.

### Decisions (with reasons)
| Decision | Reason |
|---|---|
| Report on Discord via Hermes | Hermes already runs 24/7 and posts scheduled jobs; visible on phone |
| Burner = `burner.py` + hourly Hermes job, one job per run (2026-11-09) | Jet chose the projects it may touch: ai-detector, gym, quota-pilot (others stay manual). Picks Codex/agy with the closest weekly reset, keeps 20% of each week, skips a tool Jet used in the last 60 min. Each job is a local branch `burn/<id>`; it never merges, pushes or sends. **Ask first (fixed 2026-11-09 after Jet flagged it):** a job runs only after Jet replies `approve NN` to Hermes on Discord, unless the tool's weekly reset is <24h away AND >50% is unused (quota wasted anyway). Each job is asked once. The first version skipped asking, which was wrong; the original plan already had "post to Discord first". Hermes only *starts* it detached because Hermes stops scripts after 1 h and a job + fix round can take ~90 min. Results show in the 9 AM report |
| Job checks are hard to fake (`checks/job_check.py`) | Tests must pass, no line may be deleted from an existing test, "write tests" jobs need N new tests (doing nothing fails), review jobs may only write under `reviews/`. Tested on a throwaway repo: 6 pass/fail cases |
| Morning reminders = plain script, no AI (2026-11-09) | Reading a table and posting 3 rows needs no judgment, so a script is free, fast and predictable. 3 per day because more becomes noise. Rides on the 9 AM report (one ping, not two). Hermes catches up missed jobs after the laptop wakes; `data/morning_sent.txt` stops a second send the same day. "Not touched in 14+ days" uses git date, or newest file if no git, so forgotten projects show up by themselves |
| Status file `data/quota-status.md` every 15 min (Hermes, silent) + short form in the Claude Code status line (2026-11-09) | AIs cannot see the status line, so a file is what lets every AI check quota before picking who builds (rule added to ai-os rules.md). The status line reads the file instead of calling `agy /usage`: it redraws many times a minute and agy takes seconds. "(old)" shows if the file is over 60 min stale |
| Claude data from statusline log (2026-11-09: added to the existing `~/.claude/statusline.ps1`, one line per change) | Local, free, no browser, no settings change; writing only on change keeps the file small since the statusline runs on every redraw. Trade-off: only updates when Claude Code was used |
| Show % left + hours to reset, not "sessions left" | Session counts are fake precision |
| Antigravity = `agy -p /usage` (2026-11-09) | Jet found the "Models & Quota" screen; in print mode `/usage` prints tab-separated % remaining + reset per pool (Gemini, Claude/GPT, Argon) with no model turn. Undocumented format, so parse defensively and fall back to "unknown". Call it from PowerShell or a list-args subprocess: Git Bash rewrites `/usage` into a file path |
| agy is a builder and a burn provider | User has agy on AI Pro; `agy -p --print-timeout 45m` gives a hard job timeout |
| Gemini counted from its own chat logs, not a wrapper (2026-11-09) | `~/.gemini/tmp/*/chats/*.jsonl` already records every response with a timestamp, so every call counts with nothing to remember; "~" because one response can be several API calls |
| Burn only in last 24h before a reset, skip if tool used in last 60 min | Codex/Antigravity share pools with Jet's own work — protects "no lockout" |
| 2h veto window on Discord | Matches "roll it over if I don't like them" while not wasting quota when busy |
| 45-min timeout per job | Codex can burn quota busy-waiting on long tests |
| Provider closest to an unused reset goes first | Use-it-or-lose-it |
| Fixed reserve first (Codex 20%, Gemini 200/day), measured later | No history yet; replace with measured weekly peak + 20% |
| Every job = new local branch + lesson + quiz | Never merges/pushes; Jet must be able to explain what was built |
| Off-limits: aftersell, carmick, pnok, ai-reading-car-analysis, git push, outside sends, graded homework | Others' data; user rules |

## Alternatives Considered
- **Forecast only** — spends nothing on its own; kept as phase 1.
- **Cross-provider switching** — partly used (closest-to-reset first), not a full router.
- **Fully automatic burn** — rejected; veto window instead.
- **Chrome scrape of claude.ai usage page** — needs Chrome open, breaks on page changes.
- **Headless Claude burn** — ToS/billing risk.

## Existing Tools & Similar Programs
- [ccusage](https://github.com/ryoppippi/ccusage) — Claude/Codex log reports; shows tokens/$, not plan %.
- [CodexBarWin](https://github.com/nek0der/CodexBarWin) — tray app for Claude/Codex/Gemini limits; needs WSL 2.
- Win-CodexBar — 16 providers; decrypts Chrome cookies (security risk).
- [claude-overnight](https://pypi.org/project/claude-overnight/) — limit-aware queue; Claude-only, unverified.
- Claude Code statusline `rate_limits` — the data source we use (Claude Code 2.1.319 installed; field to be confirmed in step 2).
- Codex `~/.codex/sessions/**/*.jsonl` `rate_limits` — confirmed locally 2026-11-08 (primary=5h, secondary=weekly, plan_type=plus).

## Key Resources
- [Claude Code legal & compliance](https://code.claude.com/docs/en/legal-and-compliance) — Pro OAuth scope.
- [Gemini CLI quotas](https://geminicli.com/docs/resources/quota-and-pricing/) — AI Pro ≈1,500 req/day, resets midnight Pacific (not re-confirmed for Nov 2026).
- [Antigravity rate limits (Google)](https://blog.google/feed/new-antigravity-rate-limits-pro-ultra-subsribers/) — Pro: 5h refresh, weekly ceiling.
- [Overnight agent pitfalls](https://dev.to/thebasedcapital/why-your-overnight-ai-agent-fails-and-how-episodic-execution-fixes-it-2g50) — locking, stuck runs.
- [Codex busy-wait bug](https://community.openai.com/t/bug-codex-exhausts-entire-usage-quota-busy-waiting-on-a-long-running-test-instead-of-sleeping/1408367) — reason for timeouts.

## Baseline (2026-11-08)
Claude Pro 16% week (resets Sat 2 PM). Codex Plus 10% week (resets Wed Nov 11 10:51), last week peak 8%.

## Steps
This week (deadline: before Codex reset Wed Nov 11 if possible):
1. `quota_check.py` — Codex from logs first, then Claude log, Gemini count, Antigravity (look for agy quota source in `~/.gemini/antigravity-cli`; "unknown" if none).
   → verify: output matches today's numbers (Codex 10%, Claude 16%); no keys printed.
2. Statusline script appends `{ts, five_hour, seven_day}` to `data/claude_usage.jsonl`.
   → verify: confirm field exists in 2.1.319; file gets a new line after one Claude message.
3. Gemini wrapper (`g.ps1` → logs a line, then calls `gemini`) + Hermes daily job posting the report.
   → verify: Discord message arrives on phone with all 4 providers.

Next week (after one week of real data):
4. `backlog.md` + idea scanner → learning-brain `PROP-*.md` proposals (parked features, tests/reviews, learning material, upgrade ideas).
   → verify: 3–5 proposals Jet actually wants.
5. Burn runner: last 24h before reset, skip if tool active in last 60 min, Discord veto (2h), closest-reset first, 45-min timeout, new branch, lesson + quiz.
   → verify: dry run lists jobs + target provider; then one real job ends as a reviewed branch.
6. After 3 weeks: replace fixed reserves with measured weekly peak + 20%.

## Suggested Skills (per step)
1. none (plain Python).
2. none in library; Claude Code's built-in `statusline-setup` agent fits.
3. none.
4. learning-brain — `C:\dev\claude_baseskill\manual\learning-brain\SKILL.md` — review-first proposal format.
5. ralph-loop-workflow (1.135) — `C:\dev\claude_baseskill\manual\ralph-loop-workflow\SKILL.md` — build→verify loop, stops when blocked; plus `route` for Antigravity jobs.

## Done Criteria
- Week 1: daily Discord report arrives 7/7 days with correct numbers (spot-checked against `/usage` and Codex `/status`).
- Full system: one full week where Codex and Gemini end ≥90% used, zero lockouts during Jet's own work, and Jet completes the quizzes from burn jobs (track quizzes done/week).
- Claude (suggest-only) and Antigravity (no numbers) are not part of the pass criteria.

## Risks
- **Burn runner locks Jet out** (biggest) → last-24h rule, activity check, 5% ceiling.
- Junk output nobody reads → backlog only from approved proposals; quiz metric.
- Statusline log stale when Claude Code unused → report shows "last seen <time>".
- Gemini count wrong if called outside the wrapper.
- Provider limit/billing changes (Codex ad-hoc resets, Anthropic headless billing) → re-check monthly.
- Laptop off → runner only runs when laptop is on; accept some loss.

## Rollback
Everything is additive: disable the Hermes job and the statusline line in settings; burn jobs live on local branches and can be deleted after review (ask first).
