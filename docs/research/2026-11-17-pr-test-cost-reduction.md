# Cutting per-PR test cost without losing safety (2026-11-17)

Question: how do well-run engineering organisations cut the cost of per-PR
testing (which tests run on each PR, and how many tests exist at all) while
keeping new PRs safe, and which of their practices carry down to one developer
running about 17 small-to-medium repos, with coding agents writing hundreds of
PRs a month, GitHub Actions for CI, and a local seam (`bash tests/all.sh`,
narrowed with `--changed origin/main`) that agents run before they push?

Every claim below is marked **stated** (the source says it; quoted where
quotation marks appear, otherwise a close paraphrase), **inferred** (ours,
drawn from stated facts), or **checked** (read from this repo on 2026-11-17).
All pages were fetched on 2026-11-17. arXiv preprints are labelled as such.
Nothing here was measured on the target repos: every "expected saving" in the
last section is an estimate.

## Synopsis

1. Big organisations do not run every test on every change. They run a cheap, fast, reliable subset before merge and run everything after merge, on a schedule. The full post-merge run is what keeps them safe. Selection only buys speed.
2. Google's TAP data: 5.5M affected test targets, of which only 63K ever failed and 1.23% ever caught a real breakage. Meta's learned selection halves cost and still reports over 99.9% of faulty changes, because a full "stabilization" run every few hours backs it up.
3. Every serious selection tool falls back to "run everything" for changes it cannot reason about (Microsoft TIA; Vitest `forceRerunTriggers`). A narrowed run that cannot fail closed is the main risk.
4. On GitHub Actions the cheapest savings are mechanical. Cancel superseded runs (`concurrency`), set `timeout-minutes` (the default is 360), use the built-in caches in the `setup-*` actions, and avoid running both `push` and `pull_request` on branch pushes.
5. Do not put a workflow-level `paths` filter on a required check. A skipped workflow leaves the check "Pending" and blocks the merge. Filter inside the job instead, and remember that a job skipped by `if:` reports "Success". That skip has to fail closed.
6. Merge queues (`merge_group`) only exist for public repos owned by an organisation, or for private repos on GitHub Enterprise Cloud. They are probably unavailable on personal-account repos.
7. Fuzzing and long property or corpus runs belong off the PR path, on a time budget: ClusterFuzzLite uses 600 s of code-change fuzzing per PR and 3600 s batch runs every 6 h. Hypothesis can run 100 examples on a PR and more at night.
8. Shrinking a suite is riskier than selecting from it. Coverage-based minimisation lost over 50% of fault-detection effectiveness in more than half of 1000 suites (Rothermel et al., via Yoo & Harman). Coverage only weakly predicts effectiveness. Delete a test only when a named stronger test remains, and confirm with a mutation check.
9. Agent PRs add tests more often and modify or delete them less often than human PRs (two 2026 preprints by the same group, OR 1.50–1.79). One more preprint finds that agent-written tests often do not cover the agent's own changed lines. None of these is a first-party engineering post about limiting test bloat, and none was found.
10. For this setup, rank first a guaranteed full backstop on `main` and nightly, plus a fail-closed narrowed seam. Then come GitHub Actions hygiene, slow tiers moved off the PR path, enforced time budgets, tracked quarantine, and controls on agent test additions. Machine-learned selection, Bazel-style build graphs, merge queues and TAP-style batching do not carry down.

## 1. Test impact analysis and change-based selection

### Google TAP

Source: "Taming Google-Scale Continuous Testing", Atif Memon, Zebao Gao, Bao
Nguyen, Sanjeev Dhanda, Eric Nickell, Rob Siemborski, John Micco. ICSE-SEIP
2017. Abstract page https://research.google/pubs/taming-google-scale-continuous-testing/ ;
full text https://static.googleusercontent.com/media/research.google.com/en//pubs/archive/45861.pdf
(read from the PDF text).

- **Stated:** On an average day TAP runs "800K builds and 150 Million test runs". It selects tests "using reverse dependencies on changed source files". It does not test each commit on its own. Instead it cuts "milestones", which bundle consecutive commits, "typically … every 45 minutes during peak development time".
- **Stated:** "of the 5.5 Million affected tests that we analyzed for a time period, only 63K ever failed". Of all test executions, "only a tiny fraction (1.23%) actually found a test breakage (or a code fix)". 91.3% of targets passed at least once and never failed. 46,694 of the 115,160 targets that both passed and failed were flaky.
- **Stated:** In simulation, running only targets within a build-graph distance of 10 (or 6) from the change would have saved 42% (or 55%) of resources, "and we did not miss a single breakage or fix" in their dataset.
- **Inferred:** The transferable lesson is that most tests almost never fail, and that a test far from the change in the dependency graph rarely catches its breakage. The non-transferable parts are the infrastructure (milestones, distance cut-offs on a monorepo graph). A solo repo has no build graph deep enough to cut by distance.

### Meta predictive test selection

Source: "Predictive Test Selection", Mateusz Machalica, Alex Samylkin,
Meredith Porth, Satish Chandra. arXiv:1810.05286v2, 29 May 2019 (ICSE-SEIP
2019). https://arxiv.org/abs/1810.05286 , full text https://arxiv.org/html/1810.05286v2

- **Stated (abstract):** The learned strategy "reduces the total infrastructure cost of testing code changes by a factor of two, while guaranteeing that over 95% of individual test failures and over 99.9% of faulty changes are still reported". It selects "fewer than a third of the tests that would be selected on the basis of build dependencies".
- **Stated (§II, "Stabilization"), the safety net:** "Once every few hours, all tests are exercised on the most recent version of master branch. Tickets are created for failing tests." The paper adds: "Presence of the stabilization stage means the main goal of diff- and land-time testing is to boost developer productivity … rather than to reduce risk of buggy software being released." Selection "needs not be conservative" because of this stage.
- **Stated (§V):** Flaky failures were "about four times larger" than real failures in their sample. They de-flake by retrying, and train only on failures that reproduce.
- **Inferred:** The model needs a large history of real failures. At about 1% failing tests (TAP's figure) and a few hundred PRs a month spread over 17 repos, each repo would see too few failures to train on. The part that transfers is the architecture: a cheap, non-conservative pre-merge stage plus a full scheduled run on `main` that files tickets.

### Microsoft Test Impact Analysis

Source: "Speed up testing by using Test Impact Analysis (TIA)", Microsoft Learn,
Azure DevOps docs, last updated 2025-10-27.
https://learn.microsoft.com/en-us/azure/devops/pipelines/test/test-impact-analysis

- **Stated:** TIA selects "existing impacted tests, previously failing tests, and newly added tests".
- **Stated:** It has a "Safe fallback. For commits and scenarios that TIA can't understand, it falls back to running all tests … if the code commit contains changes to HTML or CSS files, it can't reason about them and falls back to running all tests."
- **Stated:** "TIA can be conditioned to run all tests at a configured periodicity. Setting this option is recommended."
- **Stated:** To check the selection, "Run TIA selected tests and then all tests in sequence … If T1 passes, check that T2 passes as well."

### Fowler: "The Rise of Test Impact Analysis"

Source: Paul Hammant, "The Rise of Test Impact Analysis", martinfowler.com,
first published 2017-08-07, revised 2017-08-22.
https://martinfowler.com/articles/rise-test-impact-analysis.html

- **Stated:** TIA builds a map from production source to tests out of per-test coverage, then runs the tests mapped to changed files. A home-grown version runs tests one at a time under coverage and commits the map as text.
- **Stated:** "everything that you test pre-integrate should immediately be tested post-integrate in the Continuous Integration (CI) infrastructure."
- **Stated (Google Testar, 2006):** It averaged "60..70% time savings". The page lists its drawbacks: savings are inconsistent when a widely used method changes, and "if test outcome depends … on some external input, such as resource files, the user needs to explicitly specify all these files". Its author later concluded that "running all tests with a high degree of parallelization is more reliable" when hardware is available.
- **Stated:** "nobody has ever built a suite of pure JavaScript tests where 'run them all' was not quick enough anyway" (author's opinion, 2017).

### Small-repo tools (official docs)

| Tool | Mechanism (stated) | Blind spot (stated) | Source |
|---|---|---|---|
| pytest-testmon | Records each test's dependencies with Coverage.py into `.testmondata`, then runs only affected tests. "Testmon always re-executes tests which failed last time." | "doesn't track changes of … static files (txt, xml, other project assets)" or "external services". Needs one full `--testmon` run first. | https://testmon.org/ |
| pytest `--lf` / `--ff` / `--nf` / `--sw` | Re-run only the last failures, or run failures first, new tests first, or stop at the first failure and resume. `--lfnf none` "runs no tests and exits successfully" when there are no known failures. | The cache is local state. The docs recommend `--cache-clear` "for invocations from Continuous Integration servers". | https://docs.pytest.org/en/stable/how-to/cache.html |
| Jest `-o`, `--changedSince`, `--findRelatedTests` | Tests related to changed files, by git or hg. | "requires a static dependency graph (ie. no dynamic requires)". | https://jestjs.io/docs/cli (v30.5) |
| Vitest `--changed [since]`, `vitest related` | "Run tests that are affected by the changed files" through the module graph. | "not the dynamic ones (e.g., `import(filepath)`)". `forceRerunTriggers` (default `**/package.json`, `**/vitest.config.*`, `**/vite.config.*`) makes `--changed` "run the whole test suite if the trigger is found in the git diff". | https://vitest.dev/guide/cli , https://vitest.dev/config/forcereruntriggers |
| Playwright `--only-changed [ref]` | Introduced in 1.46: "will also run all test files that import any changed files". | A test that reaches the app through a browser or URL, not an import, is not followed (**inferred**). Under Bun (1.65) `--only-changed` "does not follow imports". | https://playwright.dev/docs/test-cli , https://playwright.dev/docs/release-notes |
| Nx `affected` | Uses Git to find changed files, then the tasks whose declared `inputs` include them. Recommends setting the base "to the latest successful commit on the main branch". | Lock-file changes affect every task by default. A change to a widely shared project "selects most tasks". | https://nx.dev/docs/features/ci-features/affected |

Not opened: the Turborepo and Bazel docs. Fowler's article describes
Blaze/Bazel BUILD-graph selection second-hand. **Unverified** beyond that page.

**What they pair selection with (summary).** Google runs TAP post-submit on
every milestone. Meta runs a full stabilization pass every few hours. Microsoft
recommends a periodic full run and falls back to all tests on unknown files.
Fowler says to test post-integrate immediately. Nx sets its base to the last
green `main`. No source recommends selection without a full run somewhere
behind it.

## 2. GitHub Actions mechanics

Sources: GitHub Docs, all fetched 2026-11-17 (the pages carry no publication
date).

- **Path filters.** "Workflow syntax for GitHub Actions", https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax . **Stated:** "If at least one path matches a pattern in the `paths` filter, the workflow runs." PRs are compared with three-dot diffs. "If a push contains more than 1,000 commits, the workflow will **always** run". "If generating the diff times out, the workflow will **always** run". If the diff has "more than 3,000 files and the files the workflow filter matches are not in the first 3,000 … the workflow will **not** run."
- **Required-check pitfall.** "Troubleshooting required status checks", https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/troubleshooting-required-status-checks (redirects to `…/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks`). **Stated:** when a workflow is skipped by path or branch filtering or a commit message, "Associated checks stay in a 'Pending' state and block merging. Avoid requiring workflows that can be skipped." When a job is skipped by a conditional, "The job reports 'Success'". When a job depends on a failed job, "The dependent job is skipped and may not block merging. Use `always()` with `needs`". "Successful check statuses are `success`, `skipped`, and `neutral`."
- **Inferred, a defect-class warning:** these two rules mean that a "changed files" gate job whose output is empty or malformed silently turns every heavy job into a green skip. This is the repo's defect class 1 ("an absent or malformed answer read as a benign one", AGENTS.md, **checked**). The detector has to fail closed: when it cannot decide, it runs everything.
- **Concurrency.** "Control the concurrency of workflows and jobs", https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency . **Stated:** `group: ${{ github.head_ref || github.run_id }}` with `cancel-in-progress: true` "cancels in-progress jobs or runs on `pull_request` events only". `${{ github.workflow }}-${{ github.ref }}` scopes cancellation to one workflow. `cancel-in-progress` can be an expression, for example "not on a release branch".
- **Duplicate push + pull_request runs.** **Inferred** from "Events that trigger workflows" (https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows): `pull_request` runs on the PR merge ref ("`GITHUB_SHA` for this event is the last merge commit of the pull request merge branch"), and an unfiltered `push` runs on the branch head. Both fire for one agent push. Restrict `push` to `branches: [main]`. No GitHub page states the duplicate as a pitfall in those words.
- **Merge queue.** "Managing a merge queue", https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue . **Stated:** "available in any public repository owned by an organization, or in private repositories owned by organizations using GitHub Enterprise Cloud". Workflows "**must** use the `merge_group` event". The queue tests each PR "applied to the latest version of the target branch and any pull requests already in the queue". **Inferred:** repos under a personal account cannot use it. The alternative is "Require branches to be up to date", which re-runs CI after every rebase, or a full run on `main` after merge.
- **Timeouts and fail-fast.** Workflow syntax page. **Stated:** `jobs.<job_id>.timeout-minutes`: "Default: 360". `strategy.fail-fast` "will cancel all in-progress and queued jobs in the matrix if any job in the matrix fails. This property defaults to `true`."
- **Caching.** "Dependency caching reference", https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching . **Stated:** the `setup-*` actions for npm/Yarn/pnpm and pip/pipenv/Poetry "will create and restore dependency caches for you". A PR run can restore caches from its base branch, but a cache created by a PR "can only be restored by re-runs of the pull request". Entries unused "in over 7 days" are removed. The default limit is 10 GB per repo. **Inferred:** save caches from `push` to `main` so PRs restore them.
- **Scheduled runs.** Events page. **Stated:** "Scheduled workflows run on the latest commit on the default branch." They "can be delayed during periods of high loads … some queued jobs may be dropped". "In a public repository, scheduled workflows are automatically disabled when no repository activity has occurred in 60 days." **Inferred:** a nightly backstop on a quiet public repo goes dark without notice. Something has to check that it ran (a defect-class-2 risk).
- **Parallelism.** pytest-xdist, "Running tests across multiple CPUs", https://pytest-xdist.readthedocs.io/en/stable/distribution.html . **Stated:** `-n auto` uses physical cores. `--dist loadscope`/`loadfile`/`loadgroup` keep expensive fixtures in one worker. `worksteal` "should handle tests with significantly differing duration better". Jest `--shard=i/n` and Playwright `--shard current/all` split across machines (CLI pages above). **Inferred:** a standard hosted runner has few cores, so sharding across jobs pays only for suites of several minutes. Each extra job pays its own checkout and setup cost.

## 3. Tiering: presubmit, post-submit, nightly

Source: Software Engineering at Google, ch. 23 "Continuous Integration", written
by Rachel Tannenbaum, edited by Lisa Carey (O'Reilly 2020; free at
https://abseil.io/resources/swe-book/html/ch23.html).

- **Stated:** "which tests should be run on presubmit? Our general rule of thumb is: only fast, reliable ones. You can accept some loss of coverage on presubmit, but that means you need to catch any issues that slip by on post-submit, and accept some number of rollbacks."
- **Stated:** "we typically limit presubmit tests to just those for the project where the change is happening". "Most teams at Google run their small tests (like unit tests) on presubmit". Larger tests are either made hermetic or allowed on presubmit but "disable[d] aggressively when they start failing".
- **Stated:** "CI systems for smaller repositories or projects can avoid this problem [mid-air collisions] by serializing submits".
- **Stated (Takeout case study):** moving end-to-end tests from "after nightly deploy" to "post-submit within two hours … effectively cut the 'culprit set' by 12 times". Disabling a failing test by tagging it with a bug, with automated clean-up, kept the suite green "and still provide[d] confidence".

Fuzzing off the PR path. Source: ClusterFuzzLite, "GitHub Actions",
https://google.github.io/clusterfuzzlite/running-clusterfuzzlite/github-actions/ .

- **Stated:** PR mode is `mode: 'code-change'` with `fuzz-seconds: 600`. Batch fuzzing is `fuzz-seconds: 3600` on `cron: '0 */6 * * *'` and "allows a corpus of inputs to build up over time". Running batch fuzzing on every push to main is "not recommended". Corpus pruning runs daily. With a storage repo, PR fuzzing runs "only the fuzzers affected by the current change", determined "by using coverage reports". Continuous builds let PR fuzzing skip crashes that are not new: "If the crash is not novel, PR fuzzing will not report it."

Property tests. Source: Hypothesis "API Reference",
https://hypothesis.readthedocs.io/en/latest/reference/api.html .

- **Stated:** "The default max examples is `100`." There is a built-in `ci` profile, `derandomize=True, deadline=None, database=None`, which is active when the `CI` variable is set. Profiles can be replaced with, for example, `max_examples=1000`. "we have observed Hypothesis finding novel bugs after several million test cases."
- **Inferred:** use the same tests with two budgets: a small fixed budget on the PR and a large one nightly. That is ClusterFuzzLite's split applied to Python.

Tier assignment for this setup (**inferred**, from the sources above):

| Tier | Contents |
|---|---|
| Local seam (agent, pre-push) | Narrowed suites, fast and hermetic. pytest `--lf`/testmon or Jest/Vitest related tests in the inner loop only. |
| PR CI (required check) | The narrowed seam with fail-closed widening, lint, small CP-SAT instances, Playwright smoke spec(s), fuzzers at a short time budget or not at all. |
| Post-merge on `main` | The full seam. A failure files an issue or reverts. |
| Nightly or every 6 h | Full Playwright matrix, large CP-SAT corpora, Hypothesis at a high `max_examples`, batch fuzzing with corpus kept, quarantined tests, slowest-test and over-budget report. |

## 4. Test-suite reduction: when deleting tests is safe

### Minimisation evidence

Source: S. Yoo and M. Harman, "Regression testing minimization, selection and
prioritization: a survey", Software Testing, Verification and Reliability
22(2):67–120, 2012 (online 2010-03-11), DOI 10.1002/stvr.430. Read from the
author PDF at https://coinse.github.io/publications/pdfs/Yoo2010fk.pdf (the
Wiley page returned 403).

- **Stated:** In Rothermel et al.'s Siemens study, "the fault-detection capabilities of test suites were severely compromised. The reduction in fault-detection effectiveness was over 50% for more than half of 1000 test suites considered, with some cases reaching 100%." On the larger `space` program the average loss was 8.9% with the HGS heuristic and 18.1% with random reduction. Other studies (WHLM, WHLP) found no significant loss.
- **Stated:** "the question of evaluating the effectiveness of the test suite minimization technique is very hard to answer in general". The survey separates permanent minimisation from modification-aware *selection*. A "safe" selection technique is safe only in that every modification-traversing test is selected.

Source: L. Inozemtseva and R. Holmes, "Coverage is not strongly correlated
with test suite effectiveness", ICSE 2014, pp. 435–445, DOI
10.1145/2568225.2568271. Author PDF:
https://cs.uwaterloo.ca/~rtholmes/papers/icse_2014_inozemtseva.pdf (read from
the search-result excerpt of that PDF. The ACM page returned 403).

- **Stated:** "there is a low to moderate correlation between coverage and effectiveness when the number of test cases in the suite is controlled for". Coverage "should not be used as a quality target". SWE-at-Google ch. 11 says the same from practice (below).
- **Inferred:** "this test adds no unique coverage" does not prove that the test is redundant. It may be the only assertion on lines that other tests only execute.

### Google data on tests that never fail and flaky tests

- TAP: 91.3% of targets never failed (§1 above).
- Source: John Micco, "Flaky Tests at Google and How We Mitigate Them", Google Testing Blog, 2016-05-27, https://testing.googleblog.com/2016/05/flaky-tests-at-google-and-how-we.html . **Stated:** "about 1.5% of all test runs reporting a 'flaky' result". "Almost 16% of our tests have some level of flakiness". "about 84% of the transitions we observe from pass to fail involve a flaky test". The mitigations are re-running failures, marking a test flaky so it reports failure only after "3 times in a row", and automatic quarantine that "removes the test from the critical path and files a bug". Quarantine "could easily mask a real race condition".
- **Inferred:** "never failed" is a reason to run a test less often (TAP's goal). It is not a reason to delete it: a test that never fails may be guarding code that never changes.

### Mutation testing to find tests with no detection power

- Source: Goran Petrović and Marko Ivanković, "State of Mutation Testing at Google", ICSE-SEIP 2018, https://research.google/pubs/state-of-mutation-testing-at-google/ . **Stated:** a "diff-based probabilistic approach" that mutates only covered, changed lines and skips "arid" lines, and surfaces results in code review. Used "by 6,000 engineers … on all code changes they author or review".
- Source: Goran Petrović, Marko Ivanković, Gordon Fraser, René Just, "Practical Mutation Testing at Scale", arXiv:2102.11378v2, 2021-02-26, https://arxiv.org/abs/2102.11378 . **Stated:** mutation is "done incrementally, mutating only changed code during code review", with mutants limited "per line and per code review". It was evaluated with "more than 24,000 developers on more than 1,000 projects".
- Source: StrykerJS "Incremental", https://stryker-mutator.io/docs/stryker-js/incremental/ (read from the search-result excerpt of that page). **Stated:** `--incremental` "only runs mutation testing on the changed code", reusing earlier results. It does "not detect any changes you've made in files other than mutated files and test files", or dependency and env changes. `--force --mutate src/app.js:5-7` reruns a line range.
- **Inferred:** at small scale, mutation testing transfers as Google uses it. Run it on the diff, at review time, as evidence that a *new* test catches *the* bug. Do not run it as a whole-repo score.

**How people decide what is safe to delete (synthesis, inferred):** a test is a
deletion candidate when it adds no unique detection, meaning every mutant it
kills is also killed by a named "keeper" test. A test that is merely
never-failing, slow, or adds no unique coverage is not a candidate on that
fact alone. Retire a test that is flaky with no fix in sight from the PR path
(quarantine), but keep running it on a schedule.

## 5. Suite-size discipline

Source: Software Engineering at Google, ch. 11 "Testing Overview", written by
Adam Bender, edited by Tom Manshreck (O'Reilly 2020; free at
https://abseil.io/resources/swe-book/html/ch11.html).

- **Stated:** "small tests run in a single process, medium tests run on a single machine, and large tests run wherever they want". Small tests "aren't allowed to sleep, perform I/O operations, or make any other blocking calls". The sizes are "encoded as constraints the testing infrastructure can enforce", for example a security manager that fails small Java tests that open a network connection.
- **Stated:** "a mix of around 80% … narrow-scoped unit tests …; 15% medium-scoped integration tests …; and 5% end-to-end tests" (Google's version of Cohn's pyramid, "by test case count"). The antipatterns are the "ice cream cone" and the "hourglass".
- **Stated:** "The slower a test suite, the less frequently it will be run, and the less benefit it provides … tricks [parallelism, hardware] are eventually swamped by a large number of individually slow test cases." `sleep()`-based waits add "minutes of idle time"; poll instead. "Set appropriate performance goals and refactor slow or marginal tests."
- **Stated:** On coverage targets, "instead of treating 80% like a floor, engineers treat it like a ceiling".
- **Stated:** Large teams "isolate their large tests … running them only during the build and release process".

Slowest-test reporting and time limits (official docs):

- pytest: `pytest --durations=10 --durations-min=1.0` lists "the slowest 10 test durations over 1.0s long" (https://docs.pytest.org/en/stable/how-to/usage.html).
- Playwright: `--global-timeout`, `--timeout` (default 30 s), `--max-failures`/`-x`, `--fail-on-flaky-tests`, `--forbid-only` "Useful on CI" (CLI page).
- Jest: `--testTimeout` (default 5000 ms), `--bail` (CLI page).
- GitHub Actions: `timeout-minutes` per job and per step.
- **Checked:** this repo's `tests/all.sh` header already records per-suite CPU time against a `cpu_budget`. An overrun prints but "never fails the run (#1606)", and "The nightly backstop reports every such line." So a report-only budget and a nightly backstop exist here already.

## 6. Agent-written test bloat

What was found (all arXiv preprints. None is a first-party engineering blog):

- Roberto Milanese, Francesco Salzano, Angelica Spina, Antonio Vitale, Remo Pareschi, Fausto Fasano, Mattia Fazzini, "Human-Agent versus Human Pull Requests: A Testing-Focused Characterization and Comparison", arXiv:2601.21194, 2026-01-29, https://arxiv.org/abs/2601.21194 . **Stated:** 6,582 human-agent and 3,122 human PRs (AIDev dataset). Agent PRs show "nearly doubling the test-to-source line ratio". They are "more likely to add new tests during co-evolution (OR=1.79), whereas HPRs prioritize modifying existing tests". Test-smell differences are negligible. The HTML text warns of "a bias toward expanding test suites rather than evolving them" and calls for human direction "to prevent suite bloating".
- Roberto Milanese et al., "Testing with Coding Agents: A Large-Scale Comparison of Agent-Supported and Human-Authored Pull Requests", arXiv:2610.35297, 2026-10-26, https://arxiv.org/abs/2610.35297 . **Stated:** 114,134 PRs in 391 Java repos. Agent-supported PRs "add tests more often (odds ratios 1.50-1.58) and modify (0.70-0.76) and delete (0.51-0.77) them less often". Their relationship to test quality "remains uncertain". Same research group as the previous paper, so the two are not independent confirmation.
- Atish Kumar Dipongkor, Talank Baral, Wing Lam, Kevin Moran, "Test Coverage Analysis of Agentic Pull Requests", arXiv:2607.18057, 2026-07-20 (to appear at ICSME), https://arxiv.org/abs/2607.18057 . **Stated:** agents include tests in only 49.6% of code-changing PRs. Existing tests cover "only 27.0%" of agents' changed lines in Python. Agent-written tests raise coverage in only "22.5% of Python" Code+Tests PRs. Error-handling code is the most under-tested.
- Andre Hora and Romain Robbes, "Are Coding Agents Generating Over-Mocked Tests? An Empirical Study", arXiv:2602.00409, 2026-01-30 (MSR 2026), https://arxiv.org/abs/2602.00409 . **Stated:** "36% of commits made by coding agents add mocks to tests, compared with 26% by non-agents". The authors call for "guidance on mocking practices in agent configuration files".

**None found:** no first-party engineering organisation's post or doc on *limiting* agent test volume. Opened: the four arXiv abstract pages above. Seen only in search-result excerpts and not used as evidence because they are not primary: a vendor blog (testmuai.com "AGENTS.md as a Testing Contract"), a personal blog (worldprogramming.org), a skills-directory listing ("Test Audit"), engineered.at and dev.to posts. One search phrase was used: "engineering blog coding agent generated tests low value delete tests guidance CLAUDE.md AGENTS.md".

**Inferred controls** (from §4 and §5 applied to this evidence): (a) tell agents to extend or modify the existing test that owns a behaviour before adding a new file, since the measured bias is towards adding; (b) require each new test to be shown failing on the pre-fix code or on a diff mutant, which is Google's review-time mutation idea and repo defect class 3; (c) prefer real collaborators over mocks (SWE-at-Google ch. 11 on mock abuse; Hora & Robbes); (d) periodically prune with a mutation-backed "keeper" rule, not a coverage-only one.

## What transfers to a solo, agent-driven, multi-repo setup

Ranked by expected saving per unit of risk. Savings are estimates. The cheap
way to measure each one is the Microsoft T1/T2 check: run the narrowed set and
the full set on the same commit for a week, and count the misses.

1. **Guarantee the full backstop, then narrow PRs harder.**
   *Mechanism:* the PR check runs `tests/all.sh --changed origin/main`. A `push` to `main` runs the full seam, and a nightly cron runs it again. A red `main` opens an issue or reverts the commit.
   *Saving:* PR CI time scales with the directories touched, not the repo size. Probably the largest single saving on repos with many independent directories (TAP's 42–55% and Meta's 2× are the large-scale analogues).
   *Risk:* a cross-directory or non-code dependency is missed before merge.
   *Safety net:* Meta's stabilization pattern, the full run on `main`. Plus the narrowing must fail closed: an unknown file type, a lock file, CI config or the seam script itself widens to the full run (Microsoft TIA fallback, Vitest `forceRerunTriggers`). Also needed is a check that the nightly actually ran, because public-repo crons die after 60 days idle.

2. **GitHub Actions hygiene: cancel, dedupe, cap, cache.**
   *Mechanism:* `concurrency: {group: ${{ github.workflow }}-${{ github.head_ref || github.run_id }}, cancel-in-progress: true}`; `push` only on `main`; a `timeout-minutes` matched to each job; `setup-python`/`setup-node` caching saved from `main`.
   *Saving:* agents push several times per PR, so every superseded run is cancelled, and the duplicate `push` run disappears. A hung job stops at minutes, not 360.
   *Risk:* low. A cancelled run on `main` is avoided by keying on `head_ref` and falling back to `run_id`.
   *Safety net:* the required check still has to pass on the final head SHA.

3. **Never put a workflow-level `paths` filter on a required check. Gate inside one aggregator job that fails closed.**
   *Mechanism:* one always-run workflow. A detect job computes the affected suites, and the heavy jobs are skipped with `if:`. A final `needs:` + `if: always()` job is the only required check, and it fails if any needed job failed or if detection produced no answer.
   *Saving:* the same skip savings as path filters, without PRs stuck in "Pending".
   *Risk:* a skipped job reports "Success", so an empty detection output looks green (defect class 1).
   *Safety net:* empty or unparsable detection means run everything. The full post-merge run is behind it.

4. **Move slow and long-tail tiers off the PR path, on budgets.**
   *Mechanism:* Playwright full matrix, large CP-SAT instances, batch fuzzing (ClusterFuzzLite-style 3600 s every 6 h with a stored corpus), and Hypothesis with a high `max_examples` all go nightly. The PR keeps a smoke spec, small solver instances, a 0–600 s affected-fuzzer budget, and the `ci` Hypothesis profile.
   *Saving:* the slowest suites stop multiplying by PR count.
   *Risk:* detection is delayed by up to a day, and the culprit set grows to a day's merges.
   *Safety net:* nightly failures file issues. A larger culprit set means bisecting a day's commits. Takeout's numbers show cadence trades directly against culprit-set size, so run every few hours if a day is too coarse.

5. **Enforce time budgets and report the slowest tests.**
   *Mechanism:* keep the per-suite CPU budget (**checked**: it exists and is report-only), and add `pytest --durations=10 --durations-min=1.0`, Playwright `--global-timeout`, and the Jest/Vitest timeout into the nightly report. Write new tests as Google "small" tests (no sleep, no network).
   *Saving:* this prevents creep rather than cutting today's cost. Google: slow tests eventually "swamp" parallelism.
   *Risk:* a noisy verdict on a loaded box (the reason #1606 made overruns non-failing).
   *Safety net:* a report-only budget plus a human or agent ticket for repeat offenders.

6. **Quarantine flaky tests with tracking. Never use silent retries.**
   *Mechanism:* a test that flakes is moved off the required check with a linked issue and an expiry, and still runs nightly. Playwright `--fail-on-flaky-tests` makes a retry-passed test visible.
   *Saving:* removes the false-red reruns that eat agent turns (at Google, 84% of pass-to-fail transitions involved a flaky test).
   *Risk:* masks a real race (Micco).
   *Safety net:* the nightly run of quarantined tests, plus the Takeout pattern of auto-prompting clean-up when a quarantined test has passed long enough.

7. **Limit agent test bloat at the source.**
   *Mechanism:* an AGENTS.md rule to extend or modify the existing owning test before adding new ones, and a review requirement that a new test is shown failing on the pre-change code or a diff mutant (StrykerJS `--incremental --mutate file:lines` for JS; mutate the changed lines by hand or with a tool for Python). An occasional pruning pass deletes only tests with a named keeper.
   *Saving:* slows suite growth. Preprints show agents add tests more often and test-to-source lines nearly double.
   *Risk:* deleting a test that was the only real assertion. Minimisation lost over 50% detection in many Siemens suites.
   *Safety net:* the keeper-plus-mutation rule, and coverage compared per file, not in aggregate.

8. **Fine-grained impact tools in the agent's inner loop only.**
   *Mechanism:* pytest-testmon or `--lf`, `jest --findRelatedTests`, `vitest --changed`, `playwright test --only-changed=origin/main` while iterating. The seam stays the merge gate.
   *Saving:* faster agent iterations. Little CI saving.
   *Risk:* each tool misses non-import dependencies (testmon: static files; Jest/Vitest: dynamic imports; Playwright: anything not imported).
   *Safety net:* the seam and CI run regardless.

**Does not transfer (and why, inferred):**

- *Machine-learned predictive selection* (Meta). It needs a large history of real failures, and a few hundred PRs a month over 17 repos at about 1% failure rates does not supply one.
- *Bazel/Blaze BUILD-graph selection and TAP distance cut-offs.* Maintaining BUILD files costs more than it saves at this size. Nx `affected` is worth it only inside a JS monorepo that already uses Nx.
- *Merge queue.* Unavailable on personal-account repos per GitHub's docs. Serialising merges, as SWE-at-Google ch. 23 suggests for small repos, plus a post-merge full run covers the mid-air-collision case.
- *TAP milestone batching as pre-merge policy.* Its small-scale analogue is the post-merge and nightly full run in item 1.
- *Organisation-wide flake-classification services and pH-style dashboards.* A nightly report file does the job for one person.

Not covered: Turborepo and Bazel docs were not opened. Python mutation tools
(mutmut, cosmic-ray) were not opened. No measurement was made on the 17 repos.
