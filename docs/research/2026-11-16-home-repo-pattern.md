# The Home Repo pattern, measured against this setup

Question (Chris, 2026-11-16): should the repos be reorganized around Matt
Pocock's "home repo"?

## Sources read

- Matt Pocock, "The Home Repo Pattern" article: https://www.aihero.dev/the-home-repo-pattern
- His video transcript: https://www.youtube.com/watch?v=hWe-j78vNpc
- His dictionary entry: https://github.com/mattpocock/dictionary-of-ai-coding/blob/main/dictionary/Home%20Repo.md
- A variant by Andrea Bizzotto: https://codewithandrea.com/articles/ai-agents-multiple-repos/

## The pattern, reworded

One repo holds the shared skills, the agent instruction file, shared docs and
custom tooling. Every agent session starts in that repo. Its `AGENTS.md`
lists each other repo with a one-line pointer (local path, and where to clone
from if missing), and the agent opens or clones repos from there. Each repo
keeps its code, its own `AGENTS.md`, history and issue tracker. Pocock
names two problems it solves. Skills copied into every repo drift apart. A
user-level directory is invisible to a team and falls behind the shared setup.
He also says a monorepo is better when one is possible.

Bizzotto's variant keeps sessions in the project repos. An index `AGENTS.md`
sits in the parent folder, and Claude Code loads `CLAUDE.md` from parent
directories, so a session in any repo also sees the index.

## Against this setup

- **Shared material in one versioned repo: already done.** `agent-skills`
  (`~/.agents/skills`) holds the skills, the global `CLAUDE.md`, the
  `settings.json`, the hooks and the tooling. Symlinks put them into
  `~/.claude`. Pocock's objection to the user directory is that it is
  unversioned and that teammates drift. Neither applies to one person
  whose user directory is a symlink into a versioned repo.
- **Wiki: already separate.** `second-brain-v2` is the vault, and the global
  `CLAUDE.md` imports its `Memory/` files.
- **Starting every session in the home repo: does not fit.** The workflow keys
  many mechanisms on the session's own repo. Examples are workers in
  per-repo worktrees, controllers per repo, `drain` named after the primary
  checkout, the review cache by repo key, the ownership hook and Gate 1 by
  target repo, and each repo's `AGENTS.md` seam loaded from the working
  directory. Starting from a home repo would also put every repo outside the
  session's working directories. That is the cause of the node_modules
  prompts fixed in c94be74b.
- **Repo index: missing.** No loaded file lists the ~35 repos under `~/src`
  with what each one is for. A session finds a sibling repo by
  searching, or by `all-audits/driver.py --suggest`.

## Verdict

Do not reorganize. If a repo index is wanted, it goes into a file the
global `CLAUDE.md` already loads, as one line per active repo (path, remote,
purpose). This is the Bizzotto variant, and every session keeps its own repo.
