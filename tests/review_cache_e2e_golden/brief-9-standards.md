# Standards review of #9 in skills

You review this one axis only: standards. Another reviewer holds each other axis.

## Inputs

- Worktree: <TMP>/wt
- Fixed point: origin/main
- Diff capture: <TMP>/d.patch (2 lines) — read it to the end.
- Produced by: `git diff origin/main...HEAD` — the fallback when the capture is missing or empty; say so if you use it.
- Capture stat: captured: 1 file
- Commits: abc1234 a commit

## Standards sources (listed from the worktree)

- none of CODING_STANDARDS.md, CONTRIBUTING.md, AGENTS.md, GLOSSARY.md exists here

## Defect classes

`docs/agents/defect-classes.md` does not exist in this worktree. Check these three shapes:
1. an absent or malformed answer read as a benign one
2. a stated fallback with no mechanism behind it
3. a test that passes for a reason other than the one it claims

## Settled decisions (ruled by Chris or the controller)

Never re-raise one; a diff that contradicts one is a finding.

- a ruling

## Worker's own choices — flag if you disagree (not settled)

The worker made these itself; nobody ruled on them. Flag any you disagree with and judge them like any other code.

- a choice

## Claims to check (the worker's account, not a result)

Verify each against the code and re-run any check yourself; the verdict is yours, and nothing here is settled.

- R1: a claim

## Brief

Report — per file/hunk where relevant — (a) every place the diff violates a documented standard: cite the standard (file + the rule); and (b) any baseline smell you spot: name it and quote the hunk. Distinguish hard violations from judgement calls — documented-standard breaches can be hard, but baseline smells are always judgement calls, and a documented repo standard overrides the baseline. Check the defect classes listed under "Defect classes" above. Skip anything tooling enforces, and skip the hollow-witness check — the correctness axis owns it (#938), and two opus agents mutating the same tests over the same diff cost two dispositions for one finding. Then end with a required **### Over-engineering** subsection (a `###` so it nests under the Standards heading): run the over-engineering lens over the diff and list what to cut, one line each in `OE<n>: location: <tag> <what>. <replacement>.` form using the five tags, `<n>` a per-report ordinal starting at 1 for this subsection's own series. This subsection owns Speculative Generality / Middle Man / Refused Bequest — report those cuts here, not above. Write `Lean already.` if there is nothing to cut — the subsection is required even when empty. Also give each cut a line in the same findings sidecar as your other findings, with that `OE<n>` id and `axis: "standards"`. Findings and their evidence only, no preamble.

## Output

- Full report: `~/.cache/agent-reviews/skills/review-standards-9.md`
- Findings sidecar: `~/.cache/agent-reviews/skills/findings-standards-9.jsonl`, one line per finding: `{"id": "S<n>" or "OE<n>", "axis": "standards", "severity": "hard" or "judgement", "file": "<path>", "title": "<short title>"}`. Empty file when you found nothing.
- Then the empty completion marker `~/.cache/agent-reviews/skills/findings-standards-9.done`, last, once the sidecar is complete.
- Then `python3 ~/.agents/skills/multi-axis-code-review/review_ledger.py append --repo skills --ticket 9 --type standards`.

## Limits

- You do your own reading and running and spawn no nested subagent: a nested agent reports to the top-level session, not to you, and its work is lost. A task too large for one agent is reported as such and stopped.
- Any solve, build or test run uses at most 1 worker and finishes inside 600 seconds of wall clock.
