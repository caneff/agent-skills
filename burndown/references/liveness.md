# Liveness: why the ranking reads the way it does

`burndown/SKILL.md` § Liveness: that is the ranked list. This file is the evidence
behind it — what each source was measured at on #781, and what it costs when
it is read the other way. `burndown/loop.py`'s `sweep` is the reader that
applies the mechanical half.

## The wake, and why nothing replaces it

A worker's `SendMessage` reaches an idle controller as that controller's next
turn, about a second after the send (#778). It is the only source that
carries what the worker actually has to say; every other signal below says
something about a pane, not about the work.

It has one precondition, and it is the reason the loop's wait step is written
as "be idle": a controller **inside a tool call** receives nothing until that
call returns. An untimed wait, a long sleep, a blocking read of another
session — each turns the primary path off for as long as it runs, and the
sources below are a backstop, not a substitute.

## Why the stop alert is only a hint

Measured across the two #781 runs: the alert fired **six times** and was
wrong **six times**. Three distinct benign causes, none of which is a stuck
worker:

- an outstanding background shell;
- outstanding Monitor tasks;
- a worker that had already reported and was answering a message that needed
  no reply — which means a diligent controller, answering its workers,
  manufactures its own false alerts.

#886 fixed the hook's worst case. The demotion does not depend on that fix:
a signal whose true-positive rate was 0 in 6 is read as *read this pane*, and
what the pane says is what the controller rules on. Parking a clump, holding
a slot or calling a worker stalled on the alert alone is acting on the one
thing the trial measured as noise, and `burndown/liveness.test.sh` asserts
the skill never instructs it.

## Why the backstop is a sweep, and why it is bounded

A vanished pane is findable no other way (#778): the worker sends nothing
because there is no worker, and no message ever arrives to be waited on. So
the backstop reads the machine — one `herdr agent get` per live slot — rather
than waiting harder on a channel that has nothing to deliver.

Bounded means what it says: one call per live, unlanded slot, no retry, no
wait, and nothing for a clump that already landed. `sweep` never raises on a
worker's own probe failure either — a herdr that answers for two workers and
not the third still tells the controller about two, and the third is reported
as `unreachable`, which is a different fact from `vanished`.

**One deadline covers the sweep, not each probe.** A per-probe bound looks
sufficient and is not: it composes. Five live workers with hung panes, at ten
seconds each, is fifty seconds inside one tool call — the controller is deaf
for all of it, and the worst case grows with the wave size instead of staying
a constant. So the budget belongs to the sweep: each probe is handed what is
left of it, and a slot the deadline never reached is `unswept` rather than
anything about that pane. It costs nothing to leave one for later, because
the sweep only ever runs on a wake the controller already had.

It is **not a timer**. A timer means either a sleep or a poll, and both put
the controller inside a tool call while workers are out, which is the one
state the primary path cannot survive. The sweep runs on an idle wake with
nothing else to do — a wake the controller got for free, from a worker's own
report or from Chris.

## What the sweep is blind to

The sweep answers two questions: does herdr still have a pane by this name,
and what state does herdr report it in. It answers no third question. A
worker spinning on identical no-op tool calls reads `working` on every signal
the sweep has, including the pane state (#925). That failure is the opposite
shape from the one this sweep exists for, and a controller that reads
`working` as "making progress" has over-read it.

## The core count, and the 25.8

`#351`'s worker ran `verify.py`, which hard-codes an 8-worker CP-SAT
portfolio, at ~793% CPU. Box load reached **25.8** alongside another agent's
census **with no dispatch pending**, so no box check could have caught it:
the controller's budget was counted in slots and the real contention was in
cores, and nothing bridged the two.

The bridge is the worker's own declaration, because the worker is the only
party that knows. A slot is one core's worth of machine until a worker says
otherwise; the cores past the job's own slot come off the free slots for as
long as the job is out, and the reader prints which clump is holding what so
the controller's status line can carry it.

**The declaration is state on the clump, not an argument to a dispatch.** It
lives in the run file — `running` with its core count, `none` when the worker
says it launched nothing, `done` when it reports the job finished — because a
controller that restarts mid-run has only that file. A hold that lived in one
command line is a hold the resume cannot recover, and the free slot it then
dispatches into is the 25.8 load above, reached a second time by a controller
that had already been told. For the same reason a live clump with no record
at all is refused by name rather than charged zero: silence is not zero one
layer up, and the reader obeys the same rule.

The controller's attempted fix that day is the counter-example for how
**not** to rule on this: it ordered the job down to one worker, applying an
`AGENTS.md` rule to a tool that has no such knob and times out at one worker.
That is `burndown/SKILL.md` § Before a controller rules, clause 2 —
a ruling about a tool's behaviour cites the tool's source.
