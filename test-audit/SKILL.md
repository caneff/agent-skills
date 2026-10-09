---
name: test-audit
description: Ruthlessly audit a repo's tests — cut the ones that prove nothing, rewrite the ones checking the wrong thing, keep only what earns its place.
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
the syntactically detectable smells and the `prose-assertion` smell.
`audit.py` covers pytest and `*.test.sh` files; `audit.mjs` covers vitest and
node:test. Run both first; their combined candidate list feeds the judgment
sweep below instead of starting from a blank page.

Pass one's smells, by the label each prints:

- **assertion-free test** — no assertion, or only a trivial one.
- **tautology** — a value asserted against itself.
- **mock-the-world** — many mocks, little real code.
- **interaction-only assertion** — every check is that a mock was called.
- **empty/skipped test** — an empty body, or a skip with no reason.
- **prose-assertion** — every assertion is that a prose file holds a string.
- **dead assertion in an expect-exception block** (`audit.py`) — a statement
  after the first call inside `with pytest.raises(...)` never runs, so it can
  never fail. Any statement counts, not only an `assert`: `with raises(E):
  setup(); target()` is a candidate too, and the judgment pass tells the setup
  that belongs outside the block from the target.
- **lost test (duplicate name)** — a second `def test_x` at the same module or
  class scope replaces the first (`audit.py`, reported at the shadowed
  definition, a `unittest.TestCase` class included); two `it`/`test` calls
  with a body in one `describe` of a vitest file with the same literal title
  (`audit.mjs`, reported at the repeat). `audit.mjs` looks only inside a
  `describe`, not at file scope. Vitest runs both tests of a repeated title,
  so there it is a naming defect the gate still treats as one.
- **lost test (uncollected class)** (`audit.py`) — a `Test*` class that defines
  `__init__` and a test method: pytest never collects it.
- **broad exception expectation** — `pytest.raises(Exception)` or
  `BaseException` with no `match=` (`audit.py`); `toThrow()` or `toThrowError()`
  with no argument, `.not` excluded (`audit.mjs`). It passes on the wrong
  error.
- **non-strict xfail** (`audit.py`) — `@pytest.mark.xfail` without
  `strict=True`, when the nearest pytest config does not set `xfail_strict`
  (or `strict_xfail`, or the umbrella `strict`). The test stays green whether
  the bug is fixed or not. The config is the first of `pytest.toml`,
  `.pytest.toml`, `pytest.ini`, `.pytest.ini`, `pyproject.toml`, `tox.ini`,
  `setup.cfg` that configures pytest, walking up from the test file to the repo
  root; one that cannot be read counts as not strict. A non-literal `strict=`
  is not flagged. Decorators on a test function or a class are read; a
  module-level `pytestmark = pytest.mark.xfail` is not.
- **private-API access** — a test reaches past the public surface. Python
  (`audit.py`): `x._name` on a receiver other than `self` or `cls`, reported at
  the test, and `from mod import _name`, reported at the import; dunders such as
  `__class__` do not count. TS/JS (`audit.mjs`): `(x as any).name`, `x["_name"]`,
  or a member access on the line under `@ts-ignore` / `@ts-expect-error`; an
  `expect(...).toX` chain under one is not a member access. A candidate only:
  `sys._getframe` reads the same, and the judgment pass tells them apart.
- **stub asserted called** — the same mock gets a `return_value` or
  `side_effect` and is also checked with `assert_called*` or `.called`
  (`audit.py`; the stub set by assignment, `Mock(return_value=...)`, `with
  patch(..., return_value=...) as m` or `@patch(..., return_value=...)`); a
  `mockReturnValue` / `mockResolvedValue` / `mockRejectedValue` /
  `mockImplementation` mock, a `vi.fn(impl)`, `vi.mocked(fn)` or a
  `vi.spyOn(obj, "m")` spy given one, is also under `toHaveBeenCalled*`
  (`audit.mjs`, vitest). A stub built outside the test body, in a fixture or
  `beforeEach`, is not seen. `interaction-only assertion` needs
  every check to be a call check, so this mixed form, with a real outcome
  assertion beside it, gets through there.
- **vacuous loop assertion** — every assertion sits in a `for` (Python) or a
  `for...of` / `for...in` / `.forEach` (JS) over what the code under test
  returned, so an empty result runs none of them. An assertion outside such a
  loop, a length or non-empty check included, clears it, and so does
  `expect.hasAssertions()` / `expect.assertions(n)` and a loop over a literal, a
  call on literals only, or a name the test never assigns.

**JS/TS reach.** `audit.mjs` recognizes vitest and node:test — nothing else.
A file identifies as **vitest** by importing `vitest`, or by naming tests
(`describe`/`it`/`test`) and calling `expect`. A file identifies as
**node:test** by importing `node:test`, and only that way — `assert.*` alone
is not a signal, so a node:test file that reaches its runner some other way is
out of reach. A file it can't identify as one of those two is skipped, never
flagged, so a homegrown or non-standard harness doesn't flood pass one with
false assertion-free findings. Playwright
`.spec` files are out of scope — they're e2e/visual specs, not unit tests, and
auditing them by this yardstick would misjudge them. jest, mocha, ava, and
chai are likewise out of scope. A missing `@babel/parser` prints a `run npm
ci` message and exits — bootstrap with `npm ci` in
`~/.agents/skills/test-audit/` once.

**Gate mode.** `audit.py --gate [path]` and `audit.mjs --gate [path]` are the
build-gate form of pass one: they report **only** the assertion-free and
duplicate-name smells and skip anything under a `fixtures/` directory. Those
two gate because a test that has no assertion, or that a later definition of
the same name replaced, cannot fail at all — a machine can call that a defect
without reading anything. Every other smell still runs and still fails when
the behavior breaks, so blocking a merge on one costs more than it buys; they
stay report-only. That includes the uncollected-class case of lost test.

Three exit statuses: **0** clean, **1** hollow tests found, **2** unable to
check. Only gate mode ever returns 1 — a report never fails a build — but 0 and
2 mean the same thing in both modes. A path that does not exist gets 2, never 0
— a gate that reports success while it scanned nothing is a lie, and a typo in
a repo's wiring would otherwise make that repo's gate permanently green.
`audit.mjs` also exits 2 when `@babel/parser` is missing.

The `fixtures/` exemption matches a directory of that name at any depth, so the
gate prints how many findings it suppressed, per gated smell (`N assertion-free
finding(s) suppressed under fixtures/.`, `N duplicate-name finding(s) suppressed
under fixtures/.`) even when it passes — otherwise a repo could park hollow
tests under a directory it named `fixtures` and never notice.

Wire it into a repo by adding it to that repo's local gate (`git config
land.testcmd`). In this repo that is `test-audit/assertion-free-gate.test.sh`,
picked up automatically by `tests/all.sh`'s `*.test.sh` discovery.

**The JS gate's remaining blind spot.** A file whose every test is
assertion-free has no assertion to be recognized by, so the runner *import* is
what identifies it — which leaves one case uncovered: a vitest file run
in globals mode, importing nothing, whose every test is assertion-free. It is
invisible to both signals. `audit.py` has no equivalent limit; it audits any
`test_*.py` outright.

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

## Documented intent — the author already answered

Before you Cut or Rewrite a test, read its own comments and docstring. When a
test carries an in-code comment or docstring stating *why* it exists — "a
worked example the property already owns," "a tripwire / deliberate
change-detector," an ADR reference — that is a documented-intent signal, and
evidence the test earns its place. A finding whose objection the test's own
comment already answers is arguing with the author, not naming a defect.

Default such a test to **Keep**. You may still disagree — but then surface it
as the `documented-intent` category, "author declares intent — confirm before
acting," naming the comment you would override, never a cold Cut or Rewrite.

One carve-out: a comment cannot rescue a test that *structurally* cannot
fail — the same limit the only-test warning draws above. A tripwire that *does* go
red when its guarded line changes is not this case; that is
change-detection-by-design, which documented intent moves to Keep. Documented
intent downgrades a judgment-call smell — duplicate coverage,
change-detection-by-design, an equality the author calls deliberate; it does
not resurrect coverage that was never there.

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
- **Conditional test logic.** An `if`/`else`, `try`/`except` or loop
  (`for`, `while`, `forEach`) inside the test body that changes what gets
  asserted, or whether anything is, depending on a runtime condition. Whichever
  branch runs, the test finds a way to pass — it can't fail no matter which
  branch the real behavior takes. A loop over a collection the code returned is
  the same hole: an empty collection runs the body zero times, and pass one's
  `vacuous loop assertion` is its mechanical form (Meszaros, "Conditional Test
  Logic"; tsDetect).
- **Leaking domain knowledge.** The test computes its expected value with the
  code under test's own formula (`assert total == price + price * rate`), so it
  holds the same bug the code does. It cannot fail when the algorithm is wrong,
  and it fails on a legitimate fix because it checks "implemented as before".
  Rewrite against a worked literal from the spec. `is_tautology` catches only
  the literal self-comparison; this form is for reading. Khorikov, "Leaking
  domain knowledge to tests".
- **Private-API access.** The test reads a private member, imports a
  `_name`, or casts through `as any` / `@ts-expect-error` to reach one. It
  fails when an internal refactor renames the member though no caller sees a
  change: the refactoring-resistance half that `interaction-only` does not
  cover. Pass one lists the candidates; the judgment pass confirms the target
  is private to the code under test, and keeps a deliberate type test or a
  stdlib name. Rewrite to assert through the public interface; when that
  interface cannot show the behavior, the finding is about the code under
  test, not the test.
- **Prose assertion.** The test's only assertions are that a prose file
  (Markdown, a `SKILL.md`, a doc) contains or lacks a string. It cannot fail
  when an agent stops following the rule, and fails on every rewording of the
  sentence, so it proves only that text exists. Always Cut: no behavior is
  there to rewrite toward. Pass one flags the mechanical cases: a Python test
  whose assertions are all `in`/`not in`/regex checks, that names a `.md`
  path and calls nothing but file reads and string handling; and a
  `*.test.sh` that names a `.md` file and runs nothing but text commands
  (`grep`, `sed`, `case`, `test`). A test that runs any other code is never
  flagged by pass one. Whether the output it greps is itself generated prose
  is the judgment pass's call, for example a test that greps a rendered
  report's wording instead of its content. Keep a test that runs code and
  checks a link target or a structure, such as `tests/check-section-references.py`.
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

## Verify against the fixture

`~/.agents/skills/test-audit/fixtures/` carries eleven files.
`test_pricing.py`, `test_checkout_e2e.py`, `test_user_service.py`,
`test_prose_assertions.py`, `prose_assertion.test.sh`,
`test_candidate_smells.py` and `vitest_candidate_smells.test.ts` span the
Cut/Rewrite/Keep buckets; `~/.agents/skills/test-audit/fixtures/answer-key.md`
has the pass-two bucket for each of their tests, and a run over them should
reproduce that table. `candidate-smells-fixtures.test.sh` pins what pass one
reports on those two, each smell beside its nearest negatives.
`test_pytest_smells.py`, `vitest_smells.test.js`,
`test_exact_match_smells.py` and `vitest_exact_match_smells.test.js` exist for
pass one's scanners to flag; the answer key does not cover them.
`exact-match-fixtures.test.sh` pins what both scanners report on the last two,
each smell beside its nearest negative.

## Run

1. **Start clean, scope.** Confirm a clean working tree first (`git status`).
   Then scope: audit `$ARGUMENTS` if given; with no argument, scope defaults
   per `~/.agents/skills/all-audits/SKILL.md`'s Scope section. Either way, skip vendored, generated, and dependency
   trees (`node_modules`, `dist`, `.venv`, build output, lockfiles) and any
   `worktrees/` tree — a git worktree mirrors the whole repo, so scanning it
   multiplies every finding once per worktree — and leave load-bearing
   scaffolding alone (see above). `audit.py` prunes these directory names
   itself; the same skip applies to the judgment sweep.

2. **Pass one — run both mechanical scanners.** `python3
   ~/.agents/skills/test-audit/audit.py <scope>` scans pytest and `*.test.sh` files; `node
   ~/.agents/skills/test-audit/audit.mjs <scope>` scans
   vitest and node:test files. Run both and concatenate their output into one
   `file:line: <smell>` candidate list for the mechanically detectable smells
   listed above. This is a candidate list, not a verdict — every
   line still needs the judgment pass below to confirm it and assign a
   bucket.

3. **Pass two — sweep every test, not a sample.** Walk the test files in
   scope and read each test beside the code it covers; judgment needs both,
   pass one's candidates tell you where to look first, but the sweep still
   covers every test in scope, not just the flagged lines. On a large tree,
   fan the sweep across subagents by directory — but every test in scope
   gets judged, never sampled.

4. **Judge each into one bucket** against the one test, checking the
   only-test warning and the documented-intent rule before every Cut or
   Rewrite. For each Cut or Rewrite, write the one-line concrete failure it
   names — "cannot fail when X breaks" or "fails when Y is refactored though
   nothing broke." If you can't name it concretely, you haven't finished
   judging — don't bucket it yet.

5. **Write the findings log and render the summary — the default deliverable.**
   Every judged Cut/Rewrite/Keep goes in the log (see below). Touch no test.
   The mechanical scanners' `file:line: <smell>` candidate list from pass one
   still prints to the terminal — it is a scan, not the log.

## Write the log and render the summary

See `~/.agents/skills/all-audits/harness/AUDIT-RUN.md` for the shared
write-and-deliver step (tmpdir resolution, `findings.jsonl` + `report.html`,
opening, and the final print). This skill's own bucket names, category
vocabulary, and metabar:

- **Log** — one JSONL line per judged test. `bucket` is `cut` / `rewrite` /
  `keep`. `category` is the smell that named it — `duplicate-coverage`,
  `mystery-guest`, `eager`, `sensitive-equality`, `name-mismatch`,
  `library-default`, `conditional-logic`, `flaky-by-construction`, `tautology`,
  `interaction-only`, `documented-intent`, `prose-assertion`,
  `dead-assertion`, `lost-test`, `broad-exception`, `non-strict-xfail`,
  `leaking-domain-knowledge`, `private-api-access`, `stub-asserted-called`,
  `vacuous-loop`. A rewrite carries `before`/`after`;
  a duplicate-coverage cut carries `owner` (the stronger test's `file:line`);
  a `documented-intent` row carries the comment it defers to in
  `extra.author_intent`.
- **Summary** — the verdict, the `N judged · C cut · R rewrite · K kept`
  metabar, and the findings grouped by bucket then category with counts. No
  per-test cards. Call out the standouts in a `vt-callout`: the interaction-only
  tests that are green today, the highest-value find.

## Applying the changes (opt-in)

Only when the user asks to apply — see `~/.agents/skills/all-audits/SKILL.md`'s
"Opt-in edits" section for the shared opt-in contract
(reviewable PR on its own branch, never a direct commit). Start from a clean
working tree.

Apply: delete the cuts. Rewrite each Rewrite to assert the real behavior
correctly — new assertions, isolated setup, mocked time, whatever the smell
called for. Leave every Keep untouched.

Verify before the PR: run the repo's own test command. A test you misjudged
as crap should turn the loop red here, before a human ever reviews the diff —
not after it merges.
