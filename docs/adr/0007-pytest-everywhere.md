# Python tests are pytest, everywhere

Status: accepted (ruled by Chris 2026-10-09: "pytest absolutely everywhere")

## Context

No decision put this repo's Python tests on `unittest`. The repo had no
Python environment (no `pyproject.toml`, no lock file), and adding a
dependency is a stop-and-ask, so workers wrote tests with what the system
`python3` already had. By 2026-10-09 the 41 `*_test.py` suites were 19
`unittest`, 20 plain-assert scripts and 2 that mention pytest, each run by
`tests/all.sh` as `python3 <file>`. Chris's other Python repos (gridfind,
second-brain-v2, sudokumaker-custom-constraints, sudokupad-art,
mediawiki-analytics) already declare pytest in a `pyproject.toml`;
factorio_crap holds one `unittest` file.

The impacted-test research
(`docs/research/2026-10-09-impacted-test-selection.md`) found the runner
choice also closed off pytest-based selection such as pytest-testmon.

## Decision

Every Python test in every repo Chris owns is a pytest test: pytest is a
declared dev dependency of the repo, and tests are written in pytest's idiom
(plain `assert`, fixtures, `parametrize`), never `unittest.TestCase` or a
script that asserts at import. This repo gains a `pyproject.toml` declaring
pytest, and `tests/all.sh` runs `*_test.py` under it.

## Consequences

- The seam needs pytest available, so a fresh checkout needs one setup step
  it did not need before.
- Existing `unittest` suites run under pytest unchanged, so the runner switch
  and the rewrite into pytest's idiom can land separately.
- pytest-testmon becomes a cheap option for the Python half of impacted-test
  selection; it still does not see the shell, Rust or prose edges.
