---
name: implement-spec
description: "Drive one sliced spec as one run: dispatch its slices through the loop, with an exploration pass, an integration branch its slices land on, one spec-level review and fix round, and one integration PR to the default branch."
disable-model-invocation: true
---

One spec's slices, driven as one **run**. You are the **controller**: you
dispatch a worker per clump, rule on what comes back and merge it. The terms
are `~/.agents/skills/GLOSSARY.md`'s; a worker's own job is
[`implement`](~/.agents/skills/implement/SKILL.md). A queue of unrelated
tickets is `drain`'s, one bundle at a time. Parallel work exists only here.

## Prerequisite: the spec is sliced

A spec run needs slices: sub-issues of the spec, filed by `/to-tickets`. A
spec with none is not run. Slice it with `/to-tickets` first, or, when its
slices exist unlinked, link them as sub-issues. `implement-dispatch --spec`
refuses such a spec and prints the link command.

## The dispatcher

A run is started by a session or by `drain`, and it has its own `--slots`,
5 when omitted. Nothing debits them: the box rule (§ The loop step 7) is the
only bound across runs.

- **Started with `implement-dispatch --spec <n> --slots <k>`** from a session.
  That session is this run's controller, and the brief names it. This run
  reports, parks and escalates to it the way any worker does
  (`implement/SKILL.md` § Control), and a message these sections address to
  Chris goes to that session, which rules or relays.
- **Started by `drain`.** A controller named `drain` is no session
  (`drain/drain.py` dispatches spec runs too, #1477):
  `implement/SKILL.md` § Control's rule for it governs, with the integration PR up and this run idle
  as its stop.
- **Started by typing `/implement-spec` in a session.** No controller sits
  above it. That session merges the integration PR by
  `implement/SKILL.md` § The merge, and reports to Chris directly.

Toward its slices it is a controller in every case: what a controller rules
on is `implement/SKILL.md` § Control, and the merge is that file's § The merge.

## The exploration pass

One pass over the spec, before any slice is dispatched: what the spec's
decisions say, and what the code already does about each one. Its output is a
**summary** — one line per decision — plus whatever must reach Chris.

What reaches him is read by
[`contradictions.py`](contradictions.py), not by eye:

```
python3 implement-spec/contradictions.py <exploration.json>
```

The check compares a decision the code does not implement against **the
spec's own ticket list first**. A decision a ticket of this spec builds is
**not yet built** — a summary line naming that ticket, never a ruling for
Chris. Only "the code does this, **differently**" escalates as a
contradiction. A decision the code has never heard of, that no slice builds,
is a summary line too: a gap in the slicing, for the controller to close by
filing, not drift for Chris to rule on.

Which of those two a decision is — the code has not got there yet, or the
code does it another way — is the pass's own reading, and the line between
them is drawn in the reference. Where both readings honestly fit, it is the
first: the channel that reaches Chris is the one that has to stay clean.

The three verdicts, that boundary, the input the reader takes, and the run
this rule came from: [`references/exploration.md`](references/exploration.md).

## The loop

The dispatch loop picks the next clumps, starts them, waits, and starts more as
slots free up (#779). Its mechanical steps are `loop.py`; why each rule reads
the way it does, with the evidence it came from:
[`references/loop.md`](references/loop.md).

**Where the controller runs.** A primary checkout's **default branch** — read
from `refs/remotes/origin/HEAD`, never assumed to be `main` — or the linked
worktree on this run's `spec-<n>` branch that `implement-dispatch --spec` makes.
It need not be the target repo's checkout: the loop addresses the target with
`--repo` on every tracker call. `python3 implement-spec/loop.py seat` refuses
any other linked worktree and says why, because inside one `/implement`'s
front-door rule reads the session as a **worker** and the same prompt would
start a build instead of a run. It refuses a detached HEAD and a non-default
branch too.

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
2. Read the frontier (§ The frontier) and clump **only the slices of this spec
   it reports clear** (§ Clumping): `closure.py --json` into the candidates
   file, never built by hand. `loop.py dispatch` reads no blocked-by edge, so a
   blocked slice in the candidates file is dispatched as if clear (#1542). That
   exploration is the run's **frozen** candidate set: a ticket filed while the
   run is going waits for the next run. The one exception is a ticket filed
   *during* the run **because the run is stuck on what it fixes** —
   `loop.admit` takes it only with the clump it unblocks named.
3. The **opening report** carries `closure.py`'s announcement line verbatim,
   so the reader can tell all three declaration states apart: a declared
   directive, a **declared None** — the repo has no include graph — and
   **silence**, which reads closures conservatively by directory subtree. A
   controller reading "conservative" has to know which of the last two it
   got.

**Then, until the slices and the slots are both empty:**

4. **Recompute the frontier at each landing** and dispatch into every free
   slot. Refill is **continuous**: no waves, because a wave holds slots
   empty waiting for its slowest clump. A slice of the frozen set that the
   landing newly unblocks is clumped then (`closure.py --json` over it, as
   step 2) and added to the candidates file; it was explored, so it is no
   ticket filed since (#1542).
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
   diff (`git diff --name-only` against `origin/spec-<n>`, or
   `origin/<default>` for a one-slice spec), its uncommitted edits and
   its untracked files into that closure (#1212, #1486), so a file the worker
   reached that no candidate list named still holds the clumps that share it;
   a diff it cannot read refuses the tick. A clump sharing a file or a
   directory with a live workspace, or with a clump picked earlier the same
   tick, is **off the frontier**
   (`references/loop.md` § The exclusion rule and what it costs):
   `loop.py dispatch` picks from what is left, **widest
   closure first** so a wide clump does not sit behind narrow ones and block
   them later (#1026), and prints a `held` line for the rest naming its live
   workspace or the earlier pick. That hold is what keeps clumps that
   share a file apart: clumps sharing no file and no directory run at
   once. Two consequences,
   because neither is visible from the frontier's own definition — a run drains
   **out of ticket order**, and one parked worker can hold every clump
   sharing its files off the frontier until it lands. A controller reading only "open,
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
   every `implement-dispatch`: run the `command` line `loop.py
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
   (its ticket found already fixed on `main`) with
   `runfile.py close <run-id> --clump <n> --reason <text>`, never
   a `land` at `main`'s tip (why, and the recovery when one was recorded:
   `references/run-file.md`), and each "PR up" with `runfile.py pr-up <run-id>
   --clump <n> --pr <n>` as it arrives, for § Liveness, in this file, so a
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
10. **When the last slice has landed**, finish the spec (§ The integration branch), and
    **at run close send the closing report** (§ The closing report).

## The frontier

Which slices a run may dispatch next — open, labelled, unclaimed, waiting on
nothing — is read by `frontier.py`, not by a regex at the call site:
`python3 implement-spec/frontier.py <owner/repo> <label>` prints the `unblocked`,
`blocked`, `unresolved`, `spec`, `slice` and `stranded` buckets. Native tracker
dependencies first, the `## Blocked by` section as the fallback.

A ticket whose parent carries `spec` and which nothing blocks reads as `slice`,
naming its parent, so **this run's candidates are the `slice` lines naming this
spec**, and every other line belongs to something else. A slice with an open
blocker stays `blocked` until a landing clears it. A slice whose blockers
cannot be resolved is `unresolved`: never dispatched on the assumption that
it is clear. The grammar and the sources:
[`references/frontier.md`](references/frontier.md).

## Clumping

Each slice is its own clump — one worker, one workspace, one PR (#1542, ruling
d; #1634, ruling 1). `closure.py` groups nothing, and it reads the files each
one holds off the frontier from, not from the tickets' declared seams:
`python3 implement-spec/closure.py <repo-root> <n>=<path>[,<path>]...` prints the
mode and each clump with its **include closure**
(`references/closure.md` § Every candidate is its own clump); `--json` prints the clump
list `loop.py dispatch --candidates` reads. The repo declares its include
directive and its generator command in `AGENTS.md`; the resolver follows
that declaration one hop and **never runs the generator**. A repo that declares
nothing has its closures read conservatively by directory subtree, and the run's **opening report
carries the announcement line** the reader returns, so a controller can see
which of the three modes it got. An in-flight clump's file set is wider than
its closure by the time a dispatch reads it: § The loop step 5 unions in
its workspace's real diff. The accepted cost is two slices that touch one file
running at once, and that hold is the remaining guard. The grammar and the
evidence:
[`references/closure.md`](references/closure.md).

## Run state

A run's state is **one JSON file per run** at `~/.cache/spec-run/<run-id>.json`,
read and written by `runfile.py` — not the controller's context, and
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
3. **The backstop is a bounded sweep.** `python3 implement-spec/loop.py sweep
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
does is send the closing report (§ The closing report) rather than
dispatch again.

**Escalation.** The controller's escalation list lives in
[`GLOSSARY.md`](../GLOSSARY.md)'s Controller entry. Two of its shapes are this
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

## The integration branch

A spec with more than one slice is built on its **integration branch**,
`spec-<n>`, and reaches the default branch in one PR (#1457, rulings 1a, 2a,
4y, 5y; ADR 0006). `implement-dispatch --spec <n>` pushes `spec-<n>` off
`origin/<default>`, or reuses an `origin/spec-<n>` already there, and this
run's own workspace is on it. Each slice is dispatched onto it: its workspace
branches from `origin/spec-<n>`, and it builds with TDD, its narrowed seam and
the pre-report gate but no review wave (`implement/SKILL.md` § Review). This
run merges each slice PR into `spec-<n>` by `implement/SKILL.md` § The merge
with its slice substitutions; a slice ticket stays open until the
integration PR closes it.

When the last slice has landed:

1. **Keep current.** In this workspace, take in the slices first: they
   merged into `origin/spec-<n>` on GitHub, and the local `spec-<n>` stays
   where dispatch cut it until it does. Then merge `origin/<default>` in and
   push: `git fetch origin && git merge --ff-only origin/spec-<n> && git
   merge --no-edit origin/<default> && git push origin spec-<n>`, the block
   the closing check carries. Never a rebase: it rewrites the shas the
   dispositions name. A conflict is the fix round's first job.
2. **One review.** Run the spec-level review (§ The spec-level review).
3. **One fix round.** This run is the spec's one fix worker, in its own
   workspace on `spec-<n>`: git refuses a second checkout of a branch a
   workspace already holds. It follows steps 2–3 of
   `implement/SKILL.md` § Review, with the spec number for `<n>`: every finding gets one disposition in
   `dispositions-<spec>.jsonl`, and the run is what
   `python3 ~/.agents/skills/implement/selector_check.py command --root .`
   prints from `spec-<n>`, with `origin/<default>` merged in again: the
   repo's per-change command, as `implement/SKILL.md` § Review step 3 runs
   it. The nightly backstop is the only full run. The pre-report gate
   runs the merge check on `spec-<n>` keyed on the spec number, so
   `fix-check.sh <spec> spec-<spec>` must exit 0 before the PR goes up.
4. **The integration PR.** Run step 1's block once more, and open it:
   `gh pr create --base <default> --head spec-<n>`. Its body is
   `implement/SKILL.md` § The PR's, keyed on the spec number, with a bare
   `Closes #<slice>` line for every slice and a bare `Closes #<spec>`.
   Report it to this run's own controller as "PR up" in that section's
   shape, with `fix-check.sh <spec> origin/spec-<spec>` as the controller's
   merge check. The controller merges it unchanged by
   `implement/SKILL.md` § The merge, with step 5's check that each `Closes`
   issue closed; a `ready-for-human` spec hands Chris the merge line.

A one-slice spec gets no integration branch (ruling 3a): its slice branches
from and lands on the default branch with its own review wave, as a lone
ticket does.

## The closing check

The spec has no ticket of its own for it. Once the last slice has landed on
`spec-<n>`, this run generates the closing-check section for the integration
PR with [`closing_ticket.py`](closing_ticket.py) and posts it as a comment on
the spec issue (`gh issue comment <spec> --body-file`), so the review and the
fix round read it with the spec. The end-to-end test runs there, at the seam
on `spec-<n>` merged with current `<default>`. A one-slice spec has no
integration PR: `--one-slice` makes a section for that slice's body, appended
before it is dispatched (`gh issue edit`), with no spec-level review, since
the slice's own review wave is the review. The generator refuses to omit two
things a worker left to write the section on its own would otherwise have to
invent:

```
python3 implement-spec/closing_ticket.py <repo-root> <spec> --surface <what> [--surface <what>]...
python3 implement-spec/closing_ticket.py <repo-root> <spec> --no-surface
python3 implement-spec/closing_ticket.py <repo-root> <spec> --one-slice --no-surface   # one-slice spec
```

`<default>` is read off the repo's `origin/HEAD`, or given with `--default`;
the generator refuses rather than assume `main`.

- It names the repo's **end-to-end seam** and **what that seam is blind
  to** — from the repo's `## End-to-end seam` declaration, which outranks
  the exploration pass; the pass fills only what the declaration omits, and
  where both are present and differ the generator refuses and names both. A
  seam with no stated blind spot is refused too: a green run at a seam that
  has drifted from the shipping surface is the failure this names.
- Where the spec has a **user-visible surface the seam cannot reach**, the
  section says so, and its acceptance carries **one open of the real thing**
  for each — checked in the shipping surface, not in the seam.

The declaration grammar and the evidence:
[`references/closing-ticket.md`](references/closing-ticket.md).

## The spec-level review

One wave, after the last slice lands and `origin/<default>` is merged in,
over `origin/<default>...spec-<n>` from this run's workspace on `spec-<n>`:
the three axes of `/multi-axis-code-review origin/<default>` and one Codex
pass behind `codex-usage-gate.py`, which still answers the kill switch, the
reserve ceiling and the size threshold (`implement/SKILL.md` § The Codex
pass). The integration branch holds this spec's slices and merges of
`<default>`, nothing else, so the range is the review's own; the merge-sha
list and the cherry-picked comparison a spec landing slice by slice needed
are gone.

The ticket text the review judges against is the spec and every slice,
bodies and comments, each rendered as `implement/SKILL.md` § The brief
renders a ticket. The findings sidecars, the Codex record, the review-ledger
rows and `dispositions-<spec>.jsonl` are all keyed on the spec number, so
the escape count attributes a later bug to the review that missed it. The
slices recorded no review rows at all, not skip rows.

## The closing report

A run ends with one report, and no sweep ticket: every valid review
finding was fixed in the PR that raised it, or moved onto the open ticket for
its component (`implement/SKILL.md` § Review), so no run carries findings
forward. It goes where a message for Chris goes
(§ The dispatcher, in this file), and a run under `drain` leaves it in its
pane. Before writing it, run `python3
~/.agents/skills/multi-axis-code-review/review_ledger.py harvest`, which joins each
finding's outcome from the dispositions sidecars into the ledger. The report
carries two counts, **fixed** and **moved**,

```
python3 implement-spec/counts.py <run-id> --repo <primary checkout> --spec <n>
```

read from the spec's one `dispositions-<n>.jsonl`, naming each closed clump as
skipped: slices run no review wave and have no sidecar, so none is required per
slice, and a missing spec sidecar is refused (#1542). A one-slice spec has no
integration branch, so it drops `--spec`: its slice's own sidecar is the
record. The sidecars are found under the `--repo` checkout's cache directory,
never the cwd's, which is not always the target; `--repo` is refused unless it
is the run's recorded target. A sidecar that should exist and does not is
refused by number, never counted as zero: the worker writes it even when its
reviewers found nothing.

While an ablation runs (`docs/agents/ablations.md`, a section whose heading
ends `running`), the report also carries its escape table, read from the
ledger:

```
python3 ~/.agents/skills/multi-axis-code-review/review_ledger.py escapes --repo-dir <primary checkout>
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
