# Orca removal dependency inventory

Date: 2026-09-10

## Scope and method

Searched with `rg -n -uu -i` for `orca`, `orca-ide`, `orca-wait`,
`orca-auto-enter`, and `workspace` in:

- this repository (excluding only `.git/` history from the actionable report),
- `~/.claude/CLAUDE.md`,
- `~/src/second-brain-v2/Memory/RULES.md`,
- every `AGENTS.md` below `~/src`, including ignored and dotted paths, and
- regular files in `~/.local/bin`.

"Call site" below includes an executable invocation and an operational
instruction that directs an agent to use Orca.  Plain uses of *workspace* that
do not depend on Orca are listed separately.  `NEEDS DECISION` means that git,
plain shell, and the VS Code `code` CLI cannot preserve the behavior.

## Actionable call sites

| File and line | Orca capability | Replacement limited to git, shell, and `code` |
|---|---|---|
| `~/.local/bin/orca-ide:3-23` | WSL-to-Windows bridge for the general Orca CLI | No one-for-one replacement. Retire it after its callers are rewritten; replace each operation individually. |
| `~/.local/bin/orca-wait:9,12` | Polls `orca-ide terminal show` by Orca terminal handle | Shell-owned children can record a PID and use `wait "$pid"`; **NEEDS DECISION** for attaching to an already-created IDE terminal or detecting TUI idleness. |
| `~/.local/bin/orca-auto-enter:5,11` | Finds the agent terminal in an Orca worktree | **NEEDS DECISION**. A shell can launch and own a process, but cannot discover an IDE-created terminal with these primitives. |
| `~/.local/bin/orca-auto-enter:25` | Waits for Orca terminal TUI idleness | **NEEDS DECISION**; use `wait "$pid"` only for a shell-owned process's exit. |
| `~/.local/bin/orca-auto-enter:27` | Sends Enter to an Orca terminal | **NEEDS DECISION**. Input can be supplied when creating a shell-owned process, not injected into an existing IDE terminal. |
| `flow/bin/merge-cleanup:108-113` | Tests for `orca-ide` and calls `worktree rm` | `git -C <primary> worktree list --porcelain` to resolve the branch's worktree path, then `git -C <primary> worktree remove --force <path>`. |
| `flow/bin/merge-cleanup.test.sh:40-46,135-137,189-200,223-225` | Orca CLI stub and assertions for the cleanup path | Update the test to assert the direct `git worktree remove` path; no Orca stub or Orca-specific output should remain. |
| `flow/claude/hooks/block-dangerous-git.test.sh:106` | Literal `orca-ide worktree rm` in a shell-parser fixture | Replace fixture text with `git worktree remove --force /tmp/x` (as the adjacent test already does), or remove the redundant case. |
| `flow/claude/settings.json:136` | PreToolUse lifecycle bridge at `~/.orca/agent-hooks/claude-hook.*` | **NEEDS DECISION**: remove the bridge or choose a replacement lifecycle/integration mechanism; no equivalent is supplied by git, shell, or `code`. |
| `flow/claude/settings.json:158` | PostToolUse lifecycle bridge | **NEEDS DECISION**: same as line 136. |
| `flow/claude/settings.json:183` | SessionStart lifecycle bridge | **NEEDS DECISION**: same as line 136. |
| `flow/claude/settings.json:194` | UserPromptSubmit lifecycle bridge | **NEEDS DECISION**: same as line 136. |
| `flow/claude/settings.json:205` | Stop lifecycle bridge | **NEEDS DECISION**: same as line 136. |
| `flow/claude/settings.json:216` | StopFailure lifecycle bridge | **NEEDS DECISION**: same as line 136. |
| `flow/claude/settings.json:227` | SubagentStart lifecycle bridge | **NEEDS DECISION**: same as line 136. |
| `flow/claude/settings.json:238` | SubagentStop lifecycle bridge | **NEEDS DECISION**: same as line 136. |
| `flow/claude/settings.json:249` | TeammateIdle lifecycle bridge | **NEEDS DECISION**: same as line 136. |
| `flow/claude/settings.json:261` | PostToolUseFailure lifecycle bridge | **NEEDS DECISION**: same as line 136. |
| `flow/claude/settings.json:282` | PermissionRequest lifecycle bridge | **NEEDS DECISION**: same as line 136. |
| `flow/claude/settings.json:293` | PostCompact lifecycle bridge | **NEEDS DECISION**: same as line 136. |
| `flow/claude/agent-status.md:15` | Reads an Orca terminal's cached screen | Use process state (`ps`, `kill -0 <pid>`), git HEAD, logs, and a durable progress file for shell-owned work. No equivalent exists for an arbitrary Orca terminal after Orca is removed. |
| `flow/claude/CLAUDE.md:12,20,115` and `~/.claude/CLAUDE.md:12,20,115` | One Orca workspace/worktree per task | `git -C <primary> worktree add -b <branch> <path> <base>`; optionally `code --reuse-window <path>`. |
| `flow/claude/CLAUDE.md:122-126` and `~/.claude/CLAUDE.md:122-126` | Directs `orca-wait` rather than Orca terminal wait | `wait "$pid"` and a log/progress-file poll for a shell-owned command; **NEEDS DECISION** for terminal-handle/TUI-idle semantics. |
| `flow/claude/CLAUDE.md:137-140` and `~/.claude/CLAUDE.md:137-140` | General `orca-ide` invocation and post-merge cleanup policy | There is no general CLI substitute. Use git worktree operations for cleanup as above, shell for processes, and `code` for editor operations. |
| `flow/claude/CLAUDE.md:149-150` and `~/.claude/CLAUDE.md:149-150` | `orca-ide file open`, `file diff`, and `file open-changed` | `code --reuse-window --goto <path>`; `code --reuse-window --diff <left> <right>`; derive changed paths with `git diff --name-only`. |
| `flow/claude/CLAUDE.md:174` and `~/.claude/CLAUDE.md:174` | Orca-installed, version-matched skill output | **NEEDS DECISION** on skill ownership/installation. The allowed primitives do not replace an installer or runtime-served guide. |
| `implement/SKILL.md:53-55` | Creates an Orca worktree and starts an agent with prompt/issue context | `git worktree add` replaces only creation; `code --reuse-window <path>` opens it. **NEEDS DECISION** for agent dispatch, prefilled prompt, and issue-bound workspace creation. |
| `implement/SKILL.md:61-62` | Lists Orca worktrees before creation | `git -C <primary> worktree list --porcelain`; compare the branch/path/name convention in shell. |
| `implement/SKILL.md:119` | Sets Orca worktree status | **NEEDS DECISION** for the visible workspace card. A committed or ignored status file is possible, but is not an equivalent shared UI. |
| `implement/SKILL.md:120` | Sets Orca worktree comment | **NEEDS DECISION** for the visible workspace card/comment. |
| `implement/SKILL.md:127-130` | Dispatches one Orca build worker in the workspace | **NEEDS DECISION**: no worker/task runtime exists in the allowed primitives. |
| `implement/SKILL.md:269` | Marks Orca worktree `in-review` | **NEEDS DECISION** for the workspace-card status. |
| `implement-spec/SKILL.md:9-10` | Loads version-matched Orca orchestration and CLI guides | Retire these loads and rewrite the skill against the chosen replacement; no runtime guide is needed for raw git/shell/`code` operations. |
| `implement-spec/SKILL.md:19-36,50-61,75-80` | Run/task DAG, worker status, task gates, workspace comment | **NEEDS DECISION**: the permitted tools have no equivalent task graph, mailbox, visible gate, or coordinator state. |
| `implement-spec/SKILL.md:67-70` | `orca-wait` on a terminal handle | Shell PID + `wait` for shell-owned workers; **NEEDS DECISION** for handle/TUI-idle behavior. |
| `burndown/SKILL.md:9-10` | Loads Orca guides | Retire these loads and rewrite after the foundational orchestration decision. |
| `burndown/SKILL.md:134,148,190,202` | Queries ready tasks and dispatches Orca workers | **NEEDS DECISION** for task frontier, coordination, and worker dispatch. |
| `burndown/SKILL.md:340-342` | `orca-ide worktree rm` after landing | Resolve branch to path with `git worktree list --porcelain`, then `git worktree remove --force <path>`. |
| `burndown/SKILL.md:430-434` | `orca-wait` on a terminal handle | Shell PID + `wait` for shell-owned workers; **NEEDS DECISION** for terminal idle/handle semantics. |
| `orca-cli/SKILL.md:4-9,40,44` | Orca worktrees, terminals, artifacts, browser, guide loading, and `ORCA open` | Retire/rewrite. Git covers worktrees and `code` covers source-file opening; **NEEDS DECISION** for artifacts/browser, terminals, automations, and runtime state. |
| `orchestration/SKILL.md:24-31,55,62,64,67` | Orca task coordination, handoffs, terminal control, browser, and runtime guide | **NEEDS DECISION** for structured multi-agent coordination and UI/runtime state. Git worktrees alone cover only one sub-capability. |
| `computer-use/SKILL.md:4-6,35,39` | `orca computer` OS/window input and inspection | **NEEDS DECISION**. `code` can open files but cannot inspect or control native windows, webviews, or browser UI. |
| `~/src/second-brain-v2/Memory/RULES.md:14` | `orca-ide worktree rm` in the handed merge procedure | Resolve the worktree with `git worktree list --porcelain`; run `git worktree remove <path>` before branch deletion. |
| `~/src/second-brain-v2/Memory/RULES.md:38` | Opens files/artifacts in Orca and Orca browser | Files: `code --reuse-window --goto <path>`. Rendered HTML/artifacts: **NEEDS DECISION**; the allowed tools open source but cannot provide browser rendering. |
| `~/src/twitch-rules-scroller/AGENTS.md:48` | Lists `orca-ide` among Windows-interop tools affected by Mono | No behavior to replace: remove/update the obsolete reference. VS Code's `code` CLI can remain in the check if relevant. |

## Installation and supporting-document dependencies

These are not command call sites, but must be changed with the runtime work.

| File and line | Dependency | Proposed action |
|---|---|---|
| `.skill-lock.json:454-479` | `computer-use`, `orca-cli`, and `orchestration` are installed from `stablyai/orca` | Remove or replace these three lock entries only after their replacement/retirement decision. |
| `.gitignore:12-17` | Ignores the three Orca-provided skill directories as regenerated runtime output | Remove the explanation and ignore entries when the skills are no longer Orca-installed. |
| `implement/codex-lane.md:33` | Points to the Orca `worktree create` flow in `implement` | Update after `implement/SKILL.md` is rewritten. |
| `burndown/references/spec-handoff.md:17,29` | Tells a coordinator to make an Orca workspace and dispatch an Orca task | Update after the orchestration decision and `implement-spec` rewrite. |
| `progressive-disclosure-split-report.md:34,47,50,53,220,229-257` | Historical/proposed document describing Orca instructions | Update or archive only after source instructions are changed. |
| `.scratch/setup-ideas/index.html:206-208,661-713` | Planning artifact that describes this removal and repeats the request | Not a runtime dependency; revise only if the planning record is meant to remain current. |
| `docs/research/run-in-background-reaches-pretooluse.md:36-37` | Historical transcript and cwd under an Orca workspace | Historical evidence only; no operational replacement required. |
| `burndown/cost_test.py:12-13` | Fixture paths containing `orca/workspaces` | Rename fixture paths when normalizing terminology; no runtime behavior depends on Orca. |

## Incidental `workspace` matches

The following matches do not rely on Orca and should not drive removal work:

- `flow/ccstatusline-table/table-statusline.py:184,247` reads a generic
  `workspace` field from status-line JSON.
- `~/src/sudokumaker-custom-constraints/AGENTS.md:71` uses
  `workspace-write` as a sandbox permission.
- `~/src/twitch-rules-scroller/AGENTS.md:114` names a generic durable artifact
  directory inside a workspace.
- `~/src/second-brain-v2/Memory/RULES.md:37` describes artifact placement; use
  `git rev-parse --show-toplevel` if a repo-root location must be derived.
- Teaching, marimo, landing, and package-manager skill uses of *workspace* are
  generic project/work-directory language.

All 17 `AGENTS.md` files below `~/src` were searched with `-uu`; only
`twitch-rules-scroller/AGENTS.md` and
`sudokumaker-custom-constraints/AGENTS.md` matched, as described above.

## Skills to edit, in dependency order

Non-skill prerequisites are the three local scripts, the Claude lifecycle-hook
decision in `flow/claude/settings.json`, and `merge-cleanup`.  Then edit skills
in this order:

1. `orca-cli` — foundational wrapper contract; retire it or reduce it to the
   portions actually retained.
2. `orchestration` — depends on `orca-cli` for worktrees, terminals, messages,
   task state, and browser state.  This is the primary **NEEDS DECISION**.
3. `computer-use` — separately decide the replacement for desktop/browser
   control; git, shell, and `code` do not cover it.
4. `implement-spec` — consumes orchestration, terminal wait, task DAGs, gates,
   and workspace comments.
5. `implement` — consumes worktree creation/status/comments and the
   `implement-spec` worker model.
6. `implement/codex-lane.md` — inherits `implement`'s creation/dispatch path.
7. `burndown` — consumes `implement-spec`, orchestration, worker wait, and
   worktree teardown.

After those, update their references and the two copies of `CLAUDE.md`, then
remove the lock/ignore metadata.  No files were modified during the inventory;
this note is the requested output artifact.
