---
name: test-audit
description: Ruthlessly audit a repo's tests — cut the ones that prove nothing, rewrite the ones checking the wrong thing, keep only what earns its place. Slash-only.
disable-model-invocation: true
argument-hint: "[path]"
---

Sweep the tests in scope and sort each one into Cut, Rewrite, or Keep. A suite
full of tests that can't fail, or that fail for reasons no user cares about,
trains the reader to distrust the suite — when half the tests go red for
nothing, a real failure gets waved through. Ruthless sorting is what buys the
survivors their authority.

The default deliverable is a **report**, not applied edits. The sweep writes a
machine-readable findings log and a grouped HTML summary; it touches no test.
Applying the changes is a separate, opt-in step the user asks for by name.

This is the judgment pass: the smells only reading can find. `audit.py` and
`audit.mjs` in this skill's directory are pass one — a mechanical scan for
the syntactically detectable smells (assertion-free tests, tautologies,
mock-the-world, interaction-only assertions, empty/skipped tests). `audit.py`
covers pytest; `audit.mjs` covers vitest and node:test. Run both first; their
combined candidate list feeds the judgment sweep below instead of starting
from a blank page.

**JS/TS reach.** `audit.mjs` recognizes vitest (`describe`/`it`/`test` +
`expect`) and node:test (`node:test` import + `assert.*`) — nothing else. A
file it can't identify as one of those two is skipped, never flagged, so a
homegrown or non-standard harness doesn't flood pass one with false
assertion-free findings. Playwright `.spec` files are out of scope — they're
e2e/visual specs, not unit tests, and auditing them by this yardstick would
misjudge them. jest, mocha, ava, and chai are likewise out of scope. A
missing `@babel/parser` prints a `run npm ci` message and exits — bootstrap
with `npm ci` in `test-audit/` once.

**Name collision.** This is `test-audit` — test-*file* quality. It is not
`ponytail-audit` (production-code over-engineering) or `skill-audit`
(skill-*file* quality).

## The one test

**A good test fails for exactly one real reason — a behavior a human would
be upset to see break. A crap test either cannot fail when the behavior
breaks, or fails when nothing a user cares about changed.**

Three buckets, not two — a deleted test can lose the only guard on a real
behavior, so the burden of proof splits differently than a deleted comment:

- **Cut** — proves nothing. Deleting it loses no coverage.
- **Rewrite** — the behavior is real, but the test checks the wrong thing.
  Replace it, don't delete it.
- **Keep** — earns its place.

Default when unsure is **Rewrite, not Cut.** A comment you wrongly cut just
needs re-adding; a test you wrongly cut can open a silent coverage gap that
nobody notices until the behavior it was guarding actually breaks. Only cut
when you're sure the test proves nothing at all.

**The only-test warning.** Before you cut, check whether anything else in
scope touches the same code path. If the test you're about to cut is the
*only* one that exercises that path, it is not a Cut — it's a Rewrite. The
smell that makes it a Cut candidate (mismatch, sensitive equality, whatever)
still needs fixing; it just can't be fixed by deletion.

This warning doesn't rescue a test that structurally cannot fail — a
conditional-logic test with an escape-valve assertion in every branch, or an
assertion-free test, proves nothing under any circumstance. There is no real
coverage there to lose, only-test or not, so it stays a Cut. The warning is
for tests that *can* fail, just for the wrong reason or on the wrong
grounds — a real signal aimed badly, which is worth salvaging.

## Load-bearing — never touch

Some files aren't tests, they're scaffolding the tests run on. Leave these
exactly as they are:

- `conftest.py` and other shared fixture/setup files.
- Markers, parametrize tables, and test-config (`pytest.ini`, `tox.ini`,
  `jest.config.*`) — unless a specific marker or parametrize case is itself
  the thing under judgment.
- CI wiring that invokes the suite (workflow YAML, Makefile test targets).

If cutting or rewriting a test would mean touching one of these to keep the
suite green, stop and flag it instead of editing scaffolding to make a
judgment call fit.

## Cut — judgment-pass smells

Each of these needs a human eye on the code beside the test; none is
reliably greppable. For every one, name the *concrete* failure — never a bare
label. "Cannot fail when X breaks" or "fails when Y is refactored though
nothing broke," not "this is a mystery guest."

- **Duplicate coverage across layers.** The same behavior asserted at a unit
  test and again at an integration or e2e test, where the higher layer adds
  nothing the lower layer doesn't already prove faster. Keep the lowest
  layer that owns the behavior; cut the redundant restatement — but only
  when some *other* test in scope already covers the wiring this layer
  uniquely owns. If the duplicate assertion is the only thing proving that
  wiring anywhere in scope, it's the only-test case above — rewrite it down
  to what it actually owns instead.
- **Mystery guest / resource optimism.** The test depends on state it
  doesn't build or show — an ambient fixture, a database row left by another
  test, a file assumed to exist, a service assumed to be up. It fails when
  run order or environment changes, not when the behavior breaks; and it
  can't reliably fail when the behavior *does* break, because the shared
  state may mask it.
- **Eager test.** One test body drives several unrelated behaviors and
  asserts on all of them. A failure tells you "something in here broke," not
  which behavior — collapsing several real reasons to fail into one.
- **Sensitive equality.** Asserting a full object, dict, or blob equal
  because equality was easy to write, when only one or two fields are the
  actual behavior under test. Fails whenever an unrelated field changes
  (an id, a timestamp, a field nobody asked this test to guard).
- **Name/behavior mismatch.** The test's name promises one behavior; its
  body checks something else. Readers trust the name over the assertions —
  so this doesn't just fail to prove the named behavior, it actively hides
  that nothing proves it.
- **Library-default test.** The assertion only proves a language or library
  default works (a dataclass default argument, an ORM's auto-increment id,
  a framework's built-in validation). Nothing this codebase wrote can break
  it.
- **Conditional test logic.** An `if`/`else` or `try`/`except` inside the
  test body that changes what gets asserted depending on a runtime
  condition. Whichever branch runs, the test finds a way to pass — it can't
  fail no matter which branch the real behavior takes.
- **Flakiness-by-construction.** Real `sleep`, unseeded randomness, or
  wall-clock time decides the outcome run to run. It can fail when the
  behavior is correct (bad luck) and pass when the behavior is broken (good
  luck) — the opposite of "fails for exactly one real reason."

## Rewrite

Everything in the Cut list above lands here instead of Cut whenever the
behavior is real and worth guarding — which is most of them. A test earns
Rewrite, not Cut, when:

- it is the only test on the code path it (badly) covers, or
- the smell is fixable by changing *what* the test asserts or *how* it
  builds its inputs, without abandoning the behavior.

Rewrite the assertion, the setup, or the isolation — not the intent. If you
cannot state what the rewritten test should assert instead, you have not
finished judging it; don't apply a placeholder rewrite.

## Keep

A keeper earns its place against Khorikov's four pillars — regression
protection, refactoring resistance, fast feedback, maintainability — by:

- asserting an observable outcome, not an implementation detail
- failing for exactly one reason
- surviving an internal refactor of the code it covers
- covering the behavior at the lowest layer that owns it

For what a good test looks like when you're writing one rather than judging
one, see `python-testing-patterns`'s Test Quality Gate — this skill applies
that same standard as a sweep instead of restating its positive patterns.

**The highest-value, lowest-visibility find** is the interaction-only test
that is green today: it asserts a mock was called with certain arguments and
nothing about the outcome. It looks like coverage and destroys refactoring
resistance — the moment the implementation changes shape while behavior
holds, it goes red for a reason no user cares about. Call these out first.

## The audit, worked

```python
def test_create_user_returns_expected_user():
    service = UserService()

    user = service.create_user(name="Ada", email="ada@example.com")

    assert user == {
        "id": 42,
        "name": "Ada",
        "email": "ada@example.com",
        "created_at": "2026-08-13T00:00:00Z",
    }
```

Sensitive equality: `id` and `created_at` aren't this test's business, but
locking them into a literal means the test fails the moment the id sequence
advances or a millisecond of clock drift shows up — for a reason no user
cares about. The behavior worth guarding — a created user carries the name
and email you gave it — is real. Rewrite:

```python
def test_create_user_returns_expected_user():
    service = UserService()

    user = service.create_user(name="Ada", email="ada@example.com")

    assert user.name == "Ada"
    assert user.email == "ada@example.com"
```

Two fields instead of four. `id` and `created_at` are still generated —
just no longer this test's problem.

## Run

1. **Start clean, scope tight.** Confirm a clean working tree first
   (`git status`). Then scope: audit `$ARGUMENTS` if given; with no argument,
   default to the current branch's diff against its base — resolve the base,
   don't assume `main`
   (`git diff --name-only $(git merge-base HEAD origin/HEAD)...HEAD`), not the
   whole tree — a repo-wide sweep is an explicit opt-in the user asks for by
   name. Either way, skip
   vendored, generated, and dependency trees (`node_modules`, `dist`,
   `.venv`, build output, lockfiles) and any `worktrees/` tree — a git
   worktree mirrors the whole repo, so scanning it multiplies every finding
   once per worktree — and leave load-bearing scaffolding alone (see above).
   `audit.py` prunes these directory names itself; the same skip applies to
   the judgment sweep.

2. **Pass one — run both mechanical scanners.** `python3 test-audit/audit.py
   <scope>` scans pytest files; `node test-audit/audit.mjs <scope>` scans
   vitest and node:test files. Run both and concatenate their output into one
   `file:line: <smell>` candidate list for the five mechanically detectable
   smells (assertion-free, tautology, mock-the-world, interaction-only
   assertion, empty/skipped). This is a candidate list, not a verdict — every
   line still needs the judgment pass below to confirm it and assign a
   bucket.

3. **Pass two — sweep every test, not a sample.** Walk the test files in
   scope and read each test beside the code it covers; judgment needs both,
   pass one's candidates tell you where to look first, but the sweep still
   covers every test in scope, not just the flagged lines. On a large tree,
   fan the sweep across subagents by directory — but every test in scope
   gets judged, never sampled.

4. **Judge each into one bucket** against the one test, checking the
   only-test warning before every Cut. For each Cut or Rewrite, write the
   one-line concrete failure it names — "cannot fail when X breaks" or
   "fails when Y is refactored though nothing broke." If you can't name it
   concretely, you haven't finished judging — don't bucket it yet.

5. **Write the findings log and render the summary — the default deliverable.**
   Write every judged Cut/Rewrite/Keep to `findings.jsonl`, then draw a grouped
   summary `report.html` from it (see below). Touch no test. Print the one-line
   verdict and the summary's absolute path, nothing else. The mechanical
   scanners' `file:line: <smell>` candidate list from pass one still prints to
   the terminal — it is a scan, not the log.

## Write the log and render the summary

The sweep can judge hundreds of tests; do not render one HTML card each. Write
the full record to `findings.jsonl` and a grouped summary to `report.html`,
following `~/.agents/skills/all-audits/FINDINGS-LOG.md` for both — the JSONL
schema and the summary's grouped-overview shape. Write both to
`<tmpdir>/test-audit-<timestamp>/`, then open the summary and hand off its path
as `~/.agents/skills/ponytail-audit/HTML-REPORT.md`'s asset-delivery section
describes.

- **Log** — one JSONL line per judged test. `bucket` is `cut` / `rewrite` /
  `keep`. `category` is the smell that named it — `duplicate-coverage`,
  `mystery-guest`, `eager`, `sensitive-equality`, `name-mismatch`,
  `library-default`, `conditional-logic`, `flaky-by-construction`, `tautology`,
  `interaction-only`. A rewrite carries `before`/`after`; a duplicate-coverage
  cut carries `owner` (the stronger test's `file:line`).
- **Summary** — the verdict, the `N judged · C cut · R rewrite · K kept`
  metabar, and the findings grouped by bucket then category with counts. No
  per-test cards. Call out the standouts in a `vt-callout`: the interaction-only
  tests that are green today, the highest-value find.

## Applying the changes (opt-in)

Only when the user asks to apply — never by default:

1. **Start clean.** Confirm a clean working tree first (`git status`).

2. **Apply the changes.** Delete the cuts. Rewrite each Rewrite to assert
   the real behavior correctly — new assertions, isolated setup, mocked
   time, whatever the smell called for. Leave every Keep untouched.

3. **Run the repo's own test command.** A test you misjudged as crap should
   turn the loop red here, before a human ever reviews the diff — not after
   it merges.

4. **Commit on an isolated branch and open a PR.** Every cut and rewrite is
   a judgment call; a human reads the sweep before it merges, and the
   isolated commit means the whole audit reverts in one step if a call
   proves wrong.
