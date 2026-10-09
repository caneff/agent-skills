# Running only the tests a change impacts, 2026-10-09

Question (Chris): can this repo's CI and test runs execute only the tests a
change impacts?

Short answer: they already do, by top-level directory. `tests/all.sh
--changed <base>` has been the merge gate's narrowing since #1415
(2026-10-04). Over the last 200 first-parent commits it would have narrowed
89% of them, to a median of 21 of 104 suites. The selector can miss impacted
suites in four ways, all found by reading the code: Python modules imported
across directories through `sys.path.insert`, shell suites that read or
source files in another directory, a `tests/` helper sourced by other
directories' suites, and prose read across directories. The only full run
that covers those misses is the one at the end of a `drain` run. A merge made
through `/implement` outside drain gets no full run. The fixes below need no
new dependency.

## Method

- Read in full: `tests/all.sh`, `burndown/references/closure.md`, the
  `drain/drain.py` functions `seam_cmd`, `run_in_scratch_tree`, `seam`,
  `full_run` and their call site, `implement/SKILL.md` § Review step 3 and
  § The merge step 3 (plus the slice paragraph), the CI section of
  `flow/claude/WORKFLOW.md`, `docs/agents/defect-classes.md` classes 1 and 2,
  and issue #1415's body (`gh issue view 1415`).
- `ls .github` printed `No such file or directory`, so there is no GitHub
  Actions workflow. `flow/claude/WORKFLOW.md` § CI says why: "CI is local,
  not GitHub Actions ... the Actions budget ran out on private repos."
  `git config land.testcmd` here reads `bash tests/all.sh`.
- I ran two measurements on this box (32 cores by `nproc`, default
  `TESTS_JOBS` = 32, load average about 5 at the start), both on `main` at
  553d0df9:
  - `bash tests/all.sh --changed HEAD~1` (the diff was
    `create-lmd-page/SKILL.md` and `create-lmd-page/skill_test.py`): 15
    suites, all passed, 9.6 s wall, 6.3 s user + 5.6 s sys.
  - `bash tests/all.sh` (full): 104 suites, all passed, 1:39.9 wall,
    248.7 s user + 145.6 s sys. The costliest suites by CPU:
    `flow/lane/Cargo.toml` 103.9 s (marked serial, so it runs alone after
    the concurrent ones), `flow/install.test.sh` 100.9 s,
    `drain/drain_test.py` 49.5 s. Every other suite took under 9 s.
- I did not use `~/.cache/drain/full-suite.log` for timing. drain writes it
  to the same path for every repo (`os.path.join(ctx.log_dir,
  "full-suite.log")`), and the copy there now is a `twitch-rules-scroller`
  `node --test` run from 2026-10-08. `last-green-caneff__agent-skills` reads
  10ffd0a8 (2026-10-08 13:18), 7 commits behind HEAD. My green full run
  above did not update it.
- Selection over history: a scratchpad script ran `scope_changed`'s rules
  against each of the last 200 first-parent commits' own diffs
  (`git diff --name-only --no-renames c^1 c`). It used **today's** suite
  directories for every commit, so it approximates what `--changed` would
  select now. It does not reproduce what ran then.
- Cross-directory reads: I grepped every suite file outside `tests/` for
  `$here/../<dir>/`, for root-relative paths and for `sys.path.insert(...,
  "..", ...)` in tracked `.py` files, then opened each hit. This is a grep
  over the suite files and the modules they load directly. It is not a
  trace of what each suite opens at run time (no `strace` on this box), so
  the list of misses below is a floor, not a census.
- Outside sources: each page was opened once and is listed in § Sources.
  Page content was treated as data.

## Part A: what the repo does today

### How `--changed <base>` picks

`scope_changed` in `tests/all.sh` reads `git diff --name-only --no-renames
"$base...HEAD"`, a three-dot diff from the merge base, and maps each changed
file to its first path component. The full suite runs when any changed file:

- is `tests/all.sh` itself,
- sits at the repo root (`AGENTS.md`, `CONTEXT.md`, `GLOSSARY.md`,
  `.gitignore`, `.skill-lock.json` ...), or
- sits under a top-level directory that owns no suite (`to-tickets/`,
  `research/`, `ask-matt/` ...): nothing says which suites cover it.

Otherwise it keeps every suite under the touched top-level directories,
every suite under `tests/`, and any suite at the root (`filter_dirs`). An
unreadable diff (a bad ref) exits 2 and runs nothing, rather than selecting
nothing and passing (`tests/changed.test.sh` covers this, along with the
narrowing, the `tests/all.sh` widening, serial suites and the CPU budget).

The granularity is the **top-level directory**, never the file. A change to
`flow/hooks/x.sh` runs all 26 `flow/` suites, the 104-CPU-second Cargo crate
and the 101-CPU-second install test among them.

### Who calls it, and with what

| Caller | Command | When |
|---|---|---|
| Worker, `implement/SKILL.md` § Review step 3 | `bash tests/all.sh --changed origin/<default>` after `git merge origin/<default>` | Once per ticket, just before "PR up" |
| Slice worker, `implement/SKILL.md` (the slice paragraph above § Review) | `bash tests/all.sh --changed origin/spec-<p>` | Once per slice |
| Controller, `implement/SKILL.md` § The merge step 3 | the same `--changed origin/<default>`, in a scratch worktree of `origin/<default>` with the PR head merged in | Only when `origin/<default>` moved past the worker's base |
| `drain/drain.py` `seam()` | `land.testcmd`. When that is exactly `bash tests/all.sh` it appends `--changed <default>` | Per bundle, only when main is not an ancestor of the PR head |
| `drain/drain.py` `full_run()` | `land.testcmd` unchanged, so the full suite | Once after the last bundle of a drain run that merged something. A red run stops drain and names the merges since `last-green-<repo>` |
| `flow/lane` `implement-dispatch` | writes "run the seam narrowed with --changed origin/spec-{spec}" into a slice brief | Slice dispatch |

No caller runs the full suite except `drain`'s `full_run`. A ticket merged
through `/implement` outside drain is only ever tested narrowed.

### Measured: how much narrowing buys

Over the last 200 first-parent commits, using today's suite map:

| Outcome | Commits |
|---|---|
| narrowed | 178 (89%): median 21 suites, min 14, max 79 |
| full: a root file changed | 11 (`CONTEXT.md` 3, `GLOSSARY.md` 2, `.skill-lock.json` 2, `AGENTS.md`, `CODING_STANDARDS.md`, `.gitignore`, `.extra-skills.json` 1 each) |
| full: a directory with no suite changed | 10 (`ask-matt` 3, `to-tickets` 2, `extract-coding-standards` 2, three others 1 each) |
| full: `tests/all.sh` changed | 1 |

The suite count overstates the saving. Wall time is set by the slowest
suites, and 64 of the 200 commits touch `flow/`, which selects the Cargo
crate and the install test. That pair makes up most of the full run's
100 s. A narrowed run that avoids `flow/` takes about 10 s (measured once,
above). One that touches `flow/` costs close to a full run. I did not time a
`flow/` narrowed run.

### What `closure.py` is, and is not

`burndown/closure.py` (#1478, 9cd2b8e2, "resolve Python imports as include
edges") answers a different question: which files a **ticket** would
regenerate, so that burndown can clump tickets that collide. It is not wired
into test selection, and four of its own rules stop it from serving as a
test selector as it stands:

- It follows only what `AGENTS.md` § Include closure declares, and this repo
  declares `None`, so here it runs in `no-include-graph` mode.
- It goes one hop and only backwards ("the target files plus every file that
  includes one of them"). Test impact needs the transitive reverse closure.
- Its `python imports` directive resolves `import a` against the importing
  file's directory or the repo root, "only one base is tried", and
  `spec_from_file_location` loads "are not read". This repo's cross-directory
  imports go through `sys.path.insert(0, ".../../burndown")` and the like, so
  `import frontier` in `drain/drain.py` would look for `drain/frontier.py`
  and drop out as unresolved.
- It reads no shell `source`/`.` lines and no file paths a test opens.

Its scan discipline is the part worth reusing: it fails closed on a file it
cannot read, and it never runs anything empirically.

### Where selection misses an impacted suite

Each item below was read in the source and checked against `filter_dirs`'s
rule (the kept-label lists come from `bash tests/all.sh --list` piped through
the same awk filter). None was reproduced as a real red-on-main incident. I
found no record that one has happened, and I did not look through drain's
history for one.

1. **Python imports across directories via `sys.path`.**
   `all-audits/harness/auditlib.py` and `pagelib.py` are put on `sys.path`
   by `crap-audit/audit.py`, `dead-code/audit.py`,
   `docstring-coverage/audit.py`, `duplication/audit.py`,
   `error-handling/audit.py`, `landed/generate.py`, `mutation-audit/audit.py`
   and `test-audit/audit.py`. A diff touching only `all-audits/` keeps 0 of
   those 8 directories' 13 suites. `drain/drain.py` imports
   `burndown/frontier.py`, and a `burndown/`-only diff keeps 0 `drain/`
   suites. `implement/fix_check.py` imports `burndown/runfile.py` and
   `docs/research/review_ledger.py`, and `implement/sidecar_name_test.py`
   imports `burndown/counts.py` and `runfile.py`. A `burndown/`-only diff
   keeps 0 `implement/` suites.
2. **Shell suites reading another directory's files.**
   `burndown/merge-tail.test.sh` reads `$here/../implement/SKILL.md`, and an
   `implement/`-only diff does not keep it.
   `burndown/blocked-by-grammar.test.sh` reads
   `$here/../docs/agents/issue-tracker.md`. `docs/` owns suites (the
   `docs/research/*_test.py` ones), so a `docs/`-only diff narrows to those
   and skips it. Its other read, `../to-tickets/SKILL.md`, is safe because
   `to-tickets/` owns no suite and so widens to the full run.
3. **A `tests/` helper sourced by other directories.** `tests/fixture-identity.sh`
   is sourced by `multi-axis-code-review/diff-capture.test.sh`,
   `sha-list.test.sh`, `witness-check.test.sh` and
   `mutation-audit/witness.test.sh`. A diff to that file maps to `tests/`,
   which keeps only `tests/` and root suites. Only `tests/all.sh` itself
   widens.
4. **Prose read as data.** 65 of the 104 suite files mention a `*.md` path,
   which is a rough upper bound on how many suites read prose, from a grep.
   Where the prose sits in the suite's own directory or at the root, it is
   covered. Where it sits in another suite-owning directory, it is the
   item 2 shape.
5. **Uncommitted work.** The diff is `$base...HEAD`, so edits not yet
   committed never widen the selection. That is harmless at the merge gate,
   which runs on commits, and misleading in a worker's inner loop.
6. **Rust.** `flow/lane` is the only crate, and its one `include_str!`
   pulls from `flow/lane/hooks/`, inside the crate's own top-level directory. No miss there
   today. A second crate in another directory would be a new instance of
   item 1.

**Defect class 1 shape** (`docs/agents/defect-classes.md`, "could this
success have been produced by the thing not running at all?"): a narrowed
green ends `15 suites passed`, the same line format as a full green
`104 suites passed`. Nothing on that line says 89 suites were not run. The
scope line `changed suites: create-lmd-page + tests` is printed above it, but
a reader or a log scraper keyed on the last line cannot tell a narrowed pass
from a full one. An empty selection cannot happen today, because `tests/`
always contributes 14 suites, and a run that selected nothing would print
`0 suites passed` and exit 0.

**Defect class 2 shape** ("a stated fallback with no mechanism"): #1415's
design leans on "the full suite runs once per `drain` run" to catch what
narrowing misses. That mechanism exists, but only for drain. The `/implement`
merge path names no full run, so the fallback has no carrier there.

## Part B: outside options

| Option | How it decides impact | Fit here | Cost and dependencies |
|---|---|---|---|
| **pytest-testmon** | Records, per test, the code it executed (through Coverage.py) plus env vars, Python version and package versions, and re-runs the tests whose recorded dependencies changed. It "doesn't track ... static files (txt, xml, other project assets)". It needs a full `--testmon` run first, and keeps state in `.testmondata`. | Poor. pytest is not installed here (`python3 -m pytest` reports "No module named pytest"). The 41 `*_test.py` suites run as scripts under `python3` (by a grep: 20 plain-assert, 19 `unittest`, 2 that mention pytest). It does not see bash, Rust or Markdown, and much of this repo's testing reads Markdown. Most suites here drive scripts as subprocesses, and whether testmon sees code run in a subprocess is my question, not something the page says. | New deps: pytest, pytest-testmon, coverage. A state file to keep. A runner change for 41 suites. |
| **pytest-picked** | Runs "tests from modified test files" and folders, read from `git status` (`--mode=unstaged`, the default) or from the branch (`--mode=branch --parent-branch`). | None. It selects test files that changed. It does not follow a source change to its tests, which is the whole question. | pytest plus the plugin. |
| **pytest `--lf`/`--ff`/`--nf`/`--sw`** | Last-failed, failed-first, new-first and stepwise, from pytest's cache. These are orderings and re-runs, not impact selection. With `--lf` and no known failures, the default `--lfnf=all` runs everything. | Inner-loop convenience at most, and only under pytest, which runs none of this repo's suites. | pytest. |
| **Pants** `--changed-since --changed-dependents=transitive` | Git diff, then the dependency graph Pants infers, then the targets that depend on the change, transitively. The docs recommend passing the merge base for presubmit. Changing a lockfile "will consider all users of *any* dependency changed, transitively." | The model fits exactly: transitive reverse dependencies from a diff. Adopting it means BUILD files and Pants owning test execution for Python, shell and Rust. I did not open Pants's shell or Rust backend pages, so how it would cover bash and Cargo here is unverified. | A build system adoption, so a new dependency of the largest kind. |
| **Bazel** with **bazel-diff** (Tinder) | Hashes every target's attributes and inputs at two revisions and reports the targets whose hash changed, which carries changes transitively through the graph. Bazel has no built-in revision-to-revision target diff (the README links bazelbuild/bazel#7962). The README warns that "an incorrect solution can result in a system you can't trust, because tests could be broken at a commit where you didn't select to run them." | Exact, but only for what is declared in BUILD files. A test reading `implement/SKILL.md` would need that file declared as a `data` input. The precision comes from declaring everything. | Bazel 8+, a JDK for Bazel, BUILD files everywhere. |
| **Buck2 Change Detector** (Meta, `btd`/`supertd`) | Dumps the Buck2 target graph before and after the change and reports targets that "transitively depend on the relevant changes", with a `depth` per target so huge fan-outs can be trimmed "at the risk of potentially allowing a breakage into the repo". | Same shape as Bazel: it needs a Buck2 build. | Buck2 plus this tool. It does not run the tests itself. |
| **cargo-nextest filtersets** | `rdeps(name)` selects "all tests in crates matching `name-matcher`, and all the crates that (possibly transitively) depend on" it. Selection is by crate. The filterset reference I opened shows no git-diff input. | Moot today: one crate, `lane`, so `rdeps` would select all of it. It would matter with several crates. It might also help the lane suite's serial marker, but that is my unverified guess. | `cargo-nextest` is not installed (`cargo nextest` gives "no such command"), so a new dependency. |
| **Predictive / ML selection**: Meta's *Predictive Test Selection*; CloudBees Smart Tests (formerly Launchable) | Meta learns from historical outcomes which tests to run per change. In production it cut testing infrastructure cost by half while still reporting "over 95% of individual test failures and over 99.9% of faulty changes". CloudBees ranks tests by "semantic similarity between the application source code and the test source code", does not use coverage, and by default "runs all tests" when its service is down or untrained. | Poor. Both rest on large historical outcome data. This repo has about 100 suites, a 100-second full run and few red runs to learn from. CloudBees is a hosted service. Its use-cases page also prescribes a "defensive run": "run the full suite of tests at some point later in your pipeline ... after a PR is merged". | A SaaS account, uploading code to a third party, and a CLI. Meta's system is a paper, not a product. |
| **Google TAP** (Memon et al., ICSE 2017) | The abstract reports work to control Google's CI test workload "without compromising quality". Finding: "very few of our tests ever fail, but those that do are generally 'closer' to the code they test". | Background only. It supports the idea that a near-dependency selector catches most breakage. | Not available. |
| **Shell selection** | No shell-specific test-impact tool turned up in what I opened. kcov measures "coverage ... for compiled languages, Python and Bash", which is the raw material for a testmon-style map of bash suites. | Building a selector on kcov is a project, not a flag. This was one README, not a survey: I searched for no other shell tool, so "none exists" is not established. | kcov is GPL-2.0 and not installed. |

## Part C: recommendation

**Keep the directory selector. Close its known holes with a derived
cross-directory edge map. Add a full run to the `/implement` merge path.**
At 100 s for the full suite on 32 cores, the full run is cheap enough to be
the safety net everywhere. Narrowing pays off mainly on non-`flow/` commits,
by about 90 s each.

1. **Derive cross-directory edges, do not declare them.** This step would
   carry no new dependency: bash plus a small stdlib Python scan, run in
   `scope_changed` before `filter_dirs`. Read every tracked suite and every
   `.py` it can load for three shapes: `sys.path.insert(..., "..", "<dir>",
   ...)`, `$here/../<dir>/...` or `"$root/<dir>/..."` paths, and
   `. "$here/../tests/<file>"` sources. Build a reverse map from the
   referenced directory (or the `tests/` file) to the referencing
   directories, and widen the kept set through it transitively. This repo's
   own closure doc names the reason to derive: prose typed by whoever wrote
   the test "is exactly what two workers collide over"
   (`burndown/references/closure.md`). Fail closed the way `closure.py`
   does: a suite or module the scan cannot read widens to the full suite.
   This catches items 1 to 3 above. It does not catch a path built at run
   time from variables. Item 6 below backstops that.
2. **Make a narrowed pass say so.** End a `--changed` run with `15 of 104
   suites passed (narrowed: create-lmd-page + tests)` instead of `15 suites
   passed`. This is a one-line `tests/all.sh` change, and it removes the
   class-1 reading of a narrowed green as a full one.
3. **Give the `/implement` merge path a full run.** The cheapest carrier is
   the controller's `§ The merge` step 3: run the full suite, not
   `--changed`, on the merged worktree. That adds about 90 s per merge.
   Another option is a full run on main after each merge (post-merge, off
   the critical path), recording `last-green-<repo>` as drain does, so a red
   run names the merges since the last green. Either closes the class-2
   gap. Choosing between them is a process change for Chris.
4. **Keep and extend the existing widen-to-full rules.** Root files, `tests/all.sh`
   and suite-less directories already widen. Also widen when a changed file
   is a `tests/` helper that a non-`tests/` suite sources, if step 1 is not
   built.
5. **Fix the shared `full-suite.log`.** drain writes every repo's full run
   to one path, so the agent-skills timing and failure output are gone as
   soon as another repo drains. Name it `full-suite-<repo>.log`, as
   `last-green-<repo>` already is. Strictly this is not test selection, but
   it is the evidence a full-run safety net leaves behind.
6. **A tripwire for the selector itself.** When a full run goes red on main,
   for each commit since the last green, compute what `--changed` would have
   selected and check whether the failing suite was in it. A failing suite
   outside the selection is a selector miss, and is worth filing as a
   defect-class instance. This turns misses from silent into counted.

**Not recommended now:** pytest-testmon and pytest-picked (pytest is not even
installed, and they do not see bash, Rust or prose), Pants/Bazel/Buck2 (a
build-system migration to save about 90 s a run), and ML selection (no data
to learn from, and a hosted service). cargo-nextest is worth a look only if
`flow/lane` splits into several crates. Each of these is a new dependency and
needs Chris's sign-off. None is added here.

**Cost of 1 to 3:** roughly 100 to 150 lines of bash and Python plus tests,
in `tests/all.sh` and `tests/changed.test.sh` (a fixture repo where
directory B's suite imports A's module and sources a `tests/` helper, so the
A-only diff and the helper-only diff must both select B), and an
`implement/SKILL.md` wording change for step 3. This size is my estimate,
not a measurement.

## What I could not verify

- Whether any of the misses above has ever let a red suite onto main. I
  found no incident and did not search drain's red-run history for one.
- Wall-clock time of a narrowed run that touches `flow/`. I measured only the
  `create-lmd-page` run and the full run, once each, on a box with a load
  average around 5.
- The simulation used today's suite directories for all 200 commits, so its
  percentages describe today's selector applied to past diffs.
- Pants's support for shell and Rust tests, and Bazel's native test-result
  caching. Neither page was opened.
- Whether any shell-test-selection tool exists beyond kcov's coverage. Only
  the kcov README was opened.

## Sources

Local (read this session): `tests/all.sh`; `tests/changed.test.sh` (by
grep); `burndown/references/closure.md`; `drain/drain.py` lines 70-82 and
595-700; `implement/SKILL.md` lines 285-300, 362-385, 795-805 and 860-880;
`flow/claude/WORKFLOW.md` § CI; `docs/agents/defect-classes.md`; issue #1415
via `gh issue view 1415 --repo caneff/agent-skills`; commit 9cd2b8e2's stat.

Outside, each opened once:

- testmon.org, "testmon: selects tests affected by changed files and
  methods" (project home page, undated), https://testmon.org/
- Ana Paula Gomes, pytest-picked README (GitHub, latest commit 2026-05-27),
  https://github.com/anapaulagomes/pytest-picked
- pytest-dev, "How to re-run failed tests and maintain state between test
  runs" (pytest docs, stable 9.x), https://docs.pytest.org/en/stable/how-to/cache.html
- Pants Build, "Advanced target selection" (docs version 2.33),
  https://www.pantsbuild.org/stable/docs/using-pants/advanced-target-selection
- Tinder, bazel-diff README (GitHub, latest commit 2026-10-06),
  https://github.com/Tinder/bazel-diff
- Meta (facebookincubator), Buck2 Change Detector README (GitHub, latest
  commit 2026-10-08), https://github.com/facebookincubator/buck2-change-detector
- nextest, "Filterset DSL reference" (undated),
  https://nexte.st/docs/filtersets/reference/
- Mateusz Machalica, Alex Samylkin, Meredith Porth, Satish Chandra,
  "Predictive Test Selection", arXiv:1810.05286 v2, 2019-05-29,
  https://arxiv.org/abs/1810.05286
- Atif Memon, Eric Nickell, John Micco, Rob Siemborski, Zebao Gao (as the
  page lists them), "Taming Google-Scale Continuous Testing", ICSE '17
  (2017), https://research.google/pubs/taming-google-scale-continuous-testing/
- CloudBees, "How CloudBees Smart Tests select tests" (docs, undated),
  https://docs.cloudbees.com/docs/cloudbees-smart-tests/latest/features/predictive-test-selection/how-we-select-tests
- CloudBees, "Use-cases for Predictive Test Selection" (docs, undated),
  https://docs.cloudbees.com/docs/cloudbees-smart-tests/latest/features/predictive-test-selection/use-cases-for-predictive-test-selection
- Simon Kagstrom, kcov README (GitHub, latest commit 2026-09-30),
  https://github.com/SimonKagstrom/kcov
