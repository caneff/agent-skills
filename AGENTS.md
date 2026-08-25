## Agent skills

### Issue tracker

Issues tracked in GitHub Issues via the `gh` CLI; external PRs are not a triage surface. See `docs/agents/issue-tracker.md`.

### Triage labels

Six canonical roles, all mapped to their default label strings (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `backlog`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

### After cutting a `sandcastle-template/v*` tag

The tag does not reach installed repos on its own. Once you cut a new
`sandcastle-template/v*` tag, prompt the maintainer to sweep it out with
`sandcastle-propagate` (dry-run first). See
`setup-sandcastle/references/updating-adopters.md`.
