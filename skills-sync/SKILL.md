---
name: skills-sync
description: Report and optionally repair drift between the two skill directories (~/.agents/skills canonical bodies, ~/.claude/skills symlinks). Use when a skill seems half-installed, a ~/.claude/skills entry is a real dir instead of a symlink, after manually adding/moving a skill, or to audit that every canonical body is exposed to Claude.
disable-model-invocation: true
---

# skills-sync

Reconciles the hand-wired skill layout:

```
~/.agents/skills  canonical real bodies   <- what Claude loads
~/.claude/skills  symlinks -> ../../.agents/skills/<name>
```

## Run

```bash
~/.agents/skills/skills-sync/skills-sync.sh            # dry report
~/.agents/skills/skills-sync/skills-sync.sh --fix      # repair structural cases
~/.agents/skills/skills-sync/skills-sync.sh --self-test
```

A "skill" = a directory containing `SKILL.md`. Non-dir files (`skills-lock.json`)
and dot-dirs (`.system`, `.agents`) are skipped. Matching is by directory name
only.

## Report codes

| Code | Meaning | `--fix` |
|------|---------|---------|
| `NO_SYMLINK`   | agents body has no `~/.claude` symlink | creates the symlink |
| `NOT_SYMLINK`  | `~/.claude` entry is a real dir, not a symlink | moves body to agents, symlinks back (refuses if an agents body already exists) |
| `WRONG_TARGET` | symlink resolves but points at the wrong body | relinks |
| `BROKEN_LINK`  | symlink target does not resolve | relinks if an agents body exists, else removes the dead symlink |

`--fix` creates symlinks, moves a stray `~/.claude` body into `~/.agents`, and
removes dangling `~/.claude` symlinks (ones whose body is gone). It never
deletes a real directory.

Override `AGENTS` / `CLAUDE` env vars to point at other trees (the self-test
uses this).
