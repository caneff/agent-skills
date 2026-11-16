# TokenEconomizer, measured against this setup

Question (Chris, 2026-11-16): should we adopt microsoft/TokenEconomizer?

Read: the repo README only, https://github.com/microsoft/TokenEconomizer
(Apache-2.0, created 2026-10-13). The paper, the code, and its settings
writer were not read.

## What it is, reworded

A plugin for Claude Code (and Codex, among others) that learns across a
repo's sessions. It has three mechanisms, each one can be switched off, and
it stores its state in `~/.tokeneconomizer`:

- **Micro-skills**: facts about the repo (the command spelling that works,
  a build step that must run first). The facts come from failures repeated
  across sessions, and from a model review of the recent sessions every 3
  sessions. A fact is injected at session start after 3 sessions confirm it,
  and is dropped when later sessions contradict it.
- **Tool pruning**: a tool unused over 10 prompts in 2 or more sessions, or
  over 5 sessions, is removed "through the agent's own settings". One
  command restores it.
- **Loop guard**: a judge model checks a turn that keeps hitting the same
  failures. At 0.7 confidence or more, it injects one redirect note per
  turn. It never stops a turn itself.

Reported result: 18–31% lower mean cost on 277 SWE-Bench tasks (one session
per task, run in order per repo), with Pass@1 up in 4 of 5 agent–model
combinations. That is single-session issue fixing, not parallel workers in
worktrees.

## Against this setup

- **Micro-skills overlap the friction log, the weekly retro and
  `Memory/RULES.md`.** Here a rule is promoted only after review, and the
  always-on text is capped at 1,100 words (`tests/check-always-on.py`).
  Micro-skills would be a second channel that writes facts into every
  session without that review and outside that cap. Unknown: whether it
  keys a repo by path, which would make each worktree a new repo with
  nothing learned.
- **Tool pruning writes settings.** `~/.claude/settings.json` is a symlink
  into agent-skills. A tool that edits it dirties `main` there, and one that
  writes through a temp file and `mv` replaces the symlink. Not checked
  which it does. Most MCP tools here are already deferred behind ToolSearch,
  so the gain is smaller than on a default install.
- **The loop guard targets a known failure.** `AGENTS.md` § End-to-end seam
  lists "a worker spinning on no-op tool calls" as something no test sees.
  Each judge call is paid from the same plan.
- **Installing it is a new dependency and harness work** (`WORKFLOW.md`
  § Auto mode and harness work). Chris installs it, outside auto mode.

## Verdict

Do not install the whole plugin. If anything, trial the loop guard alone
(micro-skills and tool pruning off) on one repo, after reading how it
writes settings.

## Ruling (Chris, 2026-11-16)

Not installed. Two lessons adapted instead: repeated tool failures as
retro evidence (caneff/second-brain-v2#175), and a model-free loop-guard
hook (#1914, `ready-for-human` as harness work).
