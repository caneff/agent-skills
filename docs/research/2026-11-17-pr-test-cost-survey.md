# Per-PR test cost across the active repos: survey (2026-11-17)

Question: Chris believes every active repo carries heavy test bloat: too many
tests, too much run per PR, too much time spent being safe. Is that true, where
does the time go, and what can be cut without losing real protection?

Companion note: `2026-11-17-pr-test-cost-reduction.md` (what the literature and
the GitHub docs say). This note is the survey of our own repos.

Method: five read-only survey agents, one per repo group, on 2026-11-17. The
box sat at a 1-minute load near 40, so **no agent ran a test suite**. Every
timing comes from GitHub run records, `job-run` logs or figures already written
in a repo, and is marked as such in the appendices. Savings are estimates
unless an appendix says measured. The controller spot-checked these against
`gh` afterwards: the sudokupad-scripts run total (1,328 against the survey's
1,325), grid-hunts and sudokumaker-custom-constraints 30-day run counts (267
and 146 against 268 and 147), gridfind's archived flag, the missing
`workflow=ci.yml` on the sudokumaker-custom-constraints line of
`flow/backstop-repos`, and the state of every ticket named below.

## Verdict

The belief is half right.

- **Right:** three repos add test lines at 3 to 4 times the rate of code lines,
  and the full local gate runs about twice per PR (worker, then controller) on
  an overloaded box.
- **Wrong:** GitHub CI minutes are not the cost. Most repos are public (free
  minutes) and most CI jobs take under a minute. Deleting tests would move
  wall-clock very little. Selection, reruns and a handful of single hot spots
  hold nearly all the time.
- **Not seen:** a recorded case of the bulk unit tests catching a behaviour
  regression is rare in every sample. The failures on record are mostly
  flakes, load timeouts, wording checks and infrastructure.

## Per repo

| Repo | Tests | Test:code growth, recent PRs | Biggest cost |
|---|---|---|---|
| agent-skills | 153 suites, 2,775 cases | 1.13 (40 PRs) | `drain/drain_test.py` stretches every run to 16–21 min; `--changed` selects 135 of 153 suites; gate runs about twice per PR |
| sudokupad-scripts | 1,919 unit + 1,678 live | 3.43 (40 PRs) | Full local Playwright suite, 5.4 min median, 7 of 11 full runs red under load; PR fuzz 5 min with 1 real catch in 98 runs |
| penpa-edit | 1,060 files, most are data | 3.2 (40 PRs) | Engine safety net on every PR (14.8 min median); 2.7 CI runs per PR; 428 min of superseded runs |
| twitch-rules-scroller | 205 files, about 3,600 cases | about 4 (20 PRs) | Volume only. No CI. 12 reverts were regressions only the live end-to-end run catches |
| grid-hunts | 79 suites | not the issue | Non-`.md` files under `docs/research` widen to all suites: 128 of 149 full runs |
| sudokumaker-custom-constraints | small | not the issue | Narrowed floor of about 3.5 min; nightly backstop repeats CI's nightly locally (214 min a month) |
| second-brain-v2 | 363 cases, 18 s | 1.8 (20 PRs) | Daily vault autocommits each run the full check |
| sudokupad-art | about 1:1 | 0.7 (20 PRs) | 31 s of a 49 s suite is Chromium render tests |
| sudoku-kit, visual-teach, research-queue, mediawiki-analytics, lmd-archive, drills, brain | small | n/a | Nothing to cut |
| career-ops | n/a | n/a | Actions disabled; 26 inherited workflow files; `AGENTS.md` still claims CI on every PR |
| gridfind | n/a | n/a | Archived 2026-10-12; `REPOS.md` still lists it as active |

## What can be done, ranked by leverage

1. **Stop running the gate twice per PR.** The controller's rerun repeats the
   worker's run (and, where CI is a required check, repeats CI). It lives in
   the implement skill, so one change reaches every repo. Open ticket:
   agent-skills #1949 (drain: skip the merge rerun when the worker's tested
   sha is the head). Protection given up: none when the tested sha is the
   head.
2. **Fix the five hot spots.** Each is one change in one repo.
   - agent-skills: profile `drain/drain_test.py` on a quiet box. Up to 12–14
     min per run; the cause of the 11-16 slowdown is unproven (code or load).
   - grid-hunts: stop `docs/research` paths widening the run, except the
     three that finder code references. About 4.4 min per research push.
   - penpa-edit: #280 (CI: safety net only on engine changes, live split over
     four runners, nightly full seam) has merged; widen its skip rule to
     "cannot reach `index.html`" (25 of 40 PRs skip instead of 15) once the
     asset reachability is checked.
   - sudokumaker-custom-constraints: add `workflow=ci.yml` to its line in
     `flow/backstop-repos`.
   - sudokupad-scripts: run the full live suite nightly on GitHub; workers
     run changed files only.
3. **Make the narrowed mode narrow.** agent-skills (drop false edges, link by
   file); sudokumaker-custom-constraints (42 of 115 runs selected every
   suite); penpa-edit (`AGENTS.md` has no Narrowed line at all). The backstop
   is the nightly full run, which the companion note ranks first: narrow PR
   runs are only safe behind a full run that is known to have happened.
4. **Actions hygiene.** `cancel-in-progress` on PR runs (penpa-edit,
   grid-hunts: 56 of 173 push runs superseded); `push` only on `main`
   (sudokupad-scripts: 474 duplicate runs); path-filter second-brain-v2's
   `check.yml` push trigger. No protection given up.
5. **Move slow tiers off the PR path.** Make the sudokupad-scripts PR fuzz
   advisory (keep the nightly fuzz, which found real bugs); gate
   sudokupad-art's render tests on renderer changes; move spec closing tests
   to nightly.
6. **Curb test growth at the source.** The same artefact shows up in three
   repos: per-spec closing-test files that stay after the spec closes
   (twitch-rules-scroller 17 files, sudokupad-scripts 23 files,
   sudokumaker-custom-constraints 14 tests on every run). They come from the
   implement-spec flow, so the retire-on-close rule belongs there. Add a
   review check on test-to-code growth, and require a new test to be shown
   failing on the old code. Two prose-wording tests added 11-16
   (`implement/merge_rules_test.py`, `implement-spec/skill_md_test.py`) are
   reported as against the ruling in agent-skills #1414 (test-audit: flag
   prose-assertion tests, then cut every test the audit says to cut); the
   controller has not read those two files.
7. **Quarantine named flakes.** grid-hunts
   `test_lazy_connectivity_cuts_return_a_connected_shape` (5 of 8 CI
   failures); penpa-edit "top bar on a laptop screen" (5) and the Settings
   focus test (2); sudokupad-scripts attack 78 (5 of 16 runs on its #1005).
8. **Record what the next survey needs.** Wall seconds per suite and kept run
   summaries. Per-suite times, gate runs per PR and "has this suite ever
   failed" could not be measured anywhere.
9. **Housekeeping.** Drop gridfind from `REPOS.md`; delete career-ops'
   inherited workflows or correct its `AGENTS.md`.

## Doc-versus-code contradictions (Chris's to rule on)

- grid-hunts `AGENTS.md:52-55` says to run the full gate serially before
  every commit; the implement skill runs the narrowed one.
- sudokumaker-custom-constraints `AGENTS.md` says every merge reruns
  `check-full`; the skill and the run log show only narrowed runs.

## Not measured

- Any suite's wall time on an idle box.
- Gate runs per PR, exactly: workers' direct runs leave no record.
- Whether any suite has never failed.
- Agent time spent investigating load-caused failures, which is probably the
  largest hidden cost and appears in no log.

## Appendices

The five survey reports follow unedited apart from heading depth. Each
separates verified from not verified and cites the command or file:line per
fact.

### Appendix: agent-skills

#### Test-cost survey: caneff/agent-skills (read-only), 2026-11-17

Repo state: `/home/caneff/.agents/skills` at `6232e30f` (main). Nothing in the repo was
edited. Helper scripts and raw outputs are in this scratchpad (`widen.py`, `edges.py`,
`hist.py`, `prsel.py`, `jobs.py`, `edges.txt`, `jobs.txt`, `cpu1900.txt`, `prs.json`).

Bottom line: the problem is not mainly too many tests. Wall-clock per run comes from
three things:
(a) one long-pole suite, `drain/drain_test.py`;
(b) a `--changed` mode that selects 85-100% of suites on almost every PR, so in practice
there is no narrowed run;
(c) the gate running roughly twice per PR, and about 2N+2 times for an N-slice spec.
Deleting test files would barely move any of these.

---

##### 1. Inventory (verified unless marked)

| Fact | Value | Evidence |
|---|---|---|
| Suites discovered by `tests/all.sh` | **153** | `bash tests/all.sh --list` (0.03 s, run) |
| by kind | 59 `*.test.sh`, 90 `*_test.py`, 1 Cargo (`flow/lane`), 3 mod plugins | same list, grep by suffix |
| by top dir | flow 36, tests 27, implement 13, multi-axis-code-review 10, docs 10, implement-spec 9, all-audits 8, test-audit 7, ... | `awk -F/ '{print $1}' list.txt \| uniq -c` |
| Python test functions | **2,175** `def test_` | grep over `*_test.py` |
| Rust `#[test]` | **528** (in-file `mod tests` plus `flow/lane/tests/`) | `git grep '#\[test\]' -- '*.rs'` |
| TS tests | 72 `test(`/`it(` | grep over `*.test.ts` |
| Shell suites | 59 files (case count not reliably greppable) | |
| Test LOC (sh/py/ts/rs test files, `tests/`, fixtures) | **49,342** | `git ls-files` + `wc -l` |
| Non-test code LOC (py/sh/rs/ts/js/mjs) | **54,191**, which includes about 1,528 lines of Rust in-file tests | same |
| Markdown LOC | 41,278 | same |
| `# all.sh: repo-wide` suites | **2**: `test-audit/assertion-free-gate.test.sh`, `tests/retired_name_test.py` | head-20 grep over every suite |
| `# all.sh: serial` suites | **1**: `flow/lane/Cargo.toml` | same |

Growth, measured by snapshotting `main` and classifying files with today's naming rules.
The 09-01 test count is low partly because older tests were named differently, so treat
that row as a floor:

| date | test files | test LOC | code files | code LOC |
|---|---|---|---|---|
| 2026-09-01 | 15 | 634 | 55 | 23,195 |
| 2026-10-01 | 143 | 31,534 | 105 | 41,622 |
| 2026-10-15 | 167 | 37,934 | 132 | 49,894 |
| 2026-11-01 | 173 | 39,609 | 134 | 50,793 |
| 2026-11-17 | 213 | 49,342 | 157 | 54,191 |

Since 10-01, test LOC grew by 17.8K and code LOC by 12.6K. Over the last 40 merged PRs,
**test lines added / code lines added = 5,447 / 4,824 = 1.13**, plus 318 Markdown lines
(from `prs.json`). Five of those 40 PRs added tests with zero code lines; their "code" was
a SKILL.md or template.

##### 2. What a PR actually runs

**Selection rules** (`tests/all.sh:13-21, 73-112`; `tests/suite-edges.py`). A run keeps:
- the suites under each touched top-level directory;
- all 27 `tests/` suites;
- the 2 repo-wide suites;
- the transitive closure of the cross-directory edges.

It widens to the **full** set when the diff touches any of these:
- `tests/all.sh` itself;
- a file at the repo root;
- a top-level directory that has no suites (for example a SKILL.md-only skill such as
  `audit-instructions/`, `setup-python-repo/`, `triage/` or `sm-link/`);
- a failed edge scan.

**The edge closure covers almost everything** (verified with `widen.py`, which uses the
repo's own `edges()`/`widen()`):
- Touching any one of flow, implement, implement-spec, multi-axis-code-review, docs,
  landed, mutation-audit or all-audits selects **135/153** suites. `common` selects 143,
  `tests` 139, `visual-teach` 136.
- Only leaf skills (backstop, drain, wizard, the small audits) narrow, to 30-37 suites.
  The floor is 27 `tests/` + 2 repo-wide + the leaf's own.
- `suite-edges.py` finds 66 edges (`edges.txt`). Some are real: `flow/claude/hooks/worker-dirty-stop.sh:21`
  sources `implement/pre-report-gate.sh`, `implement/codex-usage-gate.py:70` and
  `multi-axis-code-review/claude-usage-gate.py:26` load flow helpers, and
  `drain/drain_test.py:1053` reads `flow/lane/.../implement_dispatch.rs`.
- Several are false positives from the 3-line span heuristic: `flow -> docs`
  (`flow/claude/pointer_reads_test.py:20`), `implement-spec -> docs` (comments at
  `frontier.py:43`, `loop_test.py:272`), `backstop -> implement/implement-spec/flow`
  (`backstop.py:101,120`), `drain -> test-audit` (`drain_test.py:1154`, a commit
  message), `docs -> flow` (`count_automode_denials.py:38`).
- Even without the false edges, top-level-directory granularity puts flow (36 suites) and
  implement into one cluster. One file-level dependency drags in a whole directory.

**Selection measured against history:**
- Last 60 merged PRs, replaying each PR's file list through today's rules (`prsel.py`):
  **12 run the full seam, 44 run ≥130 suites, 4 run fewer than 130. Mean 132.7 of 153.**
  Without the edge widening the mean would be 75.7.
- The 12 full runs: 3 touch `tests/all.sh`, 1 touches `pyproject.toml`, and the rest
  touch a skill directory with no suites, mostly SKILL.md-only.
- What the runs themselves printed agrees. PR bodies say "134 of 152", "135 of 149",
  "128 of 145", "139 of 149", "132 of 139" (#1936, #1930, #1917/#1916, #1924, #1866).
  The job-run records in `jobs.txt` show "narrowed:" lines that list 17-19 directories.
- The last 80 first-parent commits replay the same way (`hist.py`): 8 full, 68 ≥130,
  4 ≤40. 34 of the 80 touch only `docs/`. Those auto-ship and probably never run the
  seam, but a docs file inside a PR widens it to 135.

**Runs per PR**, from the skill text:
- `implement/SKILL.md:416-442` (§ Review step 3): the worker runs the per-change command
  once after the review wave and fix round, again after any red, plus targeted mutation
  runs (`implement/SKILL.md:251-287`).
- `implement/SKILL.md:935-1023` (§ The merge step 3): the controller reruns the
  per-change command on the PR merged into `origin/<default>` in a fresh worktree. It is
  skipped when the base is already in the head, the "PR up" `Seam run at:` matches, and
  the seam section is unchanged (`:999-1023`). `drain` never skips it (`:1022`).
- Measured over the last 60 merged PRs: **36 carry a `selector: listed` comment (rerun
  done; 39 comments in all), 21 carry `seam rerun skipped`.**
- Spec mode (`implement-spec/SKILL.md:460-499`): each slice gets a worker run plus a
  merge rerun into `spec-<n>`, then the spec fix round runs once and the integration PR
  gets its merge rerun. That is about 2N+2 runs for N slices, each at about 135/153
  suites.
- The nightly backstop runs the full seam once a night per repo
  (`~/.cache/backstop/full-seam-caneff__agent-skills.log`).
- The correctness reviewer's mutation witnesses do not cost much. `review_ledger.jsonl`,
  repo `skills`: 1,651 witness-mutation rows, median 2 s, p90 21 s, 3.4 h in total
  across 166 tickets. 324 call-site rows, 1.0 h. Worker-mutation rows have median 2 s
  (their sum is corrupted by one outlier row).

Estimate (not measured): **about 2 seam runs per lone-ticket PR** (worker ≥1, plus a
merge rerun in 60% of PRs, plus reds), and about 2N+2 per N-slice spec.

##### 3. Wall-clock (measured from records)

The source is `~/.cache/agent-jobs/*/{cmd,progress,exit}` for runs whose output names
this repo's suites. The start time is the `cmd` mtime, the end is `exit` `ended=`. Some
runs are recorded twice under two names (for example `seam-1700` and
`TESTS-JOBS-4-r85kCrZ5` have identical timestamps); they count once.

| period | runs | suites | wall | where drain_test finished |
|---|---|---|---|---|
| 11-14 to 11-16 11:27Z | ~20 | 114-143 | **3.4-5.1 min** | about 2.5-3.5 min after start |
| 11-16 13:27Z to 11-17 | ~20 | 128-140 (narrowed) or 150 | **16.5-20.8 min** | 16-18.5 min after start |

The narrowed run `seam-1715` (drain + tests, **30 suites**) took **16.4 min**. The 29
other suites were done 34 s in; `drain/drain_test.py` alone finished at 16:22 with
136.9 s CPU (`seam-1715/progress`).

**drain_test is the critical path in every slow run.** Its CPU did not change (77-148 s
in both periods); its wall time went up about 5x. At 137 s CPU over 16 min it used about
14% of one core. It is one serial pytest process with 155 tests, each building real git
repos, a bare origin and stub processes (`tests/all.sh:394`).

Cause of the 11-16 jump: **not verified.** The first slow record (13:27Z) predates both
11-16 drain_test edits, `be866d57` (#1922, 20:04Z) and `11048d06` (#1918, 16:28Z). It
also predates `f3dca666` (job-run timeout and stdin, 14:04Z), unless that run was #1916's
own branch. Heavy box load (the brief says ~40; #1950 cites load 88 on 11-17) is
consistent with the data. A code change is not ruled out.

**Per-suite CPU, one narrowed run** (`seam-1900`, 134 suites, **719 s CPU total**):

| suite | CPU |
|---|---|
| `flow/lane/Cargo.toml` (serial, runs alone at the end) | 155.7 s |
| `flow/install.test.sh` | 144.3 s |
| `drain/drain_test.py` | 88.6 s |
| `flow/claude/hooks/block-dangerous-git.test.sh` | 30.4 s |
| `all-audits/driver_test.py` | 23.1 s |
| `implement/fix_check_test.py` | 19.7 s |
| `tests/changed.test.sh` | 13.7 s |
| `backstop/backstop_test.py` | 12.7 s |
| `tests/backstop_edges_test.py` | 12.0 s |
| `docs/research/review_ledger_test.py` | 10.8 s |

The top three are **54% of CPU**. By directory: flow 384 s, drain 89 s, tests 52 s,
implement 52 s, docs 41 s.

The nightly full run (`~/.cache/backstop/full-seam-caneff__agent-skills.log`, 152 suites)
used 845 s CPU: install.test.sh 195.1 s (over its 160 s budget), lane 155.9 s (over 150 s),
drain 95.0 s. That log carries no start time, so its wall time is unknown.

The lane suite's serial tail adds about 40-60 s of wall per run. For example `seam-1736`
logged the drain line at 04:57:30 and the end at 04:58:09.

##### 4. Redundancy candidates

- **Prose-pinning suites.** Chris ruled them out on 2026-10-04 (#1414, "wording is shit
  tests"), and #1636 and #1732 cut 68 tests (54 prose greps). New ones keep landing:
  - `implement/merge_rules_test.py`: 5 tests asserting sentences of `implement/SKILL.md`,
    added by #1936 on 11-16.
  - `implement-spec/skill_md_test.py`: 2 tests asserting `implement-spec/SKILL.md` text,
    added by #1934 on 11-16.
  - `docs/agents/friction-log.md:190`: two workers in spec-1733 added doc-grep tests even
    though the spec said "prose".

  Their CPU is negligible (under 1 s each), so the cost is churn, not seam time.
  `drain/skill_test.py`, `create-lmd-page/skill_test.py`,
  `implement/ticket_comment_render_test.py` and `file-ticket/blocked_by_test.py` read
  SKILL.md but run code or flags taken from it, so they are not pure prose tests.
- **review_ledger tests live in `docs/research/`.** 10 suites, about 3.3K test LOC, about
  41 s CPU. They test `multi-axis-code-review/review_ledger.py`
  (`docs/research/review_ledger_support.py:11`), and `review_ledger.py:112` imports from
  `docs/research`. That pulls `docs/` into the core cluster, so any PR that touches
  `docs/` runs 135 suites.
- **Duplicate compile.** `flow/lane/Cargo.toml` and `flow/install.test.sh` both compile
  the lane crate cold, about 300 s CPU between them. #1950 already covers this.
- **Spec-named e2e tests always run.** `tests/spec_1730_e2e_test.py` and the other
  `tests/*_e2e_test.py` run on every PR because `tests/` is always kept. They are cheap:
  all 27 `tests/` suites total about 52 s CPU.
- **Parked or retired skills: none.** No SKILL.md carries a `Parked:` description or
  banner (`git grep`). `tests/retired_name_test.py` is a cheap guard (0.3 s).
- **Evidence of catches is thin:**
  - The backstop selector verdicts (`~/.cache/backstop/selector-verdicts-caneff__agent-skills.jsonl`,
    8 rows since 10-18) record red-on-main suites:
    - `tests/section-references.test.sh` 3 times (1 graded `hit`);
    - `tests/always_on_budget_test.py` twice;
    - `flow/settings-rules.test.sh` once.

    All six are prose or doc checks, most likely tripped by direct-to-main docs commits.
  - Of 25 friction-log entries about the agent-skills seam, about 12 describe reds that
    did not come from the diff: CPU-budget overruns, an `@babel/parser` npm race, ETXTBSY,
    SIGPIPE, a stale cargo target, failures inherited from main. Heuristic grep of
    `docs/agents/friction-log.md`.
  - PR bodies cite mutations going red (by design), not seam catches of real regressions.
  - Per-suite "has never failed" history was **not established**: no log keeps a
    per-suite fail history.

##### 5. Existing tickets (do not duplicate)

`gh issue list --search "seam OR tests/all.sh OR slow"`, plus a second search.

Open:
- #1950 Rust suites: share one persistent cargo target dir
- #1949 drain: skip the merge rerun when the worker's tested sha is the head
- #1928 Correctness reviewer's seam-run instruction never fires: the seam runs after the review wave
- #1619 Prose End-to-end seam section: lint it or parse it

Recently closed and relevant:
- #1895 Narrowed seam should diff against the PR base, not origin/main (closed 11-17)
- #1808 Workers launch the narrowed seam undeclared at nproc jobs
- #1606 CPU budget goes red under box load
- #1592 per-change runs use the narrowed seam; one nightly full backstop
- #1496 merge step 3: rerun the full seam, not --changed
- #1414 / #1636 / #1732 prose-test cuts
- #1845 test-audit npm bootstrap race

Also `.audit-ignore.md:36` dismissed "move suite selection into a Python select() with an
explicit edge table" on 2026-11-13 as speculative, with the reason that "narrowing has no
open defect". The data above is that defect: the narrowing does not narrow.

---

##### Ranked recommendations

1. **Break the drain_test long pole.**
   - Mechanism: run `uv run --locked pytest drain/drain_test.py --durations=25` once on a
     quiet box to find the slow cases. Then split the file into 3-5 files by area
     (all.sh already runs files concurrently) or fix the slow cases' real waits.
   - Saves (estimate): in the current regime, **about 12-14 min per seam run**, about
     25 min per PR at ~2 runs. Pre-11-16, about 1.5-2 min per run.
   - Protection given up: none. The same tests still run.
   - Afterwards: the per-suite CPU and budget line in all.sh, plus the nightly backstop.
     Add a wall-clock print beside CPU so a future long pole is visible.
2. **Make `--changed` narrow.**
   - (a) Drop the false-positive edges: a comment, string or commit message inside the
     3-line span should not count.
   - (b) Key edges by file, not top-level directory: a suite depends on the files it
     sources or loads, so `worker-dirty-stop.test.sh` runs when
     `implement/pre-report-gate.sh` changes, not all 36 flow suites.
   - (c) A diff confined to Markdown in a suite-less skill directory should run only
     `tests/` plus repo-wide (the prose checks), not the full seam. That alone moves 6-8
     of 60 PRs off full.
   - (d) Move the `docs/research` review_ledger tests next to `review_ledger.py`.
   - Saves (estimate): mean selection from about 133 to roughly 40-75 suites. In wall
     time that saves little unless drain, lane or install drop out of the selection; it
     saves a lot of CPU on an overloaded box.
   - Protection given up: an edge the scanner misses goes unrun per-PR.
   - Afterwards: the nightly full backstop and its selector-verdict grading (already the
     designed fallback, #1592). Merge-step selector comments show what was skipped.
3. **#1950 (existing): one persistent cargo target dir.**
   - Removes most of about 300 s CPU per run and shortens the serial lane tail by about
     40-60 s wall.
   - Better still, `install.test.sh` could consume the lane test build's binaries instead
     of building its own.
   - Protection given up: a cold-build-only failure. The nightly can keep a cold build.
4. **Cut runs per change in spec mode.**
   - Mechanism: skip the per-slice merge rerun into `spec-<n>` when the slice's base is
     in its head (extend the existing skip, which already covers 21 of 60 PRs), and rely
     on the fix-round and integration runs.
   - Saves (estimate): about 1 run per slice.
   - Protection given up: catching a slice-slice interaction earlier rather than at the
     integration run.
   - Afterwards: the integration-PR run and the nightly. #1949 covers the drain variant.
5. **Enforce the prose-test ruling mechanically.** Add a check to all.sh, like its
   unittest-import check, that fails a suite whose only assertions are substring checks
   on a `.md` file. Then delete `implement/merge_rules_test.py` and
   `implement-spec/skill_md_test.py`.
   - Saves: negligible time; it stops the churn.
   - Protection given up: a pinned sentence can be edited away, which the owner already
     ruled is not protection.
   - Afterwards: test-audit's `prose-assertion` category on sweeps.
6. **Stop timing on CPU alone.** Have all.sh print wall seconds per suite and a total, and
   keep the last N run summaries (wall and CPU per suite) under `~/.cache/backstop/`. This
   survey had to reconstruct wall time from job-run mtimes.
   - Saves: no time, but it makes the next audit cheap and turns "never failed" into
     something measurable.

Not recommended: bulk deletion of tests for "bloat". Test LOC roughly equals code LOC
(1.13 on recent PRs), which is high but normal for a repo where tests are the main
reviewer. Most suites cost under 5 s CPU, and the three largest are 54% of the CPU.

##### Verified vs not verified

Verified (from records or commands cited above):
- suite and test counts, LOC and growth;
- marker counts;
- edge closure sizes;
- per-PR selection replay against today's rules;
- 36/21 rerun/skip comment counts;
- wall times and drain_test position from job-run records;
- per-suite CPU from `seam-1900` and the nightly log;
- the two new prose suites and their dates;
- the existing tickets.

Not verified:
- the cause of the drain_test slowdown on 11-16 (load vs code);
- the nightly full-seam wall time (its log has no timestamps);
- exact seam runs per PR (worker runs outside job-run leave no record, and some job
  records are duplicates);
- savings from file-level edges (an estimate, not simulated);
- the 2N+2 spec figure (taken from skill text, not counted);
- a per-suite never-failed history (no such record exists);
- shell test-case counts.

Nothing was run beyond `tests/all.sh --list`, `tests/suite-edges.py` (3 s), and read-only
Python that imports `suite-edges.py`.

### Appendix: sudokupad-scripts

#### Test-cost survey: caneff/sudokupad-scripts (2026-11-17)

Read-only. No suites run locally. Repo HEAD read: `d7cd5c9` (local checkout); `origin/main` ref fresher (`6b97a35`, #1016).
Raw data: scratchpad `sps/runs.json` (1325 runs), `sps/prs.json` (400 merged PRs), `logs/*.log` (failed-run logs).

##### Headline

The owner's suspicion is half right. **GitHub CI is not where the time goes**: the per-PR CI job is ~45 s. The cost is
(1) the **local Playwright live suite** (1678 tests, 5.4 min median, 11-13 min under load, failing in 7 of 11 sampled
full runs) run by the worker and again by the controller; (2) the **fuzz-on-PR** job (5 min fixed budget, 1 regression
caught in 10 failures); (3) **test volume growth**: test+harness lines added are 3.4x code lines added over the last 40
PRs, and the fuzz/live expectations must be edited every time UI behaviour changes on purpose.

Window note: the repo was created 2026-11-02 (`gh api repos/caneff/sudokupad-scripts --jq .created_at`); every
workflow was added 2026-11-03..09 (`git log --diff-filter=A`). "Last 30 days" = all runs that exist: 2026-11-04..17,
13 days. `gh run list --limit` caps at 1000, so runs were pulled in `--created` date windows and deduplicated.

---

##### 1. Workflows (verified, file:line)

| Workflow | Triggers | Path filter | Concurrency | Timeout | Matrix | Cache |
|---|---|---|---|---|---|---|
| `ci.yml` | `push` (all branches) + `pull_request` (ci.yml:3-5) | none | **none** | none (default 360) | none | npm via setup-node (ci.yml:21) |
| `fuzz-pr.yml` | `pull_request` (fuzz-pr.yml:4-14) | 6 `*.user.js` (not draw-tool), `lib/**`, `live/fuzz/**` | `fuzz-pr-<PR#>`, cancel-in-progress **true** (:20-22) | 25 min (:27) | none | npm; Playwright Chromium **not** cached (:38) |
| `fuzz.yml` | schedule 07:47 daily + dispatch (:4-12) | n/a | `fuzz-sudokupad`, cancel false (:19-21) | 75 min (:26) | none | npm; Chromium not cached |
| `pages.yml` | push to `main` (:3-9) | `site/**`, pages.yml | `pages`, cancel false | none | none | none |
| `watch.yml` | schedule 06:17 daily + dispatch (:3-6) | n/a | `watch-sudokupad`, cancel false | none | none | npm + Actions cache of SudokuPad recording (:33-48) |

- **push and pull_request both fire for the same commit**: yes for `ci.yml`. All 350 PR-event CI shas also have a
  push-event CI run on the same sha (analysis of `runs.json`). 474 of 697 push runs are on non-main branches.
- `fuzz-pr.yml:50` runs `npm run test:fuzz -- --minutes 5 --shrink-minutes 3`: a **time box**, not a work box; the fuzz
  step takes 301-302 s on every passing run sampled.
- No merge_group. `main` has no branch protection (`gh api .../branches/main/protection` -> 404) and no rulesets
  (`[]`): nothing is a *required* check; the controller decides what to wait on.
- No GitHub job runs the live suite (`*.live.mjs`) except `watch.yml`, and `watch:live` only does work when SudokuPad's
  version changed: the step took 1 s on runs 43901090292 and 43721788598 (AGENTS.md:73-80 and live/README.md:9 confirm
  the live suite is local-only).

##### 2. Measured CI cost (verified; startedAt->updatedAt)

| Workflow / event | Runs | Median | p90 | Total min | Fail | Cancelled |
|---|---|---|---|---|---|---|
| CI / push | 697 | 0.7 | 0.8 | 474 | 7 | 0 |
| CI / pull_request | 350 | 0.7 | 0.8 | 238 | 5 | 0 |
| Fuzz pull request | 98 | 5.6 | 6.1 | 534 | 10 | 1 (+1 in progress) |
| Fuzz SudokuPad (schedule+dispatch) | 16 | 30.7 | 33.7 | 464 | 7 | 0 |
| Pages | 148 | 0.3 | 0.5 | 73 | 0 | 0 |
| Watch SudokuPad (all events) | 16 | 1.3 | 10.3 | 58 | 6 | 0 |
| **All** | 1325 | | | **1842** | | |

~140 runner-min/day. The repo is public, so Actions minutes are not billed; the cost is wall time and queueing.

Per-step timing (`gh run view <id> --json jobs`):
- CI 44142996073 / 44140490597 / 44133769210: job 55/47/44 s; `npm test` 25/25/23 s; `npm run lint` 11/11/9 s;
  checkout+setup+`npm ci` ~10 s.
- Fuzz PR 44121538413 / 44108747733 / 44106023326: job 328/338/341 s; Playwright install 17-23 s; fuzz step 301-302 s.
- Fuzz nightly 43918568769 / 43873707456 / 43868989304: job ~1840 s; `fuzz:nightly` 1804-1815 s.
- Watch 43901090292 / 43721788598: job 76/68 s; `watch:live` 1 s; `test:tampermonkey` 36-37 s; Chromium install 17-24 s.

`npm test` in CI (log of 44142996073): **1919 tests, 113 suites, duration_ms 24624**. Slowest tests (cumulative,
files run in parallel): `the action vocabulary` 9.7 s and `focusing the actions on a script` 3.0 s
(`live/fuzz/actions.test.mjs`), settings dialogs Copy/Paste 6.9 s, `the fuzz engine on a fake page` 4.5 s
(`live/fuzz/engine.test.mjs`), and `settle` 5.0 s / `stable` 4.8 s / `clickUntil` 4.2 s / `readUntil` 1.3 s
(`live/settle.test.mjs`, which waits on real `setTimeout`s, e.g. lines 83, 136, 146, 162).

##### 3. Cost of one PR end to end

GitHub (verified, 258 merged PRs whose branch has runs): median **3 runs** per PR (CI push + CI pull_request + fuzz-pr
if paths match), 6 when the PR got a second commit. Median runner time 2.4 min, mean 4.6 min. 15 most recent merged PRs
(#949..#1012): 3 or 6 runs each, 7.1-15.0 runner-min each (all touched script paths, so all fuzzed).
Median PR open->merge: 6.7 min with fuzz-pr, 7.0 min without, so fuzz-pr is not measurably on the critical path.
Fuzz-pr finished before the merge on 83 of 85 final-sha runs, so the controller does wait for it.

Local gate (documented, partly measured):
- `git config land.testcmd` = `npm test && npm run lint` (verified). The same two commands are the whole of `ci.yml`.
- AGENTS.md:81-83: the worker runs the changed live files while iterating, then **the full live suite once before
  "PR up"**; the controller's merge check reruns either the full suite or the narrowed file set
  (live/README.md:11-19). Any change to `live/*.mjs`, `package.json`, `site/` or `.github/` forces a full rerun.
- AGENTS.md:86-89: `test:tampermonkey` also runs at merge when a `==UserScript==` header changed.
- PR-body evidence (last 120 merged PRs): 65 report a live run, 26 a Tampermonkey run, 19 a fuzz run. Full-suite
  reports: #1012 (1692 pass, *a second run failed 2 tests on timeouts*), #1008 (1675), #1005 (concurrency lowered to 2
  "because box load was high"; attack 78 failed 5 of 16 runs at load 33-51), #998 and #997 (1 fail each, pre-existing).
- Local durations from `~/.cache/agent-jobs` (only runs wrapped by `job-run`; sample, not census): full live suite
  n=11, **median 5.4 min, p90 11.2, max 13.4 (live-963, 1678 tests, concurrency 2)**, growing from 3.5 min at 1105
  tests on 11-07; **7 of 11 had at least one failing test**. `test:live:files` n=59, median 2.8 min, p90 7.5,
  19 of 59 with failures. `test:tampermonkey` n=10, median 0.3 min.

Estimated per script-touching PR (not verified as a census): 1 full live run by the worker (5-13 min) + 1 narrowed or
full rerun by the controller (3-13 min) + several file runs while iterating (~3 min each) + 2-4 `npm test` runs +
reruns after load-induced timeouts. That is roughly **15-35 min of local machine time against ~1-6 min on GitHub**.

##### 4. Failure value

CI (12 failed runs = 7 distinct causes, push and PR duplicating each other):
- 42422580839: `lint-probe.js` (a deliberate lint probe file; not a catch).
- 42443268571: `draw-tool.html stays short: its text is under 320 words` (a word-count test on a doc page).
- 42820064856: `#711: draw-tool.user.js is the script frozen at the handover version ...` (structure pin).
- 43486995296 (prototype-722): `nothing but the old stored keys ... still says draw tool` (wording test).
- 42671305437, 42671770986, 42671845878/42674224491: "workflow file issue" (an invalid workflow on the branch;
  infrastructure/config, though a true catch of a broken workflow).
- So: 0 failed CI runs caught a behaviour regression; 3 caught text/structure-pin tests the local gate should already
  have run; 3 were workflow-file errors. All happened 11-07..11-13; none since.

Fuzz pull request (10 failures, all logs read, classified with each PR's next commit):
| Run | PR | Error | Class |
|---|---|---|---|
| 42823052404 | #804 | pen-tool-extras arrow lines RangeError; fixed by 95e00d5 | **real regression caught** |
| 43438797240 | #826 (fuzz PR) | "an undo takes a step"; fixed in the fuzz harness 770b046 | harness bug in a fuzz PR |
| 43451971153 | #830 (fuzz PR) | rules-fit-pane rule broken; rule judged wrong, #828 | harness/rule bug |
| 43502087302 | #878 | `page.click: Timeout 30000ms`; **merged red** | flake/infra |
| 44088012099 | #1000 | button title "has no mode"; fix ea7f104 updates fuzz to new spelling | expectation update for an intended change |
| 44089868314 | #1001 | `locator.click: Timeout 30000ms` | flake/infra |
| 44096057739 | #1001 | undo-redo-restores; **merged red**, filed #1006 as pre-existing | real bug, not from the PR |
| 44095421135 | #1005 | note-box-color; fix 5b0ff78 updates page-state expectation | expectation update |
| 44103871680 | #1008 | Clear said "already empty"; fix 8a59691 updates fuzz | expectation update |
| 44109180441 | #1009 | digit-cells-colored after Ctrl+Z mid-drag; **merged red**, #1011 | real bug, not from the PR |
Score: 1 PR-caused regression, 2 pre-existing bugs (the nightly hunts the same code), 3 expectation edits forced by
intended UI changes, 2 harness bugs, 2 timeouts. The one regression failed at 268 s, so a shorter budget would have
missed it.

Nightly fuzz (7 failures): real bugs filed #668 (notes-survive-reload), #731/#743 (reload pen colour), #899 (pad menu
after rules widen); #1015 locator timeout (needs-info); 43050193812 setup failure (did-not-run issue). Highest yield per
minute of anything here, and off the PR path.

Watch (6 failures): 42655017428 and 44121586777 are **attack 78's time budget** (200 notes + pen lines); 43038660851
setup failure; 42423098562 / 42439298762 / 42439298762's sibling are branch-dispatched test runs during development.

Never failed in the window: `Pages` (148/148), the `npm run lint` step on a real change (only the probe), and
`test:tampermonkey` (no Tampermonkey issue filed; all 10 local runs green).

##### 5. Inventory (verified, `git ls-files` + grep for `test(`/`it(` at line start)

| Kind | Files | Lines | Cases (static) |
|---|---|---|---|
| unit `test/` (incl. 23 `test/specs/*closing*`) | 38 | 10,380 | 1,019 |
| unit `lib/*.test.js` | 15 | 2,527 | 222 |
| unit live-harness/fuzz `live/**/*.test.mjs` | 23 | 4,724 | 538 |
| live e2e `live/**/*.live.mjs` | 101 | 23,645 | 1,240 static, 1,678 at run time |
| fuzz smoke `live/fuzz/fuzz.smoke.mjs` | 1 | 650 | 69 |
| Tampermonkey e2e | 2 | 319 | 6 |
| harness: `live/fuzz/*` src 3,716, `live/*` src 2,152, `test/` helpers 360 | 49 | 6,228 | - |
| **Test total** | | **~48,500** | ~3,600 run |
| Source: `*.user.js` 18,280 (incl. frozen `draw-tool.user.js` 4,209 and lib blocks copied in by `sync-lib.js`), `lib/` 1,285, `site/` 602 | | **~20,200** | |

Test:source ~2.4:1 (~3.4:1 against the 14k live script lines). Live e2e by script: Text Anywhere 48 files, Pen Tool
Extras 19, Color by Digit 15, top-level cross-script 15, others 1-2.
Growth: test files 13 on 11-03, 95 on 11-07, 165 on 11-10, 170 on 11-13, 179 now; live files 7 -> 55 -> 101 -> 101.
The repo did not exist on 2026-09-01. Live suite size from PR reports: 1105 (11-07) -> 1678 (11-17).
Last 40 squash PRs on main (c9db1eb #811 .. 6b97a35 #1016): **test+harness lines added 9,290 vs code 2,708 (3.43x)**;
32 of 40 added more test than code; 30 of 40 added no script/lib/site code (largely fuzz-harness PRs).
(Also seen: #883 committed two 4k-line `*.user.js.orig` merge leftovers, removed in bd167d3.)

##### 6. Redundancy candidates

1. **Local gate == CI.** `land.testcmd` is exactly `ci.yml`'s two steps. CI is 45 s and is the cheap side; the
   duplication costs nothing that matters. CI did catch 3 test failures the local gate let through, so keep both.
2. **CI twice per PR commit** (push + pull_request), no concurrency group: 474 redundant branch-push runs.
3. **Full live suite twice per PR** (worker, then controller unless the narrowing rule applies), on an overloaded
   machine where it flakes (7/11 sampled full runs red). There is **no** run of the full live suite on GitHub, where
   load is not a factor.
4. **Fuzz on the PR path** with a fixed 5-minute budget, and the same code fuzzed 30 min nightly.
5. **Text/structure pins**: `test/specs/` 23 closing-test files, 71 cases, 1,854 lines, many asserting where code lives
   ("#834: loadInPlace lives in live/puzzles.mjs and nowhere else") or what text says; `test/site.test.js` 56 cases;
   word-count and naming tests. Cheap in seconds, but 3 of the 4 real CI test failures were this kind.
6. **Time-budget e2e**: attack 78 fails on load, not on code (watch x2, #1005 5/16, #1012).
7. **Real-time waits in unit tests**: `live/settle.test.mjs` (~15 s cumulative), fuzz action vocabulary 9.7 s.
8. Open audit #967 (and children #981-#987) already targets ~40 tests that prove less than their names say.

##### 7. Existing tickets (`gh issue list --search "CI OR slow OR fuzz OR flaky" --state all --limit 40`)

Open: #967 Audit sweep 2026-11-16: Test harness, tests and CI; #986 Live tests that prove less than their names say;
####987 All four workflows read Node's version from one file; #1007 Fuzz smoke: the planted-bug test times out at 120 s;
####1015 Fuzz: locator.waitFor timeout; #981 / #982 / #983 fuzz harness cleanups.
Closed and relevant: #717 Live suite: default test timeout and a narrowed merge rerun (cause: "#107's merge check ran for
hours"); #724 short fuzz run on each PR (origin of fuzz-pr.yml); #644 attacks 53 and 57 flake under the full suite's
load; #126 live dialog checks fail under heavy load; #925 3-4 hunts in the nightly; #888 four fuzz smoke tests fail on main.
No ticket proposes moving the full live suite to Actions or making fuzz-pr advisory.

---

##### Ranked recommendations

**R1. Run the full live suite on GitHub nightly (and on demand), and stop the worker's pre-PR full run.**
Mechanism: a scheduled/dispatch job (or a step in `watch.yml` that always runs `npm run test:live` on main, not only on a
new SudokuPad version); workers run only the touched files (live/README.md § The merge rerun's list); the controller
keeps the narrowed rerun and drops the "full on helper change" escalation to the nightly.
Saves: ~5-13 min local per script-touching PR, plus the reruns load-induced flakes cause; removes the worst source of
false reds. Gives up: a cross-script regression from a helper or `site/` change is caught next morning instead of
before merge. Afterwards: the nightly full run files an issue (same `file-issue-once` action) and revert is the undo.

**R2. Take time-budget and load-sensitive tests out of any merge gate.**
Mechanism: move attack 78 (and similar budgets) to the nightly job only, or relax its budget; retry-once for Playwright
`Timeout 30000ms` in fuzz-pr/smoke before failing. Saves: the investigation loops seen in #1005/#1012 (many reruns).
Gives up: an early warning of a perf regression on the PR. Afterwards: the nightly run on an unloaded runner.

**R3. Make fuzz-pr advisory, or limit it to script/lib changes.**
Evidence: 1 regression in 10 failures; 3 failures were "update the fuzz to the new intended behaviour"; 3 of the PRs were
merged red anyway. Mechanism: either drop `live/fuzz/**` from its paths (fuzz-harness PRs get their own smoke tests)
or let the controller merge without waiting and have a red run file an issue like the nightly. Saves: ~0-6 min wall
per script PR (open->merge medians did not differ, so expected wall saving is small) and the expectation-edit tax
when the PR is a deliberate UI change. Gives up: the #804-style same-PR catch before merge. Afterwards: nightly fuzz
(30 min, found 4+ real bugs) and revert. Do not shorten the budget instead: the one catch came at 268 s.

**R4. Retire `test/specs/*-closing` tests once their spec closes, keeping only behaviour checks; drop word-count and
naming pins.** Saves: seconds of run time, but most of the maintenance churn and 3 of 4 real CI test failures.
Gives up: guards that a refactor stays where a spec put it. Afterwards: code review and the behaviour tests.
Coordinate with #967/#986, which already list ~40 weak tests.

**R5. `ci.yml`: `push: branches: [main]` plus `concurrency: {group: ci-${{ github.ref }}, cancel-in-progress: true}`.**
Saves: ~35 runner runs/day, 0 min of PR wall time (runs are parallel). Gives up: CI on branches pushed without a PR.
Afterwards: the pull_request run and the local land gate.

**R6. Fake timers in `live/settle.test.mjs`; trim the fuzz action-vocabulary loop.** Saves ~5-10 s per `npm test`
(run several times per PR on a loaded box). Gives up nothing if the timer semantics are kept.

Not recommended: cutting CI's `npm test`/lint (45 s, and it caught what the local gate missed), or the nightly fuzz
(off the PR path, highest bug yield).

##### Verified vs not verified

Verified: every workflow fact (file:line); all GitHub run counts, durations, failure logs and classifications above;
test/source line and case counts; growth by commit; last-40-PR line ratios; ticket list; `land.testcmd`.

Not verified:
- How often the full live suite actually runs per PR. Local timings come from `~/.cache/agent-jobs` (only `job-run`
  wrapped runs: 11 full, 59 file runs), not a census; most runs probably happen in worker shells without a record.
- Local `npm test` wall time on the loaded machine (a handful of samples ~1.4 min; repo attribution uncertain).
- Whether the controller blocks merge on fuzz-pr by rule (inferred: 83 of 85 finished before merge).
- Whether the narrowed merge rerun or the full rerun is the common case.
- Human/agent time spent on expectation edits and flake investigations (only visible anecdotally in PR bodies).

### Appendix: penpa-edit

#### penpa-edit test-cost survey (read-only, 2026-11-17)

Repo `/home/caneff/src/penpa-edit` at `835142c`. Every `gh` call used `--repo caneff/penpa-edit`. Nothing was run
locally except `git` reads and `gh` reads. Raw data: `scratchpad/penpa/runs.json` (all 526 Actions runs),
`scratchpad/penpa/prs.json` (last 40 merged PRs), `scratchpad/penpa/master-log.txt` (CI run 44139528665 log),
`scratchpad/penpa/fail/<run-id>.txt` (`--log-failed` for all 37 failed runs).

**Note on the brief's numbers:** the window is not 30 days. The repo's whole Actions history is 526 runs, from
2026-11-09 to 2026-11-17 (`gh run list --limit 1000` returns 526). Every figure below covers those 8 days. Commits since
2026-10-01: 173 (`git log --since=2026-10-01 | wc -l`), which matches the brief. The "434 test-like files" figure does
not match what I found: by path, 1,060 tracked files are test-like (see § 5).

**Note on the scratchpad:** another agent wrote a `runs.json` for a different repo (branch `main`, `spec-951`) into the
shared scratchpad root while this survey was running. I re-fetched everything into `scratchpad/penpa/`.

##### Verdict

**Partly true.** The repo carries a lot of test code: test lines added outnumber code lines added about 3:1. But the
time is concentrated in a few places, and only one of them is volume:

1. **The engine-driver safety net runs on every PR and every master push.** The 268-recording engine replay is 1,339 s
   of the 3,326 s of summed live-test time, and fuzz plus Tier C add another 337 s. In the 8-day window it failed on a
   PR only through timeouts, or on the PR that added its own recordings.
2. **Re-runs.** Strict up-to-date merging means 32 of 70 commits in the 15 sampled PRs are master merges, and each one
   starts a full 13–20 min CI run. There is no `cancel-in-progress`, so 50 superseded PR runs kept going (428 runner-min).
   Flakes caused at least 15 of the 37 failures.
3. **The local seam.** It is the full `npm test && npm run test:live`, with no `**Narrowed**` line. The worker runs it
   and the controller runs it again on a box at load 24–40, which repeats CI's own check on the same tree.

Open issue #268 / PR #280 (`implement-268`, not yet merged) already targets the biggest lever. As written, though, its
skip list frees only 15 of the last 40 PRs.

##### 1. Workflows (verified, file:line)

| | `ci.yml` | `ui-corpus.yml` | `upstream-merge.yml` |
|---|---|---|---|
| Triggers | `push: [master]` + `pull_request` (ci.yml:3-6) | `schedule 47 5 * * *` + dispatch (ui-corpus.yml:7-10) | `schedule 17 5 * * *` + dispatch (upstream-merge.yml:8-11) |
| Path filters | none | n/a | n/a |
| concurrency | **none** | none | `concurrency: upstream-merge`, no cancel (l.18) |
| Matrix/sharding | none: one `test` job running `npm test` then `npm run test:live` (ci.yml:13-22), `--test-concurrency=4` (package.json) | none | none |
| Caching | `setup-node cache: npm` (setup-tests/action.yml:6-9). Playwright Chromium is **not** cached: `npx playwright install --with-deps chromium` on every job (action.yml:13), 20–43 s | same | same |
| Timeouts | no `timeout-minutes`. Per-test 60 s (package.json `--test-timeout=60000`) | per-test 180 s (l.22) | none |
| Push and PR on the same commit? | No: PR runs test the merge ref and push runs test the squash commit (0 shas carry both events). They do test the **same tree**: since strict mode (#221, 2026-11-17 11:51Z), 16 of 20 push runs had a tree already green on a PR run (294 of 354 min) | | |
| Other jobs | `expected-files` on PR only, 9–13 s (ci.yml:27-63) | | |

A sixth workflow, "Nightly seam", exists on GitHub (`gh workflow list --all`). It belongs to PR #280's branch (one run, on
`probe-268-nightly`, a planted failure).

##### 2. Measured cost (verified, `gh run list --limit 1000 --json ...`, 2026-11-09 to 2026-11-17)

| Workflow / event | Runs | Median | p90 | Max | Total runner-min | Failed | Cancelled |
|---|---|---|---|---|---|---|---|
| CI / pull_request | 223 | 14.8 min | 20.0 | 22.6 | 2,938 | 26 (12%) | 0 |
| CI / push | 146 | 12.9 min | 18.0 | 22.6 | 1,478 | 9 (6%) | 0 |
| UI corpus / schedule | 1 | 20.6 | | | 21 | 1 | 0 |
| Upstream merge | 5 | 0.2 | | | 1 | 0 | 0 |
| Nightly seam (PR #280 probe) | 1 | 7.9 | | | 8 | 1 (planted) | 0 |
| pages-build-deployment | 150 | 0.7 | | | 105 | 0 | 14 |

**Growth:** CI's median duration by day was 1.2 min (11-13), 14.0 (11-14), 13.7 (11-16) and 16.2 (11-17). CI
runner-minutes per day: 156, 105, 100, 1,498, 2,557. Minutes are free because the repo is public (AGENTS.md), so the
real cost is how long agents wait on the merge path.

**Per-step (verified, `gh run view <id> --json jobs`):**

| Run | Event | `test` job | setup-tests | `npm test` | `npm run test:live` |
|---|---|---|---|---|---|
| 44139528665 | push master | 895 s | 25 s | 10 s | **853 s** |
| 44136914229 | push master | 885 s | 43 s | 13 s | **819 s** |
| 44138839256 | PR implement-233 | 1,350 s | 31 s | 17 s | **1,294 s** |

`test:live` is 94–96% of the job. In PR #280's split shape, `probe-268-ui` (a docs/ui-only change) took 78–166 s per live
part and `probe-268-js` (full set over 4 runners) took 231–424 s per part (runs 44139685313, 44139689535).

**Where test:live's time goes** (top-level durations parsed from run 44139528665's log; sum 3,326 s, wall 853 s at
concurrency 4):

| Bucket | Summed s | Share |
|---|---|---|
| Engine-driver replay, 3 parts (268 recordings × 2 tests = 536 tests) | 1,339 | 40% |
| Solve-UI tests (desk, cards, settings, keys…) | 1,362 | 41% |
| UI-driver sample, 8 parts | 288 | 9% |
| Fuzz | 176 | 5% |
| Tier C | 161 | 5% |

The slowest single groups are each engine part (436–455 s), the fuzz (176), Tier C (161), "the Mouse card against the
board" (110 s, 373 tests), "the desk" (75), "the engine driver" (72), "row and column numbers" (56) and "Reset layout"
(56). `npm test` totals 611 tests in 10 s, 416 of them upstream's puzz.link snapshots.

##### 3. Cost of one PR (verified for CI; the local part is from docs only)

I sampled 15 merged PRs (#235–#273) from `prs.json` and CI runs by `headBranch`.

- **PR CI runs per PR:** 4, 2, 1, 3, 3, 3, 4, 3, 4, 6, 2, 1, 1, 3, 1, a mean of **2.7**. Runner time per PR ranged from
  14 to 117 min, a mean of **48 min**. Each PR then adds one push run of about 13 min, plus Pages.
- **Why there are several runs:** 32 of the 70 commits across those PRs are `Merge … master` commits. Strict mode (#221)
  reports a PR as BEHIND, the branch merges master, and full CI runs again. Only 9 of the 41 runs failed, so most re-runs
  are churn rather than fixes. Open-to-merge times ran from 15 to 97 min.
- **Local gate (not verified by measurement):** `~/.agents/skills/implement/SKILL.md:416-437` makes the worker run the
  seam once after the fix round, using the `**Narrowed**` command when one exists, else `**Seam**`. penpa-edit's AGENTS.md
  has no Narrowed line (AGENTS.md:47-48), so the worker runs the full seam. The controller reruns it before merge unless
  master is already in the head (SKILL.md:997-1020), which rarely holds because master moves every 15–20 min. That makes
  roughly **2 full local seams per PR**, on a 32-core box at load 24–39 (#171). PR bodies cite one green seam each (e.g.
  #251 "npm test && npm run test:live at ded9f96: 1813 pass"). I could not measure local durations; #82 recorded 359 s
  when the corpus was 258 recordings, before the solve-UI tests existed.

##### 4. Failure value (verified: all 37 failed runs read with `--log-failed`)

| Class | Runs | Evidence |
|---|---|---|
| **Flake: fuzz timeout** (akari seed 3, 60 s; #126, now closed) | 8 | 43778491710, 43785338443, 43798343549, 43801405380, 43802701782, 43805298745, 43856045280, 43863098302. 5 were on master; 4 of those had the identical tree green on its PR (tree-hash match) |
| **Flake: solve-UI tests** ("the top bar on a laptop screen" ×5, Settings focus ×2) | 7 | 44083505551 and 44099998155 were master pushes whose identical tree passed on the PR. 44076810109 and 44103398633 went green after unrelated edits. Also 44087392504, 44124818349, 44073147667. **No ticket for the top-bar one** (#265 is a different flake) |
| **Master broken by an un-rebased merge, before strict mode** (keyboard/focus cluster) | 6 | 44015390339, 44016106703 (master), 44016184971, 44016862373, 44018322238, 44018622652. A real integration catch, likely; not proven |
| **PR's own work red, fixed by the next commit** | 12 | 43799399416, 43800894946, 43802146659, 43944167084 (fixed by a test-only edit), 44005729720, 44012020057, 44019002525, 44080622439, 44115315490 (UI fuzz), 44135892039/44136163441/44136964807 (#256's new test over 60 s). All are solve-UI tests |
| Expected-file gate (process catch, works as designed) | 1 | 43861953663: "expected file changed, not listed in advance" |
| Planted probe for #268 | 2 | 44139696969, 44139697713 |
| Nightly UI corpus, new differences | 1 | 44108480432: 32 ✖ lines, about 16 recordings on solve.html. **No issue filed:** ui-corpus.yml relies on GitHub's failure email |

At least 15 of 37 failures (41%) were flakes. That is about 4% of all CI runs, and each costs a 13–20 min re-run.

**Never failed in the window (verified by grepping the failure logs for ✖ lines):**
- `npm test` (611 tests, including 416 snapshots): 0 failures. Every red `test` job failed in `test:live`.
- Engine-driver replay: 0 failures on content it already had. Its one failure (43801405380) was 60 s timeouts on
  `solve/sudoku-9x9` and `solve/killer`, the recordings that PR #34 itself added.
- Tier C, the audit plants (`safety-net.live.mjs`) and the upstream-links test: 0.
- The fuzz: every failure was the akari timeout.
- UI-driver sample on PRs: 0.
- Upstream merge: 5 runs, all "nothing new" in 0.2 min. It has never actually tested a merge in the window.

The safety net (about 2,000 of 3,326 s) caught nothing on a PR in 8 days. Every substantive catch came from solve-UI
tests, which is where the PRs' code is.

##### 5. Inventory (verified, `git ls-files`)

| What | Files | Notes |
|---|---|---|
| `live/recordings/**` (`*.steps.json` + `*.expected.json`) | 536 | 268 recordings; 19.7 MB; 425,276 lines added since 2026-09-01. Data |
| `test/snapshots/**.json` | 414 | **Upstream's** puzz.link snapshots, last touched by upstream 2026-06-01. Nothing writes them. Data |
| `live/*.live.mjs` | 70 | 12,183 lines of test code |
| `live/*.mjs` helpers + `live/ui-fuzz/` | 18+ | 15,995 lines in `live/*.mjs` in total |
| `test/*.test.mjs` + helpers | 14 mjs + 4 public | 1,289 lines |

- **Test cases (run 44139528665):** `npm test` has 611 tests: 416 snapshots, 33 for the recordings hook, 31 for
  `.gitattributes`, and so on. `test:live` has 1,840 leaf tests: 536 engine replay, 373 "Mouse card against the board",
  165 "answer after a resize", 29 Tier C, and the rest spread over about 60 files.
- **Test lines vs source:** about 17.3k lines of fork test code (`live/` plus `test/`) against about 12k lines of fork
  source (`docs/ui` 7.8k, plus +2.1k in `docs/js` and +2.2k in other `docs/` since September). `docs/js` itself is
  67.7k lines, mostly upstream.
- **Growth since 2026-09-01 (`git log --numstat`):** live test code +17,234/−1,239, `test/` +1,276, docs/ui +8,779,
  docs/js +2,081, recordings +425k.
- **Last 40 merged PRs:** 7,086 test lines added against 2,205 code lines. The median per-PR test:code ratio is 2.87,
  and 38 of 40 PRs added more test than code.

##### 6. Redundancy candidates

1. **Engine-driver replay, fuzz and Tier C on PRs that cannot reach them (verified load graph).** The engine driver
   opens `docs/index.html` (`live/page.mjs:9`), which loads nothing under `docs/ui/` (`grep -c "ui/" docs/index.html` =
   0) and not `engine_bridge.js` (only `solve.html` loads it, solve.html:133). PR #280's skip list still runs the full
   set for any `docs/js/engine_bridge.js` change (11 of the last 40 PRs) or `live/page.mjs` change (8 PRs), so only 15 of
   40 PRs skip. A rule keyed on what `index.html` loads (`docs/js/**` minus `engine_bridge.js`, `docs/index.html`,
   recordings, and the engine helpers incl. `page.mjs`) lets 25 of 40 skip.
2. **The UI corpus on the PR path:** already sampled. PRs replay the hand-made recordings plus 10 named ones
   (`live/ui-replay-part.mjs:16-29`), 288 s of test time; nightly replays all of them. This split is already lean.
3. **Local gate and CI both run the full seam on the same tree.** The controller's pre-merge rerun repeats what the
   required, strict `test` check already proves on GitHub.
4. **The push run repeats the PR's tree:** 16 of 20 since strict mode.
5. **Duplicate suites:** none of substance. `replay.live.mjs` ("the engine driver", 72 s) sits next to the three
   engine-replay parts. I did not check whether it repeats them.
6. **Snapshots that only get regenerated:** no. Upstream's snapshots are never written (AGENTS.md:51-52) and cost about
   seconds. Recording expected files are gated by `recordings:approve` and the `expected-files` job, so they are not
   bulk-regenerated.
7. **Slowest PR-path tests after #280:** the solve-UI bucket (1,362 s), led by mouse-card (110 s), desk (75 s),
   grid-numbers (56 s) and reset-layout (56 s).

##### 7. Existing tickets

The query was `gh issue list --search "CI OR slow OR corpus OR flaky" --state all --limit 40`.

- **Open:** #268 CI: run the safety net only on engine changes and nightly; split test across runners (PR #280 open) ·
  #267 Engine replay: load each recording into an open page, not a fresh boot · #265 Flaky: pins-polish swatch rows read
  once instead of settled · #195 Spec: a solve.html UI fuzz with fast-check, run nightly · #263 · #6 · #5
- **Closed:** #171 Flaky under load: upstream-prs warning setting · #126 Akari seed-3 fuzz times out at 60 s on CI ·
  #82 Split the engine-driver replay into three test files so test:live fits ~5 min · #76 Cap test concurrency at 4 ·
  #221 Require PR branches to be up to date with master · #80 UI driver: replay the tier A/B corpus · #26 Safety net
  seam · #32 Measure the safety net · #33 Gate expected-file changes · and others in the query output

---

##### Ranked recommendations

**R1. Land #280, but widen what skips the engine side to "cannot reach index.html".** The mechanism is `live/run-live.mjs`'s
selection. Run the engine-driver parts, fuzz, Tier C, `replay.live.mjs`, plants and upstream-links only when the diff
touches `docs/js/**` other than `engine_bridge.js`, `docs/index.html`, `docs/css/**`, `live/recordings/**`, the engine
helpers (`replay.mjs`, `engine-replay-part.mjs`, `canonical-state.mjs`, `page.mjs`, `settle.mjs`, `fuzz.mjs`,
`tier-c*.mjs`, `plants.mjs`), `package*.json` or `.github/**`. A solve.html change keeps the UI-driver sample, which is the
part that exercises `engine_bridge.js`.
- *Saves:* each PR CI run goes from 13–20 min wall to about 3 min (probe-268-ui's slowest part was 166 s). Across 2.7
  runs that is about 30–45 min of wait per PR. It applies to about 25 of 40 PRs, against 15 of 40 under #280 as written.
- *Given up:* a solve-page-only change that alters engine behaviour on `index.html`. The load graph says that cannot
  happen. A shared helper is the exception, and it stays on the run-all list.
- *Afterwards:* the master push run (full set) and #280's nightly.

**R2. Drop the controller's local seam rerun for this repo, and add a `**Narrowed**` line** (`npm test && node
live/run-live.mjs --base origin/master` once #280 lands). The required, strict `test` check already runs the same command
on the up-to-date merge.
- *Saves:* one full local seam per PR, about 15+ min on a loaded box (not measured), and it takes Chromium load off
  the shared machine. That load is the stated cause of the flakes in #171 and #265.
- *Given up:* nothing CI does not do.
- *Afterwards:* the required `test` check.

**R3. Add `concurrency: { group: ci-${{ github.ref }}, cancel-in-progress: ${{ github.event_name == 'pull_request' }} }`
to ci.yml.**
- *Saves:* 50 superseded PR runs and 428 runner-minutes in the window. It also frees runner slots, so a re-pushed
  PR's run starts sooner. Wall time saved per PR is small: just the queueing.
- *Given up:* the result for a sha that is already obsolete.
- *Afterwards:* the newer run.

**R4. Fix or quarantine the flakes and give the 60 s timeouts headroom.** File a ticket for "the top bar on a laptop
screen" (5 reds, 2 proven on identical trees) and for the Settings-dialog focus test (2 master reds). #265 is already
open.
- *Saves:* about 4% of runs re-run, roughly 15 min each time it fires.
- *Given up:* nothing. A flaky test protects nothing.
- *Afterwards:* the fixed test.

**R5. #267 (reuse the page across engine replays).** Profile first, as the ticket says.
- *Saves:* if boot dominates (median 4.9 s per recording), up to about 1,000 s of the 1,339 s on every push, nightly and
  engine-touching PR.
- *Given up:* isolation between recordings. A leak from one recording into the next could show as a false red. It cannot
  hide a regression unless state bleeds in a way that masks it, which is not verified.

**R6. Keep the master push run, but make it the only full run outside nightly, and fold `ui-corpus.yml` into #280's
nightly so a red night files an issue.** The 2026-11-17 nightly UI-corpus failure (about 16 recordings on solve.html)
has no issue. That is a protection gap rather than a cost.

**Do not cut:** `npm test` (10–17 s, 611 tests, cheap), upstream's snapshots (seconds, never written), the
`expected-files` gate (10 s; caught one unlisted change) or strict up-to-date merging (the pre-#221 master break shows
it has value). Once R1 makes CI about 3 min, strict mode's re-runs stop hurting. A GitHub merge queue would remove them,
but my understanding is that it is not offered on personal-account repos (not verified).

##### Verified vs not verified

**Verified:**
- workflow configuration (file:line above);
- all run counts, durations, failure classes and step timings;
- the push/PR same-tree overlap;
- superseded-run counts;
- the inventory and line counts;
- per-PR run counts and master-merge commits;
- the engine driver opening `index.html`, and `index.html` loading no `docs/ui` file or `engine_bridge.js`;
- PR #280's shape and its 15/40 skip rate (simulated over the PRs' file lists).

**Not verified:**
- local seam duration and how often it actually runs per PR (inferred from the implement skill, not measured);
- whether the 6-run keyboard/focus cluster was a real integration break or flaky;
- the 12 "PR's own work" failures as real bugs rather than test bugs (one was fixed test-only);
- the 25/40 figure under R1, which is a path simulation; `docs/css` and other shared assets loaded by `index.html` need
  a full load-graph check before the rule is written;
- R5's saving, which depends on #267's profile;
- merge-queue availability on a personal-account repo;
- whether "the engine driver" in `replay.live.mjs` duplicates the per-part replays.

### Appendix: solver-repos

#### Test-cost survey: grid-hunts, gridfind, sudoku-kit, sudokumaker-custom-constraints

Surveyed 2026-11-17. Window: runs created on or after 2026-10-18 (30 days).
Raw data and scripts: `/tmp/claude-1000/-home-caneff-src--claude-worktrees-skills-worktree-lucky-forest-8e9c/295706f2-f278-49a6-b049-9abbd1d87bb4/scratchpad/data/`
(`runs-<repo>.json` from `gh run list --repo caneff/<repo> --limit 1000 --created '>=2026-10-18' --json ...`;
`ghsum/` and `smsum/` hold the gate's last line from every push/PR run log; `stats.py` computes the duration table, using `updatedAt - startedAt`).
Nothing was run locally beyond `git log/ls-files/show`, `gh` reads and reading logs.
One deviation: I ran `git fetch -q` once in `~/src/grid-hunts` before deciding to avoid it. It only updated remote-tracking refs, and local main already equalled origin/main.

##### Cross-repo facts that frame everything

- **All four repos are public** (`gh repo view --json isPrivate` gives false for each), so Actions minutes cost no money. The cost is **latency and agent/box time**.
- **CI is on the merge critical path in practice.** The controller merges only when `gh pr view` shows `CLEAN` (`~/.agents/skills/flow/claude/OPERATIONS.md:327-330`). Measured: in grid-hunts 0 of 61 PRs, in custom-constraints 1 of 69 and in sudoku-kit 0 of 33 merged before their PR CI run finished. The median gap from CI end to merge is 0.7 min (grid-hunts) and 0.8 min (custom-constraints). The median time from PR open to merge is 4.8 min and 8.4 min.
- **Agents push once per PR.** In all three live repos, 60 of 62, 68 of 69 and 32 of 33 merged PRs had exactly one `pull_request` run. Re-pushes and `concurrency` are not a PR-side problem.
- **Merged work flows as slice PR → `spec-<n>` → spec PR → main.** In 30 days grid-hunts merged 47 slice and 15 main-based PRs, custom-constraints 48 and 21, sudoku-kit 25 and 8. Each slice gets one CI run, the spec PR gets another, and the post-merge push to main gets a third.
- **Per-change local gate** (`~/.agents/skills/implement/SKILL.md:430-449`): the worker runs the repo's `**Narrowed**` command once before "PR up", and the merger runs "the same command again on the PR merged into current `<default>`". Open ticket agent-skills **#1949**, "drain: skip the merge rerun when the worker's tested sha is the head", targets that duplicate.
- **Nightly local backstop** (`systemctl --user cat backstop.service`, `~/.agents/skills/flow/backstop-repos`). It lists `~/src/sudokumaker-custom-constraints` **without** `workflow=` and `~/src/grid-hunts workflow=ci.yml`. So grid-hunts' nightly reads CI's result, while custom-constraints runs its full seam locally every night (see that section).
- No branch protection on main in grid-hunts or custom-constraints (`gh api repos/caneff/<r>/branches/main/protection` returns 404).

---

##### 1. grid-hunts (257 commits since 2026-10-01; highest volume)

###### Facts (verified)

**Workflow** `.github/workflows/ci.yml` (one job, `check`):
- Triggers: `push` to main, `pull_request` (any base, so slice PRs into `spec-*` run too), and a nightly `schedule` at 03:17 UTC (ci.yml:3-8). No `concurrency`, no matrix, no timeout, no path filters.
- Setup: checkout with `fetch-depth: 0`, setup-uv with cache, `uv sync`, and `pantsbuild/actions/init-pants@v11` (ci.yml:18-35). Setup measures about 25-35 s (step timings of runs 43912799310, 43880987985 and 44078336237).
- Gate step (ci.yml:37-58): a PR runs `tests/all.sh --changed origin/$BASE_REF`; a push runs `--changed $BEFORE`; the schedule runs `just check` (the full non-slow seam). `GATE_JOBS: 4` runs four suites at once.
- No pytest options: 85 of the 86 test files are standalone scripts run as `uv run <file>`. One pytest suite (`finders/counting_shaded/test_counting_shaded.py`) runs with `-q` (tests/all.sh:63-64). There is no xdist and no `--durations`.
- **Widening rule** (tests/all.sh:29-38, 155-160): any changed path outside `*.md`/`archive/` that Pants cannot place widens the run to all 79 non-slow suites. That includes every non-`.md` file under `docs/`. `docs/research` holds 730 json, 352 png, 204 jsonl and 182 py files (`git ls-files docs/research`).
- **The slow group runs nowhere automatically.** Nine suites (tests/all.sh:57-66): halver/between and halver/lockout hunts, the lockout 23-line board, the five slowest U-Bahn suites, and the Doppelganger 9x9 hunt. `just check` = lint + `--group test` (justfile:2,14-15), and the nightly runs `just check`. AGENTS.md:45-48 lists them under "Blind to".

**Measured cost, 30 days** (`stats.py runs-grid-hunts.json`):

| event | runs | median | p90 | total | failures |
|---|---|---|---|---|---|
| push (main) | 173 | 4.08 min | 5.62 | 694 min | 7 |
| pull_request | 64 | 3.08 | 5.63 | 218 min | 0 |
| schedule | 31 | 4.30 | 5.50 | 140 min | 1 |
| **all CI** | 268 | 4.03 | 5.62 | **1,052 min** | 8 (3.0%) |

No cancelled runs.

**Narrowed versus widened**, from the last line of all 237 push/PR logs (`ghclass.py`):

| | runs | median | total | suites (median) |
|---|---|---|---|---|
| push, narrowed | 42 | 0.63 min | 42 min | 5 |
| push, **widened** | **129** | **4.98 min** | **651 min** | 65-79 |
| PR, narrowed | 44 | 2.22 min | 105 min | 21.5 |
| PR, widened | 20 | 4.89 min | 113 min | 65 |

- **Widening causes: 128 of 149 widened runs came from a non-`.md` file under `docs/`**, such as research scripts, JSON and PNG. Examples: `widened: docs/research/2026-11-15-skyscraper-sudoku-all-fives/scripts/sky7Jcx.py` (run 43880987985) and `widened: docs/research/2026-11-04-numbered-rooms-pro-battenburg/full-targets-2.png` (run 42057686479). The rest: `tests/` 9, `.github` 5, `finders/*` 5, `pyproject.toml` 2.
- 167 first-parent commits reached main in 30 days, and only 20 carry a `(#N)` PR suffix (`git log --first-parent --since=2026-10-18 origin/main`). **Most pushes are direct research commits.** Each widens to the full gate.
- 56 of 173 push runs were superseded by a newer push while still running (148 min that `cancel-in-progress` would have saved).

**Per-step timing**, 3 recent widened runs (`gh run view <id> --json jobs`):

| run | setup steps | Install Pants | Gate (check) |
|---|---|---|---|
| 43912799310 (push, widened) | 17 s | 12 s | 239 s |
| 43880987985 (push, widened) | 7 s | 11 s | 338 s |
| 44078336237 (schedule, full) | 6 s | 9 s | 199 s |
| 43892201948 (push, narrowed) | 10 s | 8 s | **6 s** |

The gate step is the whole cost; setup is cheap. Per-suite durations are not printed. The runner prints only PASS lines, and timestamps at `-j4` give finish order, not durations. The best per-suite source is `docs/research/2026-10-13-gate-wall-clock.md` and `docs/research/2026-10-22-ubahn-suite-times.md`, measured alone on one core. Slowest suites still in the gate:

| s (alone) | suite |
|---|---|
| ~38 (127-158 s under CI `-j4`) | `counting_shaded/test_counting_shaded.py` (pytest, 47 tests) |
| 31.2 | `ubahn/test_ubahn_battenberg_hunt.py` |
| 20.9 | `ubahn/test_ubahn_hybrid_sat.py` |
| 18.7 | `ubahn/test_ubahn_hybrid_sat_hunt.py` |
| 17.6 | `ubahn/test_ubahn_number_circles_hunt.py` |
| 16.4 | `ubahn/test_ubahn_battenberg_sat.py` |
| 14.9 | `ubahn/test_ubahn_hybrid_model.py` |
| 13.6 | `ubahn/test_ubahn_hybrid_e2e.py` |
| 12.9 | `ubahn/test_ubahn_number_circles.py` |
| 10.7 | `ubahn/test_ubahn_hybrid_links.py` |

The 17 U-Bahn suites still in the gate sum to about 190 s serial (the 2026-10-22 table). Doppelganger and halver suites added since then were not timed alone.

**Failure value** (all 8 failures read with `gh run view <id> --log-failed`):
- **3 infrastructure**: the Pants launcher download returned `curl: (22) ... 504` (42471374222, 42046593761, 42045808576).
- **5 flakes, all one test**: `test_counting_shaded.py::test_lazy_connectivity_cuts_return_a_connected_shape`, `AssertionError: control: connected admissible shapes exist` (41725143542, 41840143624, 41890807105, 42057686479, 42070310216). Each failing sha was followed minutes later by a green push with no counting_shaded change in between. The test solves under a 60 s wall budget with 4 CP-SAT workers while three other suites share the 4-vCPU runner (`connected.solve_connected(m, g, 60, 4, ...)`, test_counting_shaded.py:290-296 today, unchanged from `de289edf`). In failing runs the suite took 127-158 s, against about 38 s alone. **All five flakes ran under a docs-widened push.**
- **0 real catches in CI in 30 days.** The `pull_request` leg went 64 of 64 green: it never failed. The nightly failed once (infra).

**Runs per PR** (10 most recent merged PRs: #176-#185): one `pull_request` run each, and 60 of 62 across the window. A slice costs one PR run. A spec costs its slices' runs plus a spec PR run plus a push run.

**Local gate.** AGENTS.md:52-55 says "run before each commit and before opening a PR: `just check`, the full seam", and a local run is serial (`GATE_JOBS` unset; AGENTS.md:56-58). The implement skill instead runs the `**Narrowed**` line once per PR plus once at merge. The two documents disagree. The repo logs no local runs. A scan of 72 grid-hunts transcripts since 2026-10-18 found about 344 distinct gate result lines: about 123 widened, 44 `--group test`, 5 `slow`, the rest narrowed or full. These are approximate: CI quotes and test fixtures are mixed in.

**Inventory**:
- 86 test files in `finders/` + `tests/`, plus 21 more in `archive/` that the gate skips. Test lines 19,839 against source lines 19,578 (1.01 : 1).
- 54 finder test files and 14,876 lines at 2026-10-18 (`git rev-list -1 --before=2026-10-18`), so +59% files and +33% lines in 30 days. The repo starts 2026-09-08, which makes 2026-09-01 moot.
- Last 26 non-integration merged PRs: test lines +2,756/−2,006 against code +3,270/−2,935, a ratio of 0.84 (`gh api repos/caneff/grid-hunts/pulls/<n>/files`).

**One-off finders.** The repo's own word for a finished finder is retirement to `archive/` (AGENTS.md:39; #45 did it for five). What remains:

| finder | test files | test lines | src lines | commits in 30 d, by kind |
|---|---|---|---|---|
| ubahn | 25 (+5 slow) | 7,911 | 5,256 | no feature commit since 10-22; only the specs #115/#117 refactor and Pants wiring |
| hunt (shared layer) | 18 | 4,473 | 2,402 | live shared code |
| halver_between | 12 | 1,692 | 444 | spec refactors, #110 driver |
| doppelganger_rank | 9 (+1 slow) | 1,330 | 1,371 | created 10-22, refactors since |
| qqrr | 9 | 1,487 | 2,020 | refactors only (#158, #185, #148) |
| halver_lockout | 8 (+2 slow) | 959 | 510 | refactors, #110 |
| counting_shaded | 1 (47 tests) | 510 | 4,602 | refactor #185 only |
| query | 1 | 626 | 678 | new 11-07 |

By that reading **ubahn, qqrr and counting_shaded** (35 gate test files, about 9,900 test lines, about 230 s serial) are done finders. All their commits in the window came from cross-cutting sweeps. Their tests now serve as consumer tests of `finders/hunt` and of sudoku-kit.

**Tickets**: all closed. #18 "Cut the gate's wall clock: parallel suites in CI, trim repeated U-Bahn enumerations", #42 / #43 narrowed CI with weekly full run, #45 archive finished finders, #76 Pants selection, #77 five slowest U-Bahn suites to slow, #145 / #147 counting_shaded / qqrr tests. **None open about CI or test time.**

###### Recommendations (ranked)

1. **Stop docs/research data and scripts from widening the run.**
   - *Mechanism*: in `tests/all.sh`'s path loop, treat `docs/research/**` like `*.md` unless the path's first two components appear in a string under `finders/`. Today only `docs/research/counting_shaded`, `docs/research/2026-10-11-u-bahn-number-circles` and `docs/research/2026-10-22-doppelganger-rank-opening.png` are referenced that way (`grep -rhoE 'docs/research/[A-Za-z0-9_.-]+' finders`). Those keep widening, or get a BUILD `resources` target so Pants places them.
   - *Saves*: about 4.4 min per research push (5.0 → about 0.6 min). That is about 560 of the 1,052 CI minutes a month, and removes the docs-widened pushes that hosted all 5 flaky failures. Research pushes do not block merges, so the latency win is small: it is mostly noise and flake exposure.
   - *Gives up*: nothing that is tested today, since no finder test reads an unreferenced dated research dir. A research script that imports a finder is not a test either way.
   - *Catches a regression*: the nightly full `just check`, which the backstop reads.
2. **Fix or quarantine `test_lazy_connectivity_cuts_return_a_connected_shape`.** It is the only flaky test, behind 5 of 8 failures, and a 60 s wall-clock CP-SAT solve in the gate.
   - *Mechanism*: make it deterministic (`num_workers=1`, a fixed seed, a smaller instance or a deterministic time limit) or move it to the slow group.
   - *Saves*: false reds and their re-diagnosis. It is also the long pole of a widened run (127-158 s under `-j4`), so about 1 min per widened run.
   - *Gives up*: nothing if made deterministic; some per-PR lazy-cut coverage if moved.
   - *Catches a regression*: the other 46 counting_shaded tests and the nightly.
3. **Add `concurrency: {group: ci-${{ github.ref }}, cancel-in-progress: ${{ github.event_name == 'push' }}}`.**
   - *Saves*: 56 superseded push runs, 148 min a month. It matters less once rec 1 lands.
   - *Gives up*: a per-commit verdict on intermediate direct pushes. The next push and the nightly cover the same tree.
4. **Make AGENTS.md's per-commit gate the narrowed one.** AGENTS.md:52-55 says the full serial `just check` "before each commit". The implement flow runs `Narrowed`. This is a doc-vs-skill contradiction for Chris to rule on.
   - *Saves*: a serial full gate on the shared box at every commit. At the 2026-10-13 measure that was about 564 s for 64 suites, and the suite count has grown since. Not timed today.
   - *Gives up*: nothing that the merge-time narrowed run and the nightly do not cover.
5. **Freeze done finders.** Move ubahn, qqrr and counting_shaded to `archive/` (the repo's own retirement rule), or create a `frozen` group that runs nightly only, so PR runs that touch `finders/hunt` or sudoku-kit do not select them.
   - *Saves*: up to about 230 s serial (about 1 min at `-j4`) on PRs touching shared code, and the upkeep of about 9,900 test lines during sweeps such as #115-#118.
   - *Gives up*: same-PR detection that a shared-layer change broke a done finder. It moves to the nightly (backstop files a ticket) or, if archived, to never.
   - Only worth doing if Chris accepts that a done finder may silently rot (archive) or break overnight (frozen).
6. **Gap, not bloat**: the slow group never runs automatically. Adding `just test-slow` as a separate nightly leg would cost about 6-8 min of free runner time and nothing on the PR path.
7. **Infrastructure**: the Pants launcher download 504'd three times (and once in custom-constraints). A retry around `init-pants`, or pinning and caching the launcher, removes 3 of 8 failures.

---

##### 2. sudokumaker-custom-constraints (155 commits; second-highest volume)

###### Facts (verified)

**Workflow** `.github/workflows/ci.yml`, one job `gate`:
- Triggers: push to main, `pull_request`, schedule at 03:17 UTC, and `workflow_dispatch` (ci.yml:3-9).
- Matrix (ci.yml:28-31): push and PR get one leg, `narrowed`. Schedule and dispatch get four legs: `check`, `test-heavy-fillomino`, `test-heavy-recovery`, `soundness`.
- No `concurrency`, no timeout, no path filters. `PANTS_PROCESS_EXECUTION_LOCAL_PARALLELISM: 4` (ci.yml:27, #872). Pants `local_cache = false` and `[test] force = true` (pants.toml), so nothing is cached.
- `examples/_shared/ci_workflow.test.py` pins the scheduled legs to `just check-full` (ci.yml:18-20).

**Measured cost, 30 days**:

| event | runs | median | p90 | total | failures |
|---|---|---|---|---|---|
| pull_request | 70 | 5.99 min | 10.15 | 463 min | 1 |
| push | 45 | 5.82 | 8.30 | 267 min | 2 |
| schedule | 31 | 5.85 | 7.33 | 182 min | 1 |
| dispatch | 1 | 4.90 | | 5 min | 0 |
| **all** | 147 | 5.85 | 8.90 | **917 min** | 4 (2.7%) |

**Narrowing barely narrows** (last line of all 115 push/PR logs):
- **42 of 115 runs selected every suite.** The most recent ones read `164 of 164 suites passed` (43635390517, 43633093823) and `158 of 158 ... (narrowed: examples/_shared examples/count-digits-gac ...)` (43596525929).
- Duration by suites selected (successful runs): <40 suites, 36 runs, **4.74 min** median; 40-120, 25 runs, 5.07; 120-all, 9 runs, 5.75; all, 42 runs, 7.25. **A small diff still costs about 4.7 min.**
- **Where the floor goes.** Run 43486060481 selected 31 suites, `narrowed: examples/_shared`, and its gate step took 212 s.
  - Lint: 11 s.
  - The non-Pants "sandbox exception" suites, which run serially on every run (`tests/sandbox-exceptions.txt`): **87 s**. Of that, `spec_809_closing.test.py` 41 s, `app-session.test.mjs` 26 s and `spec_649_closing.test.py` 17 s.
  - Then one Pants call for 20 wired suites, all of which declare `//:tree` and are therefore selected by any change: **115 s**. Among them: the closing tests `spec_748/855/865/895/896/897/898_closing`, and the gate meta-tests `gate`, `seam_runner`, `ci_workflow`, `recipe_discovery` and `known_edges`, which start Pants, `just` and `tests/all.sh` inside the sandbox (examples/_shared/BUILD:111, 195-245).
- **Per-step timing** (`gh run view --json jobs`): runs 43633093823, 43596525929 and 43635390517 took 442 s, 279 s and 364 s in the narrowed step. The longest setup step is Playwright Chromium, 17-28 s. On the nightly (44077346565) the `check` leg is the critical path at 199 s of gate; the heavy and soundness legs take 28-57 s.
- **Pants named cache misses on every run.** Every `init-pants` run logs `Cache not found for input keys: pants-named-caches-Linux-v0-...` (e.g. log of 43596525929), and the post step never saves one. Impact not measured.
- Per-test durations: none available. Pants prints every wired result at once after the call ends.

**Local gate** (`~/.cache/sudokumaker-custom-constraints/seam-runs.jsonl`, written by `tests/all.sh`, 30 days):
- Narrowed: 118 runs, median **412 s**, max 820, total 699 min, **32 red (27%)**.
- Widened: 26 runs, median 465 s, 189 min, 7 red.
- `--group test` (the `just check` body): median **316 s**, max 706. AGENTS.md:141-142 still says "about 1¾ min (104 s measured 2026-10-12). Run it before each commit". **The per-commit build loop has tripled and the doc is stale.**
- **Nightly backstop runs `check-full` locally** on all 30 nights: 148 group runs at 00:3x/06:xx, 214 min on the shared box. CI's nightly schedule already runs exactly that. The backstop list gives this repo no `workflow=ci.yml` (`~/.agents/skills/flow/backstop-repos`), unlike grid-hunts.
- One local `heavy-fillomino` run on 2026-11-05 took 22,128 s (6.1 h, a hang). Related ticket #890 is closed.
- Excluding the backstop, local gate time was **about 1,069 min across 69 merged PRs: about 15 min of one core per PR**, about 3.3 runs per PR. 24 shas ran a non-group gate twice and 5 ran it three times.
- **Doc conflict**: AGENTS.md:126-131 says the controller re-runs `just check-full` before every merge (ruling 6a). `implement/SKILL.md:447-449` says the merger re-runs the narrowed command, and the log has **no `full`-mode run in 30 days**. Practice follows the skill; the doc is stale or the ruling is unenforced. This is for Chris to rule on.

**Failure value**:
- CI, 4 failures: **3 real catches** of one bug, `sudoku_kit_source.test.py`: `AssertionError: paths into a gridfind checkout` (39475051784 push, 39477216920 push, 39478154746 PR, all 2026-10-20). Two of the three were on pushes to main, so the bug landed before CI caught it. **1 infrastructure**: the Pants 504 plus `ECONNRESET` in the nightly (42470792476).
- Local: 39 red local runs out of 144. I did not classify which were work-in-progress catches.
- The `test-heavy-recovery` and `soundness` legs had no CI failure in the window. Only one scheduled run failed at all, from infrastructure.

**Runs per PR** (#985-#995): one `pull_request` run each, and 68 of 69 across the window.

**Inventory**:
- 156 test files, 25,275 lines, against 204 source files and 37,818 lines (excluding `original/`, `docs/research`, `*.min.js`). 275 Python `def test_` functions.
- Growth: 39 files and 6,439 lines at 2026-09-01 (that tree still held the finders later cut to grid-hunts, so the comparison is loose); 120 files and 20,135 lines at 2026-10-18; 156 files and 25,275 lines now.
- **14 `spec_*_closing` tests, 2,515 lines.** Their only home is `examples/_shared`; most declare `//:tree`, and two are sandbox exceptions.
- Last 24 non-integration merged PRs: test +1,834/−1,138 against code +1,749/−1,328, a ratio of 1.05.

**Tickets**: all closed. #846 "CI: run the narrowed seam per change; full gate nightly only", #872 "CI: run the wired suites' Pants call on the runner's 4 cores", #829 "Pants follow-ups: narrow //:tree, shrink the sandbox exception list", #411 "just check runs the whole example suite on every invocation", #424 "Run check-full's heavy tier as parallel CI jobs", #890 "Fillomino: the shipped board must not set the gate's time". Prior research: `docs/research/2026-10-16-pants-narrowing-rate.md` and `docs/research/2026-10-22-pants-wall-time.md` ("Has Pants made the gate faster? ... Not measurably"). **None open.** agent-skills #1949 is open and covers the merge rerun.

###### Recommendations (ranked)

1. **Point the local backstop at CI.** Add `workflow=ci.yml` to the custom-constraints line in agent-skills `flow/backstop-repos`.
   - *Saves*: about 7 min of shared-box CPU a night (214 min a month). Not on the PR path.
   - *Gives up*: nothing. CI's scheduled legs run the same recipes, and `ci_workflow.test.py` holds that equal.
   - *Catches a regression*: the backstop reads the CI scheduled run and files the same red-night ticket.
   - This is a one-line change and the cheapest win in the survey.
2. **Shrink the always-selected floor**, about 3.4 of the 4.7 min a small-diff CI run costs and likely most of the 412 s local narrowed median.
   - (a) Move the `spec_*_closing` tests off the per-change path into a nightly-only group, or delete the ones whose assertions unit tests now cover. A closing test proves a spec once at close; afterwards it copies the tree on every change.
   - (b) Give the five gate meta-tests a narrower `needs` (`//:runner`, `//:justfile`, `.github/workflows/ci.yml`, the BUILD files) instead of `//:tree`. They should select on runner and wiring changes, not on every example edit.
   - (c) Wire or replace `spec_809_closing`, `spec_649_closing` and `app-session` (84 s serial on every run).
   - *Saves, estimated*: 2-3 min per CI run (on the merge path, about 2 runs per slice) and 3-5 min per local single-core run (2 per PR). Per-suite times inside the Pants call were not measured, so this is not verified.
   - *Gives up*: per-change detection that a later change broke an old spec's acceptance (this moves to nightly), and per-change checking of new-test wiring (this moves to the runs that touch BUILD or the runner).
   - *Catches a regression*: the nightly CI full gate plus the backstop ticket. Its selector verdict shows which merge first missed it.
3. **Fix the stale build-loop doc** (AGENTS.md:141-146): the per-commit `just check` is now about 5.3 min median locally, not 1¾.
   - *Mechanism*: per commit, run `bash tests/all.sh --changed origin/main`, or `just check` scoped to touched examples. Keep `check-full` nightly.
   - *Saves*: 2-5 min per commit locally.
   - *Gives up*: nothing the per-PR narrowed run does not cover.
4. **Resolve the AGENTS.md vs implement-skill conflict** on the merge-time full seam (ruling 6a against `implement/SKILL.md:447`), and land agent-skills #1949. Skip the merge rerun when the worker's tested sha is the PR head merged onto an unmoved base. GitHub's `pull_request` run already tested `refs/pull/N/merge` on that base, and the merge waits for it.
   - *Saves*: about 7 min of one core per merge, about 8 h a month across 69 merges.
   - *Gives up*: a second local run of an identical tree.
   - *Catches a regression*: the CI PR run (same tree) and the post-merge push run.
5. **Fix the Pants named-cache miss**: the `init-pants` named-caches cache is never saved. The effect on gate time is not measured; check it before counting on any saving.

---

##### 3. sudoku-kit (31 commits; low cost)

###### Facts (verified)
- `.github/workflows/ci.yml`: push to main and `pull_request`. The matrix is `python: ["3.11", "3.14"]` with `fail-fast: false` (ci.yml:12-19). Each leg runs `just check` = `tests/all.sh`: ruff check, ruff format check, `uv lock --check`, `pytest -q` (tests/all.sh suites array). No schedule, no concurrency, no timeout.
- 30 days: **53 runs, median 0.52 min, p90 0.68, total 28 min**, 3 failures (5.7%).
- Failures: all 3 were PR `implement-59` (41696972954, 41697228596, 41697440688). Only the **3.11 leg** failed: `tests/test_link_codec.py::test_decode_refuses_a_payload_nested_too_deep_for_json - AssertionError: Regex pattern did not match`. That is **a real interpreter-difference catch by the matrix**, which is exactly why ci.yml:9-11 keeps it.
- Inventory: 12 test files, 2,407 lines, 176 test functions, against 1,142 source lines (2.1 : 1). The last 26 non-integration PRs added test/code lines at a 1.21 ratio. 10 most recent merged PRs: one PR run each.
- AGENTS.md:21-33: the seam runs in seconds, so `--changed` runs everything. It is blind to consumers, which pin a commit in `uv.lock`.
- Duplication with consumers: grid-hunts has 11 test files and custom-constraints 39 test files that import `sudoku_kit`. They use the codec to build their own links and do not re-test codec internals (spot check of `grep` hits such as `grid-hunts/finders/hunt/test_short_link.py` and `examples/_shared/sudoku_kit_source.test.py`, which guards against local copies). No duplicate suite was found.
- Tickets: #7 and #64, both closed.

###### Recommendations
- **None worth making.** About 30 s per run, and the one matrix leg that looks redundant caught a real bug in the window. Optional: drop the `push` trigger (17 runs, 9 min a month), since every change lands via a PR that already ran both legs. That would save nothing a person waits on.

---

##### 4. gridfind (4 commits since 2026-10-01; archived)

###### Facts (verified)
- **The repository is archived**: `gh api repos/caneff/gridfind --jq .archived` gives `true`, and the README's first line reads "Archived 2026-10-12 (decided 2026-10-08)". Codec → sudoku-kit, finders → grid-hunts.
- **Zero workflow runs since 2026-10-12.** The last were CI on 2026-10-12, clear-in-review on 2026-10-12 and Nightly on 2026-10-11. The 4 commits since 2026-10-01 are all pre-archive.
- Historical numbers (2026-08-22 to 2026-10-12, 300 runs): CI 126 runs, median 0.90 min, 16 failures. Nightly (`slow` + `e2e`) 50 runs, median 0.58 min. Clear in-review 124 runs, median 0.13 min. Workflows: `ci.yml` (push to main + PR: pre-commit then pytest), `nightly.yml` (`just slow`, `just e2e`), `clear-in-review.yml` (daily label sweep).
- `~/.agents/skills/flow/claude/REPOS.md` still lists gridfind as an active repo, which is stale.

###### Recommendations
- **Nothing to cut.** Archived repos run no Actions. Remove gridfind from REPOS.md's active list so future surveys skip it.

---

##### Verified versus not verified

**Verified** (command or file cited above):
- Every per-workflow config fact.
- 30-day run counts, durations, failure and cancel counts.
- The narrowed/widened split and widening causes from every push/PR log in grid-hunts (237) and custom-constraints (115).
- Step timings on 3-4 runs per repo.
- All 15 failures read and classified.
- Runs per PR, and merge-after-CI timing.
- custom-constraints local gate counts and durations from its run log.
- The backstop configuration.
- Test file, line and growth counts.
- Test/code lines added over the last ~26 PRs per repo.
- gridfind archived.

**Not verified**:
- Per-suite durations inside custom-constraints' Pants call, and per-suite durations in grid-hunts CI. Only the `-j4` finish order is logged; grid-hunts single-core figures come from the repo's 2026-10-13 and 2026-10-22 notes.
- The savings estimates for custom-constraints rec 2 and grid-hunts recs 4-5.
- grid-hunts local gate counts. There is no run log; the transcript scan (about 344 result lines) is approximate and includes quoted CI output.
- Whether red local custom-constraints runs (39 of 144) were real catches or flakes.
- Whether the Pants named-cache miss costs measurable time.
- That the controller waits for CI by policy. It is inferred from the `CLEAN` precondition and the measured under-1-minute CI-to-merge gap, not from a skill line that says "wait for checks".
- Whether the done finders' tests caught anything during the 2026-11-13/14 refactor sweeps. That would need the sweep PRs' local logs.

### Appendix: small-repos

#### Test-cost survey: ten smaller repos (read-only, 2026-11-17)

Method: `gh run list --repo caneff/<n> --limit 200 --json ...` saved per repo (runs-<n>.json in the scratchpad), duration = updatedAt - createdAt (includes queue wait, not billed minutes). `gh pr list --state merged --limit 20 --json files`. Workflow files, AGENTS.md, justfile/package.json read from `/home/caneff/src/<n>`. No test suite run, nothing written inside any repo. "Last 30 days" = since 2026-10-18.

Overall verdict: CI time is not where the bloat is. Total CI across all ten repos is a few hundred wall-minutes in two months, on private repos inside the free tier (only visual-teach is public). The real cost is (a) test volume that grows faster than code in the two agent-heavy repos (twitch-rules-scroller, sudokupad-art), which inflates every local gate and every review that re-runs it, and (b) in twitch-rules-scroller, the live e2e layer that is human-attended. The claim "too much run per PR" is mostly false for CI and partly true for local gates.

---------------------------------------------------------------------------
##### second-brain-v2 (292 commits total; 81 since 2026-10-01, 43 since 10-18)

###### Verified
- Workflows: `.github/workflows/check.yml` (on: `pull_request:` with no path filter, plus `push: branches: [main]`; no `concurrency`; one job: checkout, setup-uv, setup-just, `just check`) and `clear-in-review.yml` (on issues closed; `if: contains(labels,'in-review')`).
- Push + pull_request: both fire, but on different commits (PR head vs the merge commit on main), so not a literal duplicate. Count in last 200 runs (Aug 31 to Nov 17): 153 push, 17 PR, 30 clear-in-review (all skipped). 30-day window: 45 push runs, 0 PR runs.
- Where the pushes come from: `git log --since=2026-10-18` shows 43 commits, 35+ are "vault autocommit <date>" (autocommit.py, ~daily at 11:00 plus extras). Each one runs the full `just check` on a commit that changes vault markdown, not scripts. 25 of the 45 push runs in 30 days are in November, almost all autocommits.
- Cost, 30 days: 45 runs, median 0.3 min (~18 s), total 43 min wall, of which 24.2 min is one outlier (2026-11-04 16:00, success; queue/runner delay). Without it ~19 min. One failure in 200 runs (2026-10-22, 5.1 min), which looks like infra, not a test (not log-checked: not verified). All-time sample: 170 check runs = 81 min.
- Local gate: `just check` = `ruff check`, `ty check`, `uv run --with pytest pytest .claude/scripts` (justfile:4-17; its comment says it is "the gate Sandcastle's implementer runs per issue"). CI runs exactly the same command (check.yml last line). So CI repeats the local gate verbatim.
- AGENTS.md has no "End-to-end seam" section (grep for seam/gate/test returned nothing). The gate is only declared in the justfile.
- Inventory: 10 test files, 363 `def test_` (grep), 4,486 test lines vs 3,438 script lines (9 non-test modules in .claude/scripts). Ratio 1.3:1. Largest: test_retro.py 1,435 lines/104 tests vs retro.py 1,166; test_capture_bot.py 741; test_todos.py 743.
- Last 20 merged PRs (`gh pr list`): test lines added 1,407 vs code lines added 782 (1.8:1), across #118-#172, all Aug-Oct. 6 of the 20 touch no code or test (docs/skill).
- Tickets about CI/test time: none. Only #149 "test_retro: assert the retried model call resends the same request" (closed; test quality, not cost).

###### Not verified
- How long `pytest` itself takes (CI step timings not pulled); whole job is ~18 s median so it is small.
- Why the 2026-10-22 run failed.

###### Is it bloated?
No on CI. Test:code ratio 1.3 to 1.8 is high-ish but the suite is tiny (363 tests, job ~18 s). The one real waste is running the full gate on vault-content autocommits.

###### Recommendations (ranked)
1. Add `paths:` filter to check.yml `push` (and `pull_request`): `.claude/scripts/**`, `pyproject.toml`, `uv.lock`, `justfile`, `.github/workflows/check.yml`. Mechanism: autocommit pushes of markdown stop triggering. Saving: ~35 of 45 runs/month, ~15 wall-min/month (tiny). Protection given up: none for vault commits, since nothing under test reads them... except confirm no test reads vault files (not verified). One catch: if branch protection requires `check` as a status, a path-filtered workflow leaves required checks pending on PRs that touch only markdown; use a filter on `push` only and leave `pull_request` unfiltered. Regression catch: the unfiltered PR run, plus the local `just check`.
2. Add `concurrency: {group: check-${{ github.ref }}, cancel-in-progress: true}` for pull_request only. Saving: nearly nothing at 17 PR runs per 80 days. Skip unless PR volume rises.
3. Do not cut tests here. test_retro.py at 1.2x its source is the only candidate for a trim and it is cheap to run.

Opposite finding: none. 292 commits, mostly docs and autocommits; the script layer is gated.

---------------------------------------------------------------------------
##### twitch-rules-scroller (836 commits total; 319 since 2026-10-01; ~185 since 10-18; 12 of the 319 are revert/reapply/re-land)

###### Verified
- No `.github/` directory; no workflows (`ls .github` fails). Repo is private; Actions enabled but unused (`gh api .../actions/permissions`). `gh run list` returns `[]`. So CI cost is zero and nothing runs per PR on GitHub.
- No git hooks beyond the commit-identity guard (the common-dir hooks are `commit-identity-guard*` only).
- The scan's "0 test files" is wrong: tests are `*.test.mjs` run by `node --test`. 205 test files (`git ls-files | grep .test.`), 3,613 `test(`/`it(` lines, 49,629 test lines vs 38,646 non-test source lines (.mjs/.js/.cs/.py/.sh), 1.3:1. Breakdown: 54 `server.*.test.mjs` plus `server.test.mjs` (10,100 lines); 29 `e2e.*` files, tests of the e2e harness: 12,828 lines testing a 10,207-line harness (e2e.*.mjs + e2e/) which is itself the live-scenario runner; 17 `spec-NNNN.seam.test.mjs` files (2,596 lines).
- Local gate: AGENTS.md "End-to-end seam" (line 320-324). Seam = `npm test` (`run-tests.mjs`, wraps `node --test`, honours `TESTS_JOBS`), fakes-only. Worker runs the narrowed form `node changed-tests.mjs origin/main` before PR (selects tests by reference closure; widens to full on anything it cannot place). The merge re-runs the full `npm test` on the merged tree (line 322, 144-146). At run close the controller runs `./e2e.sh` once on main, real OBS/Chrome on a virtual monitor. A "nightly full run" (ruled 2026-10-16, issue #852) is the backstop; it is not in this repo (grep) but its output shows as issues "backstop: full seam red on main" #1027 (2026-11-08) and #1171 (2026-11-11), both closed. The nightly job lives in `~/.agents/skills` (drain / backstop files; not read in detail: not verified).
- Suite time: only measurement in repo is `docs/research/2026-10-08-js-mutation-testing.md:168`: full `npm test` 1761 tests / 67+ files = 40.8 s and 43.5 s. Now 205 files and 3,613 test lines, so roughly 2x; ESTIMATE only, ~80-90 s (not measured, machine overloaded).
- Last 20 merged PRs (#1320-#1354, Nov 15-17): test-side lines added (test.mjs, e2e*, goldens, fixtures) 6,712 vs code 1,673 = 4.0:1. Caveat: #1323 and #1327 (653 test lines each) are the same change re-landed, and #1324/#1329/#1320 are reverts; de-duplicated it is ~5,400 vs ~1,500, still 3.6:1. Single PRs: #1343 +1,273 test vs +180 code; #1331 +1,199 vs +421; #1337 +900 vs +490 (41 files).
- Churn: 12 revert/re-land commits since Oct 1. #1320, #1324, #1329 reverts say the change "breaks four switch-timing e2e" / "fails live scenarios", meaning the fakes-only seam passed and the live layer caught it afterwards.
- Existing test-cost tickets, all closed: #852 "Add a narrowed seam: npm test for only what a diff affects"; #912 FAIL line per file + TESTS_JOBS; #642 "Move the flaky-by-construction tests off real sleeps"; #647 "Delete the tests that cannot fail, fix the ones that check the wrong thing"; #727 split e2e.test.mjs; #1211 "Laptop tests that test the laptop"; #1213 delete test-only JS copy; #1232 "Server tests that stand alone and do not sleep"; #273 wire test-audit --gate; #310/#335/#521/#956/#944 flaky tests. Audit-sweep specs #1201/#1203/#1204. Open: none about suite time.
- Still 46 of 205 test files use setTimeout/sleep/delay( (grep), though #642/#1232 removed the worst.

###### Not verified
- Current wall time of `npm test` and `changed-tests.mjs` typical selection size.
- How often the full suite is actually run per PR by workers vs narrowed (no log).
- Whether the nightly runs are cheap (it is local, free in dollars, but takes cores).
- Which of the 3,613 tests are redundant; no coverage or mutation data. The 2026-10-08 research doc evaluated Stryker; not adopted.

###### Is it bloated?
Yes in volume, mild in cost. Test growth outpaces code ~4:1 in recent PRs, 12.8k lines test the e2e harness, and 17 spec-seam files duplicate what "each slice's own tests cover" (spec-1204.seam.test.mjs header says so). But the per-PR gate is already narrowed and no CI exists, so the money cost is zero; the cost is agent minutes on a local box with load ~40, and the review re-run cost. Counter-evidence that it is not over-gated: reverts show real regressions only live e2e sees.

###### Recommendations (ranked)
1. Retire spec-NNNN.seam.test.mjs files once their spec closes (17 files, 2,596 lines, ~5% of test lines). Mechanism: they are one-time "closing checks" (header of spec-1204) that overlap the slice tests; keep any that assert a cross-module story with no other owner. Saving: ~5% of lines and some seconds per full run; more importantly stops the per-spec growth pattern. Protection given up: cross-slice story check; the nightly backstop and live e2e still cover. Catch: nightly backstop issue (#1027-style) plus e2e run.
2. Cap new-test volume per fix: PRs like #1343 (+1,273 test/+180 code) and #1331 (+1,199/+421). Mechanism: a review-axis rule "test lines added vs code lines added above 3:1 needs a one-line justification"; use `test-audit --gate` (#273) idea. Saving: slows growth, not today's time. Protection given up: none directly. Catch: mutation spot-check on changed modules (#research doc).
3. Measure first, then cut: run `node --test --test-reporter=spec` per-file timing once when the box is idle, trim the top 10 files. Saving: unknown (estimate 20-40% of ~85 s). Protection given up: none if only sleeps and per-test rebuilds are removed (as in #642/#1232).
4. Re-examine the 12.8k lines of e2e harness tests (e2e.cli.test.mjs 1,635, e2e.chrome-windows.test.mjs 1,445). A test file larger than its subject is a candidate; ask whether each tests behaviour or the harness's own plumbing. Saving: up to a quarter of suite lines if halved. Protection given up: the harness refusal paths protect Chris's screen (AGENTS.md lines 151-169), so cut only duplicates. Catch: live e2e run.
5. Do NOT add GitHub CI here for the fakes layer: CI can't run OBS/Windows tests, and the merge already re-runs the full seam locally.

Opposite finding: partial. Pre-merge gating is fakes-only by design, so live regressions (the 12 reverts) reach main and are caught only at the batched e2e run (accepted cost, AGENTS.md:144-150). That is the one place too little gating bites, but the fix is e2e cadence, not more unit tests.

---------------------------------------------------------------------------
##### sudokupad-art (556 commits total; 112 since 2026-10-01; no workflows)

###### Verified
- No `.github/` (ls fails); Actions enabled, unused (`gh run list` returns `[]`). Hooks are identity guards only.
- Local gate: AGENTS.md "End-to-end seam" (line 60-70): `uv run pytest -q`, whole suite incl. golden rebuilds and determinism check, "about 49 s where playwright is installed, 31 s of it the Chromium tests in test_render_real.py". Controller re-runs it on the PR merged onto main before merge (Chris, 2026-09-26). A puzzle-only change (confined to `puzzles/<name>/`) runs only `pytest -q test_builds.py -k <name>` plus its `test_<name>_build.py` (Chris, 2026-10-09). No CI repeats it.
- Inventory: 31 test/conftest files, 554 `def test_` (many parametrized; 14 files use parametrize, test_builds.py alone parametrizes 41 puzzle names across about 5 tests, so the real case count is higher, not counted), 6,760 test lines vs 6,466 Python + 404 JS source lines (~1:1). 41 puzzle dirs, 212 tracked files under `puzzles/` (5.6 MB). Largest: test_codec.py 893, test_lmd_archive.py 856, test_lmd_publish.py 456, test_render_real.py 421.
- Where the time goes: `test_render_real.py` = 31 s of 49 s (AGENTS.md:63-64), i.e. 63% of the suite. Tests there that need Chromium are marked `needs_playwright` and skipped when Playwright is absent (test_render_real.py header lines 6-8).
- Prior pain, ticket #145 "test_retro_waves.py is 32s of a 34s suite, and it is what every review re-runs" (closed): the cost was not 34 s but that the correctness review's witness check re-ran the slow file per new test, "five minutes re-running ... before any reading", a correctness pass measured 22 minutes (2026-09-20). That file no longer exists in the tree.
- Last 20 merged PRs (#424-#456): test lines +497 vs code (py/js) +696. Not bloated by that measure. 9 of 20 are puzzle versions (Ballroom, Skyscrapers ...) adding 0 test lines, thousands of generated lines (e.g. #453 +3,519 total, +0 test). The rest are audit-sweep cleanups.
- Commit mix since Oct 1: 39 of 112 are puzzle builds; 14 are audit/sweep/cleanup/test-fix commits.
- Existing test-quality/time tickets, all closed: #145 (above); #302 "One test conftest"; #339 "Small cuts: ... two redundant tests"; #380/#383/#384/#435/#438 weak-test rewrites; #72 "retire the string-search test"; #50 golden seam; #301/#332/#381/#428 audit sweeps. Open: none.

###### Not verified
- Current wall time (only the 49 s figure from AGENTS.md; written 2026-09-26, may be stale).
- Which tests take time inside test_builds.py (41 puzzles x ~5 parametrized tests, each rebuilding a puzzle: `test_build_reproduces_its_committed_version`, `..._no_version_builds_what_the_goldens_cover`, `test_historical_versions_stay_frozen`, `test_build_prints_nothing`, plus the hash-seed determinism test at line 125). Several overlap in what they build; consolidating needs a `--durations` run.
- How many times a review re-runs the suite after #145's fix.

###### Is it bloated?
No. ~1:1 test to source, 554 tests, ~49 s, no CI, a puzzle-scoped path already ruled by Chris. The prior bloat (retro_waves) was fixed. The 31 s Chromium block is the one big cost.

###### Recommendations (ranked)
1. Split the Chromium tests out of the default run: tag `needs_playwright` tests, and run them only when `render_real.js`, `render_real.py`, `har_store.js` or `testkit.py` change (extend the AGENTS.md seam with a narrowed line like twitch-rules-scroller's). Saving: ~31 s of 49 s on most PRs (63%). Protection given up: render regressions on PRs that don't touch the renderer; they cannot be caught by an unchanged renderer unless a build change alters what it loads. Catch: merge-time full run by the controller (already there) and the nightly backstop pattern.
2. Run `uv run pytest --durations=15` once on an idle box and merge the 4 overlapping parametrized-per-puzzle tests in test_builds.py (each rebuilds each puzzle), keeping golden reproduction and determinism. Saving: unknown, maybe 5-10 s. Protection: the frozen-history and no-print checks can be assertions in the same build call. Catch: goldens.
3. Keep the puzzle-update rule (already there). No CI needed.

Opposite finding: none; the seam covers golden outputs, which is the actual product.

---------------------------------------------------------------------------
##### visual-teach (246 commits total; 1 since 2026-10-01; last run 2026-10-06; PUBLIC repo)

###### Verified
- `ci.yml` (`pull_request:` plus `push: branches:[main]`, no path filter, no concurrency): job `test` (npm ci, `npm run lint`, `npm test` = vitest, demo-mirror drift check) ~20 s; job `visual` (Playwright container, `npm run test:visual`) ~55-70 s (`gh api .../jobs`). `clear-in-review.yml` on issues closed.
- Push+PR both fire on different commits. Last 200 runs (Jun 24 to Oct 6): CI PR 86 runs (64 pass, 22 fail), CI push 56 (all pass), pages-build-deployment 56 (67 min wall total, automatic), clear-in-review 2. Median CI run 1.0 min; total CI wall 158 min over 3.5 months. Zero runs in the last 30 days (repo dormant).
- 22 PR failures (26%): sampled failed jobs show "demo assets mirror canonical" (3 of 6 sampled), "Run npm test" (1), "Run npm run test:visual" (2, when the visual job was first added Jun 26). Failures cluster at Jun 26 to Jun 27 (11) and Sep 2 (6), i.e. bursts while a feature was being built, not steady flake.
- Local gate: `.husky/pre-commit` runs `npm run showcase`, `npx lint-staged`, `npm run test` (full vitest) on every commit; CI then repeats lint+test, and adds the visual job. AGENTS.md has no seam section.
- Inventory: 35 test-like files, 116 `test(`/`it(` lines in 1,869 `.test.*` lines; 22 baseline PNG/snapshots; test overhaul tickets #189-#196 already deleted prose change-detector and source-grep tests and added stylelint.

###### Not verified
- Failure cause for the other 16 failed PR runs; vitest and Playwright job time per step.

###### Is it bloated?
No. A 1-minute CI, a small suite, already audited (#189-#196). Duplicated work: lint+vitest run in husky pre-commit and again in CI test job (intentional "unbypassable mirror" pattern in the sister repos).

###### Recommendations
1. Nothing worth doing given 1 commit in 45 days. If it wakes up: drop `npm run test` from pre-commit (keep lint-staged) since CI repeats it; saving a few seconds per commit.
2. Optional: add `concurrency` cancel-in-progress on PRs (6 failure runs on one day, Sep 2, suggest rapid pushes).

---------------------------------------------------------------------------
##### research-queue (74 commits total; 2 since 2026-10-01; private)

###### Verified
- `ci.yml`: PR + push to main, one job (`npm ci`, `npm run lint`, `npm run typecheck`, `npm test`). `land-drain.yml`: push to `claude/drain-**` branches, repeats the same lint/typecheck/test then fast-forwards main (its own comment says it is the same gate as CI).
- Runs (200-run cap, Jun 25 to Nov 13): CI PR 33, CI push 38, Land drain 34 (5 failures). Median 0.3-0.4 min each; total 36 wall-min over ~4.5 months. 30 days: 4 Land-drain runs, 2 min.
- Tests: one file `plan.test.ts` (540 lines, 36 cases) vs `plan.ts` 430 + drain.ts 120 + seed.ts 15 lines. No AGENTS.md (CLAUDE.md only). Local gate: husky pre-commit (`prepare: husky`; hook contents not read: not verified).
- Tickets: none.

###### Verdict
Not bloated. Cheapest sensible gating; the weekly drainer needs the server-side gate. No recommendation. Land drain failure rate 15% (5/34) is a signal worth a look (not investigated), not a cost problem.

---------------------------------------------------------------------------
##### mediawiki-analytics (28 commits total; 1 since 2026-10-01; private)

###### Verified
- `ci.yml`: push to main + PR; one job: setup-uv, `uv sync`, `uv run pre-commit run --all-files` (ruff + ty + hygiene), `uv run pytest`. No dbt step in CI (despite "dbt + duckdb" in the scan, nothing runs `dbt build` or `dbt test` there).
- Runs: 24 push + 15 PR since Aug 4, median 0.5-0.6 min, 23 wall-min total, 0 failures. Last run Oct 6.
- Local gate: `just check` = ruff, `ty check`, pytest (justfile; AGENTS.md:7 "Full gate"). CI does the same via pre-commit + pytest.
- Tests: one file, `src/mediawiki_analytics/smoke_test.py` (found by `git ls-files | grep test`); nothing else.
- Tickets: none.

###### Verdict
Not bloated; arguably under-gated for the data side: dbt models have no tests or build in CI, and one smoke test guards 6 lines of Python. For a data project with 28 commits and a single committer, acceptable; if the dbt models grow, add `dbt build` against the committed duckdb. No cuts.

---------------------------------------------------------------------------
##### career-ops (1,286 commits total; 1 since 2026-10-01; private)

###### Verified
- Not a GitHub fork: `gh repo view caneff/career-ops --json isFork,parent` gives `isFork:false, parent:null`; only remote is `origin` = caneff/career-ops. History starts with upstream's "Initial release" 2026-04-04 (so a copied upstream history, not a tracked fork).
- 26 workflow files in `.github/workflows/` (25 .yml + test.yml.bak). They do NOT run now: `gh api repos/caneff/career-ops/actions/permissions` returns `{"enabled": false}`. They are registered (17 listed as `active` by `gh api .../actions/workflows`) but with Actions disabled at repo level nothing triggers.
- They did run once: 48 runs on 2026-08-05 (17:23-19:33 UTC), then stopped. Most failed: Tests PR 5/5 failed, CodeQL 8/8 failed, Release Please 3/3 failed; others success/skipped. 48 runs, ~64 wall-min total. Commit fd5d4a4c (2026-08-31) "ci: run tests on Linux only, drop macOS/Windows matrix" was edited afterwards and has never run.
- test.yml: on pull_request to main, `concurrency` cancel-in-progress, `node test-all.mjs --quick` + `go test ./...`; plus a `cv-visual` job. test-all.mjs is 15,394 lines in one file. AGENTS.md:353 still claims "GitHub Actions on every PR: the full test-all.mjs suite" (a doc-vs-reality mismatch: Actions disabled).
- Test inventory: ~616 tracked files match "test" by name (includes `test-fixtures`, `tests/`, `*-tests.mjs`, `.test.mjs`), 15.4k-line test-all.mjs. Not counted precisely.
- Tickets: #12/#13/#28/#33/#35 are drill-engine tickets in this repo's history, none about CI time.

###### Verdict
No test cost today: Actions are off. The 26 workflows are dead weight carried from upstream (stale AGENTS.md line 353, `.bak` files, MANIFESTO/guestbook bots that need upstream community infrastructure). The one repo where "too much test" is literally unused: delete the unused workflow files and `.bak`s, or leave them if upstream merges are wanted. Cron `scan.mjs` runs locally (crontab), not in Actions. Do not re-enable Actions without pruning to `test.yml`; CodeQL/Release Please/Dependabot all failed or irrelevant on a one-person data repo.

---------------------------------------------------------------------------
##### lmd-archive, drills, brain (one line each)
- lmd-archive (15 commits, last 2026-11-15): archive data; 0 test-like files, no workflows, no AGENTS.md gate (`git ls-files | grep -ciE "test|spec"` = 0). The tests for it live in sudokupad-art (test_lmd_*.py). Fine.
- drills (34 commits, last 2026-10-04): no workflows; 3 hand-rolled test files (`drill-engine-tests.mjs`, `drill-session-tests.mjs`, `drill-store-tests.mjs`, 683 lines total) run via package.json; no CI. Fine.
- brain (17 commits, last 2026-10-06): markdown vault, only `land-vault.yml` (2 runs, 1 failure, 0.1 min) which fast-forwards `claude/vault-**` into main with no test (its own header says "no build/test gate"). 4 test-like files by name. Fine.

---------------------------------------------------------------------------
##### Cross-repo top five recommendations
1. sudokupad-art: carve the 31 s of Chromium render tests out of the default seam, run them only when the renderer files change (63% of a ~49 s suite; the merge-time full run stays).
2. twitch-rules-scroller: retire closed-spec `spec-NNNN.seam.test.mjs` files (17 files, 2.6k lines) and put a test-to-code growth check on reviews (recent 20 PRs: 4:1 test to code); then run a one-time idle-box per-file timing and trim the slowest/sleeping files.
3. second-brain-v2: path-filter the push trigger of `check.yml` so daily vault autocommits stop running `just check` (about 35 runs/month, tiny dollars, zero protection lost).
4. career-ops: Actions are disabled; either delete the 26 inherited workflows and `.bak` files or fix AGENTS.md:353 to say CI is off, so the repo stops claiming a gate it does not run.
5. mediawiki-analytics: the only under-gated repo (one smoke test, no dbt build in CI); add `dbt build` or `dbt test` to `just check` if the models grow.

Not recommended: adding GitHub CI to twitch-rules-scroller or sudokupad-art (local narrowed seams plus controller merge re-run plus nightly backstop already do the job on private repos where nothing in CI can run OBS or Chromium cheaply), and no repo has CI time worth cutting by itself.

