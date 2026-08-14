# ccstatusline-table

Bordered ASCII-table statusline for Claude Code. Replaces the `ccstatusline`
segment bar with a colored box-drawing grid.

## Wiring

`~/.claude/settings.json`:

```json
"statusLine": {
  "type": "command",
  "command": "python3 /home/caneff/.agents/skills/ccstatusline-table/table-statusline.py",
  "padding": 0,
  "refreshInterval": 10
}
```

## Layout

```
╭────────────────┬───────────┬──────────────┬─────────────────────────╮
│ O 4.8 (M)      │ Ctx 60.0k │ ⎇ main +0,-0 │ 🏰 idle                 │
├────────────────┼───────────┼──────────────┼─────────────────────────┤
│ ~/src/gridfind │ 94% 2d·6% 3h │ f38b22aa  │ ✅0 🔥1 🗺️1 🚧0 📋2 💤5 │
╰────────────────┴───────────┴──────────────┴─────────────────────────╯
```

Frame color signals context fill: green <140k, yellow ≥140k, red ≥180k,
purple when no transcript yet.

The path cell shows the **project name** only — `Path(root).name`, matching the
blind-test toast's `Path(cwd).name` convention. `root` is the main worktree
(`git-common-dir`'s parent), so a linked worktree collapses to the project name
too, never the worktree's.

## Dependencies

Reads the session JSON on stdin, then fans it out to helper scripts. Three
are vendored in `helpers/` (versioned here):

- `helpers/effort-abbrev.py` — thinking-effort abbreviation
- `helpers/usage-segment.sh` — weekly/session %, resets
- `helpers/issue-counts-segment.sh` — repo issue counts

The fourth is the sibling `sandcastle-watch` skill (already in this repo),
resolved at its installed path:

- `~/.claude/skills/sandcastle-watch/sandcastle-segment.sh` — sandcastle status

Git branch/changes and context tokens are computed in-script.

## Test

```
python3 table-statusline.py --selftest
```
