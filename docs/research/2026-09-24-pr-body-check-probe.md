# `runfile.py leftover --pr-body` over real PR bodies (2026-09-24, #1147)

The probe ran the PR-body check (`runfile.refuse_disagreeing_pr_body`) over
the 40 most recent merged PRs on `caneff/agent-skills`. Each PR had a
dispositions sidecar on disk at `~/.cache/agent-reviews/skills/dispositions-<lowest closing ticket>.jsonl`.
Each body was fetched with `gh pr view <pr> --json body --jq .body`.

- **38 passed:** PRs 1089 to 1169, except the two below.
- **2 refused.** Both are a body and a sidecar that really disagree, not a
  line the reader misparsed:
  - PR 1127 (#1107): the body records `S1` as `leftover, judgement` (the
    verifier contested the worker's dispute), and the sidecar says `fixed`
    at `cc40c88`.
  - PR 1088 (#1040): the body records `S2 — leftover (judgement)`, and the
    sidecar says `fixed` at `1bf57f5` (adjacent).

The first reader (whole body, one id per line, first outcome word on the
line) refused PRs 1142, 1150, 1153, 1160, 1166 and 1167 as round-1
review found them:

- **grouped ids:** `- S3, S5, S6, P2: leftover` resolved only `S3`.
- **a description ahead of the disposition:** `**S1** (...): ... Claimed
  fixed in 2abe0b9; ... leftover.` read as `fixed`.
- **a Codex id named only as `sidecar codex-gate-1`** at the end of the line.
- **a leftover the body never cites** was refused.

The reader that shipped handles all four, and the probe above is the result
for that reader.
