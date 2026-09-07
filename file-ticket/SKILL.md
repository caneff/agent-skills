---
name: file-ticket
description: Turn a review finding or chat conclusion into a tracked issue, one-shot. Use when the user says "file it", "file 1", "file a ticket for X", or "file tickets for X and Y" — a capture request, not a spec to slice or a batch to triage.
---

# File Ticket

One-shot capture: the thing just discussed becomes one issue, labeled
`needs-triage`, in the current repo's tracker. Not `to-tickets` (spec
slicing) and not `/triage` (sorting an existing backlog) — this only fires
on a direct "file it" request.

## Resolve the target

"File it" points at the most recent finding or conclusion in the
conversation. "File 1" or "the label collision" narrows it. A request that
names more than one target files one issue per target, run through this
same process each time.

If it's unclear which finding "it" refers to — more than one was raised and
none was named — **ask one question** listing the candidates. Do not
guess and do not create an issue until the target is confirmed.

## Write the issue

- **Title**: short, imperative, matches this repo's existing style — sample
  recent titles with `gh issue list --repo <owner>/<repo> --limit 20 --json
  title` before writing one from scratch.
- **Body**: three parts — what (the finding or conclusion, in your own
  words), where (file:line, command output, or the part of the conversation
  it came from), evidence (the concrete detail that makes it checkable: a
  grep hit, an error string, a repro step).
- **Label**: the triage role this repo calls `needs-triage` — read
  `docs/agents/issue-tracker.md` (or wherever the repo's setup skill points)
  for the tracker convention and its triage-label mapping if one exists;
  fall back to the literal string `needs-triage` when no mapping doc exists.

## Create it

Every `gh` call in this skill carries an explicit `--repo`, even though the
tracker doc's own examples omit it — infer `owner/repo` from `git remote -v`
in the current worktree, never rely on `gh`'s cwd-inference alone:

```
gh issue create --repo <owner>/<repo> --title "<title>" --body "<body>" --label needs-triage
```

`gh issue create` prints the new issue's URL on success — print that URL
back **bare**, on its own line, nothing else wrapped around it.
