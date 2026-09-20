## Agent skills

### Issue tracker

Issues tracked in GitHub Issues via the `gh` CLI; external PRs are not a triage surface. See `docs/agents/issue-tracker.md`.

### Triage labels

Six canonical roles, all mapped to their default label strings (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `backlog`, `wontfix`). See `docs/agents/triage-labels.md`.

### Include closure

None — no file in this repo is generated from another. Add a `**Directive**:` and a `**Generator**:` line here the day that stops being true. The grammar, and what a run does with it: `burndown/references/closure.md`.

### Domain docs

Single-context: one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
