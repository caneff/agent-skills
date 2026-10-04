---
paths:
  - "**/docs/research/**"
---
# Writing under `docs/research/`

A research note, and a script here that nothing imports or runs, is not code:
it auto-ships (edit on `main`, commit, push). A script here that something
runs (a cron line, a hook, an import) is code and goes through the code lane.

This file loads when a session reads or edits a file under a `docs/research/`
inside its cwd (`docs/research/2026-10-04-user-path-rules-probe.md`).
