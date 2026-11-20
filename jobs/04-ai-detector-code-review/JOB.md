# Job: read-only code review (ai-detector)

Read the Python files at the repo root (e.g. `similarity.py`, `detector.py`, `calibrate.py`) and `tests/`. Do NOT edit
any code or test. Write exactly one new file: `reviews/2026-11-review-ai-detector.md`.

In it, list up to 10 findings, most serious first. For each:
- `file:line`
- What can go wrong, in one plain sentence
- A concrete input that triggers it (e.g. "an essay written in Thai", "a 3-word text", "Ollama not running")
- Severity: high / medium / low
- A suggested fix in one sentence (do not apply it)

Pay special attention to: inputs that make a score wrong without an error (silent wrong answers), and any score that
could be read as proof that someone cheated when the method can't support that. No style comments. End with one line:
"Checked files: ...".
