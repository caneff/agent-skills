# ccstatusline-table

Bordered ASCII-table statusline for Claude Code. Replaces the `ccstatusline`
segment bar with a colored box-drawing grid.

## Wiring

`~/.claude/settings.json`:

```json
"statusLine": {
  "type": "command",
  "command": "python3 $HOME/.agents/skills/flow/ccstatusline-table/table-statusline.py",
  "padding": 0,
  "refreshInterval": 10
}
```

## Layout

```
╭───────────┬──────────┬───────────┬────────────────┬──────────────╮
│ O 4.8 (M) │ gridfind │ Ctx 60.0k │ 94% 2d · 6% 3h │ ⎇ main +0,-0 │
╰───────────┴──────────┴───────────┴────────────────┴──────────────╯
```

Frame color signals context fill: green <140k, yellow ≥140k, red ≥180k,
purple when no transcript yet.

The path cell shows the **project name** only — `Path(root).name`, matching the
blind-test toast's `Path(cwd).name` convention. `root` is the main worktree
(`git-common-dir`'s parent), so a linked worktree collapses to the project name
too, never the worktree's.

## Dependencies

Reads the session JSON on stdin, then fans it out to helper scripts vendored
in `helpers/` (versioned here):

- `helpers/effort-abbrev.py` — thinking-effort abbreviation
- `helpers/usage-segment.sh` — weekly/session %, resets. The usage cell calls
  its `all` mode once per tick and splits the tab-separated line; the
  single-field modes (`weekly`/`session`/`wreset`/`breset`) still work
  standalone for compatibility.
- `helpers/codex-usage.py` — Codex's own rate limit, read from the newest
  `~/.codex/sessions/**/rollout-*.jsonl`, which is where the Codex CLI records
  what OpenAI last told it. Renders as a labelled `Cdx 12% 6d` cell so the
  unlabelled percentages beside it stay Claude's. Blank until Codex has run,
  blank once the window it describes has reset, and marked `12%?` when the
  snapshot is over a day old — Codex refreshes it only when Codex runs.

Git branch/changes and context tokens are computed in-script.

## Test

```
python3 table-statusline.py --selftest
helpers/usage-segment.sh --selftest
python3 helpers/codex-usage.py --selftest
```

`statusline.test.sh` runs all three, so the repo's `tests/all.sh` picks them up.
