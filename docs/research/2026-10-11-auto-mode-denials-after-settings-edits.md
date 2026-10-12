# Auto-mode denials after the October settings edits, re-counted 2026-10-11

Ticket #1538. Question: with the settings as they are now, which denial
categories remain, and at what rate? The ticket says the
[10-06 count](2026-10-06-auto-mode-denial-rates.md) was taken before five
edits. Three of them (the reversibility line, the Irreversible Local
Destruction rule and the LMD archive entry) are 10-04 commits that precede
that note, so only the read-only git allow, the wider self-modification entry
and the later 10-09 and 10-11 entries are new to it. This pass splits the
whole period at every edit rather than at the note.

## Method and coverage

The script is [`count_automode_denials.py`](count_automode_denials.py), saved
beside this note, with tests in `count_automode_denials_test.py`:

```
python3 docs/research/count_automode_denials.py          # tables below
python3 docs/research/count_automode_denials.py --json   # same, machine form
python3 docs/research/count_automode_denials.py --edit 2026-10-12T09:00:00-04:00="label"
```

It reads every `~/.claude/projects/**/*.jsonl`, subagents included, and
counts `tool_use` blocks (deduplicated by id) against three error kinds: a
classifier denial (`auto mode classifier` with a bracketed `Reason:`), a hook
block (`PreToolUse:`, named by hook script) and a user reject (`The user
doesn't want to proceed`). Each event goes into the window between two
settings edits. The edits are the author times of the commits that changed
`flow/claude/settings.json` since the 10-04 trim, listed in `EDITS`. The
`--settings` file supplies the current `soft_deny` names, so each reason is
marked `soft_deny` or `built-in`. Its `Denied calls` section lists every classifier denial after
W0 with its command, which is what the tables below were read from.

Read 2026-10-11 evening, at `main` 1909b3eb. 4,517 files, 133,573 tool calls,
374 denial-class events. Coverage limits:

- Transcripts on disk run from 2026-09-06 20:27 to 2026-10-11 21:37, local.
  There are none for 09-07..09-11 and 09-25: a gap on disk, not zero denials.
  The 10-06 note's 09-01..14 figures cannot be reproduced from what is left.
- An edit's time is its commit time. A live edit to the symlinked file can
  precede its commit, so a denial within minutes of a boundary is ambiguous.
- Which settings a session actually loaded is not in the transcripts. A
  session started before an edit may still run the old text.
- Denials the user saw and denials a worker absorbed alone are not separated.
- The command text kept per denial is the first 300 characters. Reasons for
  the post-edit denials were judged by hand from that text, so a long command
  may be misread.
- W1 is not one edit: five more settings commits later on 10-04 (hooks, a
  `resolve-controller` allow, `uv run:*`, an ask list) fall inside it, and so
  does the DISPLAY env edit of 10-09. Its rate is a mixed state's.
- One hook error is from a `/tmp` probe hook (`probe: denied by a parallel
  hook`, 10-05) and is reported apart from the 11 configured-hook blocks.

## Correction to the 10-06 note

The 10-06 pass counted every `auto mode classifier` error as a denial. Some of
them are not: `The server-side auto mode classifier gave no verdict (timed
out|error)` is a classifier outage with no judgement of the action. This pass
counts those as `No verdict`, apart from denials: 11 of them, all on 09-28. The
10-06 note's "about half carry no bracketed reason" was mostly this.

Cross-check against the old note on days both cover: hook blocks 09-22..30
match exactly (91), and 10-01..06 match in classifier (42) and hook (39) counts
and reject (1). The 09-22..30 classifier count is 30 here against 43 there,
which is the 11 outages plus 2 events I cannot place.

## Windows

| W | Settings state from | Calls | Classifier | /1k | No verdict | Hook | Reject |
|---|---|---|---|---|---|---|---|
| W0 | baseline, to 10-04 15:14 | 112,897 | 119 | 1.1 | 11 | 175 | 27 |
| W1 | 10-04 batch: reversibility line, ILD, LMD, soft_deny trim (mixed, see above) | 3,387 | 7 | 2.1 | 0 | 5 | 0 |
| W2 | 10-06 11:01 read-only git allow | 8,483 | 5 | 0.6 | 0 | 2 | 1 |
| W3 | 10-09 10:58 twitch rig entry | 1,433 | 4 | 2.8 | 0 | 0 | 2 |
| W4 | 10-09 13:04 git commit allow, wider self-modification | 3,766 | 5 | 1.3 | 0 | 0 | 2 |
| W5 | 10-11 13:08 ledger rewrite, run-output reads | 3,669 | 4 | 1.1 | 0 | 4 | 0 |
| W2..W5 | since the read-only git allow | 17,351 | 18 | 1.0 | 0 | 6 | 5 |

## Findings

- **The classifier rate did not move.** 119 of 112,897 calls before the 10-04
  batch (1.05/1k); 18 of 17,351 since the read-only git allow (1.04/1k). The
  per-window rates are 4–7 events each and swing 0.6 to 2.8 on noise, so only
  the aggregate is a comparison. The settings edits did not lower the
  classifier's rate per call, and they did not raise it either.
- **Hook blocks fell.** 175 in W0 (1.55/1k) against 11 since 10-04 15:14
  (0.53/1k). `block-dangerous-git.sh` is 171 of the 175 and all 11. No
  settings edit in `EDITS` changes that hook, so this pass does not say why it
  fell.
- **User rejects stay near zero**: 27 in W0, 5 since 10-06.

## Which categories remain

All 18 classifier denials since the 10-06 11:01 edit, each command read by
hand (judgement, from the first 300 characters of each command):

| Reason | Source | n | What was denied |
|---|---|---|---|
| Irreversible Local Destruction | soft_deny | 8 | `git rm` of tracked files; a `cp` backup plus inline rewrite of `~/.cache/agent-reviews/ledger.jsonl`; an `ls`/`grep` of the ledger; a python pass over an all-audits collection; a second ledger `cp` backup; `job-run --status` plus `cat` of run output; `rm ~/.config/agent-skills/codex-reviews-off`; a `mv -n` merge of two cache directories |
| Self-Modification | built-in | 5 | all on 10-09 12:49–13:05 EDT, before the 13:08 blanket: an `update-config` Skill call, a `git commit` of CLAUDE.md, `ls`/`json.load` of settings, an inline edit of settings.json, and `git status` / `git log -1` |
| Production Deploy | soft_deny | 2 | a `cmd.exe` call to `stream-rig.exe res 1920x1080`; `job-run --status` plus `tail` of an e2e log |
| Irreversible Deletion (general) | soft_deny | 1 | `tasklist.exe \| grep \| awk` |
| Public Data-Sharing Upload | soft_deny | 1 | `gh repo create` of a sudoku-kit repo |
| Code from External | soft_deny | 1 | `git add` + `git commit` of a uv git-source dependency pin |

- **6 of 18 are read-only commands**: the ledger `ls`/`grep` (ILD), the
  settings `ls`/`json.load` (Self-Modification), `git status` / `git log -1`
  (Self-Modification), two `job-run --status` reads (Production Deploy, ILD)
  and the `tasklist` pipe (Irreversible Deletion).
- **The 10-06 read-only git allow names Self-Modification and still lost
  once.** `git status --porcelain; git log -1 --format=...` was denied as
  Self-Modification on 10-09 13:05 EDT, after that entry existed. It is the
  contextual shape the 10-06 note named: a read-only follow-up denied inside a
  session that is editing settings.
- **Self-Modification is 0 after the 10-09 blanket** (commit 13:08): all five
  precede it, and the blanket's own 13:08 timestamp is a commit time, so the
  last of them is within three minutes of the boundary.
- **Since the latest edit, 423ecc8 (10-11 13:08 EDT, 3,669 calls so far),
  there are 4 denials and none is read-only**: `rm` of the Codex kill-switch
  file, a `mv -n` of cache directories, `gh repo create`, and the uv
  dependency pin. Each is an action its rule exists to stop.
- **Irreversible Local Destruction is the largest remaining category**, 8 of
  18, and its coverage by later entries is mostly not established. The
  one clear case is the 10-11 `job-run --status` plus `cat` of run output,
  which 423ecc8's entry names. The 10-08 ledger rewrite uses its own
  `fcntl`/`os.replace` code, not `review_ledger.update_ledger`, which the
  current entry requires, so that entry does not cover it. The 10-08 ledger
  `ls`/`grep` reads a directory no entry names. The 10-11 backup-and-rewrite
  (16:59Z) is cut off by the 300 characters kept, so whether it goes through
  `update_ledger` is unknown. The all-audits python pass rewrites source
  text; it is not a removal or move. So the covered count is 1 clear, 1
  unknown, and the other six are not covered by any later entry.

## What the next settings change should use

- 4 events per window cannot separate a rate change from the 0.6–2.8/1k
  swing. Do not widen a rule on one window.
- The remaining non-intended class is a read-only command denied under a rule
  unrelated to the read (6 of 18), and an allow entry that names the rule did
  not stop it once. A category-by-category edit does not address that shape;
  `#1534` (prototype automode-entry) does.
- Re-run the script after roughly 20,000 more calls, adding each new edit with
  `--edit`, before the next change.
