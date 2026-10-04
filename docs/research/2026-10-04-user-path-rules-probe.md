# User-level `paths:` rules: do they fire in every repo? (2026-10-04)

Question (#1413): does a user-level `~/.claude/rules/*.md` file with a
`paths:` frontmatter list fire in every repo, and what is its glob relative
to? The memory doc (https://code.claude.com/docs/en/memory) is silent on both.

## Answer

- **Yes, in every repo.** The same rule files fired in two unrelated scratch
  repos.
- **The glob is relative to the session's cwd**, not the git root, not `~`,
  not `/`. `sub/probe-rel.txt` matched with cwd at the repo root and did not
  match with cwd at `sub/` (same file, same git root).
- **A file outside the cwd never matches**, even with `**/`. An absolute glob
  and a `~/**` glob matched nothing.
- **A symlinked rule file loads** (the `InstructionsLoaded` record names the
  link's target), and **a dangling rule symlink is ignored**: the session
  ran, and the other rules still loaded.

So `**/SKILL.md` fires on any `SKILL.md` under the session's cwd, in any repo.
It does not fire when a session edits a file outside its cwd, such as
`~/.claude/CLAUDE.md` from a session opened in another repo.

## Method

Claude Code 2.1.289, `claude -p --model claude-haiku-4-5-20251001
--allowedTools=Read --settings <probe settings>`, the probe settings adding
one `InstructionsLoaded` hook that appended its stdin JSON to a log. herdr and
messaging variables were unset for the child so it could not report itself as
the parent's pane. Two scratch git repos, `repoA` and `repoB`, each holding
`sub/probe-{star,rel,abs,tilde}.txt`. Rule files in `~/.claude/rules/`:

| Rule | `paths:` | cwd repo root, file under cwd | cwd `repoA/sub` | file in another repo |
|---|---|---|---|---|
| STAR | `**/probe-star.txt` | loaded (A and B) | loaded | not loaded |
| REL | `sub/probe-rel.txt` | loaded (A and B) | not loaded | — |
| ABS | `<repoB absolute>/sub/probe-abs.txt` | not loaded | — | — |
| TILDE | `~/**/probe-tilde.txt` | not loaded | — | — |
| LINK (symlink to a file outside `~/.claude`) | `**/probe-link.txt` | loaded | — | — |
| dangling symlink | — | ignored, no error | — | — |

Each "loaded" row is an `InstructionsLoaded` record with `load_reason:
path_glob_match`, the rule's `file_path`, the `trigger_file_path` that was
read and the `globs`; the model's own listing of the rule text agreed with the
log in every run. The probe rule files were deleted afterwards.

## What #1413 did with it

The three file-edit rules moved to `flow/claude/rules/`, linked one file at a
time into `~/.claude/rules/` by `flow/install.sh`: instruction files
(`**/CLAUDE.md`, `**/AGENTS.md`, `**/RULES.md`, `**/CODING_STANDARDS.md`),
`**/SKILL.md`, and `**/docs/research/**`. The outside-cwd gap is accepted:
edits to those files happen in a checkout of the repo that holds them.
