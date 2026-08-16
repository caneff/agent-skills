---
name: mutation-audit
description: Point at ONE module to learn which of its tests pass without actually catching a bug — run mutmut, scrape the survivors, emit test-audit findings. Opt-in, never in the default sweep. Slash-only.
disable-model-invocation: true
argument-hint: "<target-module.py>"
---

Run mutmut against one target module and report which mutants survive — a
surviving mutant is proof that some test exercises that code but doesn't
assert hard enough to notice the behavior changed. This is expensive (it
reruns the test suite once per mutant) and only meaningful pointed at a
single module you're actually worried about, so it is **never** part of
`all-audits`' default sweep — it runs only when asked for by name, and it
never mutates a whole repo.

**Two passes**, mirroring `dead-code`. `audit.py` in this skill's directory
is pass one — mechanical: run mutmut, parse `mutmut results`' stable text
format into candidate rows. It never decides `rewrite` vs `cut` beyond the
default, and it never knows the real source line — `mutmut show <mutant>`
diffs the isolated mutant, not the real file, so the line comes from reading
the target module. Pass two below does that reading and finalizes each row.

## Buckets — test-audit vocabulary

Findings use `test-audit`'s buckets so they're ingestible by a later
`test-audit` grill (see `test-audit/SKILL.md` for the full definitions):

- **`rewrite`** — the default. A test already exercises the mutated code
  path (that's *why* mutmut could run a mutant there at all) but doesn't
  assert hard enough to catch the mutation. Give a concrete `before`/`after`:
  the test as it stands, and the added/changed assertion that would kill it.
- **`cut`** — only when the covering test is independently a Cut by
  `test-audit`'s own smells (assertion-free, tautological, mystery guest) —
  i.e. the fix isn't "assert harder," it's "this test proves nothing,
  remove it." Still name what a replacement test would need to assert; a
  Cut here is not "no test needed."
- **`keep`** — not used by this audit. A killed mutant means the covering
  test already earns its place; killed mutants are dropped before findings
  are written, not reported as keeps (see below).

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
   python3 mutation-audit/audit.py --suggest <scope>
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

4. **Run mutmut, capture results.**
   ```sh
   uvx --with pytest mutmut run          # add --with <pkg> for the target's own test deps
   uvx mutmut results --all true > /tmp/mutmut-results.txt
   python3 mutation-audit/audit.py /tmp/mutmut-results.txt
   ```
   `parse_mutmut_results(text) -> list[dict]` is the tested seam
   (`fixtures/mutmut-results.txt` + `fixtures/answer-key.md` back it,
   mirroring `dead-code/fixtures/`) — pure, no subprocess inside it, fed
   mutmut's captured text. It returns one candidate row per **surviving**
   mutant only; killed mutants are counted into `killed_count` and dropped
   — they aren't findings. `main()` wraps it: reads a file argument or
   stdin, prints one JSON row per survivor. `file` is a best-effort guess
   from the dotted module name and `line` is `null` — step 5 overwrites
   both.

5. **Pass two — read each survivor, finalize the row.** For every candidate
   row: run `uvx mutmut show <mutant>` to see the diff (the specific
   operator/literal flip), then read the target module to find the real
   line the diff's `-` side matches and the test file to see what it
   actually asserts. Rewrite `failure` to name the concrete mutation —
   "the `<` → `<=` mutation at line 14 survives — no test fails when
   `value` sits exactly at `low`" — never the placeholder pass one wrote.
   Fill `line` with the real number, set `before`/`after` to the covering
   test as it stands and the assertion that would kill the mutant. Confirm
   `bucket`: `rewrite` unless the covering test is independently a Cut by
   `test-audit`'s own smells (see Buckets above).

6. **Write the findings log and render the summary — the default
   deliverable.** Write every finalized row to `findings.jsonl`, then draw
   a grouped summary `report.html` from it, following
   `~/.agents/skills/all-audits/harness/findings-schema.md` for both — the
   JSONL schema and the summary's grouped-overview shape. Write both to
   `<tmpdir>/mutation-audit-<timestamp>/`, then open the summary and hand
   off its path as `~/.agents/skills/all-audits/harness/HTML-REPORT.md`'s
   asset-delivery section describes. This audit touches no test — rewriting
   a weak assertion is a separate, opt-in step the user asks for by name.

   - **Log** — one JSONL line per surviving mutant. `bucket` is `rewrite`
     (almost always) or `cut`. `category` is always `surviving-mutant`.
     `extra.mutant`/`killed`/`survived`/`killed_count`/`survived_count`
     carry the mutation-testing signal.
   - **Summary** — the verdict, an `N mutants · K killed · S survived ·
     R rewrite · C cut` metabar, findings grouped by bucket with counts. No
     per-mutant cards. Call out in a `vt-callout` the module's overall kill
     rate (`killed_count / (killed_count + survived_count)`) — the single
     number that says how trustworthy this module's suite is.

## Verify against the fixture

`mutation-audit/fixtures/sample.py` + `test_sample.py` is a real mutmut run
(not a hand-built guess): `is_adult` is tested at and around its boundary
(both mutants die), `clamp` is only tested in-range (both boundary mutants
survive). `fixtures/mutmut-results.txt` has the captured `mutmut results
--all true` output; `fixtures/answer-key.md` has the expected pass-one
candidate rows and the pass-two finalized findings. Running this skill over
`fixtures/sample.py` should reproduce that table.
