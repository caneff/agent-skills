# Spec #509 exploration notes

Repo: `caneff/agent-skills`, worktree branch `caneff/spec`. Spec #509 + tickets
510–517 read via `gh api repos/caneff/agent-skills/issues/<n> --jq .body`.

## 1. all-audits harness

- `all-audits/SKILL.md` — the doc ticket #510 makes the single owner of the
  findings-log/summary/tmpdir/scope spec. Currently still enumerates flags
  inline and has a full grilling-workflow section (both need to collapse to
  pointers per #510).
- `all-audits/harness/findings-schema.md` (102 lines) — findings.jsonl schema.
- `all-audits/harness/HTML-REPORT.md` (100 lines) — summary/report rendering spec.
- `all-audits/run-audits.sh` (~700 lines) — bash orchestrator. Runs each audit
  as its own `claude -p "/name"` process (required because the audits carry
  `disable-model-invocation`, which blocks the `Skill` tool). Flags: `[REPO]`,
  `--out DIR`, `--only NAME[,NAME]`, `--short`, `--index`, `--force/--all`,
  `--mutation a.py,b.py`.
- `all-audits/should_run.py`, `all-audits/cache.py` — staleness cache for the
  two expensive LLM passes (`domain-drift`, `type-tightness`); per-repo record
  at `~/.cache/all-audits/<repo-key>.json`.
- **Test script**: `all-audits/test_run_audits.sh` — hermetic bash test, no
  `claude` invoked (`AUDITS_NO_SYNTH=1`, `AUDITS_NO_OPEN=1`). Run it directly:
  ```
  bash all-audits/test_run_audits.sh
  ```
  Covers `--index` rebuild, `report_path_from_log` (marker vs legacy path),
  `audit_prompt`, `--mutation` selection/cap/auto-select, `module_slug`,
  `collect_module_report`, the mutation sub-index, and the `--short` alias.
  This is the seam #510 says must "pass unmodified except where consolidated
  scope rules change expected output" — re-run after any scope-default change.

## 2. The ten audit skills — fixtures + run commands

Two families. **Script-backed** (fixtures/answer-key.md present, pass one is a
Python parser over a captured tool-output file):

| Skill | Fixture dir | Fixture run command (from repo root) |
|---|---|---|
| dead-code | `dead-code/fixtures/` | `python3 dead-code/audit.py /tmp/vulture-out.txt` *(relative path — bug)* |
| docstring-coverage | `docstring-coverage/fixtures/` | `python3 docstring-coverage/audit.py /tmp/ruff-out.json /tmp/interrogate-out.txt` *(relative — bug)* |
| duplication | `duplication/fixtures/` | `python3 duplication/audit.py /tmp/jscpd-out/jscpd-report.json` *(relative — bug)* |
| error-handling | `error-handling/fixtures/` | `python3 error-handling/audit.py /tmp/ruff-out.json /tmp/bandit-out.json` *(relative — bug)* |
| mutation-audit | `mutation-audit/fixtures/` | `python3 ~/.agents/skills/mutation-audit/audit.py "${TMPDIR:-/tmp}/mutmut-results.txt"` (already absolute) |
| test-audit | `test-audit/fixtures/` | `python3 ~/.agents/skills/test-audit/audit.py <scope>` + `node ~/.agents/skills/test-audit/audit.mjs <scope>` (already absolute) |

Spec text says "three audit skills invoke by relative path" — the actual count
in this worktree is **four**: dead-code, docstring-coverage, duplication,
error-handling all show a bare `<skill>/audit.py` invocation in their SKILL.md
run section (`.py:60`, `:56`, `:51`, `:57` respectively). Worth flagging when
#515 lands — the fix (absolute `~/.agents/skills/<skill>/audit.py`) is the
same shape mutation-audit and test-audit already use as precedent.

Each script-backed skill's SKILL.md has a "## Verify against the fixture"
section spelling out the expected buckets — that prose is the spec for
`answer-key.md`, not a separate contract.

**Prose-driven / LLM-judgment audits** — no fixtures dir, no answer-key,
"no automated seam" by design (spec's own Testing Decisions section confirms
this for the LLM passes):

- `comment-audit/SKILL.md` — **has no `fixtures/` dir today**, despite #516's
  acceptance criterion "comment-audit fixture runs reproduce their answer
  keys." This is a gap: either #516 needs to add fixtures, or that acceptance
  line is stale against the repo's current state. Flag this explicitly to
  whoever picks up #516.
- `test-audit/SKILL.md` — has fixtures (listed above), so its half of that
  acceptance line is satisfiable as written.
- `type-tightness/SKILL.md`, `domain-drift/SKILL.md` — no fixtures dir, pure
  judgment passes with a "## The one test" burden-of-proof section instead.
- `ponytail-audit/SKILL.md` + `ponytail-audit/HTML-REPORT.md` (170 lines) —
  no fixtures; the HTML-REPORT.md is the private report doc #516 trims to
  "card anatomy + tag palette."

## 3. `.extra-skills.json` + skills-safe-update

`.extra-skills.json` at repo root, current sole entry:

```json
{
  "prompt-master": {
    "repo": "nidhinjs/prompt-master",
    "path": "",
    "treeSha": "e6f8879b688c827fb0ed7e1fc43dc5f0977a8b80"
  }
}
```

Format: `{ "<skill-name>": { "repo": "<owner/repo>", "path": "<subfolder or \"\">", "treeSha": "<git tree SHA of that folder>" } }`.
`treeSha` comes from `gh api repos/<repo>/commits/<ref> --jq .commit.tree.sha`
for a root-level skill; the update script bumps it on every sync.

`prompt-master/SKILL.md` frontmatter carries `disable-model-invocation: true`
and a `version: 1.8.0` line (no other skill in the repo has a `version:` key —
that's prompt-master's own upstream convention, not a repo pattern to copy).
No local README/LICENSE stripping has happened for prompt-master; it kept its
`LICENSE` and `README.md` files as-is. **This is the precedent #513 follows**
for humanizer/read-the-damn-docs, except #513 explicitly wants *more*
stripping (scaffolding removed) than prompt-master got — prompt-master is the
registration-mechanics precedent, not necessarily the "how much to strip"
precedent.

`skills-safe-update/scripts/safe-update.sh` syncs any `.extra-skills.json`
entry from its GitHub upstream inside the same git buffer as the `npx skills
update` pass, with the same edit-protection logic (compares local tree SHA to
recorded `treeSha`; diverged = protect). `skills-safe-update/scripts/skills-status.sh`
is the read-only status check — SKILL.md's own "Check status first" section
(#514 wants this reordered ahead of the mutating steps in the doc) says run it
before `safe-update.sh`.

Run:
```
bash skills-safe-update/scripts/skills-status.sh   # read-only status
bash skills-safe-update/scripts/safe-update.sh      # do the update
```
Both default to `SKILLS_DIR=$HOME/.agents/skills`; this worktree is a separate
checkout, so testing #513's `.extra-skills.json` entries against the real
scripts means either pointing `SKILLS_DIR` at this worktree or working in the
real `~/.agents/skills` checkout.

`.protected-skills` (repo root, 2 lines: `ponytail-audit`, `to-tickets`) is
the manual-override list unioned with the auto-detected edited set — separate
mechanism from `.extra-skills.json`, don't conflate the two when touching
skills-safe-update docs.

## 4. flow/ layout, ccstatusline wiring, progress-file grammar

`flow/` (already outside the skills tree — #512 moves `ccstatusline-table`
*into* here):
```
flow/README.md
flow/backup-sync.sh
flow/bin/issue-counts, issue-counts.test.sh
flow/ccstatusline/issue-counts-segment.sh
flow/ccstatusline/settings.json
flow/claude/{CLAUDE.md,RTK.md,hooks/*,settings.json,settings.local.json,subagent-tiers.md}
flow/install.sh
flow/vscode/settings.json
```

`ccstatusline-table/` (currently still in the skills tree, at repo root
alongside the skill dirs):
```
ccstatusline-table/README.md
ccstatusline-table/table-statusline.py
ccstatusline-table/helpers/{burndown-segment.sh, effort-abbrev.py, issue-counts-segment.sh, usage-segment.sh}
```
No `SKILL.md` in this dir — it's config/tooling, not a skill, which is
exactly #512's rationale for relocating it.

**Hardcoded home path** (#512's "no absolute `/home/...` path remains in the
wiring snippet"): `ccstatusline-table/README.md:13` —
```
"command": "python3 /home/caneff/.agents/skills/ccstatusline-table/table-statusline.py",
```
That's the one wiring snippet to fix to `$HOME`-relative. Note
`flow/ccstatusline/settings.json` also has several `/home/caneff/...`
`commandPath` entries (effort-abbrev.py, usage-segment.sh ×4,
publish-usage.sh, sandcastle-segment.sh, issue-counts-segment.sh) — those are
a live personal config file, not documentation, and are **not** in #512's
scope; don't touch them under this ticket.

**Progress-file grammar** — currently stated in **two places** (the
duplication #512 wants collapsed to one):
1. `burndown/SKILL.md:85-92` (step 7) — prose description of the line forms.
2. `ccstatusline-table/helpers/burndown-segment.sh:7-13` — a comment block
   literally titled "Line grammar — a contract with burndown/SKILL.md, change
   in lockstep," restating the same four line forms
   (`burning #<n>`, `#<n> landed <sha>`, `#<n> parked: <why>`, `done`).

Per #512, the single home becomes the segment helper's doc comment (it sits
next to the `awk` parser that actually consumes the grammar), and
`burndown/SKILL.md` points at it instead of restating it — dropping its
"lockstep" cross-reference note along with the duplication. Progress file
itself lives at `~/.cache/burndown/<repo dir name>.progress` (never in-repo);
location is unchanged by #512/#517.

## 5. burndown and implement-spec — current structure

`burndown/SKILL.md` (122 lines) — today's hand-rolled orchestration:
1. List queue (`gh issue list --label ready-for-agent --state open`).
2. Compute frontier manually (check blocking edges per ticket).
3. One-time exploration subagent (`sonnet`), notes to
   `~/.cache/burndown/<repo>.notes.md`.
4. Build: run `implement` skill per ticket, builder stops after commit.
5. Review: fresh `opus` subagent per finished ticket, runs `/code-review`
   directly (slash invocation — #517 wants this to reach code-review "by
   skill pointer, not slash invocation").
6. Land one at a time; **`TaskStop` each builder by name** once its ticket
   settles (named background agent, manual release) — this is the
   "TaskStop bookkeeping" #517 deletes.
7. Append progress-file lines (grammar above).
8. Refill slot, re-list, loop; stop at ticket cap or two-parks-with-no-landing.

Manual frontier computation (step 2) and the named-background-builder
lifecycle (steps 4–6) are exactly what #517 says gets deleted in favor of
Orca's Task/dependency/ready-frontier machinery, mirroring
`implement-spec/SKILL.md`'s shape.

`implement-spec/SKILL.md` (68 lines) — the Orca-Run pattern to mirror: one Run
per spec, one Task per ticket plus an exploration task every ticket task
depends on, dependencies = blocking edges, workers via Orca `claude`/`sonnet`
(or `opus` if the ticket names it), frontier = "Orca's ready-task query."
Sections: Shape, The brief (file-ownership map), Waiting (known
`waiter_exists` retry quirk), Gates (`gate-create --task`), Landing (draft PR,
owner merges), end-of-spec review loop (P0/P1 exit criterion).

I did **not** find literal "three ways" text in the current
`implement-spec/SKILL.md` to confirm #517's "'three ways' miscount" fix
target — the doc as it stands has no enumerated "three ways" list. Either an
earlier version had it (check `git log -p implement-spec/SKILL.md` before
touching #517) or the miscount is elsewhere in the doc's prose that a close
read will surface; don't assume the line number without re-checking against
whatever #517's slice actually branches from.

Neither skill references `flow/` or `ccstatusline-table` directly except
through the progress-file grammar link above (§4) — #517 is blocked by #512
specifically because it inherits the "unchanged location, unchanged grammar"
contract #512 establishes as the single doc.

## 6. Skills with `disable-model-invocation: true`

Full grep (`grep -rl "disable-model-invocation" --include=SKILL.md .`), 56 skills:

```
add-molab-badge, all-audits, anywidget-generator, ask-matt, audit-instructions,
auto-paper-demo, burndown, claude-handoff, comment-audit, create-lmd-page,
dead-code, docstring-coverage, domain-drift, duplication, error-handling,
extract-coding-standards, find-skills, git-guardrails-claude-code, grill-me,
grill-with-docs, handoff, humanizer, implement-paper-auto, implement-paper,
implement-spec, improve-codebase-architecture, jupyter-to-marimo, loop-me,
marimo-batch, marimo-notebook, migrate-to-shoehorn, mutation-audit, pickup,
prompt-master, scaffold-exercises, setup-matt-pocock-skills,
setup-peacock-color, setup-pre-commit, setup-python-repo,
setup-ts-deep-modules, skill-audit, skills-safe-update, skills-sync,
streamlit-to-marimo, teach, test-audit, thermo-nuclear-code-quality-review,
to-questionnaire, triage, type-tightness, visual-plan, wasm-compatibility,
wizard, writing-beats, writing-fragments, writing-shape
```
`ww` and `sm-link` are **not** in this list — confirmed: neither
`ww/SKILL.md` nor `sm-link/SKILL.md` carries `disable-model-invocation`,
matching #511/#509's explicit decision that both stay model-invoked.
`ponytail-audit` is also **not** in this list (it has a multi-line YAML
`description: >` block with a trigger-phrase list instead) — that's the local
skill #509 wants denied via user-settings permission rule, not via
`disable-model-invocation`, since the goal is suppressing only the *plugin*
twin while keeping this one model-invocable.

#511's acceptance criterion ("every `disable-model-invocation` skill's
description becomes one human-facing line") applies to all ~54 names above —
spot check shows several already comply (`comment-audit`, `test-audit`,
`type-tightness`, `domain-drift` all end "... Slash-only." today, which is
exactly the suffix #511 says to cut) but most weren't inspected line-by-line
here; that's #511's own read-through work.

## 7. Gotchas for workers

- **Path convention bug is real and reproducible**: dead-code, docstring-coverage,
  duplication, error-handling all show `python3 <skill>/audit.py ...` (relative
  to cwd) in their SKILL.md "Run" step, while mutation-audit and test-audit
  already use `~/.agents/skills/<skill>/...`. Fixing #515 means literally
  changing that one line's path form in four files, matching the two that
  already work.
- **comment-audit has no fixtures/answer-key.md today.** #516's acceptance
  criteria assume one exists ("comment-audit fixture runs reproduce their
  answer keys") — this needs either building fixtures or re-scoping that
  line. Don't silently skip it; it's a real spec/repo mismatch.
- **Shared files across tickets**: `all-audits/SKILL.md` is the harness single
  owner (#510) that #515/#516 both point their five audits' "harness pointer"
  at — #510 should land first or in the same slice as anything that deletes a
  per-skill copy of the shared block (spec's own slicing note says this).
  `#517` is blocked by `#512` for the progress-file-grammar contract, not for
  any code dependency.
- **`ccstatusline-table` move (#512) touches two repos' worth of concerns**:
  the skill-tree copy here moves to `flow/`, but `flow/ccstatusline/settings.json`
  is a *live personal config* with its own hardcoded `/home/caneff/...`
  `commandPath` entries unrelated to this move — don't "fix" those as
  drive-by cleanup, they're out of scope and point at real per-machine paths
  (`~/src/research-queue`, `~/.claude/skills/sandcastle-watch`) that aren't
  part of this repo.
- **`.protected-skills`** (repo root) already lists `ponytail-audit` and
  `to-tickets` as manually protected from `skills-safe-update` overwrites —
  unrelated to `.extra-skills.json`'s upstream-tracking mechanism; don't merge
  the two concepts when writing #513's doc changes.
- **`.gitignore` traps**: `.claude/worktrees/`, `node_modules` (no trailing
  slash — also catches a worktree symlink), `__pycache__/`, `.scratch/`, and
  three Orca-managed skill-guide dirs (`computer-use/`, `orca-cli/`,
  `orchestration/`) are all ignored. `test-audit/` has a checked-in
  `package.json`/`package-lock.json` — if a worker runs `npm install` there
  for the vitest/node:test fixtures, `node_modules` won't accidentally get
  committed, but don't assume it's absent either; check before any fixture
  run that depends on it.
- **`all-audits/test_run_audits.sh` is fully offline** (`AUDITS_NO_SYNTH=1`,
  `AUDITS_NO_OPEN=1`, no real `claude` calls) — safe to run repeatedly while
  iterating on #510's scope-default changes without burning API calls or
  opening a browser tab.
- **prompt-master's `version:` frontmatter key is unique to it** — it's an
  upstream convention from `nidhinjs/prompt-master`, not a repo-wide pattern;
  don't propagate it to humanizer/read-the-damn-docs in #513 unless their own
  upstreams already use it (worth checking their source repos directly).
