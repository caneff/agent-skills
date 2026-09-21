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
  Quote every scrap of another ticket you paste — `> ` on each line, or
  a closed fence around it. A bare `Blocked by` heading inside your
  evidence is read as this ticket's own declaration and beats the one
  the skill appends below, so the ticket reports blockers it never
  claimed; indenting does not neutralise it, because the reader allows
  leading whitespace on a heading. An unterminated ``` is the other way
  a section goes unread: everything after it is quoted, which swallows
  the `## Blocked by` section below and reads the ticket as
  **unresolved**.
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
  repo you are filing into**, one per list item, or the literal `None —
  can start immediately.` when nothing blocks it. Never omit it, and
  never leave it to the filer's judgement: a ticket carrying neither
  native dependency edges nor that section reads as **unresolved** to
  the frontier reader — neither blocked nor unblocked, and never
  dispatched — so a controller resolves it by hand before any wave. You
  are usually filing a finding raised inside a known piece of work, so
  the blocker is known here: it is the ticket whose build raised this
  finding, whenever that build has to land before this one can start.
  A blocker in another repo is written `owner/repo#NNN` in full, never a
  bare `#NNN` (the reader would resolve that against this repo and gate
  the ticket on an unrelated issue). The grammar refuses the full form on
  purpose, so the section alone leaves the ticket **unresolved** until the
  native edge below exists; that is the true answer, and the edge is what
  carries the gate.
  The grammar and what each answer means:
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
  --body "$(cat <<'EOF'
<body>

## Blocked by

- None — can start immediately.
EOF
)"
```

With blockers, that last line becomes one `- #<n>` line per blocking
issue. **Then** add the tracker's native edge, as a second command over
the issue the first one printed:

```
gh issue edit <n> --repo <owner>/<repo> --add-blocked-by <#>
```

For a blocker in another repo the edge takes the full issue URL, which
`gh` accepts (2.95.0): `gh issue edit <n> --repo <owner>/<repo>
--add-blocked-by https://github.com/<owner>/<repo>/issues/<n>`, with the
blocker's own owner, repo and number.

In addition to the section, never instead of it: native edges are the live
gate — closing a blocker moves the count with nobody editing prose — and
the section is the fallback the reader parses where the tracker holds no
edges. The edge comes second so that the ticket exists and reads correctly
whatever the edge does: an old `gh` without the flag, or a tracker with no
dependency support, is a reported failure over a filed, readable ticket
rather than a filing that never happened. (`gh` 2.95.0 has both
`--add-blocked-by` here and `--blocked-by` on the create; the second
command is for the machines that do not.) Say so in your reply when the
edge fails — the section still states the relationship, and nobody has to
find out from the tracker later.

Filing more than one target prints one URL per line, in the order the
targets were given.
