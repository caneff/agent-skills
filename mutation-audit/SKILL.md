---
name: mutation-audit
description: Point at ONE module to learn which of its tests pass without actually catching a bug — run mutmut, scrape the survivors, emit test-audit findings. Opt-in, never in the default sweep.
disable-model-invocation: true
argument-hint: "<target-module.py>"
---

Run mutmut against one target module and report which mutants survive. A
surviving mutant means one of two things: a test runs that line but doesn't
assert hard enough to notice the behavior changed (`rewrite`), or no test
reaches that line at all (`no-coverage`). mutmut runs every mutant against
the whole suite whether or not a test covers the mutated line, so a survivor
is never proof of coverage. This is expensive (it
reruns the test suite once per mutant) and only meaningful pointed at a
single module you're actually worried about, so it is **never** part of
`all-audits`' default sweep — it runs only when asked for by name, and it
never mutates a whole repo.

**Two passes**, mirroring `dead-code`. `audit.py` in this skill's directory
is pass one — mechanical: run mutmut, parse `mutmut results`' stable text
format into candidate rows. It reads the bucket straight off mutmut's status
— `survived` -> `rewrite`, `no tests` -> `no-coverage` — but never upgrades a
`rewrite` to `cut`, and never knows the real source line (`mutmut show
<mutant>` diffs the isolated mutant, not the real file, so the line comes
from reading the target module). Pass two below does that reading and
finalizes each row.

## Buckets

A survivor **with** a covering test gets a `test-audit` verdict — `rewrite`
or `cut` — ingestible by a later `test-audit` grill (see `test-audit/SKILL.md`
for the full definitions). A survivor with **no** covering test is
`no-coverage` — mutation-audit's own bucket, because there is no existing
test for `test-audit` to judge; the fix is to write one.

- **`rewrite`** — the default for a covered survivor. A test runs the
  mutated line but doesn't assert hard enough to catch the mutation. Give a
  concrete `before`/`after`: the test as it stands, and the added/changed
  assertion that would kill it.
- **`no-coverage`** — no test reaches the mutated line or branch at all: the
  survivor is a coverage hole, not a weak assertion. There is no covering
  test to edit, so it carries no `before`/`after`. Instead name the test to
  write and the concrete behavior it must exercise and assert. This is the
  sharper finding — a genuine gap, not a test that under-asserts.
- **`cut`** — only when the covering test is independently a Cut by
  `test-audit`'s own smells (assertion-free, tautological, mystery guest) —
  i.e. the fix isn't "assert harder," it's "this test proves nothing,
  remove it." Still name what a replacement test would need to assert; a
  Cut here is not "no test needed."

`category` is always `surviving-mutant`. `extra` carries
`{"mutant": "<module>.x_<func>__mutmut_<N>", "killed": false, "survived": true,
"killed_count": N, "survived_count": M}` — the mutant id plus the run's
overall tally, so a later grill can see how thoroughly the module was
covered without re-running mutmut.

## Run

1. **Resolve the target.** `$ARGUMENTS` is the target module. If it's
   given, skip to step 2.

   **No target — suggest, don't sweep.** Walk the current directory
   (`os.walk`, skipping `.git`, `node_modules`, `dist`, `build`, `.venv`,
   `venv`, `vendor`, `worktrees`, `mutants`, and any dotdir) collecting
   `.py` paths, then:
   ```sh
   python3 ~/.agents/skills/mutation-audit/audit.py --suggest <scope>
   ```
   This calls `suggest_candidates` — the tested pure seam: a module is a
   candidate when it's a plain module (not `__init__.py`, not a test file,
   not under a `fixtures/` dir) **and** a sibling test file exists for it
   (`test_<name>.py` or `<stem>_test.py`) — mutmut needs a test suite to
   mutate against, so an untested module isn't a useful target. Print the
   suggestions and **stop** — ask which one to run. Never fall back to
   running mutmut over the whole repo; an empty suggestion list is a valid
   answer ("nothing here has a sibling test to mutate against"), not an
   error.

2. **Confirm the target is mutation-testable.** It must be a real `.py`
   file with a sibling test file (same rule as the suggester). If it has
   no tests, mutmut has nothing to run against — say so and stop.

3. **Scope mutmut to just the target.** mutmut 3.x reads `[tool.mutmut]`
   (pyproject.toml) or `[mutmut]` (setup.cfg) for `source_paths` — there is
   no CLI flag for it. Check for an existing section first:
   - Already scoped to the target (or a directory containing only it) →
     leave it alone.
   - Otherwise, write a temporary `setup.cfg` with
     `[mutmut]\nsource_paths=<target>` (or add a `[tool.mutmut]` table to
     `pyproject.toml` if one doesn't already exist) scoped to the single
     target module — never the whole repo. This is a transient audit
     artifact: remove what you added (and mutmut's own `mutants/` and
     `.mutmut-cache`) once the run finishes.

**Speed knobs.** `source_paths` (step 3, above) is the one big zero-risk
speed knob and it's already applied — mutate only the target module, never
the whole repo. Two other mutmut config keys sound like speed knobs but trade
away accuracy, so neither is set by default here:

- **`mutate_only_covered_lines`** (default `false`) skips lines
  `coverage.py` says no test reaches. Leave it **off**. Turning it on drops
  the `no-coverage` bucket entirely — there's nothing left to mislabel a
  no-coverage line as, mutmut just never mutates it. If a future fast,
  coverage-only mode gets offered, it must be explicit opt-in and say up
  front that it drops the no-coverage findings.
- **`max_stack_depth`** (default none) trims how deep mutmut looks for a
  killing test, which is faster but accuracy-risky: a mutant killed only by
  a test several stack frames down can get mislabeled `no-coverage` or
  `rewrite` — a false finding. It's an opt-in knob the user reaches for by
  name, never a default here.

Incremental caching (git change detection) is on by default — there's no
config key for it. When `all-audits` runs this per module, each module gets
its own disposable git worktree, so every run starts with a cold
`.mutmut-cache` — caching stays active but its cross-run benefit is limited
in that setup.

4. **Run mutmut, capture results.**
   ```sh
   uvx --with pytest mutmut run          # add --with <pkg> for the target's own test deps
   uvx mutmut results --all true > "${TMPDIR:-/tmp}/mutmut-results.txt"
   python3 ~/.agents/skills/mutation-audit/audit.py "${TMPDIR:-/tmp}/mutmut-results.txt"
   ```
   `parse_mutmut_results(text) -> list[dict]` is the tested seam
   (`fixtures/mutmut-results.txt` + `fixtures/answer-key.md` back it,
   mirroring `~/.agents/skills/dead-code/fixtures/`) — pure, no subprocess inside it, fed
   mutmut's captured text. It returns one row per mutant that isn't killed —
   a `survived` mutant as a `rewrite`, a `no tests` mutant as a `no-coverage`;
   killed mutants are counted into `killed_count` and dropped, they aren't
   findings. `main()` wraps it: reads a file argument or stdin, prints one
   JSON row per finding. `file` is a best-effort guess from the dotted module
   name and `line` is `null` — step 5 overwrites both.

5. **Pass two — read each row, finalize it.** Pass one already set `bucket`
   from mutmut's status; this pass fills the detail. For every row: run `uvx
   mutmut show <mutant>` to see the diff (the specific operator/literal flip),
   then read the target module to find the real line the diff's `-` side
   matches. Fill `line` with the real number and rewrite `failure` to name
   the concrete mutation — never the placeholder pass one wrote. Then:
   - **`no-coverage`** — read the test file to confirm no test reaches the
     line. Leave `before`/`after` empty; name the test to write and what it
     must assert. "the `kind=='invalid'` branch at line 42 has no test — add
     one that renders an invalid `LinkView` and asserts the error row."
   - **`rewrite`** — read the covering test to see what it asserts. Set
     `before`/`after` to the test as it stands and the assertion that would
     kill the mutant. Upgrade to **`cut`** only when that test is
     independently a Cut by `test-audit`'s own smells (see Buckets above).

6. **Write the findings log and render the summary — the default
   deliverable.** Write every finalized row to `findings.jsonl`, then draw
   a grouped summary `report.html` from it, following
   `~/.agents/skills/all-audits/harness/findings-schema.md` for both — the
   JSONL schema and the summary's grouped-overview shape.
   Write both to `<tmpdir>/mutation-audit-<timestamp>/` and deliver the summary
   per `~/.agents/skills/all-audits/harness/HTML-REPORT.md` — tmpdir resolution,
   opening, and handing off the path all live there. This audit touches no test —
   rewriting a weak assertion is a separate, opt-in step the user asks for by name.

   - **Log** — one JSONL line per surviving mutant. `bucket` is `rewrite`,
     `no-coverage`, or `cut`. `category` is always `surviving-mutant`.
     `extra.mutant`/`killed`/`survived` plus the run tally
     `killed_count`/`survived_count`/`no_coverage_count` carry the
     mutation-testing signal.
   - **Summary** — the verdict, an `N mutants · K killed · S survived ·
     R rewrite · NC no-coverage · C cut` metabar, findings grouped by bucket
     with counts. No
     per-mutant cards. Call out in a `vt-callout` the module's overall kill
     rate (`killed_count / (killed_count + survived_count +
     no_coverage_count)`) — the single number that says how trustworthy this
     module's suite is. Uncovered mutants belong in the denominator: a
     coverage hole is a caught-nothing line, not a free pass.

7. **Verify the cleanup.** Confirm every transient artifact from step 3 is
   actually gone: the `mutants/` directory, `.mutmut-cache`, and — if you
   added one — the `[mutmut]`/`[tool.mutmut]` config section (leave it alone
   if it pre-existed). Check with `test -e mutants` / `test -e .mutmut-cache`
   and `git status --porcelain` or `git diff` on `setup.cfg`/`pyproject.toml`,
   not by assuming the removal worked — a failed cleanup leaves
   mutation-testing state for the next run to trip over.

## Verify against the fixture

`~/.agents/skills/mutation-audit/fixtures/sample.py` + `test_sample.py` is a real mutmut run
(not a hand-built guess), covering all three buckets: `is_adult` is tested at
and around its boundary (both mutants die), `clamp` is only tested in-range
(both boundary mutants `survived` → `rewrite`), and `scale` has no test at
all (its mutant is `no tests` → `no-coverage`). `fixtures/mutmut-results.txt`
has the captured `mutmut results --all true` output; `fixtures/answer-key.md`
has the expected pass-one candidate rows and the pass-two finalized findings.
Running this skill over `fixtures/sample.py` should reproduce that table.
