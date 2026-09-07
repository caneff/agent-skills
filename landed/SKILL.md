---
name: landed
description: Render recent commits across the workspace's repos as a local HTML review page, and open it in the browser. Use when the user asks what landed, what was committed recently, wants to review recent agent work, or asks to open the landed page.
---

# Landed

One local HTML page of what recently landed across the workspace — a tab per
repo, commits grouped by day, diffs collapsed behind each commit. This is the
after-the-fact review surface for merged work — the page the owner reads
instead of a PR queue.

## Steps

1. Run the generator. The argument is a count (`20`), a duration (`3d`, `2w`),
   or a rev range (`abc123..main`); default `7d`:

   ```
   python3 ~/.agents/skills/landed/generate.py [range]
   ```

   It scans every git repo under `~/src` plus `~/.agents/skills`, renders a
   tab for each repo with commits in range, and writes
   `~/.claude/landed.html`. It prints the path, tab count, and size — or says
   so and writes nothing when the range is empty everywhere.

2. Open it: `wslview ~/.claude/landed.html`. Report the per-run counts.

The page is a snapshot, cheap to rebuild, never appended to. Every `git push`
also regenerates it in the background via the push-sync hook, so
regenerating here just guarantees freshness before opening.

Page anatomy lives in `generate.py` itself — read it there, don't restate it
here.

`generate.py` also takes `--roots <comma-separated paths>` and `--out <path>`
to override which repos it scans and where it writes, for testing against a
throwaway git repo instead of the real workspace. Not needed for normal use.
