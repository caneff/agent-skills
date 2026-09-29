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

## Vocabulary on disk (tallied 2026-09-29 across all repos)

- **Findings `severity`:** only two values, `hard` (265) and `judgement`
  (3522). Codex findings use high / medium / low in their `.out` text, and
  a few of those reach dispositions as `leftover` rows.
- **Dispositions `severity`:** absent on almost every `fixed` (2392 of
  2393), `disputed` (808) and `filed` row. It has to be joined back to the
  findings sidecar by id.
- **Dispositions `outcome`:** the four canonical values dominate (fixed
  2393, disputed 808, leftover 474, filed 155). There is also drift:
  `not-fixed` / `not_fixed`, `partial` / `fixed-partial`,
  `fixed-with-regression`, `regression`, `contested`, `open`, `new`, and
  free-text severities such as `judgement, PLAUSIBLE`.
- The verification axis is written as both `verification` and `verify`.

## Rulings (Chris, 2026-09-29)

1. **Scope:** every review type. That is the three axes, the
   over-engineering section, the reviewers' constraint and call-site
   mutations, the verification pass, each Codex phase (gate, second, third)
   and the worker's own mutation check.
2. **Value:** fixed findings weighted by severity, plus cost accounting for
   each review type.
3. **Data:** both a backfill harvest over the existing cache and
   transcripts, and a ledger row written by every review from now on.
4. **Severity weights:** the ledger records severity as written, and the
   analysis applies the weights: `hard` 3, `judgement` 1; Codex high 3,
   medium 2, low 1.
5. **Cost:** Claude reviewers are costed in tokens by kind (input, output,
   cache write, cache read) plus wall clock, and turned into dollars at
   analysis time from a price table. Codex is costed in wall clock plus the
   change in its weekly usage percentage.
6. **Outcomes:** `fixed` and `filed` count as value. `leftover` gets its
   own column with no value. `disputed` gets zero value and its own column
   as the reviewer's noise rate.
7. **Overlap:** counts. A unique finding (no other reviewer raised it on
   that PR) is worth more than a shared one. Controller's default, not
   Chris's, flag if you disagree: a finding raised by k reviewers gives
   each 1/k of its weighted value, and the split is an analysis parameter.
   Escapes (defects a review missed that a later ticket fixed) are a
   follow-up, not part of this work.
