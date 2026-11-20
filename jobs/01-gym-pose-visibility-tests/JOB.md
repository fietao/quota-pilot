# Job: tests for the low-visibility joint filter (gym)

Add a NEW file `tests/test_pose_visibility.py`. Do not edit any existing file (no changes to `coach/` or other tests).

What to test, in `coach/pose.py`:
- `_point(frame, name)`: returns `(x, y)` when visibility >= `MIN_VISIBILITY` (0.5), including exactly 0.5 (the code
  uses `<`, so 0.5 is kept); returns `None` when visibility is below 0.5 and when the joint is missing.
- `_body(frame)`: returns `None` if any joint in `LANDMARKS` is hidden or missing; returns a dict of `(x, y)` pairs
  (2-tuples, visibility dropped) when every joint is visible.
- Use small hand-made frames (dicts of name → (x, y, visibility)). No video files, no MediaPipe, no network.

At least 4 test functions. All tests (old and new) must pass with `.venv\Scripts\python.exe -m pytest tests -q`.
If a test reveals a real bug, do NOT fix the code: mark that test `@pytest.mark.xfail(reason="...")` and explain.
