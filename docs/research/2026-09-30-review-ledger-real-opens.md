# Review ledger: the three opens of the real thing (#1302)

Closes spec #1262. The end-to-end test (`tests/review_ledger_e2e_test.py`) cannot see
whether a model follows a `SKILL.md`. These are the three things it is blind to,
read from `~/.cache/agent-reviews/ledger.jsonl` after #1302's own heavy build on
2026-09-30; § 2 was added on 2026-10-11 (#1308). Row ids carry no finding text.

## 1. A real `/multi-axis-code-review` run appends its rows: observed

The spec-level review of #1302 (three axes, then a verification pass, each a
`diff-reviewer` subagent following `multi-axis-code-review/SKILL.md` § 4 and § 6)
left one row per run, origin `append`, tokens `known` from the subagent transcript:

- `skills/1302/standards/1/findings-standards-1302`
- `skills/1302/over-engineering/1/findings-standards-1302` (cost `inside standards`)
- `skills/1302/spec/1/findings-spec-1302`
- `skills/1302/correctness/1/findings-correctness-1302`
- `skills/1302/verification/1/findings-verify-1302`

Each reviewer ran `append` unprompted by anything but the skill's prose; none refused.

## 2. A real controller merge writes one `codex-<phase>` row per pass: observed (#1308)

Observed 2026-10-11, the day Chris ended the Codex-pass ablation and the usage gate
exited 0 (`codex usage 0% — ok`). Four heavy merges collected a pass that day, all
in public repos; each left one `codex-gate` row with `exit_status` 0 and wall clock
`known`:

| Row id | Wall clock | `usage_delta` |
| --- | --- | --- |
| `sudoku-kit/749/codex-gate/1/codex-adversarial-749-gate` | 89 s | `unknown`, recorded as different windows: `0 1792345020` / `2 1792345028` |
| `sudokumaker-custom-constraints/795/codex-gate/1/codex-adversarial-795-gate` | 95 s | `known`, 2 → 4, delta 2 |
| `sudokumaker-custom-constraints/792/codex-gate/1/codex-adversarial-792-gate` | 79 s | `known`, 4 → 6, delta 2 |
| `sudokumaker-custom-constraints/794/codex-gate/1/codex-adversarial-794-gate` | 118 s | `known`, 6 → 8, delta 2; one finding row |

Three of four rows are right: the deltas chain (2 → 4 → 6 → 8) with no gap and no
overlap between passes. The first is wrong in the safe direction. Both readings
are the same weekly window: the reset times are 2026-10-18 13:37:00 and 13:37:08,
8 s apart. A 0% reading's `resetsAt` moves with the clock and `_usage_delta`
compares it for equality, so a real +2 points is recorded `unknown`. Never a
zero, so no consumer is misled; the delta is lost. One earlier row from a
private repo has the same shape (before-reading 0%), so the count is 2 of 42
collected passes with both readings. Filed as #1552 against #1269's code, not
fixed here.

Earlier collected passes in this repo (`skills/1304/codex-gate/1/codex-adversarial-1304-gate`
and its siblings, 2026-10-02) already showed `known` deltas. They predate the
cap, so this is the first observation after the ablation, not the first ever.

## 3. A real heavy build's mutation checks write their rows: observed

- Worker: `skills/1302/worker-mutation/1/{split,leftover,weight}`, each `red`, run in
  throwaway worktrees under `.scratch/` per `implement/SKILL.md` § Heavy tier.
- Correctness reviewer, witness recipe of `multi-axis-code-review/SKILL.md` § 4:
  `skills/1302/witness-mutation/1/{w-refusal,w-sidecar,w-decode,w-window,w-fell,w-keeprefusal,w-percent,w-stream,w-restated,w-lock}`
  and `skills/1302/call-site-mutation/1/{cs-outcome,cs-exit4}`, all `red`, none refused.
