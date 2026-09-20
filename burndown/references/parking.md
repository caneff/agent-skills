# Parking, escalation and the ruling bar: where each rule came from

`burndown/SKILL.md` § Parking and escalation, and § Before a controller
rules: those two are the policy. This file is the evidence — every clause below is a ruling or
a stall that happened on #781, and the cost it carried.

## Why exactly three park causes

A park costs the run a slot, a workspace and Chris's attention. Three causes
earn that cost, and they share a shape: the controller **cannot** rule.

1. **A question only Chris can answer.** A ruling he has reserved, a product
   decision, a repo he does not own.
2. **A lane-mandated step the harness refuses.** The controller structurally
   cannot act: every route to the same result either launders a denial or
   breaks a hard rule. Both hard blocks of the burn were this shape — a
   rebase the lane mandated and the classifier denied, and a `.scratch/`
   deletion the skill mandated and the classifier denied. Obeying the skill
   and obeying the hard rules both ended at a human.
3. **A worker that cannot get its PR to CLEAN.** The merge step refuses a PR
   that is not CLEAN, so the run has nowhere to take it.

Everything else — a spec reading, a tool's behaviour, a review finding's
disposition, a collision, an ordering — is a **controller ruling**, made
under a stated assumption and reported. A fourth cause is how "the controller
decides" turns back into the hand-run coordination the lane was rebuilt to
replace, so `burndown/parking.test.sh` counts the causes rather than only
matching them.

## Why a parked clump keeps everything

A park is not a release. The clump keeps its workspace, and its include
closure stays off the frontier while it is parked, because a second worker
dispatched into those files is the collision `burndown/SKILL.md` § The loop
step 5 exists to prevent — and the parked worker may still be holding uncommitted work in
that workspace. The cost is stated out loud in the loop: one parked worker
can hold a whole include family off the frontier until it lands. That is
starvation, it is correct, and the fix is to land or reconcile the holder.

**Two consecutive parks with no landing between them stop the run.** A run
that has stopped landing has stopped working; carrying on dispatches fresh
workers into whatever is wrong with the run rather than with the tickets.

## The two escalation shapes added

`CONTEXT.md`'s Controller entry already carried a spec-ruling change, a new
dependency, an irreversible deletion, and a repo Chris does not own. Two
more, from the burn:

- **The spec is silent on something the user needs.** There was no ruling to
  change, so this was being filed under "spec-ruling change" for want of
  anywhere better, which reads to Chris as a reversal rather than a gap.
- **A lane-mandated step the harness refuses.** The one escalation where the
  controller structurally cannot act, named so it stops being reported as a
  worker's failure.

## The ruling bar, clause by clause

**1 — runtime behaviour is checked against the thing that ships.** `#367`'s
no-ring header verified green against the headless bundle and shipped. A
later slice opened it in the live editor, where `sudoku` documents open 9×9
whatever their width; 4×4 and 6×6 were broken, and the ruling was reversed a
slice later. A proxy answers the proxy's question.

**2 — a tool's behaviour cites the tool's source.** `#559` was filed from one
sentence of `merge-cleanup --help`, which reads as a disjunction where
`is_cache` is a conjunction. The worker implemented it, disproved it by dry
run, and had to stop and ask; filed as #875. The same misreading cost `#351`
a SIGSTOP and a round trip, when a controller ordered a job "down to one
worker" — an `AGENTS.md` rule applied to a tool that hard-codes an 8-worker
portfolio, has no such knob, and times out at one worker. Help text
compresses; source does not.

**3 — a Codex finding's recommendation is evaluated, not couriered.** The
Codex pass on that same `#559` recommended **the exact approach the dry run
had already disproved**, having made the same help-text misreading.
Forwarding it would have spent the worker's last review round on a
regression. What prevented it was the controller having read the source an
hour earlier for something unrelated — luck, not process, which is why the
clause exists.

## The bounded probe

The counter-example worth keeping. Instead of forwarding three options blind,
the controller commissioned a probe with its shape stated: at most three clue
counts, one browser, no givens. It came back in minutes as a table and turned
an abstract spec question into a one-message ruling. A probe is cheap, it is
bounded by the controller and not by the worker's judgment, and it is what
clause 1 looks like when the thing that ships has not been opened yet.
