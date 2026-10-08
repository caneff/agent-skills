# Upstream mattpocock/skills not installed here, 2026-10-08

Question (Chris, 2026-10-08): did the 2026-10-06 skills update consider new
skills in mattpocock/skills, or only update the installed ones?

Answer: only the installed ones. `skills-safe-update` merges upstream into
the skills that have an entry in `~/.agents/.skill-lock.json`. It has no
step that lists upstream skills missing from the lock.

## Method

- Upstream: every `*/SKILL.md` path in `gh api repos/mattpocock/skills/git/trees/HEAD?recursive=1`,
  38 in all. Each name is the skill's directory.
- Installed: the 32 lock entries whose source is `mattpocock/skills`.
- Last-change dates come from `gh api repos/mattpocock/skills/commits?path=<dir>&per_page=1`.

## Upstream, not installed

| Skill | Upstream path | Description (upstream frontmatter) | Last changed |
|---|---|---|---|
| implement-spec | engineering/ | Implement the result of /to-spec and /to-tickets in code. | 2026-09-24 |
| pr | engineering/ | Use when writing a PR body. | 2026-09-24 |
| retro | engineering/ | Conduct a retrospective on a coding session. | 2026-09-24 |
| chief-of-staff | in-progress/ | Pursue a long-running goal in a single session by co-ordinating subagents. | 2026-10-06 |
| claude-handoff | in-progress/ | Hand the current conversation off to a fresh background agent that picks up the work immediately. | 2026-10-06 |
| migrate-to-shoehorn | misc/ | Dropped from the lock on 2026-10-06 as dead drift. | — |
| scaffold-exercises | misc/ | Dropped from the lock on 2026-10-06 as dead drift. | — |

Overlaps with local skills (names only; no skill body compared yet):

- `implement-spec`: same name as the local, hand-written `implement-spec`. An `npx skills add` would collide.
- `pr`: the PR body is written by `implement/SKILL.md` § The PR.
- `retro`: the weekly retro (ADR 0005, `Memory/RULES.md`).
- `claude-handoff`: the installed `handoff`.
- `chief-of-staff`: `burndown` and `implement-spec`.

## Installed, gone upstream

`resolving-merge-conflicts`. Upstream removed it on 2026-09-24 ("Remove
resolving-merge-conflicts. No longer needed."). It is still in the lock and
on disk here.
