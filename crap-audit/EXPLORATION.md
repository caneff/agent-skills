# crap-audit — family conventions map

Exploration notes for building `crap-audit` (per-function CRAP score audit)
shaped like the rest of the `all-audits` family. Read-only recon, no
implementation here.

## SKILL.md frontmatter shape (slash-only audit)

Every audit in the set uses this exact frontmatter — copy it verbatim, change
`name`/`description`/`argument-hint`:

```yaml
---
name: dead-code
description: Find code nobody calls — dead functions, classes, unreachable branches, stray imports — and sort real dead code from code that only looks unused. Slash-only.
disable-model-invocation: true
argument-hint: "[path]"
---
```

- `disable-model-invocation: true` is load-bearing: it blocks the `Skill` tool
  from launching the audit inside a live agent session. `all-audits`
  deliberately runs each audit as its own `claude -p "/name"` subprocess
  *because* of this gate (a user slash-invocation is allowed through; an
  agent's `Skill` tool call is not). `crap-audit` needs the same gate to fold
  into the sweep the same way.
- `description` ends with "Slash-only." as a spoken convention across the
  family, not just the gate.
- `argument-hint` is `"[path]"` for a whole-repo default, `"<target-module.py>"`
  for a single-target audit like `mutation-audit`. CRAP is naturally
  whole-repo (like dead-code/duplication), so `"[path]"`.

## Two-pass structure (dead-code is the closest prior art)

Every mechanical-tool-backed audit (dead-code, mutation-audit, duplication)
splits into exactly two passes:

1. **Pass one — `audit.py`, pure, mechanical, tested.** Runs the external
   tool (vulture / mutmut / jscpd), captures its stdout/JSON, and parses it
   into findings-schema rows via one pure function: `parse_vulture(text) ->
   list[dict]`, `parse_mutmut_results(text) -> list[dict]`,
   `parse_jscpd(json_str) -> list[dict]`. No subprocess call *inside* the
   parse function — the parser is fed already-captured text/JSON, which is
   what makes it fixture-testable offline. `main()` is a thin CLI wrapper:
   read stdin or a file argument, print one JSON row per finding. Pass one
   never assigns a real verdict — it defaults `bucket` to a placeholder
   (`"unsure"` for dead-code) or a construction-guaranteed initial bucket
   (`"consolidate"` for duplication, since a jscpd match is real duplication
   by construction). A `--selfcheck` (dead-code doesn't have this flag but
   duplication/mutation do — check pattern) or a `_selfcheck()` function run
   under `if __name__ == "__main__"` guard doubles as the ponytail-mandated
   "one runnable check."
2. **Pass two — the LLM judgment pass, described in prose in SKILL.md, not
   code.** Reads each pass-one row in context (the flagged symbol's
   definition, decorators, callers) and reassigns `bucket` + rewrites
   `summary`/`failure` to say *why*, quoting the concrete evidence read from
   the file — never a templated one-liner repeated across every row of a
   category. This is where dead-code tells `dead` from `dynamic`, duplication
   downgrades a boilerplate clone to `keep`, mutation-audit decides
   `rewrite` vs `no-coverage` vs `cut`.

For `crap-audit`: pass one is almost certainly "run radon `cc -j` +
`coverage json`, join on `(file, lineno==start_line)`, compute
`CRAP = CC² × (1 − coverage)³ + CC`" — see the research summary below, this
computation is itself mechanical/deterministic, so it may collapse to a
single pure function rather than "parse tool output, pass 2 judges." The
judgment analog for CRAP is likely: is a high-CRAP function a real risk, or
noise (trivial getter with an unreachable error branch, generated code,
etc.) — worth deciding during spec/design, not assumed here.

## Buckets & categories — the shared row vocabulary

Every audit defines its own **closed bucket set** (2–3 values) and its own
**category vocabulary** (a small closed slug set), both named in SKILL.md's
"Buckets & categories" section:

| audit | buckets | category source |
|---|---|---|
| dead-code | `dead` / `dynamic` / `unsure` | vulture kind, slugged: `unused-function`, `unused-import`, `unused-class`, `unused-method`, `unused-variable`, `unused-attribute`, `unused-property` |
| duplication | `consolidate` / `keep` / `unsure` | `token-clone` (pass 1) or `semantic-duplicate` (pass-2-only sweep) |
| mutation-audit | `rewrite` / `no-coverage` / `cut` (no `keep` — killed mutants are dropped, not reported) | always `surviving-mutant` |

Default-to-caution is a repeated rule: dead-code says "false 'dead' costs
more than a false 'unsure'"; duplication has an explicit `unsure` for
"genuinely ambiguous." `crap-audit` should pick its own bucket set up front
(likely something like `hotspot` / `acceptable` / `unsure`, or just a
severity tier off the raw score — a design decision, not copied verbatim from
any one sibling).

## `findings.jsonl` — the exact shared row schema

Defined once in `all-audits/harness/findings-schema.md`, referenced (not
restated) by every audit's own SKILL.md. One JSON object per line, scan
order:

```jsonl
{"bucket":"cut","file":"layers/group_sum_test.py","line":111,"category":"duplicate-coverage","summary":"count=3 example subsumed by the arity hypothesis test","failure":"cannot fail for any reason line 261 doesn't already catch faster","owner":"layers/group_sum_test.py:261"}
```

Fields:

- `bucket` (required) — the skill's own closed verdict-bucket vocabulary.
- `file` (required) — repo-relative path.
- `line` (required) — integer line number.
- `category` (required) — the skill's own closed smell/kind slug vocabulary;
  this is the axis the HTML summary groups on.
- `summary` (required) — one line, what the finding is.
- `failure` (required for anything but a plain `keep`) — the **concrete**
  consequence: what breaks/goes unnoticed if this stands as-is. Never a bare
  label.
- `before` / `after` (optional) — concrete before/after text (a weak
  assertion and its fix, a comment and its replacement). Omit for a plain
  keep.
- `owner` (optional) — `file:line` of whatever already owns this behavior
  (used by duplicate-coverage cuts).
- `extra` (optional) — flat object, audit-specific signal beyond the six
  fixed fields. Real examples: dead-code → `{"confidence": 60}` (vulture's
  raw %); type-tightness → `{"suggested_type": "Sequence[int]",
  "severity": "blanket"}`; domain-drift → `{"should_be": "Order", "source":
  "CONTEXT.md"}`; duplication → `{"clone_tokens": 42}`; mutation-audit →
  `{"mutant": "flip <", "killed": false, "survived": true}` plus a run-level
  tally `{"killed_count": N, "survived_count": M, "no_coverage_count": K}`
  riding on the first row (`all-audits/run-audits.sh`'s `mutation_tally`
  reads this off the first row carrying it — a convention worth reusing if
  `crap-audit` wants a run-level rollup surfaced in the index).

For `crap-audit`, `extra` is the natural home for `{"complexity": CC,
"coverage": 0.42, "crap": 18.6}` — the raw numbers behind the bucket.

## Report shape: `findings.jsonl` + grouped `report.html`, no per-finding cards

`all-audits/harness/findings-schema.md` is explicit: for an audit that finds
*many* things, don't render a card per finding — write the JSONL log (the
grill reads this) and a grouped-summary HTML (a human eyeballs this):

- **Header** — `vt-kicker` skill label, `<h1>` repo, `vt-lede` one-line
  verdict, `vt-metabar` with the count: `"N judged · C cut · R rewrite · K
  kept"` (adapt to the audit's own bucket names).
- **Grouped overview** — per-bucket, per-category counts with a one-line
  gloss; a per-file roll-up when the audit is large. Tables/lists, not cards.
- **Standouts** — a short `vt-callout` naming a *handful* of highest-value
  finds by `file:line`, not every row.
- **Full record** — one line pointing at `findings.jsonl` beside the page.

This is the shape dead-code, duplication, mutation-audit, test-audit, and
comment-audit all use. The other three set-members
(`ponytail-audit`, `thermo-nuclear-code-quality-review`,
`improve-codebase-architecture`) instead render full per-finding HTML cards —
their own `HTML-REPORT.md` files hold that pattern; not relevant to
`crap-audit`, which is a many-findings audit like dead-code.

Given CRAP naturally produces one row per function across a repo (i.e. a
"many findings" audit, same shape as dead-code/duplication/mutation), the
grouped-summary + JSONL shape is the right target, not per-finding cards.

## Asset delivery — `all-audits/harness/HTML-REPORT.md`

Shared mechanism every HTML-rendering audit uses, do not deviate:

- Report is a single self-contained HTML file written to
  `<tmpdir>/<skill>-<timestamp>/report.html`, `<tmpdir>` = `$TMPDIR` else
  `/tmp`.
- Copy `visual-teach`'s `assets/` (resolved once from
  `~/.agents/skills/visual-teach/assets/`) **next to** the report at render
  time and link relatively — never inline, never remote. Always copy
  `base/base.css` + `base/base.js` (the spine: shell, prose, dark-mode
  tokens, theme toggle). Copy only the `components/<name>/<name>.css` a
  report actually uses (`callout`, `chip`, `code`, `diagram` are the
  reusable set; `code.js` too if code is highlighted). Prism grammars only
  if code is highlighted; mermaid only if a diagram is used.
- `<!doctype html>` must be line 1. Never add `type="module"` to
  `base.js`/`code.js`/the mermaid tag — `file://` blocks CORS and it breaks
  silently.
- **Print the marker line on its own line after writing the report**:
  `ALL_AUDITS_REPORT=/abs/path/to/report.html` — `run-audits.sh`'s
  `report_path_from_log` greps stdout for exactly this (falls back to a bare
  `*.html` path grep for older audits, but the marker is the real contract).
  This is how the fan-out collects each audit's report — get this wrong and
  the sweep silently drops `crap-audit` from the index.
- Then open the report (`xdg-open`/`open`/`start`) and print its absolute
  path — **except** inside an `all-audits` sweep, where `run-audits.sh`'s
  `audit_prompt()` explicitly tells the subprocess "Do NOT open the report" —
  the sweep opens only the final index.

## The fan-out return struct (`findings-schema.md`, "The fan-out return
struct")

What every audit subagent conceptually returns, regardless of which audit
ran (this is prose describing the contract `run-audits.sh` mechanically
reconstructs by scanning stdout logs, not a literal function return value):

- `audit` — the skill name.
- `headline` — the one-line verdict from the report.
- `count` — how many findings.
- `report_path` — absolute path to `report.html` (the grouped summary for
  many-findings audits like this one).
- `log_path` — absolute path to `findings.jsonl`, omitted for audits that
  render full per-finding HTML cards instead.
- `findings` — a short list, `{ target, note }` per finding, `target` =
  repo-relative file, `note` = one-line summary.

## `run-audits.sh` — how a new audit joins the sweep

- Add the skill name to the `AUDITS=(...)` array (`all-audits/run-audits.sh`,
  ~line 335) to fold into the default twelve-audit sweep. Currently 12
  entries; `mutation-audit` is deliberately excluded (opt-in, single-module,
  invoked by name — same posture `crap-audit` should probably *not* take,
  since CRAP is naturally a whole-repo sweep like dead-code).
- If `crap-audit` turns out to be expensive/LLM-heavy like `domain-drift`/
  `type-tightness`, it can opt into the staleness cache by adding an entry to
  `GATED_GROUND_TRUTH` (empty string if no doc-based ground truth to
  invalidate on, like `type-tightness`). Given CRAP's pass-one is a
  deterministic tool run (radon+coverage.py), it's more likely *not*
  LLM-expensive and doesn't need gating — a design call, not settled here.
- `audit_prompt()` (top of `run-audits.sh`) is the prompt every fanned-out
  audit gets: forces whole-repo scope (overriding any diff-only default),
  excludes vendor/build/`.git`/`worktrees` trees, and tells the subprocess
  not to open its own report. `crap-audit`'s own "Scope tight" step in
  SKILL.md should list the same exclusion set dead-code/duplication both
  spell out verbatim: `node_modules, .venv, dist, vendor, build output,
  lockfiles, .git/, worktrees/`.
- `collect_module_report`/`report_path_from_log` is how a fresh run's report
  folder gets pulled into `COLLECTION/<name>/` and (for gated audits)
  persisted to the stable per-repo cache — automatic once the marker line
  prints correctly, no code change needed elsewhere.
- The index build (`index.html`) auto-discovers `crap-audit`'s report the
  same way as every other audit — no special-casing needed, as long as it's
  in the `AUDITS` array and prints the marker.

## Test conventions across the family

- Every `audit.py` pass-one parser ships with `fixtures/` (a real captured
  tool-output file + a hand-authored fixture source file) and
  `fixtures/answer-key.md` (a markdown table: raw captured tool output, then
  a `# | Symbol | Line | Kind | Bucket | Reason` table giving the *expected
  judged verdict* for every row — this is the answer key for the LLM
  judgment pass, not just the parser). Running the skill fresh over
  `fixtures/` should reproduce that exact table — this is the acceptance
  test for the whole two-pass skill, not just pass one.
- `audit.py` itself carries a `_selfcheck()` (dead-code, duplication) run via
  `--selfcheck` or invoked directly under `__main__` — asserts the parse
  function's shape/field values against a small inline sample, no fixture
  files needed, no test framework. This is the ponytail-mandated "one
  runnable check" for pass one's non-trivial parsing logic.
- `all-audits/test_run_audits.sh` is a hermetic bash test of the
  orchestrator's own seams (`--index` rebuild, `report_path_from_log`
  marker-vs-legacy extraction) — `source`s the script to reach its functions
  directly, no `claude` subprocess invoked (`AUDITS_NO_SYNTH=1`). Not
  something `crap-audit` itself needs to write, but the shape to imitate if
  `crap-audit` ships its own bash/python helper worth testing offline.
- No pytest / unittest framework anywhere in this family — every test is
  either a fixture-diffing prose contract (`answer-key.md`) or a
  hand-rolled `assert`-based self-check / bash script. Matches ponytail's
  "no frameworks" test default.

## Research: worked CRAP tooling pipelines (Python + TypeScript)

Full docs on local research branches — not merged, read via `git show`:

- **Python**: `research/crap-python-tooling` (commit `a95d390`),
  `docs/research/crap-python-tooling.md`.
- **TypeScript**: `research/crap-ts-tooling` (commit `2bb412b`),
  `docs/research/crap-ts-tooling.md`.

### Python — bottom line

**Don't build from scratch: `crap4py`** (PyPI, MIT, June 2026) is a direct
port of Uncle Bob's `crap4go`/`crap4clj` and already implements
`CC² × (1−coverage)³ + CC`. Its one gap vs. the ticket's exact formula:
`crap4py` uses **branch coverage only** (via LCOV), not
`min(statement, branch)`.

Fallback/from-scratch pipeline if the gap matters:

- `radon cc -j` gives per-function/method/class cyclomatic complexity.
  `lineno` = the `def`/`async def` line. **Methods are double-reported**
  (once nested under the class's `"methods"`, once flattened at top level
  with `classname` set) — read only the flattened entries. **Gap: nested
  (non-method) functions are NOT flattened** — they only appear in the
  parent's `"closures"` list; must recurse into `closures` or nested
  functions are silently dropped.
- `coverage json` (coverage.py **≥ 7.13.1**, current PyPI 7.16.0) natively
  ships a per-file `"functions"` key with per-function `percent_covered`
  (statement) **and** `percent_branches_covered` (branch) already computed —
  no LCOV step, no hand-rolled line→function attribution needed. Function
  keys are dotted qualified names (`"Foo.method"`), and `start_line` matches
  radon's `lineno` exactly — this is the join key between the two tools.
  Nested functions get their own correctly-excluded region. Requires
  `coverage run --branch` (or `[run] branch = True`).
- Formula: `min(percent_covered, percent_branches_covered)` per function,
  joined to radon's CC by `(file, lineno == start_line)`.

### TypeScript — bottom line

No clean single off-the-shelf tool; three-part pipeline plus one real
existing package worth evaluating first:

- **Complexity**: ESLint's `complexity` rule set to `max: 0` forces a report
  for every function; the report `message` string embeds the real computed
  number (`"{{name}} has a complexity of {{complexity}}..."`) — parse it out
  of `--format json` output. Zero new dependency if ESLint's already in the
  repo. Alternative with a first-class numeric field:
  `cyclomatic-complexity` (npm, actively maintained, native `--json`
  `functionComplexities` array). `typhonjs-escomplex` is dead (2018) —
  avoid.
- **Coverage**: Istanbul-shaped `coverage-final.json` — `fnMap`/`f` (per
  function, hit count), `branchMap`/`b` (per branch outcome),
  `statementMap`/`s` (per statement) — **no documented join field between
  statements and functions**; per-function statement coverage requires a
  hand-rolled spatial join (a statement's `Location` falls inside a
  function's `loc` range). Vitest needs `provider: 'istanbul'` explicitly
  (default is `v8`, unverified schema-equivalent); Jest's default `babel`
  provider already produces this shape.
- **Existing tool worth evaluating first**: `@barney-media/crap-typescript-core`
  (npm, Apache-2.0, actively maintained, last push same day as the research)
  implements the exact ticket formula, reads `coverage-final.json` directly,
  ships a CLI with Vitest/Jest auto-detection and a `--changed`-only mode.
  Its internal complexity engine is undocumented in the README — verify
  against a known-complexity fixture before trusting it matches classic
  McCabe CC.

Both docs end with an explicit numbered "known gaps" list (arrow-function
`fnMap` attribution unverified from a primary source, TS source-map
coordinate space asserted not proven, v8/istanbul provider schema
equivalence unproven) — worth re-reading in full before `crap-audit`'s
TypeScript pass-one is implemented, since these are exactly the edge cases a
parser needs to handle or explicitly punt on.

## Open design questions for the spec (not answered here)

- Bucket vocabulary: CRAP has no natural 3-way verdict the way
  dead/dynamic/unsure or consolidate/keep/unsure do — likely a severity tier
  off the raw score (repo-relative or absolute threshold), a decision for
  `/to-spec`, not this doc.
- Whether `crap-audit` is a whole-repo sweep member (`all-audits` `AUDITS[]`)
  or opt-in/targeted like `mutation-audit` — CRAP's naturally cheap
  deterministic pass-one argues for sweep membership; whether a Python-only
  vs. Python+TS pipeline ships first is also open.
- Whether pass two (LLM judgment) does real work here the way it does for
  dead-code (dead vs. dynamic) — or whether CRAP's pass-one output is
  already the verdict and pass two only needs to write the summary/why
  text for the highest-scoring functions.
