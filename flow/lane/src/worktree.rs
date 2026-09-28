//! The primary checkout of a repo: the first entry `git worktree list`
//! prints. Every linked worktree shares its hooks dir, and the lane's
//! commands run from it, so `implement-dispatch` and `controller-adopt` read
//! it the same way from here.

use crate::runner::{quiet_stdout, quiet_stdout_bounded, run};
use std::time::Duration;

/// The primary checkout of the repo at `repo`, as `git worktree list
/// --porcelain` names it; `None` when `repo` is not in a git repo or git
/// names no worktree.
pub fn primary(repo: &str) -> Option<String> {
    let out = quiet_stdout("git", &["-C", repo, "worktree", "list", "--porcelain"])?;
    out.lines().next()?.strip_prefix("worktree ").map(str::to_string)
}

/// `primary`, with the reason when there is none: a `git worktree list` that
/// failed (its own message included) is a different answer from one that
/// succeeded and named no worktree (#1209).
pub fn primary_checked(repo: &str) -> Result<String, String> {
    let out = run("git", &["-C", repo, "worktree", "list", "--porcelain"])
        .map_err(|e| format!("git worktree list could not run in {repo}: {e}"))?;
    if !out.success {
        return Err(format!("git worktree list failed in {repo}: {}", out.combined));
    }
    out.combined
        .lines()
        .next()
        .and_then(|l| l.strip_prefix("worktree "))
        .map(str::to_string)
        .ok_or_else(|| format!("git worktree list named no worktree in {repo}"))
}

/// `primary`, bounded (#849): `implement-dispatch` is the only caller of
/// this variant — its first git call, before it has even resolved the
/// origin slug — so a hang here must fail loud rather than be read as "not
/// a git repo" the way `primary`'s own `None` already reads a real
/// failure. `controller-adopt` calls the plain, unbounded
/// `primary_checked`, unchanged by that ticket.
pub fn primary_timeout(repo: &str, timeout: Duration) -> Result<Option<String>, String> {
    let out = quiet_stdout_bounded("git", &["-C", repo, "worktree", "list", "--porcelain"], timeout)?;
    Ok(out.and_then(|out| out.lines().next().and_then(|l| l.strip_prefix("worktree ")).map(str::to_string)))
}
