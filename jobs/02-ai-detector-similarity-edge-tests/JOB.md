# Job: edge-case tests for the winnowing similarity checker (ai-detector)

Add a NEW file `tests/test_similarity_edges.py`. Do not edit any existing file (no changes to `similarity.py` or other tests).

Test `similarity.compare(a, b, k=5, w=4)` and `similarity.fingerprints` for:
1. Both texts empty → all scores 0.0, no matches, no crash.
2. Punctuation-only text (e.g. "!!! ... ???") → treated like empty.
3. Same words, different case and extra spaces/newlines → scores 1.0 (normalize lowercases and splits on non-word chars).
4. Thai text copied word-for-word (e.g. a Thai sentence repeated in both) → document CURRENT behaviour: `normalize`
   keeps only `[a-z0-9']`, so Thai becomes empty and the score is 0.0. Write the test to assert 0.0 and add a comment
   `# known limit: non-Latin text is not compared` so the gap is visible.
5. Text exactly k words long in both → one shared k-gram is found.
6. Text with k-1 words → returns zeros (short-text rule).
7. `w=1` keeps every k-gram hash (fingerprint count == number of distinct k-grams).

At least 5 test functions. All tests must pass with `.venv\Scripts\python.exe -m pytest tests -q`.
If a test reveals a real bug, do NOT fix the code: mark it `@pytest.mark.xfail(reason="...")` and explain.
