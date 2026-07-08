# <pkg> — agent guide

<one line: what this project is>

## Commands

- **Full gate — run before calling any task done:** `just check`
- Test: `uv run pytest`
- Type check: `uv run ty check`
- Lint + format: `just fmt`

## Where things are

- Coding + testing standards → [`CODING_STANDARDS.md`](CODING_STANDARDS.md)
- Domain / context → `CONTEXT.md` (see `docs/agents/` for consumer rules)
- Source: `src/<pkg>/`; tests are interleaved as `*_test.py` next to the code

## Conventions (summary — full rules in CODING_STANDARDS.md)

- Package manager is **uv**. Never `pip` or `poetry`.
- Type checker is **ty**, linter/formatter is **ruff** — both gate CI.
- Test files use the **`*_test.py`** suffix, never `test_*.py`.
