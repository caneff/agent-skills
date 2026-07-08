# Coding standards

The rules a change must satisfy. A reviewer (human or Sandcastle) loads this
file to judge a diff. The gate (`just check`) enforces the mechanical parts;
this doc covers the parts a linter can't.

## Tooling is law

- **uv** for everything. No `pip`, no `poetry`, no `python -m venv` by hand.
- **ruff** lints + formats; **ty** type-checks. If `just check` is red, the
  change is not done. Don't `--no-verify` or add blanket `# noqa` / `# ty: ignore`
  to silence a real finding — fix it, or narrow the suppression with a reason.

## Types

- Public functions and methods carry annotations (ruff `ANN` enforces presence;
  ty checks them). ty is gradual — it won't demand annotations, so `ANN` is what
  forces them. Don't leave public signatures inferred.
- Prefer precise types over `Any`. Reach for `Any` only at genuine boundaries,
  and say why.
- `X` (capital) is allowed for feature matrices — that's why `N803`/`N806` are
  off. Don't abuse the exception for ordinary variables.

## Tests

- Test files are **`*_test.py`**, interleaved next to the code they test.
- Test **behavior**, not implementation. A test that only restates the code is
  noise.
- **No assertion-free tests.** A test that exercises code without asserting an
  observable outcome is worse than no test — it inflates coverage and proves
  nothing. Coverage is a soft signal; a green bar with hollow tests is a lie.
- Use **hypothesis** for numeric / edge-heavy logic (parsers, transforms,
  anything with a range of valid inputs) — it finds the cases you won't enumerate.
- Markers must be registered (pytest runs `--strict-markers`). An `xfail` that
  passes is a failure (`xfail_strict`) — remove the marker when the bug is fixed.

## Style

- Boring over clever. The reader at 3am wins.
- pathlib over `os.path` (ruff `PTH`). Don't shadow builtins (`A`).
- Keep public API surface small and typed — downstream agents type-check
  against it via `py.typed`.
