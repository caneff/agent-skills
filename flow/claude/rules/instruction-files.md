---
paths:
  - "**/CLAUDE.md"
  - "**/AGENTS.md"
  - "**/RULES.md"
  - "**/CODING_STANDARDS.md"
---
# Editing an always-on instruction file

Progressive disclosure governs this file and every always-on agent doc
(`CLAUDE.md`, `AGENTS.md`, `CODING_STANDARDS.md`, `Memory/RULES.md`). A rule
stays inline only if it fires in most sessions or guards an expensive or
irreversible mistake. Anything else gets one action-worded pointer line
("Before you X: read Y"), with the detail in a read-on-demand doc. A rule a
hook already enforces is one line naming the guard. Each rule is stated once,
in the place that loads it.

The global `CLAUDE.md` plus its `@`-imports is held under 1,100 words by
`tests/check-always-on.py` in the agent-skills repo, which also fails a
pointer line whose path does not exist (#1413).

This file loads when a session reads or edits a matching file under its cwd
(`docs/research/2026-10-04-user-path-rules-probe.md`).
