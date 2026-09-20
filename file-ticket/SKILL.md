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
  Close every code fence you paste: the frontier reader treats everything
  after an unterminated ``` as quoted, which swallows the `## Blocked by`
  section below and reads the ticket as **unresolved**.
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
- **Blocked by**: a `## Blocked by` section, last in the body, on every
  ticket this skill files — one bare `#NNN` per blocking issue **in the
  repo you are filing into**, one per list item, or the literal `None — can
  start immediately.` when nothing blocks it. Never omit it, and never leave it to the filer's
  judgement: a ticket carrying neither native dependency edges nor that
  section reads as **unresolved** to the frontier reader — neither blocked
  nor unblocked, and never dispatched — so a controller resolves it by hand
  before any wave. You are usually filing a finding raised inside a known
  piece of work, so the blocker is known here: it is the ticket whose build
  raised this finding, whenever that build has to land before this one can
  start. The grammar and what each answer means:
  `~/.agents/skills/burndown/references/frontier.md`.

## Create it

Pass `--repo <owner>/<repo>` on every `gh` call. Read the owner/repo pair
from the `origin` remote (`git remote -v`) — if `origin`'s owner isn't your
`gh` login, hand the command back instead of filing it yourself.

Build the body through a heredoc so evidence text (backticks, `$(...)`,
`$N`) isn't shell-expanded:

```
gh issue create --repo <owner>/<repo> --title "<title>" \
  --label "<role label>[,<bug-or-enhancement label>]" \
  [--blocked-by <#,#>] \
  --body "$(cat <<'EOF'
<body>

## Blocked by

- None — can start immediately.
EOF
)"
```

With blockers, that last line becomes one `- #<n>` line per blocking issue,
and `--blocked-by <#,#>` names the same issues — the tracker's **native**
edge, set **in addition to** the section and never instead of it. Drop the
bracketed flag when nothing blocks the ticket. Native edges are the live gate: closing a blocker moves the count with
nobody editing prose. The section is the fallback the reader parses where
the tracker holds no edges, so where `gh` rejects the flag it still states
the relationship on its own.

Filing more than one target prints one URL per line, in the order the
targets were given.
