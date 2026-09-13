---
name: skills-sync
description: Report and optionally repair drift between the two skill directories (~/.agents/skills canonical bodies, ~/.claude/skills symlinks).
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

`skills-sync.test.sh` wraps the self-test so the repo's `tests/all.sh` runs it.

A "body" = a directory containing `SKILL.md` or `.claude-plugin/plugin.json`.
Non-dir files (`.skill-lock.json`) and dot-dirs (`.system`, `.agents`) are
skipped. Matching is by directory name only.

## Report codes

| Code | Meaning | `--fix` |
|------|---------|---------|
| `NO_SYMLINK`   | agents body has no `~/.claude` symlink | creates the symlink |
| `NOT_SYMLINK`  | `~/.claude` entry is a real dir, not a symlink | moves body to agents, symlinks back (refuses if an agents body already exists) |
| `WRONG_TARGET` | symlink resolves but points at the wrong body | relinks |
| `BROKEN_LINK`  | symlink doesn't resolve to a body, but its canonical name (`~/.agents/skills/<n>`) is a healthy body, or nothing is there at all | relinks if the canonical body is healthy, else removes the dead symlink |
| `NOT_A_BODY`   | symlink's canonical name exists but isn't a body (no marker file, or a dangling `plugin.json` symlink) | left untouched — relinking would never converge |

`--fix` creates symlinks, moves a stray `~/.claude` body into `~/.agents`, and
removes dangling `~/.claude` symlinks (ones whose body is gone). It never
deletes a real directory.

Override `AGENTS` / `CLAUDE` env vars to point at other trees (the self-test
uses this).
