---
name: file-ticket
description: Turn a review finding or chat conclusion into a tracked issue, one-shot. Use when the user says "file it", "file 1", "file a ticket for X", or "file tickets for X and Y" — a capture request, not a spec to slice or a batch to triage.
---

# File Ticket

One-shot capture: the thing just discussed becomes one tracked issue, filed
ready to start unless its readiness is genuinely in doubt.

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
- **Label**: take the label strings from the triage-label mapping that
  should have been provided to you. Default to the ready state:
  `ready-for-agent`, or `ready-for-human` when the work needs a human's
  hands. Use `needs-triage` only when you are genuinely unsure the ticket
  is ready to start, or unsure which label attaches, and say in the body
  what is in doubt. Why: a ticket whose scope the conversation already
  settled, filed as `needs-triage`, waits for a manual relabel before
  anyone can dispatch it. When the finding is obviously a bug or an
  enhancement, add that label too.

## Create it

Pass `--repo <owner>/<repo>` on every `gh` call. Read the owner/repo pair
from the `origin` remote (`git remote -v`) — if `origin`'s owner isn't your
`gh` login, hand the command back instead of filing it yourself.

Build the body through a heredoc so evidence text (backticks, `$(...)`,
`$N`) isn't shell-expanded:

```
gh issue create --repo <owner>/<repo> --title "<title>" \
  --label "<ready or needs-triage label>[,<bug-or-enhancement label>]" \
  --body "$(cat <<'EOF'
<body>
EOF
)"
```

Filing more than one target prints one URL per line, in the order the
targets were given.
