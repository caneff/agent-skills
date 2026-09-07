# Spec handoff

Read this when step 2 finds a ticket whose parent issue carries the `spec`
label. Nothing else in a burn reaches it.

A ticket whose parent issue carries the `spec` label is a slice, and slices
are built together or not at all: one workspace, one branch, one PR that
closes the spec and every child, with the end-to-end review loop that only
`implement-spec` runs. Building them one PR at a time here loses that loop and
lands a spec in pieces a human has to reassemble.

So the spec, not the slice, is the unit. Find the parent with
`gh api repos/<owner>/<repo>/issues/<n>/parent` (or the `Part of #N`
reference in the body when the tracker has no sub-issues) and confirm its label.
Then:

- Make one Orca workspace **from the spec issue** and dispatch one Orca task
  in it — a top-level `claude` session seeded with the spec URL and the pointer
  `~/.agents/skills/implement-spec/SKILL.md`, which it follows as coordinator.
  That coordinator owns the spec's exploration, frontier, gates, review loop,
  and PR; this burn does not look inside.
- Every open slice of that spec — ready or still blocked — leaves this burn's
  queue at handoff, and the cluster counts against the ticket cap as its
  number of slices. Slices already `in-progress` under a burn worker finish
  as they are; the spec coordinator picks up from their landings.
- Progress lines use the spec's number: `burning #<spec>`, then `#<spec> pr
  <ref>` or `#<spec> parked: <why>`. A gate the spec coordinator raises is that
  burn's `ready-for-human` for the whole spec — park it, do not answer it.
- The spec's workspace is the coordinator's to tear down, not this burn's.

A slice with no `spec`-labelled parent is an ordinary ticket. A spec with
exactly one open slice is still handed off — the loop is the point, not the
count.
