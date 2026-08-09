# Skills reach the tracker doc through `AGENTS.md`, not by path

Status: accepted

## Context

Most engineering skills here say "the issue tracker should have been provided to
you — run `/setup-matt-pocock-skills` if not" and never name a file. Only
`AGENTS.md` and the setup skill name `docs/agents/issue-tracker.md` directly.
Read as a dependency graph this looks like friction: eight consumers, three
references, five skills apparently depending on a doc they never point at. An
architecture review raised exactly that and proposed making every consumer cite
the path.

## Decision

Skills keep referring to "the issue tracker" and do not hardcode
`docs/agents/issue-tracker.md`.

Two facts make the indirection correct. `AGENTS.md` is loaded into agent context
already and names the path there, so the doc is present without each skill
repeating it. More importantly, these skills are installed into *other* repos,
where the tracker may be GitLab or plain markdown files and the doc may sit
elsewhere — `/setup-matt-pocock-skills` writes one of three adapter templates.
A hardcoded path would weld every skill to this repo's layout and break the
adapter seam that lets the same skill drive three trackers.

## Consequences

- Do not "fix" the missing path references. The vagueness is load-bearing.
- The real coupling risk is the opposite one: this repo's own tracker doc is the
  one that gets improved in daily use, and those edits do not flow back to the
  three generator templates. That drift is worth watching; the reference style
  is not.
