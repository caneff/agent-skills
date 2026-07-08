# Convert an existing repo

Reach the same target state as a greenfield setup, but **non-clobbering**: this
repo has history, config, and choices a human made. Migrate deltas; don't
bulldoze. Report what changed and what you deliberately left alone.

## 1. Survey before touching anything

Read and note the current state:

- `pyproject.toml` — build backend, existing `[tool.*]`, deps, `requires-python`.
- Lockfile — `poetry.lock` / `requirements.txt` (→ migrate) vs `uv.lock` (already uv).
- Layout — flat (`<pkg>/` at root) vs src (`src/<pkg>/`).
- Test naming — `test_*.py` (legacy) vs `*_test.py` (target).
- Existing `.pre-commit-config.yaml`, CI workflows, `.githooks/`, hooks.
- `CLAUDE.md` / `AGENTS.md` / `CONTEXT.md` — don't overwrite prose a human wrote.

Present a short before→after diff and the migration plan. Get a nod before
editing if anything is destructive.

## 2. Migrate to uv (if not already)

- Poetry → uv: translate `[tool.poetry.dependencies]` to `[project.dependencies]`
  + `[dependency-groups]`, then `uv sync`. Remove `poetry.lock`.
- requirements.txt → `uv add` each, then delete the txt.
- Add the dev tools: `uv add --dev ruff ty pytest pytest-cov hypothesis pre-commit`.

## 3. Layout + test naming

- Flat → src: move `<pkg>/` to `src/<pkg>/`, add `py.typed`. Update any
  `[tool.*] include`/packages paths.
- Rename `test_*.py` → `*_test.py`. This is mechanical but touches imports/CI —
  do it as one reviewable commit. (A `test_` *helper* that isn't a test drops
  the prefix entirely, e.g. `testing_support.py`.)

## 4. Merge config, don't replace

Apply `templates/pyproject-snippet.toml` by **merging** into existing `[tool.*]`
tables. If the repo already sets a rule/line-length deliberately, surface the
conflict rather than silently overwriting. Same for `.gitignore` — append
missing entries, don't clobber.

## 5. Replace ad-hoc hooks with the pre-commit framework

If the repo uses bare `.githooks/` + a hand-written CI mirror (my old pattern),
retire both: install `templates/pre-commit-config.yaml`, move the CI to
`pre-commit run --all-files`, delete the bash mirror and `core.hooksPath`. One
source of truth now.

## 6. Docs + task runner

Add `justfile`, `AGENTS.md`, `CODING_STANDARDS.md` if absent. If a `CLAUDE.md`
exists, fold its content into `AGENTS.md` and leave a note (Claude Code reads
AGENTS.md) — don't maintain both.

## 7. Rejoin

Return to `SKILL.md` **step 8 (Verify)**: `just check` must be green before you
commit. Then commit the migration; push if the remote already exists (skip the
`gh repo create` step — this repo is already on GitHub).

## Rules

- Non-clobbering: never overwrite human prose or a deliberate config without
  flagging it.
- One concern per commit (uv migration, layout move, test rename) — a reviewer
  has to be able to read it.
- Report a final summary: changed / migrated / left untouched.
