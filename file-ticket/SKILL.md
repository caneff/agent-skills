---
name: file-ticket
description: Turn a review finding or chat conclusion into a tracked issue, one-shot. Use when the user says "file it", "file 1", "file a ticket for X", or "file tickets for X and Y" — a capture request, not a spec to slice or a batch to triage.
---

# File Ticket

One-shot capture: the thing just discussed becomes one tracked issue,
filed with the role that says who acts on it next.

## Resolve the target

"File it" points at the most recent finding or conclusion in the
conversation. "File 1" or "the label collision" narrows it. A request that
names more than one target repeats **Write the issue** through **Create it**
once per target.

If it's unclear which finding "it" refers to — more than one was raised and
none was named — **ask one question** listing the candidates. Do not
guess and do not create an issue until the target is confirmed.

## Write the issue

- **Title**: short, imperative, matches this repo's tone, under about 70
  characters.
- **Body**: two to five sentences, covering — what (the finding or
  conclusion, in your own words), where (durable anchors: file plus symbol
  or grep string, never a line number — those drift), evidence (the
  concrete detail that makes it checkable: a grep hit, an error string, a
  repro step), and a trailing "Filed from" line naming the source
  (conversation, review, digest).
- **Label**: the triage-label mapping should have been provided to you —
  it maps each role below to this repo's label string. Give the ticket
  exactly one of three roles: `ready-for-agent` when it is fully specified
  and an agent can build it unattended; `ready-for-human` when it is
  specified but a human builds it (a taste call, credentials, something
  the user wants to write themselves); `needs-info` when it needs grilling
  first. A ticket genuinely too unclear to call is `needs-info`, with the
  body saying what is unclear. Never `needs-triage` — that role is for
  issues outside people open. Why: the filer already knows the ticket's
  state, and a ticket filed as `needs-triage` waits for a manual relabel
  before anyone can dispatch it. When the finding is obviously a bug or an
  enhancement, add that label too.

## Create it

Pass `--repo <owner>/<repo>` on every `gh` call. Read the owner/repo pair
from the `origin` remote (`git remote -v`) — if `origin`'s owner isn't your
`gh` login, hand the command back instead of filing it yourself.

Build the body through a heredoc so evidence text (backticks, `$(...)`,
`$N`) isn't shell-expanded:

```
gh issue create --repo <owner>/<repo> --title "<title>" \
  --label "<role label>[,<bug-or-enhancement label>]" \
  --body "$(cat <<'EOF'
<body>
EOF
)"
```

Filing more than one target prints one URL per line, in the order the
targets were given.
