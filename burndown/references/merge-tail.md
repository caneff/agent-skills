# Merge tail: branches that conflict with each other

Read this when the dry-run merge in § Report shows two of this burn's branches
conflicting with each other. Until it does, the one-line merge is all you need.

**Branches that conflict with each other get linearised, not squashed.** Two
PRs that touch the same line (an import list, a scenario count) both merge
clean against the default branch and then conflict with each other after the
first squash, so the one-line merge stops halfway. When the dry run shows
that, rebase the later branches into one linear stack in merge order,
resolving only the shared line, verify each rebased branch's diff is identical
to its reviewed diff apart from that line, run the seam at the stack tip,
force-push (with lease), note the new base sha in each PR body, and hand the
line with `--merge` in place of `--squash` — merge commits keep a linear stack
mergeable in one line, squashes do not. Every PR still opens against the
default branch, never against its base branch: GitHub closes a PR whose base
branch is deleted and cannot reopen it.
