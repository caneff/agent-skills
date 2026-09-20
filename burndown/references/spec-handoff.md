# Spec handoff

> **Parked** with the rest of the burndown skill until the multi-worker lane
> is rebuilt on herdr — see
> [#700](https://github.com/caneff/agent-skills/issues/700)'s "Out of scope"
> note. Written against that rebuild; not executable policy until the lane is
> unparked. The retired Orca-era text: `git show
> 7c7eb30:burndown/references/spec-handoff.md`.

Read this when a burn's candidate turns out to be a slice — its parent issue
carries the `spec` label. Nothing else in a burn reaches this file.

A spec's slices are built together or not at all, as one nested run under
[`implement-spec`](~/.agents/skills/implement-spec/SKILL.md), which is that
run's whole policy. This file states none of it and adds nothing to it; what
a burn owes the handoff is only this:

- The **spec**, not the slice, is the unit. Find the parent and confirm its
  label before anything else: `gh api
  repos/<owner>/<repo>/issues/<n>/parent`, or the `Part of #<n>` reference in
  the body where the tracker has no sub-issues.
- Every open slice of that spec leaves this burn's own candidate set at
  handoff, ready or blocked alike. A slice already in flight under a burn
  worker finishes where it is; the spec run picks up from its landing.
- The spec run is a worker to this burn. It reports, parks and escalates as
  one; its workspaces are its own to hold and to tear down; and what its
  slots cost this burn is stated where the nesting is, not here.

A slice whose parent carries no `spec` label is an ordinary candidate. A spec
with one open slice is still handed off: the run's closing ticket and
spec-level review are the point, not the count.
