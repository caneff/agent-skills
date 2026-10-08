# Test smells the test-audit skill does not catch, 2026-10-08

Question: which test smells and bad test types from the literature does
`test-audit` not already catch, and which are worth adding?

## Method

- Local baseline: `test-audit/SKILL.md` read in full. `audit.py` read for its
  five detectors (`is_assertion_free`, `is_tautology`, `is_mock_the_world`,
  `is_interaction_only`, `is_empty_or_skipped`) and the prose-assertion
  section. `audit.mjs` grepped for how it recognizes assertions, modifiers and
  interaction matchers.
- Probe: I wrote a vitest file and a pytest file in the session scratchpad,
  each holding one example of a candidate gap, and ran both scanners on them.
  `audit.mjs` flagged only the dangling `expect(r)` and the uncalled
  `.toBeTruthy` (both as assertion-free). `audit.py` printed
  `no mechanical smells found` for: an assert after the raising line inside
  `pytest.raises`, two functions both named `test_dup`,
  `pytest.raises(Exception)`, a stub that is also asserted called, a
  snapshot-only test and a `print` in a test. `audit.mjs` also did not flag
  `test.only` or an unawaited `.resolves`. Python 3.12.3 confirmed two
  language facts: a second `def test_dup` replaces the first in the module
  namespace, and a statement after the raising line inside a
  suppressing `with` block never runs. pytest itself is not installed here,
  so I did not run pytest on these.
- Sources: each was opened once, as listed in § Coverage. Content was
  treated as data.

Columns in the gap table: **Detect** says whether the smell suits pass one
(the mechanical scan, with the rough signal) or only pass two (judgment).
**Rank** is the value order, 1 being most worth adding.

---

## 1. Gaps, ranked

| Rank | Smell (names in sources) | Concrete failure | Detect | Why this rank | Primary source |
|---|---|---|---|---|---|
| 1 | **Leaking domain knowledge**: the test recomputes the expected value with the SUT's own formula. Other names: Production Logic in Test, "ugly mirror", tautological test. | Cannot fail when the algorithm is wrong, because the test holds the same wrong formula. It also fails on a legitimate bug fix, since it checks "implemented as before", not "correct". | Pass two. Pass one can only hint: the expected side of an `assert ==` is built from arithmetic, string concatenation or a loop over the same inputs passed to the SUT. | Both halves of "the one test" fail at once. Agent-written tests produce it a lot. `audit.py`'s `is_tautology` docstring already sends this form to the judgment pass, but SKILL.md's pass-two list never names it, so nobody is told to look for it. | Vladimir Khorikov, "Leaking domain knowledge to tests", 2018-01-30, https://enterprisecraftsmanship.com/posts/leaking-domain-knowledge-tests/ ; also Gerard Meszaros, "Conditional Test Logic" (cause *Production Logic in Test*), 2006-10-31, http://xunitpatterns.com/Conditional%20Test%20Logic.html ; Erik Kuefler, *Software Engineering at Google* ch. 12 "Unit Testing", § Don't Put Logic in Tests (logic in the expected URL hid a double-slash bug), https://abseil.io/resources/swe-book/html/ch12.html |
| 2 | **Private-API access**: the test calls private methods or reads private state. Other names: The Inspector, X-Ray Specs, Exposing private state. | Fails when an internal refactor renames or removes a private member, even though callers see no change. | Pass one, as a candidate. Python: an attribute access `x._name` on anything except `self`/`cls`, or `from mod import _name`. TS/JS: `(x as any).`, `// @ts-expect-error` / `@ts-ignore` placed before a member access, or `x["_name"]`. | Interaction-only already covers mock coupling. This is the other half of refactoring resistance, and no category covers it. A high-signal AST check. | Khorikov, "Unit testing private methods", 2017-10-23, https://enterprisecraftsmanship.com/posts/unit-testing-private-methods/ ; Khorikov, "Exposing private state to enable unit testing", 2017-11-01, https://enterprisecraftsmanship.com/posts/exposing-private-state-to-enable-unit-testing/ ; SWE at Google ch. 12, § Test via Public APIs (same URL as above) |
| 3 | **Asserting interactions with stubs, or overspecified interaction**: a double that feeds the SUT input (`return_value`) is also asserted called, or `assert_called_once_with` pins arguments the test is not about. | Fails when the SUT gets its input another way (caches it, batches it, reorders calls) while its output is unchanged. | Mostly pass one. The same mock attribute gets `.return_value`/`.side_effect` (or `mockReturnValue`) **and** `assert_called*`/`toHaveBeenCalled*`. Judging which arguments are incidental is pass two. | `interaction-only` flags a test only when **every** assertion is a call check (`is_interaction_only` returns `all(checks)`). A test with a real outcome assertion plus a stub-call check gets through, and that is the common shape. | Khorikov, "When to Mock", 2020-04-15, https://enterprisecraftsmanship.com/posts/when-to-mock/ ("you should never assert interactions with stubs") ; Andrew Trenk & Dillon Bly, *SWE at Google* ch. 13 "Test Doubles", § Avoid overspecification, https://abseil.io/resources/swe-book/html/ch13.html ; Meszaros, "Fragile Test" (cause *Overspecified Software*), 2007-02-18, http://xunitpatterns.com/Fragile%20Test.html |
| 4 | **Dead assertion inside an expect-exception block** | Cannot fail. Any assertion after the raising line inside `with pytest.raises(...)` never runs, so whatever it claims is unchecked. | Pass one, exact. In a `With` whose context expression is `pytest.raises`/`raises`, any statement after the first call (or any `assert`/`assert_*` at all inside the block). | Zero false positives and cheap. It is a Neverfail Test in its mechanical form. Confirmed in the probe: `audit.py` does not flag it. | pytest docs, "API Reference" § `pytest.raises` Note ("Lines of code after that, within the scope of the context manager will not be executed"), pytest 9.0, https://docs.pytest.org/en/stable/reference/reference.html ; Meszaros, "Production Bugs" (cause *Neverfail Test*), 2007-02-18, http://xunitpatterns.com/Production%20Bugs.html |
| 5 | **Lost test**: a test that never runs. Covers a second `def test_x` that shadows the first, a `Test*` class with `__init__`, and a test-shaped function without the `test` prefix. | Cannot fail. The shadowed or uncollected body never runs, so it guards nothing, and it still looks like coverage. | Pass one, exact. Duplicate `FunctionDef` names at module or class scope; a `Test*` class defining `__init__`; for vitest, two `it`/`test` calls in one `describe` with the same literal title. | Structurally cannot fail, which is the gate's own standard. The duplicate-name case could join `--gate`. | Meszaros, "Production Bugs" (cause *Lost Test*), same page as above ; pytest docs, "Good Integration Practices" § Conventions for Python test discovery ("Test prefixed test classes (without an `__init__` method)"), https://docs.pytest.org/en/stable/explanation/goodpractices.html |
| 6 | **Vacuous loop assertion**: assertions only inside `for x in result:`. | Cannot fail when the SUT returns an empty collection, because the loop body never runs. | Pass one. Every assertion sits inside a `For`/`forEach` body whose iterable comes from the SUT, and there is no length or non-empty assertion outside the loop. | SKILL.md's *conditional test logic* names only `if`/`else` and `try`/`except`. Meszaros and tsDetect both count loops. Tests that go green on empty output are common. | Meszaros, "Conditional Test Logic" (cause *Conditional Verification Logic*: "the use of loops to verify the contents of collections"), URL as rank 1 ; Peruma et al., testsmells.org "Test Smell Types" § Conditional Test Logic (rule includes `for`, `foreach`, `while`), https://testsmells.org/pages/testsmells.html |
| 7 | **Unspecced or unfaithful double**: `Mock()`/`MagicMock()`/`patch()` without `spec`/`autospec`/`spec_set`, or a fake that does not match the real contract. | Cannot fail when the real API is renamed or its signature changes. The mock accepts any attribute and any call, so the test stays green while production breaks. | Pass one for Python: a mock constructor or `patch` call without a `spec*`/`autospec` keyword. Whether a hand-written fake is faithful is pass two. | Python's own docs describe exactly this failure. Common in agent-written tests. It overlaps `mock-the-world` only when there are many mocks; a single unspecced mock gets through. | Python docs, "unittest.mock" § Autospeccing ("tests can all pass even though your code is broken"), https://docs.python.org/3/library/unittest.mock.html ; SWE at Google ch. 13 § The Fidelity of Fakes ; Martin Fowler, "Contract Test", 2011-01-12, https://martinfowler.com/bliki/ContractTest.html |
| 8 | **Broad exception expectation**: `pytest.raises(Exception)` with no `match=`, or vitest `toThrow()` with no argument. | Cannot fail when the code raises the wrong error, for example a `TypeError` from a typo instead of the intended `ValueError`. | Pass one, exact. The `raises` argument is `Exception`/`BaseException` and there is no `match`; the `toThrow`/`toThrowError` call has no arguments. | pytest's docs warn against it by name. Cheap check. | pytest docs, "API Reference" § `pytest.raises` Warning ("it is easy for this to hide real bugs"), URL as rank 4 |
| 9 | **Non-strict xfail** | Cannot fail the suite. The docs say "Both XFAIL and XPASS don't fail the test suite by default", so a test marked xfail stays green whether the bug is fixed or not. | Pass one. `@pytest.mark.xfail` without `strict=True`, when the ini file does not set `strict_xfail`/`xfail_strict`. | `is_empty_or_skipped` looks only at `skip`. This is the same kind of hole, but it carries a marker that reads like intent. | pytest docs, "How to use skip and xfail" § strict parameter, https://docs.pytest.org/en/stable/how-to/skipping.html |
| 10 | **Structural inspection**: asserting a type, an interface, attribute presence or the SUT's internal composition. | Fails when a refactor drops an interface or reorders sub-components, even though the output is unchanged. It cannot catch a wrong output. | Pass one, as a candidate. Every assertion is an `isinstance`/`issubclass`/`hasattr`/`callable`/`type(x) is` check, or `toBeInstanceOf`/`toHaveProperty`. | Close to *library-default*, but it pins the codebase's own structure. Only the narrow all-structural case is high-signal. | Khorikov, "Unit testing anti-patterns: Structural Inspection", 2016-07-21, https://enterprisecraftsmanship.com/posts/structural-inspection/ ; Alex Eagle, "Testing on the Toilet: Change-Detector Tests Considered Harmful", Google Testing Blog, 2015-01-27, https://testing.googleblog.com/2015/01/testing-on-toilet-change-detector-tests.html |
| 11 | **Snapshot-only test** | Cannot fail on the run that writes the snapshot, so it proves only what a reviewer checked in the snapshot file. A large snapshot then fails on any unrelated field (sensitive equality at file scale). | Pass one, as a candidate. The only assertion is `toMatchSnapshot`/`toMatchInlineSnapshot`, or `== snapshot` (syrupy). Judging the snapshot's size and focus is pass two. | Partly covered by *sensitive equality*, but no detector looks for it, and `-u` turns every failure green. Both runners' docs say a snapshot is only as good as its review. | Vitest docs, "Snapshot" guide ("should be committed alongside code changes, and reviewed"), v5.0.3, https://vitest.dev/guide/snapshot.html ; Jest docs, "Snapshot Testing" § Treat snapshots as code, https://jestjs.io/docs/snapshot-testing |
| 12 | **General / Fragile Fixture**: setup builds more than the test uses, or many tests depend on values in shared setup. | Fails when someone edits the shared fixture for a new test, even though the behavior of the failing tests never changed. | Pass two. Pass one could hint: a fixture whose fields most tests never read (tsDetect's rule). | Real, but it shows up as maintenance cost more than wrong verdicts. *Mystery guest* covers the hidden-state half, not the over-building half. | Meszaros, "Obscure Test" (cause *General Fixture*), 2006-12-20, http://xunitpatterns.com/Obscure%20Test.html ; Meszaros, "Fragile Test" (cause *Fragile Fixture*), URL as rank 3 ; van Deursen, Moonen, van den Bergh & Kok, "Refactoring Test Code", CWI report SEN-R0119, 2001-07-31, Smell 4, https://ir.cwi.nl/pub/4324/04324D.pdf ; SWE at Google ch. 12 § Shared Setup |
| 13 | **Committed focused test** (`it.only`/`test.only`/`describe.only`) | Every other test in the file silently stops running, so the file cannot fail on them. | Pass one, exact. `testModifier(call) === "only"` (`audit.mjs` already parses the modifier; `isEmptyOrSkipped` ignores `only`). | Vitest refuses `.only` only when `CI` is set (`allowOnly` default `!process.env.CI`). A local `land.testcmd` gate that does not set `CI` would run it. I did not check whether the gate sets `CI`. | Vitest docs, "allowOnly" config, https://vitest.dev/config/allowonly.html |
| 14 | **The Sequencer**: the test asserts the order of an unordered collection. | Fails when iteration order changes (for example, Python `set` of `str` under hash randomization), even though no behavior changed. | Pass one, as a candidate. `assert list(<set or .keys()>) == [...]`, or an equality against a list literal on a query result that has no ordering. | A narrow form of *flaky-by-construction*, which SKILL.md does not name. Low frequency. | James Carr, "TDD Anti-Patterns", 2006-11-03, archived copy https://web.archive.org/web/20080820001233/http://blog.james-carr.org/2006/11/03/tdd-anti-patterns/ |
| 15 | **Test logic in production / code pollution**: test-only methods, `if TESTING` switches, test hooks in production code. | The shipped code carries a branch that only tests exercise. Tests can pass through the test branch while the real branch is broken. | Pass one grep, but on **production** files: `PYTEST_CURRENT_TEST`, `"pytest" in sys.modules`, `if testing`/`is_test`, names like `*_for_testing`. | The smell lives in production code, outside test-audit's scope (test files). It fits better as a ponytail-audit or standards check, so it is listed but ranked last. | Meszaros, "Test Logic in Production", 2007-02-18, http://xunitpatterns.com/Test%20Logic%20in%20Production.html ; Khorikov, "Code pollution", 2018-03-19, https://enterprisecraftsmanship.com/posts/code-pollution/ ; van Deursen et al. 2001, Smell 9 "For Testers Only", URL as rank 12 |

Ranks 4, 5, 8 and 9 are exact AST matches with essentially no judgment
needed. Of those, the duplicate-name half of rank 5 is the only one that
meets the gate's standard ("structurally cannot fail").

---

## 2. Considered and judged covered, or not worth adding

### Already covered by an existing category

| Smell (source) | Covered by |
|---|---|
| Empty Test, Unknown Test (testsmells.org); The Secret Catcher (Carr) | `assertion-free`, `empty/skipped` |
| Redundant Assertion (testsmells.org) | `tautology` (literal form) |
| Ignored Test (testsmells.org) | `empty/skipped` for a skip without a reason. A skip that has a reason is not flagged, and that seems right. |
| The Mockery (Carr); Mock Happy (Garousi Table 4) | `mock-the-world` |
| Change-detector test (Eagle 2015), when every assertion is a call check | `interaction-only`. The mixed form is gap 3. |
| Eager Test (van Deursen Smell 5; Meszaros); The Free Ride, The One, The Giant (Carr); Test Behaviors, Not Methods (Kuefler, Google Testing Blog, 2014-04-14, https://testing.googleblog.com/2014/04/testing-on-toilet-test-behaviors-not.html) | `eager` |
| Sensitive Equality (van Deursen Smell 10, the `toString` form; Meszaros); The Nitpicker (Carr) | `sensitive-equality`. SKILL.md frames it as whole-object equality. The literature's original is string-representation equality, and the same reasoning covers it. |
| Mystery Guest, Resource Optimism, Test Run War (van Deursen Smells 1–3); Interacting Tests, Lonely Test, Unrepeatable Test (Meszaros, "Erratic Test", 2007-02-04, http://xunitpatterns.com/Erratic%20Test.html); Generous Leftovers, Hidden Dependency, Local Hero, OS Evangelist, Peeping Tom (Carr) | `mystery-guest` |
| Nondeterministic Test (Meszaros); Sleepy Test (testsmells.org); Time, Asynchronous Behavior (Fowler, "Eradicating Non-Determinism in Tests", 2011-04-14, https://martinfowler.com/articles/nonDeterminism.html); "Non-determinism in tests" (Khorikov, 2018-04-16, https://enterprisecraftsmanship.com/posts/non-determinism-tests/); Time Bombs (Garousi) | `flaky-by-construction` |
| Exception Handling (testsmells.org); The Greedy Catcher (Carr); Flexible Test, Conditional Test Logic `if` form (Meszaros) | `conditional-logic`. Loops are not covered: gap 6. |
| The Dodger, The Enumerator (`test1`, `test2`) (Carr) | `name-mismatch`. The Enumerator is trivially greppable, but it costs readability, not a wrong verdict. |
| Indirect Testing (van Deursen Smell 8; Meszaros); The Stranger (Carr); test implication (van Deursen Smell 11) | `duplicate-coverage` |
| The Liar, Success Against All Odds (Carr); Neverfail Test (Meszaros) | These are umbrella names for "cannot fail". The existing categories catch the general forms. The specific mechanical forms found here are gaps 4, 5, 6 and 9. |
| Working with time (Khorikov ch. 11 § 11.6; heading only) | `flaky-by-construction` |

### Not worth adding

| Smell (source) | Why not |
|---|---|
| Assertion Roulette, Missing Assertion Message (van Deursen Smell 7; Meszaros, "Assertion Roulette", 2006-10-31, http://xunitpatterns.com/Assertion%20Roulette.html; testsmells.org) | The original problem is a JUnit runner that cannot say which assertion failed. pytest assertion rewriting and vitest both report the failing line and both values. That claim comes from my knowledge of both runners; I did not open a doc page for it this session. The eager-test half is already covered. |
| Magic Number Test (testsmells.org) | Literals in assertions are what SWE at Google ch. 12 § Shared Values and DAMP-over-DRY argue *for*. Flagging them would push tests toward the Hard-Coded/shared-constant obscurity that Google warns against. |
| Lazy Test (van Deursen Smell 6; testsmells.org) | tsDetect's rule ("multiple test methods calling the same production method") flags one-test-per-behavior, which Kuefler 2014 recommends. |
| Duplicate Assert (testsmells.org) | Low value. A repeated identical assertion is noise, not a wrong verdict. |
| Constructor Initialization (testsmells.org) | The JUnit form does not apply. The pytest consequence (class not collected) is folded into gap 5. |
| Default Test (testsmells.org) | Android Studio only. |
| Redundant Print; The Loudmouth (testsmells.org; Carr) | Console noise. It does not change whether the test can fail. Probe confirmed it is not flagged, which is the right call. |
| Test Code Duplication (van Deursen Smell 11; Meszaros, http://xunitpatterns.com/Test%20Code%20Duplication.html) | SWE at Google ch. 12 argues DAMP, not DRY, for tests. A sweep that cuts duplication fights that. |
| Slow Tests, Too Many Tests (Meszaros, "Slow Tests", 2006-10-11, http://xunitpatterns.com/Slow%20Tests.html) | A suite-level metric (`--durations`). It is not a per-test Cut/Rewrite/Keep verdict. The sleep form is already `flaky-by-construction`. |
| Manual Intervention (Meszaros, http://xunitpatterns.com/Manual%20Intervention.html) | Not applicable to these automated suites. |
| Missing Unit Test, Untested Code, Untested Requirement (Meszaros, "Production Bugs") | These are coverage gaps, not properties of an existing test. test-audit judges tests that exist. |
| Unawaited `expect(...).resolves`/`.rejects` | Vitest docs, "expect" § resolves: "If the assertion is not awaited, the test will be marked as 'failed' at the end of the test" (https://vitest.dev/api/expect.html). The runner already catches it. |
| Misspelled mock assertion (`m.called_once_with(...)`) | Python 3.12.3 raises `AttributeError: 'called_once_with' is not a valid assertion` (checked here). The docs record the `assert*`/`assret*` prefix guard as added in 3.5. The runtime catches it. |
| Mocking concrete classes (Khorikov ch. 11 § 11.5) | Only the heading was readable (paywalled), so I could not check his argument. The Python-relevant half overlaps gap 7. |

---

## 3. Coverage

**Opened and read (the parts named):**

- xunitpatterns.com (Meszaros' pre-publication drafts; each page says the book
  text "has likely changed substantially"): the "Test Smells" index
  (http://xunitpatterns.com/Test%20Smells.html) for the list and dates, and
  the smell pages Fragile Test, Erratic Test, Obscure Test, Test Logic in
  Production, Test Code Duplication, Assertion Roulette, Slow Tests, Manual
  Intervention, Frequent Debugging, Buggy Tests, Conditional Test Logic and
  Production Bugs. I extracted each page's "Cause:" sections. I did not read
  every code example in full.
- testsmells.org "Test Smell Types" page (19 smells with detection rules;
  the page shows no date). The tsDetect paper: Peruma, Almalki, Newman,
  Mkaouer, Ouni & Palomba, "tsDetect: An Open Source Test Smells Detection
  Tool", ESEC/FSE 2020, preprint
  https://testsmells.org/assets/publications/FSE2020_TechnicalPaper.pdf. Text
  was extracted with a zlib stream reader. I read Table 1 and the precision
  table.
- Garousi & Küçük, "Smells in software test code: A survey of knowledge in
  industry and academia", JSS 138 (2018) 52–81, accepted-manuscript preprint
  https://pureadmin.qub.ac.uk/ws/files/178889150/MLR_Smells_in_test_code_Dec_9.pdf.
  I read § 6.4 and the partial Table 4 (139 of 196 smells) through the
  extracted text. Used to find candidate names. Each smell is cited to the
  source that coined it where I could open that source.
- van Deursen, Moonen, van den Bergh & Kok, "Refactoring Test Code", CWI
  report SEN-R0119 (2001-07-31; published at XP2001),
  https://ir.cwi.nl/pub/4324/04324D.pdf. Smells 1–11 read in full. The
  report has 11 numbered smells. xunitpatterns' bibliography page says 12; I
  did not resolve the difference.
- Khorikov blog (Enterprise Craftsmanship): unit-testing-private-methods,
  exposing-private-state-to-enable-unit-testing,
  leaking-domain-knowledge-tests, code-pollution, structural-inspection,
  when-to-mock, non-determinism-tests. Each read for its opening argument,
  roughly the first 3–8 KB of body text. Book ch. 11 on Manning liveBook
  (https://livebook.manning.com/book/unit-testing/chapter-11): only the
  section headings and intro were visible.
- *Software Engineering at Google* (online edition, abseil.io): ch. 12
  (Kuefler) TL;DRs plus § Test via Public APIs, § Don't Put Logic in Tests,
  § Shared Values, § Shared Setup and § Shared Helpers; ch. 13 (Trenk & Bly)
  TL;DRs plus § Tests become less effective, § The Fidelity of Fakes and
  § Avoid overspecification. Ch. 14: headings only. The 2020 publication date
  comes from my knowledge, not the page.
- Google Testing Blog: Eagle 2015-01-27 (change-detector) and Kuefler
  2014-04-14 (behaviors, not methods), both in full.
- Fowler: "Eradicating Non-Determinism in Tests" (2011-04-14; Lack of
  Isolation, Remote Services and Time sections), "Mocks Aren't Stubs"
  (2007-01-02 revision; § Coupling Tests to Implementations, § Test
  Isolation), "Contract Test" bliki (2011-01-12) and "Test Pyramid" bliki
  (2012-05-01; intro only, no gap came from it).
- James Carr, "TDD Anti-Patterns", 2006-11-03, Wayback snapshot of
  2008-08-20. Read the catalogue in full; read the comments only up to the
  start of Frank Carver's comment.
- Python docs: `unittest.mock` § Autospeccing and the `unsafe` parameter.
  pytest docs: reference § `pytest.raises` (Warning and Note), "How to use
  skip and xfail" § strict parameter, "Good Integration Practices"
  § discovery. Vitest docs: `expect` (resolves, rejects,
  `expect.assertions`), the Snapshot guide and `allowOnly`. Jest docs:
  "Snapshot Testing" best practices.

**Could not reach or did not open:**

- Khorikov, *Unit Testing Principles, Practices, and Patterns* ch. 11 body:
  paywalled. Only headings were visible. His blog posts were used for the
  same topics; "Mocking concrete classes" has no blog equivalent that I
  found in the archive listing, which I filtered by link titles containing
  "anti-pattern", "mock" or "test".
- Meszaros "Hard-to-Test Code" page: HTTP 404 at
  `http://xunitpatterns.com/Hard-to-Test Code.html`. The printed book was
  not available.
- The online full classification that Garousi & Küçük link (goo.gl/1ZrL65):
  not opened. The publisher's version of record (doi
  10.1016/j.jss.2017.12.013): not opened; the preprint was used.
- Peruma et al. CASCON 2019 (tsDetect's reference [22], the catalogue
  paper): not opened.
- The StackOverflow unit-testing anti-patterns thread (Garousi [S157]) and
  the "ugly mirror" talk (Garousi [S128]): not opened. Those names are cited
  only through the sources that coined their concepts (Khorikov, Meszaros).
- Fowler's "Test Pyramid" was opened, but no gap or coverage judgment rests
  on it.
- pytest's own behavior on the probe file was not run (pytest not
  installed). The duplicate-name and dead-code facts were checked against
  CPython 3.12.3 semantics, and the dead-code fact is also stated in pytest's
  docs.
