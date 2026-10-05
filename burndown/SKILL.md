---
name: burndown
description: "Drain a mixed-origin ticket queue to empty as one supervised run, frontier-first, one PR per ticket."
disable-model-invocation: true
---

A **burn**: one mixed-origin ticket queue, drained to empty as one run. You
are the **controller** — a session on a primary checkout's default branch,
dispatching a worker per clump and ruling on what comes back. The terms are
`~/.agents/skills/CONTEXT.md`'s; a worker's own job is
[`implement`](~/.agents/skills/implement/SKILL.md).

One spec's slices are a different run and a different policy:
[`implement-spec`](~/.agents/skills/implement-spec/SKILL.md). A spec that
turns up inside a mixed queue is handed off to it whole —
[`references/spec-handoff.md`](references/spec-handoff.md).

## The loop

The dispatch loop — pick the next jobs, start them, wait, start more as slots
free up — lives **here and nowhere else** (#779). Its mechanical steps are
`burndown/loop.py`; why each rule reads the way it does, with the evidence it
came from: [`references/loop.md`](references/loop.md).

**Where the controller runs.** Any primary checkout's **default branch** —
read from `refs/remotes/origin/HEAD`, never assumed to be `main` — and not
necessarily the target repo's checkout: the loop addresses the target with
`--repo` on every tracker call. `python3 burndown/loop.py seat` refuses a
linked worktree and says why, because inside one `/implement`'s front-door
rule reads the session as a **worker** and the same prompt would start a
build instead of a run. It refuses a detached HEAD and a non-default branch
too. The one linked worktree it accepts, and says so, is a `spec-<n>`
branch (`references/loop.md` says why).

**Open the run.**

1. Take the seat (above), then `runfile.py start` the run with its slot
   budget (5 when `--slots` is omitted), the controller's own herdr
   agent name, and `--repo <primary checkout>`, required: the run's target,
   which every printed `implement-dispatch` command carries and
   `counts.py --repo` is checked against (§ Run state). Resuming an existing run instead:
   `runfile.py resume`, and then **one message per live, unsettled worker**
   — its `announce` bucket and only that one, via `loop.announce`. A
   landed or closed clump's worker gets none however its agent looks; a vanished one
   gets none either, and is reconciled or parked by hand. The bucket
   names each worker by its **herdr agent name**, which is
   the durable key and not an address: resolve it to a reachable session at
   **send time** (#923), and never write a resolved address into the run
   file.
2. Read the frontier (§ The frontier) over the **whole queue**, not the first
   wave's worth, and clump it (§ Clumping): `closure.py --json` into the
   candidates file, never built by hand. That exploration is the run's
   **frozen** candidate set: a ticket filed while the run is going waits for
   the next run. The one exception is a ticket filed *during* the run
   **because the run is stuck on what it fixes** — `loop.admit` takes it only
   with the clump it unblocks named. Then **tag the tier before any
   dispatch** (§ Tier tagging): `python3 burndown/tier.py <owner/repo>
   <n>=<path>[,<path>]...` writes the missing `documentation` label onto
   every docs-only candidate and strips it from every candidate targeting
   code, because the tier is read off the ticket at dispatch and a label
   changed after that is a label that came too late.
3. The **opening report** carries `closure.py`'s announcement line verbatim,
   so the reader can tell all three declaration states apart: a declared
   directive, a **declared None** — the repo has no include graph — and
   **silence**, which clumps conservatively by directory subtree. A
   controller reading "conservative" has to know which of the last two it
   got. It also carries `tier.py`'s lines (§ Tier tagging), which **name
   every label the exploration pass wrote**, every label it stripped and
   every ticket it withheld the label from because its body names code, and
   say `labels written: none`, `labels stripped: none` and
   `labels withheld: none` when it did none of them — a report silent about labels reads the same from a
   pass that wrote nothing and a pass that never ran, and the difference
   between those two is a ticket dispatched at the wrong tier.

**Then, until the queue and the slots are both empty:**

4. **Recompute the frontier at each landing** and dispatch into every free
   slot. Refill is **continuous**: no waves, because a wave holds slots
   empty waiting for its slowest clump.
5. **At each dispatch, re-resolve the closures** — the clump's own and
   every **in-flight** clump's, through `closure.py` against current `main`,
   **one hop**; an in-flight clump's tickets and workspace come from the run
   file, its closure from that re-resolution, and the two together are
   `loop.py dispatch`'s `--in-flight`; its job record is in neither, and
   `--run <run-id>` is required, and dispatch reads it from the run file by
   the clump's lowest ticket, ignoring any `job` in the in-flight file.
   `loop.py dispatch` reads a clump the run file records as closed as not
   live, drops any candidate whose lowest ticket is a clump the run file
   records as landed or closed (printing `landed #<n>: skipped` for each),
   so the candidates file stays the frozen set and the run file is the
   progress, and then unions each unsettled in-flight workspace's real
   `git diff --name-only origin/<default>...HEAD`, its uncommitted edits and
   its untracked files into that closure (#1212), so a file the worker
   reached that no candidate list named still holds the clumps that share it;
   a diff it cannot read refuses the tick. A clump sharing a file or a
   directory with a live workspace, or with a clump picked earlier the same
   tick, is **off the frontier**
   (`references/loop.md` § The exclusion rule and what it costs):
   `loop.py dispatch` picks from what is left, **widest
   closure first** so a wide clump does not sit behind narrow ones and block
   them later (#1026), and prints a `held` line for the rest naming its live
   workspace or the earlier pick. That hold is what keeps a **family's
   clumps** apart: family members sharing no file and no directory run at
   once. Two consequences,
   because neither is visible from the frontier's own definition — a run drains
   **out of ticket order**, and one parked worker can hold a **whole family**
   off the frontier until it lands. A controller reading only "open,
   unblocked, unclaimed" would dispatch into the collision.
6. **Full re-exploration fires on one trigger**: a landing whose diff touched
   a **hub** — a file two or more candidates' closures share
   (`loop.py hub`). Every other landing gets step 5 and nothing more.
7. **Box check before every dispatch** — read `uptime` and `free -g`, and
   pass the committed `ulimit -v` GB to `loop.py dispatch`, which weighs every
   worker the tick would start, takes only as many as the box has room for,
   and refuses outright when that is none. The **28** cap is on **Claude
   sessions**, subagents included, across the whole shared box, not this
   run's and **not OS processes**: an idle WSL box holds ~190 of those, so
   `ps | wc -l` refuses every dispatch. `loop.py` counts herdr's **working**
   panes (`herdr agent list`; every `agent_status` counts except `idle`
   and `done`, so a missing or unrecognised status fails closed as
   working rather than vanishing) plus every `claude` pid `ps -eo
   pid,comm` shows that no herdr pane resolves to — a subagent or
   headless run herdr does not pane-list, matched to panes through the
   sessions registry the same way `resolve-controller` does — validated
   against `/proc/<pid>/stat`'s own start time, since a pid recycles and a
   stale registry record naming a live pid must not silently claim it; an
   unmatched pid fails closed and counts, the same as a herdr pane whose
   session cannot be resolved at all. Idle and done panes are the only thing
   excluded. It falls back to a flat process count (`ps -eo comm= |
   grep -cx claude`, by command name: `pgrep -f claude` also matches plugin
   scripts and hook shims and overcounts more than 2x) only when herdr
   cannot answer, or when its listing is empty or matches none of the
   box's actual claude pids while some exist — herdr's registry read as
   broken, not the box read as idle. `--processes <n>` overrides both, and
   the refusal names the number and the counter it used. A box it cannot
   measure by either counter, or a process listing no `claude` at all (the
   controller is one), is refused, never read as empty; pass `--processes`
   with a count you took. The ~**24 GB**
   ceiling is on the sum of the per-process `ulimit -v` caps. A slot the box
   cannot afford stays empty; that is not a reason to dispatch into it
   anyway. A slot is budgeted at its **peak**, not its steady state (#933):
   `references/loop.md` § The box check, and `loop.py dispatch` prints the
   `peak:` line that goes in the status line below. `loop.py box` takes
   `--live <n>`, the workers already running; omitting it is refused.
8. Dispatch and merge through
   [`implement`](~/.agents/skills/implement/SKILL.md) § Dispatch, which
   claims the clump and starts the worker, passing `--run <run-id>` on
   every plain `implement-dispatch`: run the `command` line `loop.py
   dispatch` prints under each pick, which carries it;
   `implement/SKILL.md` § The merge,
   which merges and cleans up, is the controller's own step there. The loop
   restates neither grammar. When two in-flight branches turn out to touch
   the same files, the collision procedure, the closure defect it implies,
   and the rule that every outstanding worker question is answered **before**
   cleanup: [`references/merge-tail.md`](references/merge-tail.md). Register
   each dispatched clump with
   `runfile.py clump` — its workspace and its worker's herdr agent name, or
   step 1's resume has nothing to re-announce to — each landing with
   `runfile.py land`, each clump that finishes with no landing of its own
   (its ticket found already fixed on `main`, or handed to a nested spec
   run, once that run has finished and not at the hand-off) with
   `runfile.py close <run-id> --clump <n> --reason <text>`, never
   a `land` at `main`'s tip (why, and the recovery when one was recorded:
   `references/run-file.md`), and each "PR up" with `runfile.py pr-up <run-id>
   --clump <n> --pr <n>` as it arrives, for this file's § Liveness, so a
   restart can pick the run back up with nothing transcribed by hand. The controller clears the
   PR-up record with `runfile.py pr-up <run-id> --clump <n> --clear` whenever
   it hands findings back to the worker (a red seam's failure, or any ruling
   that sends it back to work), since the PR stays open through the fix round,
   and records it again on the next "PR up".
9. **Wait on the wake, and sweep on an idle one.** The loop waits by being
   idle, never inside a tool call: a controller in one hears no worker until
   it returns. What it trusts while it waits, in rank order, and the bounded
   backstop it runs when it wakes with nothing else to do: § Liveness. A
   clump that cannot go on parks, and a run that parks twice with no landing
   between stops: § Parking and escalation.
10. **At run close, send Chris the closing report** (§ The closing report).

## The closing report

A burn ends with one report to Chris, and no sweep ticket: every valid review
finding was fixed in the PR that raised it, or moved onto the open ticket for
its component (`implement/SKILL.md` § Review), so no run carries findings
forward. Before writing it, run `python3
~/.agents/skills/docs/research/review_ledger.py harvest`, which joins each
finding's outcome from the dispositions sidecars into the ledger. The report
carries two counts, **fixed** and **moved**,

```
python3 burndown/counts.py <run-id> --repo <primary checkout>
```

read from each landed clump's dispositions sidecar, which the worker writes
(`implement/SKILL.md` § Review), naming each closed clump as skipped. The
sidecars are found under the `--repo` checkout's cache directory, never the
cwd's, which is not always the target; `--repo` is refused unless it is the
run's recorded target. A landed clump with no dispositions sidecar is refused
by number, never counted as zero: the worker writes the sidecar even when its
reviewers found nothing.

While an ablation runs (`docs/agents/ablations.md`, a section whose heading
ends `running`), the report also carries its escape table, read from the
ledger, and the controller appends the burn's line to that file's log:

```
python3 ~/.agents/skills/docs/research/review_ledger.py escapes --repo-dir <primary checkout>
```

The table has one line per skipped component, with the number of PRs it was
skipped on and the escapes attributed to them. What decides the ablation, and
when, is that file's.

The report also carries the **friction-log count**: the commits the run made
to the log (§ The friction log), counted with
`git -C ~/.agents/skills log --oneline --since=<run start> --grep='^friction:'`.
A run that stopped on two parks (§ Parking and escalation) sends the same
report.

## The friction log

A friction point the controller hits — a harness refusal, a rule that cost a
turn, a tool that misreported — is one line appended to the one log,
`docs/agents/friction-log.md` in this skills repo (`~/.agents/skills`),
whichever repo the run targets, and never a ticket of its own. Each line is
committed on its own with the subject `friction: <what happened>`; the line
itself is date, repo, what happened, what it cost (ADR 0005). The weekly retro
reads the log; a point becomes a ticket only on its second occurrence, and
then through the search-before-filing rule in `~/.claude/CLAUDE.md`. The line
is a docs-only change and ships on the default branch the way any non-code
edit does.

## What the controller says to Chris

Only two things reach Chris: a decision that is contested or cannot be undone,
restated in full (the number, the options and the recommendation, never "as
above"), and the one closing report. A routine reversible choice is applied on
the controller's recommendation and listed in the closing report. A worker's
idle or stop notice and its "PR up" are never relayed, and a duplicate idle
notification gets no reply at all. The one hand-off is a `ready-for-human`
ticket's merge line, which Chris merges himself (`implement/SKILL.md` § The merge).

## The frontier

Which tickets a run may dispatch next — open, labelled, unclaimed, waiting on
nothing — is read by `burndown/frontier.py`, not by a regex at the call site:
`python3 burndown/frontier.py <owner/repo> <label>` prints the `unblocked`,
`blocked`, `unresolved`, `spec` and `slice` buckets. Native tracker dependencies
first, the `## Blocked by` section as the fallback, and a ticket with neither
is **unresolved** — never dispatched on the assumption that silence means
clear. A `spec`-labelled parent is none of those three: it is dispatchable by
a different verb, and its entry names that verb —
`implement-dispatch --spec <n> --slots <k>` — so a controller can act on the
line without opening another document. A `slice` is the same verb seen from
the other side: a ticket whose parent carries `spec` is handed off with its
parent (`implement-dispatch --spec <parent> --slots <k>`), never dispatched as
an ordinary ticket, whether or not the parent itself carries the queue label. When the parent
carries the queue label too, its `spec` line and its slices' `slice` lines
are one handoff: run the `--spec <parent>` line once.
The grammar and the three sources:
[`references/frontier.md`](references/frontier.md).

## Clumping

Which candidates are one clump — one worker, one workspace, one PR — is read
by `burndown/closure.py`, not from the tickets' declared seams:
`python3 burndown/closure.py <repo-root> <n>=<path>[,<path>]...` prints the
mode and the **families** — the connected components of the collision graph
over each candidate's **include closure** — each split into its **clumps**
(`references/closure.md` § Families run as clumps); `--json` prints the clump
list `loop.py dispatch --candidates` reads. The repo declares its include
directive and its generator command in `AGENTS.md`; the resolver follows
that declaration one hop and **never runs the generator**. A repo that declares nothing is
clumped conservatively by directory subtree, and the run's **opening report
carries the announcement line** the reader returns, so a controller can see
which of the three modes it got. An in-flight clump's file set is wider than
its closure by the time a dispatch reads it: the run loop's step 5 unions in
its workspace's real diff. The grammar and the evidence:
[`references/closure.md`](references/closure.md).

## Tier tagging

A candidate's **tier** is read off its `documentation` label at dispatch, so
a docs-only ticket whose author forgot the label takes TDD, a three-axis
review and a PR for a page of prose (#781's `#371`), and a labelled ticket
whose candidate targets a `SKILL.md` goes out light (#969). After clumping and
**before the first dispatch**, `burndown/tier.py` writes that missing label
onto the ticket, and removes `documentation` from a candidate whose targets
include code (#1118: dispatch reads only the body's paths, so this pass is
the one that sees the clumper's) — `python3 burndown/tier.py <owner/repo>
<n>=<path>[,<path>]... [--dry-run]`, the clumper's own candidate grammar. The
label, not a flag: `merge-cleanup`, `/landed` and a resumed controller all
read the ticket, and a flag is gone the moment dispatch returns.

It **touches one label, `documentation`**: it adds it when every target
is prose and the body names no code the way dispatch reads it (a body that
does is reported under `labels withheld:`, #1211), and removes it when any
target is code. A candidate is docs-only when every file it targets is
prose — `.md`, `.markdown`, `.txt`, `.rst`, and never a `SKILL.md` — and
anything else it cannot read as prose counts as code, which is deliberately
stricter than `flow/claude/WORKFLOW.md` § Gate 2: light tier lands with no PR
and no reviewer, so a wrong label there ships code unreviewed. A worker's
right to raise light to heavy is untouched, and nothing lowers heavy to
light. The grammar, the divergence and the evidence:
[`references/tier.md`](references/tier.md).

## Run state

A run's state is **one JSON file per run** at `~/.cache/burndown/<run-id>.json`,
read and written by `burndown/runfile.py` — not the controller's context, and
not a per-repo log. It holds the run id, the slot budget (default 5, set by
`runfile.py start --slots <k>`), the controller's herdr agent name, the target repo
(`runfile.py start --repo <checkout>`, recorded as the absolute path of its
primary checkout, so a linked worktree names the same target; a
run file from before the field makes `loop.py dispatch` and `counts.py
--repo` refuse, since a missing target must not read as no check), and
per clump its ticket list, workspace, worker's herdr agent name, the
parallel job its worker has out (§ Liveness) and squash sha once it
lands. `runfile.py resume <run-id> --live
<names> --controller <my agent name>` reads it back and splits the clumps into
the live workers to **re-announce** the controller to, the vanished ones to
reconcile by hand, and the landings already banked — the live names read off
the machine, never off the file.

A worker is addressed by its **herdr agent name** throughout, because a WSL
restart renames every Claude session and every brief hard-codes
`--controller "<name>"`. The contract, the JSON shape and the
resume procedure: [`references/run-file.md`](references/run-file.md).

A single spec's slices in one workspace are
[`implement-spec`](~/.agents/skills/implement-spec/SKILL.md)'s job, not this
skill's.

## Liveness

How a controller knows its workers are alive, in rank order. The measurements
behind the ranking, and what each source costs when it is read the other way:
[`references/liveness.md`](references/liveness.md).

1. **The wake is primary.** A worker's `SendMessage` reaches an idle
   controller as its next turn, about a second after the send (#778). Nothing
   replaces it, and nothing below is read as a report that has not arrived.
2. **The stop alert is a hint.** It means *read this pane*, and never that a
   worker is stuck: across the two #781 runs it fired **six times** and was
   wrong six times, from three benign causes the reference names. So a
   controller reads the pane the alert names and rules from what that pane
   says; it never parks a clump, holds a slot or calls a worker stalled on
   the alert alone.
3. **The backstop is a bounded sweep.** `python3 burndown/loop.py sweep
   --run <run-id>` probes each live slot once through `herdr
   agent get` — no retry, no wait, one call per slot and none for a landed
   clump. Run it when the controller wakes for any reason and has **nothing
   else to do**. It is **never a timer** and never a blocking call: the wake
   is the primary path, and a controller sitting in a blocking call while
   workers are out cannot hear any of them.

   Bounded is **one deadline for the whole sweep**, not one per probe — a
   per-probe bound composes, and five hung panes at ten seconds each is
   fifty seconds deaf, which is the same deafness by another route. Each
   probe gets what is left of it, and a slot the deadline did not reach is
   `unswept`: nobody asked, it is read on the next wake, and it is never
   confused with a pane that answered.

   A **vanished** pane — herdr has no agent by that name — is the sweep's own
   verdict, distinct from an `idle` one, and it is the only failure nothing
   else in the lane can find (#778). What the sweep cannot see is the
   opposite shape: a pane that is present and busy reads `working` whatever
   it is busy with, so a worker spinning on no-op calls passes every signal
   the sweep has (#925). The sweep answers whether there is still a pane and
   what herdr says it is doing — never whether the work is progressing.

   A finished pane — `done`, or `idle` once someone has focused it — on an
   unsettled clump with no "PR up" on record is **`stalled`**, distinct from
   `idle`. Its turn ended with no "PR up", so it either stopped mid-lane or
   is waiting on your answer to a question; the line says to read the pane,
   and the pane says which. The record is
   the run file's `pr_up` (`references/run-file.md` § The PR-up record); with
   it, the sweep prints herdr's own word.

**A worker declares its job size.** A worker that launches a parallel job
writes its own record, naming the job's **core count**, before it launches,
and `--done` when it ends
(`implement/SKILL.md` § Control, #1339). `runfile.py clump` records `none`
when it registers the clump, because a worker starts with nothing out and a
record that waited for its "PR up" idled every free slot for the hour before
it (#1311). That default would charge a later job nothing, so a worker
declares a job past one core before it launches it. Writing the record
itself removes the controller's turn from the send-to-record interval
(#1339); a tick that has already loaded the run file when the write lands
still dispatches on what it read, and the next tick holds the slots. The worker's
`job: <k> cores` message is a notice. The controller's own `runfile.py job` is
the fallback, for a worker whose write was refused (its clump not yet
registered, or the lock timed out) and who is waiting on the reply: record the
job on arrival of that message, reply, and the worker launches. A clump with
**no** record at all (a file from before jobs existed) is still refused:
silence is not zero. Whoever writes it, the record is on the clump
— `runfile.py job <run-id> --clump <n> --cores <k>`, or `--none`, or
`--done` once the job has finished — and `loop.py dispatch --run <run-id>`
reads the charge from **that record**, never from its own argv or
`--in-flight`: a declaration that lived in one command line is a hold a
restart cannot recover, and the free slot a resumed controller then
dispatches into is the contention #351 produced.

The charge is arithmetic, so "heavy" needs no threshold: a slot is one core's
worth of machine until a worker says otherwise, and the cores past the job's
own slot come off the free ones — a 2-core job holds one further slot, an
8-core job holds seven, which on a run of three slots is every slot there is.
A live clump with **no record at all** is not charged zero; the dispatch
refuses it by name and says which worker to record. The line the reader
prints — which clump declared what, and what is left — goes in the
controller's **status line** while any declaration is outstanding; so does
the `peak:` line `loop.py dispatch` prints on every dispatch tick.

## Parking and escalation

**Three park causes, and no others.** A clump parks when:

1. a question only **Chris** can answer arises;
2. a **lane-mandated step the harness refuses** blocks it;
3. a worker **cannot get its PR to CLEAN**.

Everything else is a **controller ruling** — the controller decides it, states
the assumption it decided under, and the run goes on. A park is a comment on
the ticket saying which of the three it is and what it is waiting on, plus a
label swap to `ready-for-human`. What each cause cost on #781, and why a
fourth one is not added quietly:
[`references/parking.md`](references/parking.md).

A park, and any friction the controller hit on the way to it, is also a line
in the friction log (§ The friction log), not a ticket.

A parked clump **keeps its workspace**, and its include closure stays **out of
the frontier** while it is parked: releasing either invites a second worker
into the same files, which is the collision § The loop step 5 exists to
prevent. **Two consecutive parks with no landing between them stop the run** —
a run that has stopped landing has stopped working, and the next thing it
does is send the closing report (§ The closing report) to Chris rather than
dispatch again.

**Escalation.** The controller's escalation list lives in
[`CONTEXT.md`](../CONTEXT.md)'s Controller entry. Two of its shapes are this
run's to recognise: *the spec is silent on something the user needs*, which is
a gap and not a change to a ruling, and *a lane-mandated step the harness
refuses*, the one escalation where the controller **structurally** cannot
act.

**A bounded probe before escalating.** A controller **may commission a bounded
probe** from a worker before it escalates — a named, small, time-boxed
measurement whose shape it states, so an abstract question reaches Chris as a
table instead of three options in the dark
([`references/parking.md`](references/parking.md) § The bounded probe).

## Before a controller rules

Two clauses, each a ruling that went wrong on #781. The evidence behind each:
[`references/parking.md`](references/parking.md). A friction point met while
ruling goes to the friction log (§ The friction log, in this file), not to a
new ticket.

1. A ruling about **runtime behaviour** is checked against **the thing that
   ships**, not a proxy. A headless bundle, a unit harness or a build artifact
   is a proxy, and green on one is not green in the app.
2. A ruling about a **tool's behaviour** cites the **tool's source**, not its
   help text. Help text compresses; a conjunction reads as a disjunction and
   the ticket filed from it is wrong.
