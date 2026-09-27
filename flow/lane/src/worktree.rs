//! The primary checkout of a repo: the first entry `git worktree list`
//! prints. Every linked worktree shares its hooks dir, and the lane's
//! commands run from it, so `implement-dispatch` and `controller-adopt` read
//! it the same way from here.

use crate::runner::quiet_stdout;

/// The primary checkout of the repo at `repo`, as `git worktree list
/// --porcelain` names it; `None` when `repo` is not in a git repo or git
/// names no worktree.
pub fn primary(repo: &str) -> Option<String> {
    let out = quiet_stdout("git", &["-C", repo, "worktree", "list", "--porcelain"])?;
    out.lines().next()?.strip_prefix("worktree ").map(str::to_string)
}
