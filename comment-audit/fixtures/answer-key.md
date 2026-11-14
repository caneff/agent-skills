# Answer key

The verdict the skill must reach for each comment in `sample.py`,
`test_sample.py` and `sample.rs`, each judged from its own text. A citation
that carries a why is a salvage (strip every number, keep the why); a whole
delete only when nothing but the number remains.
`comment-audit/fixtures_test.py` parses this table and checks it against the
fixture files.

| # | File | Line | Bucket | Category | After |
|---|------|------|--------|----------|-------|
| 1 | `sample.py` | 1 | cut | citation | Upload client: storage 404s the first cold read, so uploads retry. |
| 2 | `sample.py` | 2 | load-bearing | directive | |
| 3 | `sample.py` | 10 | cut | citation | — gone — |
| 4 | `sample.py` | 13 | cut | restatement | — gone — |
| 5 | `test_sample.py` | 5 | keep | why | |
| 6 | `sample.rs` | 1 | keep | api-contract | |
| 7 | `sample.rs` | 4 | cut | citation | — gone — |
| 8 | `sample.rs` | 5 | cut | restatement | — gone — |

Rows 1, 5 and 6 are the three mis-cuts the 2026-11-13 sweep showed:

- **1, a module docstring that carries a citation.** The `(spec #412, decision
  3)` goes and the why stays. Cutting the whole docstring loses the reason for
  the retry.
- **5, a test-intent comment.** It names the failure the assertion guards
  (a double charge), which the test's name and body cannot say. A keep, never
  a restatement.
- **6, an API contract on a Rust `///` line.** It states the `None` promise
  callers depend on. A keep, `api-contract`; a `///` line is a doc comment,
  not narration.
