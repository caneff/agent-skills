# Global CLAUDE.md: always-on load and pointer-doc reads (2026-10-04)

Question: is the always-on agent text bloated, and do sessions actually read
the progressive-disclosure docs under `flow/claude/`?

## Always-on load (words, `wc -w`)

| File | Words |
|---|---|
| `flow/claude/CLAUDE.md` (symlinked as `~/.claude/CLAUDE.md`) | 1915 |
| `second-brain-v2/Memory/RULES.md` (imported) | 407 |
| `second-brain-v2/Memory/SOUL.md` (imported) | 68 |
| this repo's `AGENTS.md` | 440 |
| **Total every session in this repo** | **2830** |

CLAUDE.md by section: Hard rules 660, Communication 474, Done means verified
226, Workflow 181, Agents and jobs 157, Precedence 108, Gotchas 73.

## Pointer-doc reads

Space covered: the 584 top-level transcripts under `~/.claude/projects`
modified in the last 14 days (subagent transcripts excluded). A session
"triggered" a doc if a Bash `command` matched the regex; it "read" the doc
if a `file_path` or `command` field names `flow/claude/<doc>.md`.

| Doc | Trigger regex | Triggered | Read |
|---|---|---|---|
| OPERATIONS | `gh pr merge\|implement-dispatch\|merge-cleanup` | 226 | 23 (10%) |
| WORKFLOW | `gh issue create\|gh issue edit` | 175 | 12 (7%) |
| VISUAL-INSPECTION | `shot-scraper\|zed ` | 36 | 6 (17%) |
| SHELL-SAFETY | `pkill\|kill -\|kill [0-9]` | 36 | 0 |

Caveats: the regexes are coarse. A worker running `gh issue edit` under a
skill may not need WORKFLOW at all, and a session may have read a doc through
a path form the match misses. A first pass that grepped the bare path
reported 100% reads; that was the injected CLAUDE.md text matching itself,
not a read.

## Reading

- The pointers are trailing `Detail — <topic list>: <path>` lines at the end
  of a section. They name topics, not the action that should fire them.
- Each section already inlines a summary of its doc, so the agent judges it
  has enough. SHELL-SAFETY (0/36) sits right after the inline kill rule it
  elaborates.
- RULES.md is an inbox meant to be promoted and emptied; its 407 words are
  still all present.
- Unexplained: 90% of merging sessions never read OPERATIONS. Either the
  skills those sessions run already carry what they need (doc is partly dead
  weight) or they act without it. Not checked.

## Follow-up: sessions where a skill already covered the action

Same 14-day space. A session counts as "covered" if its transcript contains
`Base directory for this skill: .../<skill>` for a skill that carries the
procedure.

| Doc | Triggered | Not covered by a skill | Of those, read the doc |
|---|---|---|---|
| OPERATIONS (covering: `burndown`, `implement`) | 227 | 14 | 9 |
| WORKFLOW (covering: `burndown`, `implement`, `file-ticket`, `to-tickets`, `to-spec`, `wayfinder`, `grilling`) | 175 | 4 | 0 |
| VISUAL-INSPECTION (covering: `computer-use`, `visual-teach`, `prototype`) | 36 | 35 | 6 |
| SHELL-SAFETY (covering: `diagnosing-bugs`) | 36 | 36 | 0 |

Revised reading: the low raw rates for OPERATIONS and WORKFLOW are mostly
sessions where a skill already carried the procedure. When no skill was
loaded, OPERATIONS was read 9 of 14 times. VISUAL-INSPECTION and
SHELL-SAFETY have no covering skill, and the pointer misses most or all of
the time.

Already hook-enforced (in `flow/claude/settings.json`): Agent `model`
(`require-agent-model.sh`), push and `gh pr merge` ownership plus history
destroyers (`block-dangerous-git.sh`), background-job wrapping
(`wrap-background-jobs.sh`). Commit identity is enforced by the lane's git
hooks. The CLAUDE.md prose for these restates a deterministic guard.

## The count as a script (#1413)

`flow/claude/pointer_reads.py count --end <iso>` replays both tables above.
A transcript is in the window when its mtime or any top-level `timestamp`
falls in the 14 days before `--end`, and only its lines up to `--end` are
searched, so a session that kept running after the count does not shift it.
The mtime half matters: two transcripts had untimestamped lines appended in
the window, which `find -mtime -14` counted and timestamps alone would not.

Checked 2026-10-04 against the original runs, which started at 17:52:01Z
(first table) and 17:54:33Z (follow-up table): `--end 2026-10-04T17:52:01Z`
gives 584 sessions, 226/23, 175/12, 36/6 and 36/0; `--end
2026-10-04T17:54:33Z` gives 227/14/9, 175/4/0, 36/35/6 and 36/36/0. Both
match the tables above exactly. Transcripts older than Claude Code's cleanup
period are deleted, so this replay only holds while the 2026-09-20 files
still exist.

`pointer_reads.py recount` runs daily from a user crontab line tagged
`# pointer-reads-recount-1413`. Fourteen days after #1413 closes it appends
a dated re-count of the 14 days after closing to this note, pushes it, and
removes its own line.
