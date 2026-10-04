# Burn machinery audit (over-engineering pass, 2026-10-04)

The question: under the proposed direction (one agent per ticket by default, a burn only for 5+
independent tickets, a controller that relays only real decisions), which parts of the burn
machinery can be deleted or replaced by something much simpler, and which must stay because they
guard a real, observed failure?

The scope was `burndown/` (code, tests, SKILL.md, references), the burn-only parts of `flow/lane`
(`implement-dispatch --run`, the worker-record sidecar, `controller-restore`, `controller-adopt`,
`resolve-controller`, and `merge-cleanup`'s record removal), and the worker-supervision hooks in
`flow/claude/hooks`. The method is `ponytail-audit/SKILL.md`. The caller asked for Markdown at this
path, so the report is not the skill's HTML report.

These are already decided and owned elsewhere, so the counts below leave them out: everything in
#1401 (one review wave, retire sweeps: `runfile.py leftover`/`sweep-check`, `sweep.py
render`/`blocked-by`, burndown § The sweep, implement's per-PR sweep) and everything in #1402
(no closing tickets, no default slicing).

## Verdict

About **7,200 lines** come out at low risk: two dead measurement scripts, the spin alert, the tier
tagger, a burn-only duplicate of the general controller-recovery path, the liveness sweep and its
PR-up record, the landing-tail gate, and one stale wording test. About **1,800 more** come out at
medium risk: the core-count job declarations and the box-counter elaborations. The collision
stack (~3,000) and the frontier reader (~1,800) guard real failures and should go through ADR
0005's ablation, not a straight delete. The controller-recovery binaries, the stop alert, the seat
check and the dispatch and cleanup cores stay.

Sizes: `burndown/` is 16,882 lines and `flow/lane` is 14,725 (`git ls-files | xargs wc -l`).

## Ranked candidates (lines removed per unit of risk)

Line counts are code / tests / prose. Each test count is the sum of the `def test_` blocks
classified by name, and prose is the sections named. Each is an estimate to within about 10%.

### 1. Delete `burndown/cost.py` and `burndown/phases.py`: 433 / 674 / 0 = **~1,107**, risk: none

- **What they do.** They read a worktree's Claude transcripts for per-ticket token cost
  (`cost.py`) and phase timings (`phases.py`).
- **Introduced by.** `cost.py`: e8264f5 (#628, 2026-09-07, "per-ticket cost"). `phases.py`:
  f88eabb (#826, 2026-09-15). Both were measurement instruments, not guards against any failure.
- **Callers.** `git grep` outside tests finds only `phases.py` importing `cost.py`.
  `cost.py`'s own docstring says "No caller … nothing runs it today". The only other mentions are
  historical research docs.
- **Still applies?** There is no failure to apply.
- **Replacement.** Nothing. If the cost of a ticket is ever needed, the review ledger or
  `ccusage` answers it.

### 2. Delete the spin alert (`worker-spin-alert.sh`, its test and fixtures): 180 / 2,996 / ~28 = **~3,200**, risk: low

- **What it does.** A `PostToolUse` hook that runs on **every tool call in every session**. It
  alerts the controller when one worker repeats the same tool input 20 times in a row.
- **Introduced by.** 7c5cb71 (#925, 2026-09-21).
- **The failure it was built for.** It was seen once: `skills-893` ran `echo ok` 180 times while
  polling a subagent. The work was intact and committed, so the cost was turns and tokens.
- **Track record.** `~/.claude/worker-spin-alerts.log` holds 27,095 lines. Exactly **1** is a sent
  alert (2026-09-22, worker #982, `Bash {"command":"true"}`). **27,094** are `lib-missing`
  failures, logged on every tool call from 2026-09-22 to 2026-09-27. For five days the hook could
  not run at all, and nothing noticed. That is evidence nothing depends on it. It has sent no
  alert since the fix on 09-27.
- **Still applies?** A spin can still happen, but its cost is tokens, and the rule against
  spinning is already in RULES.md.
- **Replacement.** Nothing. Remove the `settings.json` `PostToolUse` entry, its line in
  `install.sh` and the OPERATIONS.md paragraph (lines 228–246). `worker-alert-lib.sh` stays
  because the stop alert uses it.
- **The 2,775 lines of fixtures** are synthetic transcripts (`window-501/502.jsonl` alone is
  2,008).

### 3. Delete `burndown/tier.py` (dispatch keeps its own label strip): 301 / 648 / ~205 = **~1,154**, risk: low

- **What it does.** Before dispatch, it writes the `documentation` label onto docs-only candidates
  and strips the label from code candidates.
- **Introduced by.** d8400d7 (#898). The failure: #781's ticket #371, a single research `.md`,
  went heavy (TDD, three-axis review, PR) because nobody had labelled it.
- **Follow-up history.** Four of tier.py's five commits since then (#1108, #1118, #1211, #1239)
  fix disagreements between tier.py and implement-dispatch's own reader (`flow/lane/src/targets.rs`).
  The two now share a fixture, and a Rust test reads tier.py's source to keep them in sync. That
  is two readers of one fact.
- **Still applies?** Barely.
  - The failure costs one unnecessary review, which is the safe direction.
  - The dangerous direction is a `documentation` label on a code ticket, which would ship code
    with no review. implement-dispatch already guards that: it strips the label at claim when the
    body names code (`targets.rs`), and it keeps doing so.
  - With one agent per ticket, tier.py never runs, since it is burn-only.
  - Gate 2 (CLAUDE.md) already sends docs-only work to auto-ship, not to the code lane.
- **Replacement.** Nothing. Also delete `tier_test.py` (561), `tier-tagging.test.sh` (87),
  `references/tier.md` (164), burndown § Tier tagging, the label lines in the opening report
  (steps 2–3), and the `targets.rs` test that reads tier.py's source. Keep `body_targets.json`
  for `targets.rs`.

### 4. Delete the burn's own resume path; the general controller-recovery path covers it: ~139 / 292 / ~79 = **~510**, risk: low

- **What it does.** `runfile.py resume`/`reconcile` plus `loop.py announce`/`resolve_via_binary`.
  After a restart it re-announces the controller to each live, unlanded worker.
- **Introduced by.** dd34846 (#924/#892) and e57acca (announce). The failure: a WSL restart
  renamed every session in the #781 trial (#923).
- **Still applies?** Yes. Since 2026-09-22, though, every `implement-dispatch`, burn or not,
  writes a worker record. `controller-restore` (SessionStart) lists the workers, and
  `controller-adopt` moves a dead controller's workers and prints the re-point message.
  - #1098's own body says "Burns already have a path (`runfile.py resume`); plain pairings do
    not". Both paths now exist for the same event.
  - Transcripts show real `controller-adopt <agent>` commands in 8 transcripts, including on
    burns (`skills-spec-1357`, `skills-spec-1365`). Real `runfile.py resume <id>` commands
    appear in 3.
- **Replacement.** `controller-restore` plus `controller-adopt`, which already run. Also delete
  run-file.md § Resume, loop.md § What resume owes each worker, and step 1's resume clause.

### 5. Delete the liveness sweep and the PR-up record: ~191 / 566 / ~94 = **~850**, risk: low–medium

- **What it does.**
  - `loop.py sweep` (with `_verdict`, `render_sweep` and `herdr_get`) makes one `herdr agent get`
    per live slot under a single deadline, with the verdicts `vanished`, `unswept`, `stalled` and
    `unreachable`.
  - `runfile.py pr-up` (and `--clear`) records "PR up" so a `done` pane can be read as `stalled`.
- **Introduced by.** 5660540 (#894: sweep) and 705d466 (#1148: pr-up/stalled).
- **The failures.** A vanished pane is findable only by asking herdr (#778 prototype). A worker
  that ended its turn mid-lane went unseen for about 10 minutes (#1148, burn-2026-09-23).
- **Still applies?** Yes, but with one to five workers the controller can read the same facts
  directly.
  - `timeout 10 herdr agent list` shows every agent's status, and a missing agent is a vanished
    one.
  - The controller's own context says whether a "PR up" arrived.
  - `gh pr list --head implement-<n>` answers it from the tracker after a restart.
  - The stop alert, which stays, covers #1148's mid-lane stop.
- **Real use.** `loop.py sweep --run <id>` commands appear in 2 transcripts.
- **Replacement.** One sentence in burndown § Liveness: "on an idle wake, run `timeout 10 herdr
  agent list`". Also delete the related paragraphs in `liveness.md` and run-file.md § The PR-up
  record.

### 6. Delete the landing-tail gate (`loop.py landing`, `questions`, `cleanup_ready`): ~97 / 219 / ~28 = **~340**, risk: low

- **What it does.** It refuses to clear cleanup while a worker question is still unanswered.
- **Introduced by.** f3ccd00 (#896, the merge-tail ticket from the #781 trial).
- **Still applies?** The rule is sound, but a 300-line checker over a list of questions that the
  controller types in by hand checks nothing the controller did not already know.
  `merge-cleanup` already refuses to remove a worktree while that worker's session is `working`.
- **Real use.** `loop.py landing --clump <n>` commands appear in 2 transcripts.
- **Replacement.** The one sentence already in merge-tail.md § Answer, then merge, then cleanup.
  Keep that section and delete the code and its tests.

### 7. Delete the stale wording test `burndown/run-file-retirement.test.sh`: **64**, risk: none

- **What it does.** It asserts that nothing writes the per-repo `.progress` log, which was
  retired on 2026-09-20 (#892).
- **Still applies?** No. It guards against a regression to a format nobody remembers.

**Low-risk total (1–7): 1,107 + 3,204 + 1,154 + 510 + 851 + 344 + 64 = ~7,230 lines.**

### 8. Replace the core-count job declarations with a load-average check: ~250 / 537 / ~134 = **~920**, risk: medium (needs #1401 first)

- **What it does.**
  - Before launching a parallel job, a worker writes `runfile.py job --cores <k>` (or `--none`
    or `--done`).
  - `loop.py dispatch` reads every record (`job_cores`, `core_room`, `with_run_jobs`), charges
    the job's cores against the free slots, and refuses to dispatch while any live clump has no
    record.
  - `implement-dispatch --run` exists so that a worker knows a run file is under it. Once #1401
    removes per-PR sweeps, this record is the flag's only remaining use. The flag accounts for
    roughly 35 lines of code, 35 of unit test and 107 of integration test, plus about 20 lines of
    `implement/SKILL.md`.
- **Introduced by.** 5660540 (#894). The failure: #351's `verify.py` ran an 8-worker CP-SAT
  portfolio and drove load to **25.8**.
- **Follow-ups were failures of the mechanism itself.**
  - #1311: a missing record idled four slots for 15–40 minutes, three times.
  - #1339: a race between the worker's send and the controller's record, found by Codex.
  - That is defect class 2: a rule that depends on every worker declaring correctly.
- **Still applies?** Only inside a burn. #351 itself says no dispatch-time check could have
  caught it ("with no dispatch pending"), so the declaration only holds future dispatches back.
  A load-average gate does the same job and also counts jobs nobody declared.
- **Replacement.** The box check already requires `uptime`. Add a refusal when the 1-minute load
  is at least (cores − 4). That is about 10 lines. Then delete `runfile.py job`, `--run`, the
  job paragraphs in § Liveness, implement § Control's "declare a parallel job", `liveness.md`
  § The core count, and run-file.md § The job record.
- **Residual risk.** The 1-minute average lags, so a job launched seconds before a dispatch tick
  is not yet visible. The memory side (the committed `ulimit -v` GB, which is what crashed WSL at
  66 GB) is a separate check and stays.

### 9. Shrink the box counter to a flat count: ~342→40 / 545→60 / 89→20 = **net ~-856**, risk: medium (needs a RULES.md edit, which is Chris's)

- **What it does.** `count_working_herdr_agents` (the PLR0912 hit at loop.py:408),
  `_session_pids`, the `/proc` start-time check, the unlisted-pid matching and peak budgeting
  (`projected_processes`, `render_peak`).
- **Introduced by.**
  - a85c2df (#893).
  - 678ec4b (#933): 35 processes on a box capped at 28, from three workers' review fan-out.
  - #1081 (#1075/#1079): the flat count over-counted idle sessions and refused dispatches that
    were fine.
- **Still applies?** Only for a burn. With one agent per ticket, a flat
  `ps -eo comm= | grep -cx claude` that over-counts errs in the safe direction: it refuses too
  much.
- **The obstacle.** Memory/RULES.md names "burndown's counter" as the reference, so this needs
  Chris's edit to RULES.md first.
- **Replacement.** A flat count, load and `free -g`, keeping the committed-GB ceiling. The peak
  rule shrinks to one constant ("a slot costs 5").

### 10. Ablate rather than delete: the collision stack, ~3,000 gross, risk: medium–high

- **What it is.** `closure.py` (557 code, 892 test, 77 wording test), `loop.py`'s
  frontier/picks/refill/hub/admit/workspace-diff code (~380 code, ~722 test), `closure.md` (198),
  loop.md's frozen-set, freshness and exclusion sections (~96), and steps 5–6.
- **The failures it guards.**
  - Concurrent workers editing the same files: #891, #1212 ("merged clean by luck") and #1342
    (paid a rebase).
  - The include-closure half is live in two repos. `twitch-rules-scroller` declares
    `from "<path>"` and `sudokumaker-custom-constraints` declares `// #include <path>`, and
    colliding over generated output is the expensive case there.
- **Under the direction.** "5+ independent tickets" and #1402's disjoint-file slices move the
  independence judgement to planning.
- **Candidate replacement.** A ~40-line dispatch check: refuse a ticket whose named paths
  intersect a live workspace's `git diff --name-only origin/<default>...`. Keep merge-tail's
  "first to land wins, regenerate generated files".
- **Recommendation.** Make this an ablation target under ADR 0005, not a delete, because its
  escapes cost real rebases.

### 11. Ablate rather than delete: the frontier reader, ~1,800 gross, risk: medium

- **What it is.** `frontier.py` (495 code, 1,033 test, 93 wording test, `frontier.md` 202),
  introduced in 64f01fe (#906/#890).
- **The failure it guards.** Dispatching a ticket whose blocker is still open, which costs a
  whole build. A burn still needs it.
- **What can shrink.** After #1402 (one ticket by default), the prose `## Blocked by` grammar
  with its three forms and fence parsing could give way to GitHub's native dependencies alone.
- **Constraint.** `implement-spec/closing_ticket.py` imports `key_line`, `unfenced` and
  `visible`, and #1402 may leave it alive. `to-tickets` and `docs/agents/issue-tracker.md` both
  state the grammar.
- **Recommendation.** Revisit after #1402 lands.

## Deliberately leaving alone (each guards a real, observed failure)

- **`controller-restore`, `controller-adopt` and the worker-record sidecar (`workers.rs`)**:
  about 1,450 code and 750 test lines. They cover `/clear` and a dead controller: #964/#1043, and
  #1098's orphaned twitch-rules-scroller PR #375. Real `controller-adopt` commands appear in 8
  transcripts. They apply to every dispatch, not just burns, and they exist because of the hard
  rule that only a worker's controller merges.
- **`resolve-controller`** (57 code, 107 test): #923, where a WSL restart renamed sessions. Every
  worker still reports "PR up" over SendMessage.
- **`worker-stop-alert.sh`** (270 code, 729 test):
  - It was built for two silent stops in #781 that cost about 4 hours (#820), plus #1148's
    mid-lane stop.
  - It sent 235 alerts (81 on 2026-10-03 alone). That volume is a cost under "quiet controller",
    but the alert goes to the controller, not to Chris, and it is the only wake for a worker that
    stops without reporting.
  - A simpler possible shape, not recommended yet: a plain "worker stopped" notice with no
    false-positive suppression. It should be ablated, not deleted.
- **`loop.py seat`** (~53 code, 150 test): it stops a controller from starting inside a worktree,
  where `/implement` would read it as a worker.
- **The implement-dispatch core** (claim lock, worktree, herdr launch, brief) and **merge-cleanup**:
  one agent per ticket still needs one command to start a worker and one to clean up.
- **Parking's three causes and the two-park stop, merge-tail's "first lands wins and regenerate
  generated files" rule, and the committed-GB memory ceiling**: short prose, each tied to a #781
  or WSL-crash incident.
- **`wrap-background-jobs.sh`** (#597): out of scope, because it records every background job
  (the solver runs too), not only workers'.

## Notes

- **Ruff PLR hits.**
  - `loop.py` `run()` (28 branches) and `runfile.py` `main()` are plain subcommand dispatch, and
    they shrink as subcommands go.
  - `loop.py:408` falls inside candidate 9.
  - `runfile.py:681` and `:886` fall inside #1401's scope.
  - `phases.py:159` falls inside candidate 1.
- **`implement-spec` inherits the burndown loop wholesale.** Its SKILL.md lines 12–33 point at
  § The loop for the box check, clumping, the frontier and the run file. Each delete above also
  changes nested spec runs, and the matching wording tests in `implement-spec/nested-run.test.sh`
  must move with it.
- **What #1401 leaves of `runfile.py`.** After #1401, `runfile.py` keeps
  start/clump/land/close/show plus the lock and IO (about 420 code, about 1,040 test). With
  candidates 4, 5 and 8 applied, it is a ticket→workspace→agent→sha ledger. GitHub (in-progress
  labels, `implement-<n>` branches, merged PRs) plus `git worktree list` already hold that ledger.
  Whether the file is needed at all is the next question after this round. It is not costed here.

## Checks run

- Callers: `git grep` over tracked files, excluding tests, for each module and subcommand.
- Origins: `git log --diff-filter=A` and `git log -S` per function, and `gh issue view` for #628,
  #826, #893, #894, #896, #898, #906, #920, #923, #924, #925, #933, #1043, #1081, #1098, #1148,
  #1212, #1311, #1339, #1342, #1401 and #1402.
- Alert history: `~/.claude/worker-stop-alerts.log` and `~/.claude/worker-spin-alerts.log`.
- Real use: `rg` over `~/.claude/projects` for `"command":"…<subcommand> <arg>`. These counts are
  lower bounds, and mentions in loaded skill text were left out.
- Include directives: the `AGENTS.md` files under `~/src`.

**Not verified:** whether each stop alert was a true positive (the log does not record the
outcome), and the exact line split inside shared CLI functions (estimated).
