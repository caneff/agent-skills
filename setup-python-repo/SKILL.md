---
name: setup-python-repo
description: Set up a new Python repo — or convert an existing one — to my standard 2026 agent-assisted stack (uv, ruff, ty, pytest, pre-commit, GitHub Actions, justfile, AGENTS.md).
disable-model-invocation: true
---

# Set up a Python repo

Bring a repo to my standard stack: **uv, ruff, ty, pytest, pre-commit, GitHub
Actions, justfile, AGENTS.md.** Works on an empty dir (new) or an existing repo
(convert). The **target state is identical** either way — only the starting
point differs.

## 0. Detect: new or convert

Run `git remote -v`, `ls`, and read any `pyproject.toml`.

- **Empty / greenfield** → follow the steps below.
- **Existing project** (has `pyproject.toml`, source, or history) → **read
  [`convert.md`](convert.md) and follow it instead**, then rejoin at step 8
  (Verify). Convert is non-clobbering; the steps below assume a clean slate.

**Done when:** you've classified the repo and, if converting, loaded
`convert.md` (which itself rejoins here at step 8).

## 1. Init + structure

```bash
uv init --lib --name <pkg>      # src layout + hatchling + py.typed
```

Target layout (interleaved tests — test sits next to the code it tests):

```
src/<pkg>/__init__.py
src/<pkg>/py.typed
src/<pkg>/<module>.py
src/<pkg>/<module>_test.py     # *_test.py suffix, NEVER test_*.py
pyproject.toml
```

`uv init --lib` already writes `.python-version`, `.gitignore`, `README.md`, and
uses the `uv_build` backend — later steps *merge into* these, don't clobber them.

**Done when:** `src/<pkg>/py.typed` exists and layout is src, not flat.

## 2. Python version

Set `requires-python = ">=3.14"` and write `.python-version` = `3.14`.

**Done when:** both agree on 3.14.

## 3. Dependencies

Ask the optional data-science set — one round, defaults shown, veto any:

- **pandas + pandas-stubs** — [Y]  (pulls numpy transitively)
- **plotly** — [Y]
- **marimo** — [n]

```bash
uv add pandas pandas-stubs plotly        # whichever were kept
uv add --dev ruff ty pytest pytest-cov hypothesis pre-commit
uv tool install rust-just                # the `just` binary, in-ecosystem (needed for the justfile)
```

`uv add --dev` pins exact versions in `uv.lock` — that IS the pin (ty is beta;
the lock is what stops it floating).

**Done when:** dev group has all six tools and `uv.lock` exists.

## 4. Config

Merge the blocks from [`templates/pyproject-snippet.toml`](templates/pyproject-snippet.toml)
into `pyproject.toml` (ruff, ty, pytest, coverage, wheel-exclude). Don't
clobber the `[project]` uv already wrote — merge, don't overwrite.

**Done when:** `uv run ruff check .` and `uv run ty check` both execute (may
report findings — that's fine; they must *run*).

## 5. Gates: pre-commit

Copy [`templates/pre-commit-config.yaml`](templates/pre-commit-config.yaml) →
`.pre-commit-config.yaml`, then:

```bash
uv run pre-commit autoupdate      # refresh hook revs to current
uv run pre-commit install
```

Pattern: upstream isolated hooks (ruff, hygiene) + one `local` system hook for
`ty` (ty needs your venv to resolve imports). **pytest is NOT a hook** — too
slow for every commit; it lives in CI only.

**Done when:** `uv run pre-commit run --all-files` executes end to end.

## 6. Gates: CI

Copy [`templates/ci.yml`](templates/ci.yml) → `.github/workflows/ci.yml`. Pin
`astral-sh/setup-uv` to the current tag. CI = the same pre-commit config +
pytest, so there's no bash mirror to keep in sync.

Also copy [`templates/clear-in-review.yml`](templates/clear-in-review.yml) →
`.github/workflows/clear-in-review.yml`. It strips the `in-review` orchestration
label when an issue closes, so a merged PR's `Closes #N` doesn't leave the label
stranded on the closed issue. The job is gated on the label being present, so it
sits inert until the `/implement` → PR flow starts using it.

**Done when:** both workflow files exist; `ci.yml` references `setup-uv` +
`pytest`.

## 7. Docs + task runner

Copy these templates, filling `<pkg>` / project one-liner:

- [`templates/AGENTS.md`](templates/AGENTS.md) → `AGENTS.md` — thin router:
  overview + commands + pointers. No CLAUDE.md.
- [`templates/CODING_STANDARDS.md`](templates/CODING_STANDARDS.md) →
  `CODING_STANDARDS.md` — the standards a reviewer loads to judge a diff.
- [`templates/justfile`](templates/justfile) → `justfile` — `just check` runs
  the whole gate.
- [`templates/gitignore`](templates/gitignore) → `.gitignore`.
- [`templates/LICENSE`](templates/LICENSE) → `LICENSE` — MIT, fill year + author.
- `README.md` — stub if missing.

**Done when:** AGENTS.md points at `just check` and `CODING_STANDARDS.md`.

## 8. Verify (local, before it goes public)

```bash
just check      # ruff + ty + pytest — must be GREEN
```

Fix anything red. A repo that fails its own gate must not become a remote
artifact.

**Done when:** `just check` is fully green.

## 9. GitHub (new repos only — LATE, after green)

```bash
git add -A && git commit -m "Initial setup: uv + ruff + ty + pytest + CI"
gh repo create <name> --source=. --private --push
```

Push a working repo, not a WIP. Skip if converting an already-remote repo.

**Done when:** the remote exists and CI is running on the first push.

## 10. Matt Pocock skills config

Invoke `setup-matt-pocock-skills` (issue tracker / triage labels / domain docs).
It runs **after** AGENTS.md exists (it writes its `## Agent skills` block there)
and after the remote exists (it inspects `git remote` for the issue tracker).

**Don't ask its three questions — my answers are always the same: this
repo's own `AGENTS.md` (root) states them. Pass those and proceed
non-interactively.**

Only stop to ask if the repo state contradicts them (e.g. no GitHub remote).

**Done when:** `docs/agents/*` exist and AGENTS.md has an `## Agent skills` block.

## 11. Peacock window color (optional)

Give the repo its own VS Code window color so it's distinct at a glance. Ask
once — "Want a Peacock window color? (pick / skip)". If yes, invoke
`setup-peacock-color` (shows the picker, writes `.vscode/settings.json` with
`peacock.remoteColor` for WSL). Purely cosmetic — skip without ceremony if the
user declines.

**Done when:** user picked a color (settings.json written) or declined.

## Notes

- **ty is beta.** Its `[tool.ty]` surface drifts — the snippet was verified but
  re-check against current ty docs if a key is rejected.
- Everything except layout/packaging is identical for libraries and apps —
  there is no lib/app fork. "Publish" is a later, separate act.
