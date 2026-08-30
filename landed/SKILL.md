---
name: landed
description: Render recent commits across the workspace's repos as a local HTML review page. Use when the user asks what landed, what was committed recently, or wants to review recent agent work.
---

# Landed

One local HTML page of what recently landed across the workspace — a tab per
repo, commits grouped by day, diffs collapsed behind each commit. This is the
after-the-fact review surface for the `land` lane — the page the owner reads
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

2. Report the path and the per-run counts. The page regenerates only when this
   skill runs — it is a snapshot, cheap to rebuild, never appended to.

Page anatomy (all in `generate.py`, edit there): agent-built commits are the
ones with a `Co-Authored-By: Claude` trailer; `Closes #n` trailers link to the
repo's GitHub issues; commits over 400 changed lines link out instead of
inlining their diff; the selected tab persists per browser via localStorage.
