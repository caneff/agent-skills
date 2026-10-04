---
paths:
  - "**/SKILL.md"
---
# Editing a `SKILL.md`

A `SKILL.md` is code: its body changes what every later session does, so an
edit to it goes through the code lane (workspace, `/implement`, PR), never
auto-ship.

The one exception auto-ships: a change that only alters the shape of a
recurring report Chris said "always" about (a burndown verdict table, a
report format). When Chris says "always" about the shape of a recurring
output, the change goes into the skill that produces it, not into one
session's compliance.

This file loads when a session reads or edits a `SKILL.md` under its cwd
(`docs/research/2026-10-04-user-path-rules-probe.md`).
