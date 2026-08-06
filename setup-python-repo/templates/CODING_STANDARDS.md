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

- Annotate everything, everywhere — not just the public surface. Internal
  helpers, test functions, and test helpers all carry annotations too. `ANN`
  runs on `*_test.py` as well (only `S101`, the assert rule, is relaxed there),
  so a bare `def test_...():` is a lint failure — write `def test_...() -> None:`.
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
- Prefer **`@pytest.mark.parametrize`** where it makes sense: when several tests
  share one body and differ only by data (inputs and expected outcomes), fold
  them into one parametrized test with a named `id` per case, rather than copying
  the body. "Where it makes sense" is the limit — don't force unrelated cases
  together, don't parametrize when each case needs its own distinct assertions or
  a descriptive name that carries real meaning, and prefer an assert helper over
  a cross-cutting parametrize when a known upcoming file split would fight it.
- Markers must be registered (pytest runs `--strict-markers`). An `xfail` that
  passes is a failure (`xfail_strict`) — remove the marker when the bug is fixed.

## Style

- Boring over clever. The reader at 3am wins.
- pathlib over `os.path` (ruff `PTH`). Don't shadow builtins (`A`).
- Keep public API surface small and typed — downstream agents type-check
  against it via `py.typed`.
