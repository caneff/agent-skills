Positive control for `tests/lane-unparked.test.sh`. Not a skill, not policy,
and deliberately outside the skills tree the check sweeps: every line below
is one of the parked markers the check hunts, so the check can prove it can
see a marker before its silence about the real tree means anything.

Every marker pattern the check knows must match at least one line here. A
pattern that matches nothing here is a pattern that would pass the real
sweep whatever the tree said, and the check fails on that rather than on the
tree.

description: "Parked: drain a mixed-origin ticket queue to empty as one supervised run."
> **Parked** until the multi-worker lane is rebuilt on the herdr lane — see #700.
Written against the lane being rebuilt, and parked with the rest of this skill.
Parked along with the rest of the burndown skill (see #700's "Out of scope" note).
Nothing here is executable policy until the multi-worker lane is unparked.
Nothing re-announces today because nothing runs a burn today: this skill is parked.
Full text: `git show 7c7eb30:burndown/SKILL.md`.
