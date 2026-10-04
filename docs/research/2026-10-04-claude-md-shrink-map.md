# Global CLAUDE.md shrink: where each removed line went (#1413, 2026-10-04)

`flow/claude/CLAUDE.md` went from 1,983 words to 573 (1,048 with its two
`@`-imports, against the 1,100 budget `tests/check-always-on.py` enforces).
Each line removed or cut down is listed below with where its meaning now
lives. "Hook" means the teaching hook shows that section on the precursor
command (#1412); "rule" means a `paths:` file under `flow/claude/rules/`,
linked into `~/.claude/rules/` (`2026-10-04-user-path-rules-probe.md`).

## Hard rules

| Removed or cut | Now lives in |
|---|---|
| Merge ownership: the full ready-for-human explanation | one line kept; why: `WORKFLOW.md` § Gate 2; procedure: `implement/SKILL.md` § The merge; foreign merges blocked by `block-dangerous-git.sh` |
| STOP and ask: tracked file removal is undoable | `WORKFLOW.md` § Undoable or not |
| STOP and ask: regenerated files, `merge-cleanup --discard` | `WORKFLOW.md` § Undoable or not |
| STOP and ask: rebase-conflict resolution and `--force-with-lease` to a worker branch are not rewrites; force to `main` still asks | `WORKFLOW.md` § Undoable or not; the worst destroyers are blocked by `block-dangerous-git.sh` (named in the line) |
| Gate 1 detail | one line kept; detail and the push guard: `WORKFLOW.md` § Gate 1 |
| One workspace per task, resumed across sessions; a terminal on `main` means dispatch; auto-ship commits on `main` | primary-checkout ban kept in the Gate 2 line; the rest: `WORKFLOW.md` § Gate 2 |
| Gate 2: the not-code list, lane mechanics | `WORKFLOW.md` § Gate 2 |
| Gate 2: the one `SKILL.md` auto-ship exception | rule `skill-files.md` (loads on any `SKILL.md`) |
| Denial: name the root-cause fix, never a one-off allow | `WORKFLOW.md` § Auto mode and harness work; the pointer line names "report a denial" |
| Commit identity: the email is identification, GitHub's email-privacy block, the guard's two scripts and override | one line kept naming the commit-identity guard; detail: `OPERATIONS.md` § Dispatch |
| Progressive disclosure paragraph | rule `instruction-files.md` (loads on `CLAUDE.md`, `AGENTS.md`, `RULES.md`, `CODING_STANDARDS.md`) |
| "Always" about an output's shape → change the skill | one line kept in § Work (a path rule would not fire, since hearing "always" opens no `SKILL.md`) |

## Precedence

| Removed or cut | Now lives in |
|---|---|
| "A persona never overrides a rule above it" | the numbered order itself says it |
| Before a rename or golden regeneration, `ls` the siblings and hold the ruling provisional | `WORKFLOW.md` § Rulings and changes to the workflow |

## Done means verified

| Removed or cut | Now lives in |
|---|---|
| "Asserting a negative from memory…" (the why) | cut; the rule stays |
| `rg` skips ignored and dotted paths | `rg -uu` named in the line; detail: `SHELL-SAFETY.md` § Searching |
| Never infer a flag's blast radius from a one-line mention | folded into "has had its scope read this session" |

## Communication

All twelve bullets moved, word for word, to § Communication in the Quill
output style (`flow/claude/output-styles/quill.md` and the live
`~/.claude/output-styles/quill.md`). The delta bullet absorbed
`OPERATIONS.md`'s "Relay the delta" paragraph, which was deleted there.

## Workflow

| Removed or cut | Now lives in |
|---|---|
| `/wayfinder` only when the work outgrows a session | `WORKFLOW.md` § Pipeline notes |
| A named catalogue or fixture set is used before regenerating | `WORKFLOW.md` § Requests with a fixed shape |
| Never a bare open issue: every one carries a state label | `WORKFLOW.md` § Issue state; `file-ticket/SKILL.md` |
| Before filing, search open issues on the same component | hook `teach-filing.sh` → `WORKFLOW.md` § Before filing a ticket |
| Detail pointer (topic list) | action-worded pointer to `WORKFLOW.md` in § Hard rules |

## Agents and jobs

| Removed or cut | Now lives in |
|---|---|
| explore → `sonnet`, review → `opus` | `OPERATIONS.md` § Dispatch (the agent-model guard) |
| Status from the process table, never the terminal tail | `OPERATIONS.md` § Status |
| Long job → `job-run` + a progress file | `job-run` and the background-job guard kept in § Work; progress file: `OPERATIONS.md` § Wait |
| "My comment on a ticket sets the standard…" | `WORKFLOW.md` § Rulings and changes to the workflow |
| A merge: `--repo`, only after not-draft and CLEAN | hook `teach-merge.sh` → `OPERATIONS.md` § Merge preconditions |
| Detail pointer (topic list) | action-worded pointer to `OPERATIONS.md` in § Work |

## Gotchas

| Removed or cut | Now lives in |
|---|---|
| settings.json symlink: "four times on 2026-10-04" | cut; the rule stays in § Work |
| A process kill gets its own Bash call; SHELL-SAFETY pointer | hook `teach-process-kill.sh` → `SHELL-SAFETY.md` § Killing a process |
| Never print a path, open it with `zed`; read pages with `shot-scraper` | hook `teach-visual.sh` → `VISUAL-INSPECTION.md`; action-worded pointer kept in § Work for the sections no hook shows |
| Windows desktop, WSL shell only, never a Linux GUI | one line kept in § Work |

## Stated once

A rule kept in `CLAUDE.md` was removed from the pointer docs where they
restated it: the agent-model and permission-flag rules and the
`git status` before a sha (`OPERATIONS.md`), the settings.json symlink and
the code-file test (`WORKFLOW.md`), and "a `SKILL.md` is code"
(`rules/skill-files.md`). Skill bodies were left alone (#1409, Out of
Scope), so `implement/SKILL.md` still states commit identity and the
`git status` check at the step where a worker needs them.
