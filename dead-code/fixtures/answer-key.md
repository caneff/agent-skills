# Answer key

`uvx vulture dead-code/fixtures/sample.py` reports six hits. This table is
the expected triage verdict for each — the bucket the LLM-triage pass in
`dead-code/SKILL.md` must land it in. Running the skill over `fixtures/`
must reproduce this table: every `dead` stays `dead`, and the two
dynamically-reached symbols land `dynamic`, never `dead`.

Captured raw vulture output (this repo, vulture via `uvx`):

```
dead-code/fixtures/sample.py:6: unused import 'os' (90% confidence)
dead-code/fixtures/sample.py:10: unused function 'helper' (60% confidence)
dead-code/fixtures/sample.py:15: unused class 'UnusedHelper' (60% confidence)
dead-code/fixtures/sample.py:18: unused method 'run' (60% confidence)
dead-code/fixtures/sample.py:22: unused function 'main' (60% confidence)
dead-code/fixtures/sample.py:28: unused function 'fixture_db' (60% confidence)
```

| # | Symbol | Line | Kind | Bucket | Reason |
|---|--------|------|------|--------|--------|
| 1 | `os` | 6 | import | **dead** | Imported and never referenced anywhere in the module — no mechanism (entrypoint, fixture, dynamic dispatch) reaches an unused import. Safe to delete. |
| 2 | `helper` | 10 | function | **dead** | Defined, never called anywhere in the fixture, and not named or decorated as an entrypoint, test, or fixture. Nothing dynamically reaches it. |
| 3 | `UnusedHelper` | 15 | class | **dead** | Never instantiated. No dynamic-dispatch or registration pattern (no metaclass registry, no `getattr`-by-name lookup) reaches it. |
| 4 | `run` | 18 | method | **dead** | Only reachable through an instance of `UnusedHelper` (#3), which is itself dead — the method inherits its owner's verdict. |
| 5 | `main` | 22 | function | **dynamic** | Named and shaped as a module entrypoint (`def main():` with no internal caller) — the mechanism that reaches it is `python sample.py` / a `console_scripts` entry point, which vulture's static analysis can't see. Not dead. |
| 6 | `fixture_db` | 28 | function | **dynamic** | Decorated `@pytest.fixture`. pytest injects fixtures into test functions by parameter name at collection time — a dependency-injection mechanism vulture can't see. Not dead. |

Tally: 4 dead, 2 dynamic, 0 unsure.
