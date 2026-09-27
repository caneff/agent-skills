# Prompt audit 2026-09-27 — cluster `testing`

Skills: `python-testing-patterns`. 9 findings.
Hunks are proposals written against `main` at 9a1c304; re-read the current line before applying. Where a finding has no hunk, write the edit from its action and ruling.
Target model for every judgment: Claude Opus 5.5. Method: the bundled `claude-api` skill's `shared/prompt-audit.md`.

## `batch-1:F9` — python-testing-patterns/SKILL.md:39-51

- **Confidence:** Medium
- **Pattern:** 2 / Verbose SKILL.md explaining what the model knows
- **Evidence:** "**Test Discovery**: Files matching `test_*.py` ... **Assertions**: Use `assert` statements"
- **Why:** pytest discovery, scopes, and `assert` are trained knowledge. Line 47 is the one local rule in the section; it moves into Prefer.
- **Action:** remove + move line 47 (hunk)
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/python-testing-patterns/SKILL.md
+++ b/python-testing-patterns/SKILL.md
@@ -28,26 +28,13 @@
 - small local builders for domain objects
 - parametrization for the same behavior matrix
 - exact text checks only where the formatter or composer owns wording
+- expected-value-driving data local to the test; shared fixtures for mechanics, builders, and cleanup, not hidden business examples
 
 Delete or rewrite:
 
 - tests that only prove a dependency or library default
 - tests that repeat full workflow coverage in a unit file
 - tests whose name says one behavior but assertions check unrelated fields
 - tests that inspect private implementation unless no public behavior exposes the contract
 
-## Core Concepts
-
-**Test Discovery**: Files matching `test_*.py` or `*_test.py`, functions starting with `test_`
-
-**Fixtures**: Reusable test resources with setup and teardown
-- Scopes: `function` (default), `class`, `module`, `session`
-- Composition: Build complex fixtures from simple ones
-- Share via `conftest.py` for project-wide availability
-- Keep expected-value-driving data local to the test; use shared fixtures for mechanics, builders, and cleanup, not hidden business examples.
-
-**Assertions**: Use `assert` statements, `pytest.raises()` for exceptions
-
-**Organization**: Separate `unit/`, `integration/`, `e2e/` directories
-
 ## Quick Reference
```

## `batch-1:F10` — python-testing-patterns/SKILL.md:71-80

- **Confidence:** Medium
- **Pattern:** 2 / Verbose SKILL.md
- **Evidence:** "## Resources / **pytest**: https://docs.pytest.org/ ... **testcontainers**: Docker containers for testing"
- **Why:** A link list of libraries the model already knows; nothing here changes behavior.
- **Action:** remove (hunk)
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/python-testing-patterns/SKILL.md
+++ b/python-testing-patterns/SKILL.md
@@ -69,12 +69,1 @@
 | Best practices, test quality, fixture design | `~/.agents/skills/python-testing-patterns/references/best-practices.md` |
-
-## Resources
-
-- **pytest**: https://docs.pytest.org/
-- **unittest.mock**: https://docs.python.org/3/library/unittest.mock.html
-- **pytest-asyncio**: Testing async code
-- **pytest-cov**: Coverage reporting
-- **pytest-mock**: pytest wrapper for mock
-- **Hypothesis**: https://hypothesis.readthedocs.io/
-- **pytest-xdist**: Parallel test execution
-- **testcontainers**: Docker containers for testing
```

## `batch-1:F6` — python-testing-patterns/references/async-testing.md:115-125

- **Confidence:** Medium
- **Pattern:** 2 / Volatile specifics
- **Evidence:** "## Event Loop Management / @pytest.fixture def event_loop():"
- **Why:** Overriding the `event_loop` fixture was deprecated in pytest-asyncio 0.22 and removed in 1.0; the same file's line 149 says "Don't write manual event loop code".
- **Action:** remove (hunk)
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/python-testing-patterns/references/async-testing.md
+++ b/python-testing-patterns/references/async-testing.md
@@ -113,15 +113,4 @@
```

## `batch-1:F1` — python-testing-patterns/references/best-practices.md:8-11

- **Confidence:** Medium
- **Pattern:** 2 / Instruction files contradict
- **Evidence:** "# Good: Tests one concept / def test_user_creation_sets_default_role(): ... assert user.role == \"user\""
- **Why:** test-audit (added 2026-08-13, newer than this 2026-06-22 snapshot) cuts exactly this test as a library-default test (answer-key #9 `test_user_model_default_role_is_member`). Two skills rule opposite on one example.
- **Action:** rewrite (hunk)
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/python-testing-patterns/references/best-practices.md
+++ b/python-testing-patterns/references/best-practices.md
@@ -7,10 +7,11 @@
```

## `batch-1:F2` — python-testing-patterns/references/best-practices.md:104-110

- **Confidence:** Medium
- **Pattern:** 2 / Instruction files contradict
- **Evidence:** "random.seed(42) ... value = random.randint(1, 10) / assert value == 2  # Deterministic"
- **Why:** Taught as the fix, but it asserts only the stdlib RNG's output: test-audit's library-default smell. The value also depends on CPython's RNG implementation.
- **Action:** rewrite (hunk)
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/python-testing-patterns/references/best-practices.md
+++ b/python-testing-patterns/references/best-practices.md
@@ -104,7 +104,8 @@
-# Fix: Control randomness
-def test_random_generation_fixed():
-    import random
-    random.seed(42)  # Fixed seed
-    value = random.randint(1, 10)
-    assert value == 2  # Deterministic
+# Fix: inject the randomness and assert on your code's behavior
+class LowestRoll:
+    def randint(self, a, b):
+        return a
+
+def test_roll_die_returns_lowest_face_for_lowest_roll():
+    assert roll_die(rng=LowestRoll()) == 1
```

## `batch-1:F5` — python-testing-patterns/references/best-practices.md:251-264

- **Confidence:** Medium
- **Pattern:** 2 / Instruction files contradict
- **Evidence:** "### 13. Verify Interactions / Assert mocks were called correctly"
- **Why:** The example asserts only mock calls and no outcome; test-audit calls that interaction-only test its "highest-value find" to rewrite.
- **Action:** rewrite (hunk)
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/python-testing-patterns/references/best-practices.md
+++ b/python-testing-patterns/references/best-practices.md
@@ -251,14 +251,13 @@
 ### 13. Verify Interactions
-**Assert mocks were called correctly:**
+**Assert a call only when the call is the outcome — a message sent across a
+system boundary — and assert the returned result beside it. A test that checks
+only mock calls breaks on refactors that keep behavior:**
```

## `batch-1:F7` — python-testing-patterns/references/best-practices.md:307-334

- **Confidence:** Low
- **Pattern:** 2 / Volatile specifics
- **Evidence:** `@pytest.mark.database` / `@pytest.mark.e2e` with `addopts = -v --strict-markers` registering only unit/integration/slow
- **Why:** Following both sections as written, pytest errors on the unregistered markers.
- **Action:** flag
- **Ruling:** audit recommendation (fix), accepted by Chris. Two sections together make pytest error on unregistered markers; a real bug.

_No hunk — write the edit._

## `batch-1:F3` — python-testing-patterns/references/best-practices.md:383-397

- **Confidence:** Medium
- **Pattern:** 2 / Instruction files contradict
- **Evidence:** "def test_divide_edge_cases(): # Normal case ... # Edge: zero ... # Edge: negative"
- **Why:** Four behaviors in one body: the eager test that §1 of this same file and test-audit's "Eager test" both reject.
- **Action:** rewrite (hunk)
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/python-testing-patterns/references/best-practices.md
+++ b/python-testing-patterns/references/best-practices.md
@@ -383,15 +383,14 @@
```

## `batch-1:F11` — python-testing-patterns/references/pytest-fundamentals.md:1-80 and SKILL.md:59

- **Confidence:** Medium
- **Pattern:** 2 / Verbose SKILL.md
- **Evidence:** "# Pytest Fundamentals ... pytest -x ... AAA Pattern"
- **Why:** The whole file is pytest basics (CLI flags, AAA) Opus 5.5 knows; AAA is repeated in best-practices.md §3.
- **Action:** remove file + its table row (hunk for the row)
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/python-testing-patterns/SKILL.md
+++ b/python-testing-patterns/SKILL.md
@@ -57,5 +57,4 @@
 | Task | Reference File |
 |------|----------------|
-| Pytest basics, test structure, AAA pattern | `~/.agents/skills/python-testing-patterns/references/pytest-fundamentals.md` |
 | Fixtures, scopes, setup/teardown, conftest.py | `~/.agents/skills/python-testing-patterns/references/fixtures.md` |
```
