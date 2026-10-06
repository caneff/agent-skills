# Auto-mode denial rates, 2026-09-02 to 2026-10-06

Question (Chris, 2026-10-06): auto-mode issues feel ten times worse than a few
weeks ago — what changed?

## Method and coverage

A Python pass over every `~/.claude/projects/**/*.jsonl` transcript, subagents
included. It counted `tool_use` blocks, plus `tool_result` blocks with
`is_error` set whose text contains:

- `auto mode classifier` (classifier denial)
- `PreToolUse:` (a hook blocked the call)
- `The user doesn't want to proceed` (Chris rejected a prompt)

Weeks are calendar buckets: days 1–7, 8–14, 15–21 and 22–end.

Not covered:

- Anything before 2026-09-02, the oldest transcript on disk. "A few weeks ago"
  before that date cannot be measured here.
- Denials that never reached a transcript.
- Which denials Chris saw, as against ones a worker absorbed alone.

The 2026-10 week is partial: six days, of which 10-05 and 10-06 are nearly
empty.

## Weekly counts

| Week | Tool calls | Classifier denials | /1k | Hook blocks | /1k | User rejects |
|---|---|---|---|---|---|---|
| 09-01..07 | 11,638 | 19 | 1.6 | 24 | 2.1 | 21 |
| 09-08..14 | 20,847 | 28 | 1.3 | 19 | 0.9 | 21 |
| 09-15..21 | 31,220 | 35 | 1.1 | 35 | 1.1 | 10 |
| 09-22..30 | 47,988 | 43 | 0.9 | 91 | 1.9 | 4 |
| 10-01..06 | 24,521 | 42 | 1.7 | 39 | 1.6 | 1 |

Daily classifier peaks: 10-03 had 29 denials over 9,091 calls (3.2/1k), and
10-04 had 33 over 9,204 calls (3.6/1k). Earlier peaks were 09-07 (18) and
09-22 (18), each about 2/1k.

## Findings

- Classifier denials per week rose about 2.2x, from 19 to 42. The per-call
  rate stayed flat at about 1–1.7/1k. Volume drives the absolute rise: weekly
  tool calls grew about 4x as more workers ran in parallel.
- Hook blocks per week rose about 3.8x, from 24 to 91, in the 09-22 week. They
  outnumbered classifier denials that week.
- The per-call classifier rate doubled only on 10-03 and 10-04. Those are the
  days of the autoMode settings edits: `995e036` added the reversibility
  carve-outs, and `14d6328` trimmed `soft_deny` to ten rules. They are also
  the days of the self-modification denials in
  `2026-10-04-auto-mode-self-modification-denials.md`.
- The denial reasons shifted. Late September added Irreversible Local
  Destruction (10) and Git Destructive (6). October 1–6 added Auto-Mode
  Bypass (9) and Instruction Poisoning (5), neither seen in early September.
  Self-Modification stays the largest named reason (14, then 13). About half
  of the denials carry no bracketed reason that the regex could read.
- Prompts Chris rejected fell from 21 a week to 1, so more of the friction
  now arrives as denials and blocks than as prompts.

No tenfold rise in any measured series. The largest is hook blocks at about
3.8x absolute.

## Breakdown (second pass, same transcripts)

Hook blocks come almost entirely from `block-dangerous-git.sh`: 75 before
09-22 and 127 from 09-22 on. `require-agent-model.sh` accounts for 5 in all.
Of the pattern names the block messages carry, the matches were
`git branch -D` 44, `gh pr merge` 22 and `git reset --hard` / `reset --hard`
14. The other messages carry no pattern name.

The 10-03 and 10-04 classifier denials, 39 with a readable tool input:

- 34 Bash, 4 Edit, 1 Skill.
- Several are read-only commands: `resolve-controller` (3), `gh issue view`,
  `claude auto-mode config | grep`, `grep` of RULES.md, `readlink`/`grep` of
  settings, `git merge-base`/`git show`, `sed -n` of settings.json, and
  `git status`/`git diff --quiet`.
- They cluster in sessions that were editing `autoMode` or
  `flow/claude/settings.json`, or probing a hook (implement-1366's
  `probe-mod`). There, Self-Modification, Auto-Mode Bypass and Instruction
  Poisoning fire on follow-up reads as well as on the edits.
- The same shape recurred on 2026-10-06. A read-only
  `git ls-files | wc -l; git status --porcelain | wc -l` was denied as
  Irreversible Local Destruction right after the git hook blocked a
  `git reset --hard`.

Reading: the spike is contextual. Once a transcript holds a settings edit or
a blocked destructive command, the classifier judges benign follow-up reads
as pursuit of that outcome. The rule text alone does not account for it.
Response (2026-10-06): an `autoMode.allow` entry for read-only git
inspection, covering that shape explicitly.
