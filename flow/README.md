# flow — the local tooling the dev flow depends on

The scripts, hooks, and Claude config that the plan→build→ship flow runs on live
outside any repo, at `~/.local/bin` and `~/.claude`. If this machine died, they
would be gone. This directory is their backup: the repo holds the canonical
copy, `install.sh` symlinks the live locations back to it, and from then on
every commit here is a backup.

## What's here

| Repo path | Live location | What it is |
|---|---|---|
| `bin/ship` | `~/.local/bin/ship` | Merge a PR, wait for it to land, sync main |
| `bin/pushpr` | `~/.local/bin/pushpr` | Push branch + open PR through the outward gate |
| `bin/issue-counts` | `~/.local/bin/issue-counts` | Open-issue counts per wayfinder group for the current repo |
| `claude/CLAUDE.md` | `~/.claude/CLAUDE.md` | Global instructions (hard rules, the two gates) |
| `claude/RTK.md` | `~/.claude/RTK.md` | RTK proxy notes |
| `claude/settings.json` | `~/.claude/settings.json` | Harness config: hooks, permissions |
| `claude/settings.local.json` | `~/.claude/settings.local.json` | Machine-local overrides |
| `claude/hooks/*` | `~/.claude/hooks/*` | git guardrail + main-sync hooks |
| `ccstatusline/settings.json` | `~/.config/ccstatusline/settings.json` | ccstatusline layout + per-widget colors |
| `ccstatusline/issue-counts-segment.sh` | `~/.config/ccstatusline/issue-counts-segment.sh` | Cached statusline widget calling `issue-counts` |

`~/.claude/skills` is already this repo, so it isn't duplicated here.

## Copy-only backups (not symlinked)

These live on the Windows side of WSL, where a repo symlink won't hold, so
they're plain snapshots — `install.sh` does not touch them, and they go stale
unless re-copied after you change them.

| Repo path | Live location | What it is |
|---|---|---|
| `vscode/settings.json` | `/mnt/c/Users/<you>/AppData/Roaming/Code/User/settings.json` | Windows VS Code user settings (incl. GitHub-issue queries) |

Re-copy into the repo after editing VS Code settings; restore with the reverse
`cp`.

The other segments `ccstatusline/settings.json` references (`effort-abbrev.py`,
`usage-segment.sh`, `sandcastle-segment.sh`, `publish-usage.sh`) are not backed
up here yet — a fresh restore links the config but those widgets won't run until
their scripts exist.

## Restore on a fresh machine

```sh
git clone <agent-skills>  ~/.agents/skills   # or wherever it lives
~/.agents/skills/flow/install.sh
```

`install.sh` is idempotent and moves any existing real file aside to
`<file>.pre-flow` before linking, so nothing is overwritten silently.

## Notes

- `CLAUDE.md` `@`-imports the second-brain vault (`~/src/second-brain-v2`),
  which is its own repo — back that up there, not here.
- `settings.local.json` is machine-local by convention; it's kept for disaster
  recovery, but review it before linking on a second machine.
