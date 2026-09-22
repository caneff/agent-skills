# Burn `burn-2026-09-21-0930` on agent-skills: what landed, what the loop did, what broke

Controller: this session, seated on the primary checkout's `main`, herdr agent `skills-dc`. Five slots. The first supervised burn driven by `burndown/loop.py` after #885 closed.

## Outcome

- **27 tickets landed** in 26 clumps (final; the report was first written at 25 with two in flight) (one clump of three, one of two, the rest singles), plus #901 landed just before the run opened. Every landing went through the heavy tier: TDD, three review axes, a verification pass, a Codex pass at the merge gate, squash, `merge-cleanup`.
- **1 park**: #874, cause 2 (a lane-mandated step the harness refuses). The correctness reviewer's read-only diff of `~/.local/bin` was blocked by the auto-mode classifier as Unauthorized Persistence; the prompt sat in the worker's pane from 14:36 until Chris pressed `1` at 16:58. The park ended, the worker's PR (#1018) went through two Codex passes, and Chris merged it at 05:47 the next morning as a `ready-for-human` ticket; the installer ran from the primary checkout after. #964, held behind #874 over `flow/claude/OPERATIONS.md`, dispatched at 05:48, landed at 06:36 (d578e5c) after two Codex passes: three of four findings fixed in-round, one filed (#1044).
- **0 workers vanished; 0 collisions between live workspaces.** Two stop alerts were benign (a worker replying to a controller message with a subagent still out); two were real (#905 and #934 stopped after building to ask, in their pane, whether they could run the review), and both were caught by the alert and resumed by a controller ruling.

## The loop, as run

- The queue opened as **one 27-ticket family** under the old clumping. #970 was filed and admitted mid-run as the one exception the loop allows (the run was stuck on what it fixes); it landed the family/clump split and `closure.py --json`, and the run refilled from its output.
- **Serialisation worked by file overlap alone**: no two live workers ever held the same file, and the run drained out of ticket order as the loop says it will.
- **Every landing that touched a hub triggered a re-exploration**; `closure.py` in declared-None mode gave the same clumps each time, so re-exploration cost seconds.
- The **box check** from #933 landed mid-run and immediately capped the run at three live workers on a box holding 12 agent processes, because each live worker now reserves its review fan-out. That is the ceiling #933's worker flagged as Chris's call.
- Every controller call to `loop.py dispatch` needed the in-flight list built by hand from the run file plus each landed-but-uncleaned workspace; #1003 covers the accounting bug that made a landed clump with a null job refuse the tick.
- The **liveness sweep** reads herdr's status from the wrong level of the reply and calls every pane unknown (#988); direct probes with `herdr agent get` and `herdr agent read` did its job.

## The Codex pass

- **Early launch at round 1: 4 launched, 4 raced, 0 banked.** Every worker pushed fix commits after "Round 1 out", so the gate refused every early verdict. The controller stopped launching early after the fourth and ran the pass once at PR-up for the rest of the run; #1015 proposes making that the rule.
- **At the gate it earned its place.** Of 23 heavy PRs, the gate pass found a real, codex-only defect the three Claude axes had missed on 15, and the worker fixed each in one round. The pattern was consistent: the axes reviewed the diff, Codex reviewed the invariant the diff claimed and found the case one step past the fixture — a name one space away, a status the parser did not model, a path that fell back to zero when its input was absent.
- **Second passes mostly produced follow-up tickets**, not fixes: 11 filed from final rounds (#981, #982, #990, #998, #999, #1003, #1005, #1009, #1013, #1014, and #969's wording note). Each is narrow and real; none was worth a third round.

## Controller mistakes worth a rule

- Merged one PR (#978) while `gh pr view` read UNKNOWN; every later merge was gated on CLEAN in the same command.
- Pushed main red twice for about two minutes each: once by chaining a commit with `;` after a failing checker, once by writing examples that the section checker read as live references. Both fixed the same way: gate the commit on the check, in one `&&` chain.
- Asserted a `--selfcheck` flag from memory; the worker corrected it. Read the source first.

## Filed during the run

By the controller: #969, #970, #981, #982, #988, #990, #998, #999, #1003, #1005, #1009, #1013, #1014, #1015. By workers: #971, #973, #975, #976, #983, #991, #993, #994, #1000, #1006, #1011.

Also filed at the tail: #1044 (controller), #1016, #1017, #1031, #1032 (workers). Spec #1024 with seven slices (#1025–#1030, #1033) came out of the review of this run's follow-up count: 26 closed, 26 opened.

Run closed 2026-09-22 06:40. Left for Chris: the #951 upstream report to the Codex plugin; #867 has no state label; the three-worker ceiling under #933's box check.
