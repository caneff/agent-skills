# Review ledger: the three opens of the real thing (#1302)

Closes spec #1262. The end-to-end test (`tests/review_ledger_e2e_test.py`) cannot see
whether a model follows a `SKILL.md`. These are the three things it is blind to,
read from `~/.cache/agent-reviews/ledger.jsonl` after #1302's own heavy build on
2026-09-30. Row ids carry no finding text.

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

## 2. A real controller merge writes one `codex-<phase>` row per pass: not yet observed

A collected pass with live `usage_before` / `usage_after` cannot be observed before
the Codex usage cap resets, 2026-10-03 17:53. Nothing here stands in for it. The
skip path was observed on #1301: `skills/1271/codex-gate/1/codex-skipped-1271-gate`.
Open item for the controller.

## 3. A real heavy build's mutation checks write their rows: observed

- Worker: `skills/1302/worker-mutation/1/{split,leftover,weight}`, each `red`, run in
  throwaway worktrees under `.scratch/` per `implement/SKILL.md` § Heavy tier.
- Correctness reviewer, witness recipe of `multi-axis-code-review/SKILL.md` § 4:
  `skills/1302/witness-mutation/1/{w-refusal,w-sidecar,w-decode,w-window,w-fell,w-keeprefusal,w-percent,w-stream,w-restated,w-lock}`
  and `skills/1302/call-site-mutation/1/{cs-outcome,cs-exit4}`, all `red`, none refused.
