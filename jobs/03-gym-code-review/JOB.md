# Job: read-only code review (gym)

Read the code in `coach/` and `tests/`. Do NOT edit any code or test. Write exactly one new file:
`reviews/2026-11-review-gym.md`.

In it, list up to 10 findings, most serious first. For each:
- `file:line`
- What can go wrong, in one plain sentence
- A concrete input or situation that triggers it (e.g. "a video where the person turns their back for 3 s")
- Severity: high / medium / low
- A suggested fix in one sentence (do not apply it)

Only real problems you can point to in the code (bugs, crashes, wrong results, missing error handling for things that
can actually happen). No style comments. If you find fewer than 10, list fewer. End with one line: "Checked files: ...".
