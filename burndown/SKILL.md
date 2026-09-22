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
too.

**Open the run.**

1. Take the seat (above), then `runfile.py start` the run with its slot
   budget (5 when `--slots` is omitted) and the controller's own herdr
   agent name (§ Run state). Resuming an existing run instead:
   `runfile.py resume`, and then **one message per live, unlanded worker**
   — its `announce` bucket and only that one, via `loop.announce`. A
   landed clump's worker gets none however its agent looks; a vanished one
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
   every docs-only candidate, because the tier is read off the ticket at
   dispatch and a label written after that is a label that came too late.
3. The **opening report** carries `closure.py`'s announcement line verbatim,
   so the reader can tell all three declaration states apart: a declared
   directive, a **declared None** — the repo has no include graph — and
   **silence**, which clumps conservatively by directory subtree. A
   controller reading "conservative" has to know which of the last two it
   got. It also carries `tier.py`'s line (§ Tier tagging), which **names
   every label the exploration pass wrote** and says `labels written: none`
   when it wrote none — a report silent about labels reads the same from a
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
   `loop.py dispatch`'s `--in-flight`. A clump whose closure intersects a
   live workspace's is **off the frontier**: `loop.py dispatch` picks from
   what is left and names what holds the rest. That hold, with `picks`'
   same-tick guard (two clumps sharing a file are never picked in one tick,
   and that skip prints its own `held` line, naming the earlier pick it
   collided with rather than a live workspace), is what keeps a **family's
   clumps** apart: a clump sharing a file with a live or just-picked one waits, and
   family members sharing no file run at once. Two consequences, because
   neither is visible from the frontier's own definition — a run drains
   **out of ticket order**, and one parked worker can hold a **whole family**
   off the frontier until it lands. A controller reading only "open,
   unblocked, unclaimed" would dispatch into the collision.
6. **Full re-exploration fires on one trigger**: a landing whose diff touched
   a **hub** — a file two or more candidates' closures share
   (`loop.py hub`). Every other landing gets step 5 and nothing more.
7. **Box check before every dispatch** — read `uptime` and `free -g`, and
   pass the committed `ulimit -v` GB to `loop.py dispatch`, which weighs every
   worker the tick would start, takes only as many as the box has room for,
   and refuses outright when that is none. The **28** cap counts **agent
   processes** — Claude sessions, subagents included — across the whole
   shared box, not this run's and **not OS processes**: an idle WSL box holds
   ~190 of those, so `ps | wc -l` refuses every dispatch. `loop.py` measures
   the agent count itself (`ps -eo comm= | grep -cx claude`, by command name:
   `pgrep -f claude` also matches plugin scripts and hook shims and
   overcounts more than 2x); `--processes <n>` overrides it, and the refusal
   names the number and the counter. A box it cannot measure, or
   one listing no `claude` at all (the controller is one), is refused, never
   read as empty; pass `--processes` with a count you took. The ~**24 GB**
   ceiling is on the sum of the per-process `ulimit -v` caps. A slot the box
   cannot afford stays empty; that is not a reason to dispatch into it
   anyway. A slot is budgeted at its **peak**, not its steady state (#933):
   `references/loop.md` § The box check, and `loop.py dispatch` prints the
   `peak:` line that goes in the status line below. `loop.py box` takes
   `--live <n>`, the workers already running; omitting it is refused.
8. Dispatch and merge through
   [`implement`](~/.agents/skills/implement/SKILL.md) § Dispatch, which
   claims the clump and starts the worker; `implement/SKILL.md` § The merge,
   which merges and cleans up, is the controller's own step there. The loop
   restates neither grammar. When two in-flight branches turn out to touch
   the same files, the collision procedure, the closure defect it implies,
   and the rule that every outstanding worker question is answered **before**
   cleanup: [`references/merge-tail.md`](references/merge-tail.md). Register
   each dispatched clump with
   `runfile.py clump` — its workspace and its worker's herdr agent name, or
   step 1's resume has nothing to re-announce to — and each landing with
   `runfile.py land`, so a restart can pick the run back up.
9. **Wait on the wake, and sweep on an idle one.** The loop waits by being
   idle, never inside a tool call: a controller in one hears no worker until
   it returns. What it trusts while it waits, in rank order, and the bounded
   backstop it runs when it wakes with nothing else to do: § Liveness. A
   clump that cannot go on parks, and a run that parks twice with no landing
   between stops: § Parking and escalation.

## The frontier

Which tickets a run may dispatch next — open, labelled, unclaimed, waiting on
nothing — is read by `burndown/frontier.py`, not by a regex at the call site:
`python3 burndown/frontier.py <owner/repo> <label>` prints the `unblocked`,
`blocked`, `unresolved` and `spec` buckets. Native tracker dependencies
first, the `## Blocked by` section as the fallback, and a ticket with neither
is **unresolved** — never dispatched on the assumption that silence means
clear. A `spec`-labelled parent is none of those three: it is dispatchable by
a different verb, and its entry names that verb —
`implement-dispatch --spec <n> --slots <k>` — so a controller can act on the
line without opening another document.
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
which of the three modes it got. The grammar and the evidence:
[`references/closure.md`](references/closure.md).

## Tier tagging

A candidate's **tier** is read off its `documentation` label at dispatch, so
a docs-only ticket whose author forgot the label takes TDD, a three-axis
review and a PR for a page of prose (#781's `#371`). After clumping and
**before the first dispatch**, `burndown/tier.py` writes that missing label
onto the ticket — `python3 burndown/tier.py <owner/repo>
<n>=<path>[,<path>]... [--dry-run]`, the clumper's own candidate grammar. The
label, not a flag: `merge-cleanup`, `/landed` and a resumed controller all
read the ticket, and a flag is gone the moment dispatch returns.

It **only ever adds**. A candidate is docs-only when every file it targets is
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
`runfile.py start --slots <k>`), the controller's herdr agent name, and
per clump its ticket list, workspace, worker's herdr agent name, the
parallel job its worker has out (§ Liveness) and squash sha once it
lands. `runfile.py resume <run-id> --live
<names> --controller <my agent name>` reads it back and splits the clumps into
the live workers to **re-announce** the controller to, the vanished ones to
reconcile by hand, and the landings already banked — the live names read off
the machine, never off the file.

A worker is addressed by its **herdr agent name** throughout, because a WSL
restart renames every Claude session and every brief hard-codes
`--controller "<name>"`. The retired per-repo `~/.cache/burndown/<repo>.progress`
file is gone; nothing reads or writes one. The contract, the JSON shape and the
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
   --workers <run file's clumps>` probes each live slot once through `herdr
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

**A worker declares its job size.** A worker that launches a parallel job
names that job and its **core count** in its report, and a worker that
launched none **says so explicitly**: silence is not zero. A worker that
forgot to declare reads exactly like one that ran nothing, and the controller
would charge zero against the free slots either way — the same fail-closed
posture the reader takes one layer down. The controller records it on the
clump — `runfile.py job <run-id> --clump <n> --cores <k>`, or `--none`, or
`--done` when the worker reports it finished — and `loop.py dispatch` reads
the charge from **that record**, never from its own argv: a declaration that
lived in one command line is a hold a restart cannot recover, and the free
slot a resumed controller then dispatches into is the contention #351
produced.

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

A parked clump **keeps its workspace**, and its include closure stays **out of
the frontier** while it is parked: releasing either invites a second worker
into the same files, which is the collision § The loop step 5 exists to
prevent. **Two consecutive parks with no landing between them stop the run** —
a run that has stopped landing has stopped working, and the next thing it
does is report to Chris rather than dispatch again.

**Escalation.** The controller's escalation list lives in
[`CONTEXT.md`](../CONTEXT.md)'s Controller entry. Two of its shapes are this
run's to recognise: *the spec is silent on something the user needs*, which is
a gap and not a change to a ruling, and *a lane-mandated step the harness
refuses*, the one escalation where the controller **structurally** cannot
act.

**A bounded probe before escalating.** A controller **may commission a bounded
probe** from a worker before it escalates — a named, small, time-boxed
measurement whose shape it states, so an abstract question reaches Chris as a
table instead of three options in the dark. On #781 that was three clue
counts, one browser, no givens; it came back in minutes and turned a spec
question into a one-message ruling.

## Before a controller rules

Three clauses, each a ruling that went wrong on #781. The evidence behind
each: [`references/parking.md`](references/parking.md).

1. A ruling about **runtime behaviour** is checked against **the thing that
   ships**, not a proxy. A headless bundle, a unit harness or a build artifact
   is a proxy, and green on one is not green in the app.
2. A ruling about a **tool's behaviour** cites the **tool's source**, not its
   help text. Help text compresses; a conjunction reads as a disjunction and
   the ticket filed from it is wrong.
3. A **Codex finding's recommendation** is **evaluated by the controller**
   before it reaches the worker. The controller is not a courier: a plausible
   remedy forwarded unread can spend a worker's last review round on a
   regression.
