# Spec review of #9 in skills

You review this one axis only: spec. Another reviewer holds each other axis.

## Inputs

- Worktree: <TMP>/wt
- Fixed point: origin/main
- Diff capture: <TMP>/d.patch (2 lines) — read it to the end.
- Produced by: `git diff origin/main...HEAD` — the fallback when the capture is missing or empty; say so if you use it.
- Capture stat: captured: 1 file
- Commits: abc1234 a commit
- Spec: #9

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

Report: (a) requirements the spec asked for that are missing or partial; (b) behaviour in the diff that wasn't asked for (scope creep); (c) requirements that look implemented but where the implementation looks wrong. When the diff knowingly deviates from an acceptance criterion's literal wording, rule on whether it preserves the spec's intent, not the letter — look for a competing, higher AC the deviation exists to satisfy — but flag the deviation, never pass it silently. Quote the spec line for each finding. Check the defect classes listed under "Defect classes" above. Findings and their evidence only, no preamble.

## Output

- Full report: `~/.cache/agent-reviews/skills/review-spec-9.md`
- Findings sidecar: `~/.cache/agent-reviews/skills/findings-spec-9.jsonl`, one line per finding: `{"id": "P<n>", "axis": "spec", "severity": "hard" or "judgement", "file": "<path>", "title": "<short title>"}`. Empty file when you found nothing.
- Then the empty completion marker `~/.cache/agent-reviews/skills/findings-spec-9.done`, last, once the sidecar is complete.
- Then `python3 ~/.agents/skills/multi-axis-code-review/review_ledger.py append --repo skills --ticket 9 --type spec`.

## Limits

- You do your own reading and running and spawn no nested subagent: a nested agent reports to the top-level session, not to you, and its work is lost. A task too large for one agent is reported as such and stopped.
- Any solve, build or test run uses at most 1 worker and finishes inside 600 seconds of wall clock.
