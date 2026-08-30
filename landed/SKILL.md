---
name: landed
description: Render the repo's most recent commits as a well-formatted HTML review page (an artifact). Use when the user asks what landed, what was committed recently, or wants to review recent agent work on a repo.
---

# Landed

Turn the recent history of the current repo into one HTML page the owner can
skim: what landed, when, by whom, and what each commit touched. This is the
after-the-fact review surface for the `land` lane — the page the owner reads
instead of a PR queue.

## Steps

1. **Pick the range.** An argument wins: a count (`20`), a duration (`3d`,
   `2w`), or a rev range (`abc123..main`). Default: `--since='7 days ago'` on
   the default branch, capped at 50 commits. Zero commits → say so and stop;
   render no empty page.

2. **Gather.** From the repo root, collect per commit: hash, author date,
   author, subject, body, `--stat` summary, and the issues it closes
   (`Closes #n` trailers). For commits touching ≤ 400 changed lines, also grab
   the diff. Mark a commit **agent-built** when its body carries a
   `Co-Authored-By: Claude` trailer. Read `origin`'s URL so hashes and issue
   numbers can link to GitHub when the origin is a github.com repo.

3. **Design.** Load the `artifact-design` skill, then build the page:
   - Commits grouped by day, newest first; each entry shows subject, short
     hash (linked when possible), author + agent-built badge, relative stat
     bar, and the closed-issue links.
   - Body and per-file diff live in a collapsed `<details>` per commit — the
     page skims as a list, expands to a review.
   - Diffs render as add/remove-colored lines inside `overflow-x: auto`
     blocks. A commit whose diff was skipped for size says so and links to
     the commit on GitHub instead.
   - Title the page `Landed — <repo name>`.

4. **Publish — one page per repo, stable URL.** Check `Artifact` with
   `action: "list"` for an existing `Landed — <repo name>` artifact; if found,
   pass its `url` to update it in place. Otherwise publish fresh (favicon
   `🛬`). Report the URL and a one-line count: how many commits, how many
   agent-built.
