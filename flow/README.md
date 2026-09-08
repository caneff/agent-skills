# flow — the local tooling the dev flow depends on

The scripts, hooks, and Claude config that the plan→build→ship flow runs on live
outside any repo, at `~/.local/bin` and `~/.claude`. If this machine died, they
would be gone. This directory is their backup: the repo holds the canonical
copy, `install.sh` symlinks the live locations back to it, and from then on
every commit here is a backup.

## What's here

| Repo path | Live location | What it is |
|---|---|---|
| `bin/issue-counts` | `~/.local/bin/issue-counts` | Open-issue counts per wayfinder group for the current repo |
| `claude/CLAUDE.md` | `~/.claude/CLAUDE.md` | Global instructions (hard rules, the two gates) |
| `claude/settings.json` | `~/.claude/settings.json` | Harness config: hooks, permissions |
| `claude/settings.local.json` | `~/.claude/settings.local.json` | Machine-local overrides |
| `claude/hooks/*` | `~/.claude/hooks/*` | git guardrail, landed-refresh, agent-model-guard hooks |

`~/.claude/skills` is already this repo, so it isn't duplicated here.

## Copy-only backups (not symlinked)

These live on the Windows side of WSL, where a repo symlink won't hold, so
they're plain snapshots — `install.sh` does not touch them.

| Repo path | Live location | What it is |
|---|---|---|
| `vscode/settings.json` | `/mnt/c/Users/<you>/AppData/Roaming/Code/User/settings.json` | Windows VS Code user settings (incl. GitHub-issue queries) |

`backup-sync.sh` walks a manifest of these repo↔live pairs (one line per file,
top of the script):

- `backup-sync.sh` — refresh the repo copies from the live files.
- `backup-sync.sh --commit` — refresh, commit any that changed, then push main.
  A SessionStart hook runs this, so the snapshots stay fresh on their own. It
  pushes only when the checkout is on main, and a rejected push warns rather
  than failing: fix that drift by hand with `git pull --rebase`.
- `backup-sync.sh --restore` — write the repo copies back onto a machine.

The `--commit` path is scoped to the manifest paths, so it never sweeps an
unrelated edit into its commit. It copies each file **whole**, so keep secrets
out of the listed files.

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
- Output styles: `/output-style` is gone (v2.1.91+); the style is picked in
  `/config` and stored as `outputStyle` in settings.json. The menu shows the
  style file's frontmatter `name:`, not its filename — set that, then `/clear`
  so the new session loads it.
