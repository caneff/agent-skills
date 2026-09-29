# Review data inventory: what each review type already records (2026-09-29)

Input to Chris's ask of 2026-09-29: gather data for every review type so we
can tell which ones earn their keep. This note records what exists on disk
today. It proposes no design.

## Value side: what a review found, and what became of it

All under `~/.cache/agent-reviews/<repo>/`, 17 repo directories. File counts
were taken 2026-09-29 with `find -maxdepth 2`. This repo's directory is
`skills/`, not `agent-skills/`: `agent-skills/` stops at 2026-09-22.

| Record | Count | Per | Carries |
|---|---|---|---|
| `review-<axis>-<n>.md` | 1465 | axis run | free-text report |
| `findings-<axis>-<n>.jsonl` | 1141 | axis run | `id`, `axis`, `severity`, `file`, `title` |
| `dispositions-<n>.jsonl` | 378 | PR | `id`, `outcome` (fixed / leftover / filed / disputed), `severity`, `file`, `title`, `text`. Kept since 2026-09-16 |
| `verification-<n>.md` | 11 | PR | free-text verdict on round-1 fixes (#1188 made it mandatory) |
| `codex-adversarial-<n>-<phase>.json` + `.out` | 611 | Codex pass | `phase` (gate / second / third), `status`, start and end times, shas; findings are in `.out` as free text |

A finding id's prefix names its concern: S standards, P spec, C
correctness, OE over-engineering.

## Cost side

- **Claude reviewers:** not recorded in the review cache. A subagent's
  transcript does carry it:
  `~/.claude/projects/<project>/<session>/subagents/agent-<id>.jsonl` has a
  `usage` block on every message and a timestamp on every line, and there is
  a `.meta.json` beside each. There were 228 subagent transcripts under this
  repo's primary project directory on 2026-09-29. Worker sessions live under
  their worktree's own project directory.
- **Codex:** wall clock only, from the record file above. The
  `2026-09-20-codex-pass-durations.md` log has one row per pass.

## Not recorded anywhere

- Mutation outcomes: whether the worker's own check or a reviewer's witness
  mutation went red, and what it cost. The worker gets one `Mutation check:`
  line in "PR up"; the reviewers write free text.
- Overlap: whether two reviewers raised the same finding.
- Escapes: a defect a review missed that a later ticket fixed.

## Prior analyses

- `2026-09-16-review-axis-tally.md` (#854): one-off, three axes, value side
  only.
- `2026-09-20-codex-pass-durations.md` (#942): Codex wall clock.
- sudokupad-art `docs/research/2026-09-28-leftover-causes.md`: what share of
  leftovers a PR created itself.
