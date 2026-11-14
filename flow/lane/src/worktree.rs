//! A repo's worktrees, as one `git worktree list --porcelain` read: the
//! primary checkout first, then every linked worktree, each with the branch it
//! has checked out. The lane's commands take one snapshot and ask it what they
//! need — the primary checkout every linked worktree shares its hooks dir
//! with, which worktree holds a branch — rather than each listing for itself.

use crate::runner::{run, stdout_bounded};
use std::time::Duration;

/// One entry of the listing.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Worktree {
    /// The path git records, which is the resolved one.
    pub path: String,
    /// The local branch checked out there, without `refs/heads/`; `None` on
    /// a detached HEAD or a bare entry.
    pub branch: Option<String>,
}

/// A successful listing. Never empty: the first entry is the primary
/// checkout, and a listing that named no worktree is an `Err` from `list`.
#[derive(Debug, Clone)]
pub struct Worktrees {
    entries: Vec<Worktree>,
}

impl Worktrees {
    /// The one porcelain parser. `None` when the text names no worktree.
    /// Lines other than `worktree` and `branch` (`HEAD`, `detached`,
    /// `locked`, `prunable`, a stderr warning appended by the caller) say
    /// nothing either reader needs and are skipped.
    pub fn parse(porcelain: &str) -> Option<Self> {
        let mut entries: Vec<Worktree> = Vec::new();
        for line in porcelain.lines() {
            if let Some(path) = line.strip_prefix("worktree ") {
                entries.push(Worktree { path: path.to_string(), branch: None });
            } else if let Some(b) = line.strip_prefix("branch refs/heads/")
                && let Some(last) = entries.last_mut()
            {
                last.branch = Some(b.to_string());
            }
        }
        (!entries.is_empty()).then_some(Self { entries })
    }

    /// The primary checkout: the listing's first entry.
    pub fn primary(&self) -> &str {
        &self.entries[0].path
    }

    /// Every entry, the primary checkout first.
    pub fn all(&self) -> &[Worktree] {
        &self.entries
    }

    /// The linked worktrees: every entry but the primary checkout.
    pub fn linked(&self) -> &[Worktree] {
        &self.entries[1..]
    }

    /// The worktree, primary checkout included, that has `branch` checked out.
    pub fn holding(&self, branch: &str) -> Option<&str> {
        held(&self.entries, branch)
    }

    /// The linked worktree — never the primary checkout — that has `branch`
    /// checked out.
    pub fn linked_holding(&self, branch: &str) -> Option<&str> {
        held(self.linked(), branch)
    }
}

fn held<'a>(entries: &'a [Worktree], branch: &str) -> Option<&'a str> {
    entries.iter().find(|w| w.branch.as_deref() == Some(branch)).map(|w| w.path.as_str())
}

/// The worktrees of the repo at `repo`. `Err` says why there is no listing: a
/// `git worktree list` that failed (its own message included) is a different
/// answer from one that succeeded and named no worktree (#1209), and neither
/// is ever read as an empty listing (#1762).
pub fn list(repo: &str) -> Result<Worktrees, String> {
    let out = run("git", &["-C", repo, "worktree", "list", "--porcelain"])
        .map_err(|e| format!("git worktree list could not run in {repo}: {e}"))?;
    if !out.success {
        return Err(format!("git worktree list failed in {repo}: {}", out.combined));
    }
    named(repo, &out.combined)
}

/// `list`, bounded (#849): `implement-dispatch` calls it first, before it has
/// even resolved the origin slug, so a hang or any git failure here fails
/// loud, with git's own words, rather than reading as "not a git repo"
/// (#1254).
pub fn list_timeout(repo: &str, timeout: Duration) -> Result<Worktrees, String> {
    named(repo, &stdout_bounded("git", &["-C", repo, "worktree", "list", "--porcelain"], timeout)?)
}

fn named(repo: &str, porcelain: &str) -> Result<Worktrees, String> {
    Worktrees::parse(porcelain).ok_or_else(|| format!("git worktree list named no worktree in {repo}"))
}

#[cfg(test)]
mod tests {
    use super::*;

    const LISTING: &str = "worktree /src/repo\nHEAD 1111111111111111111111111111111111111111\nbranch refs/heads/main\n\n\
worktree /src/repo/.claude/worktrees/implement-7\nHEAD 2222222222222222222222222222222222222222\nbranch refs/heads/implement-7\n\n\
worktree /src/repo/.scratch/verify\nHEAD 3333333333333333333333333333333333333333\ndetached\n\n\
worktree /elsewhere/locked\nHEAD 4444444444444444444444444444444444444444\nbranch refs/heads/spec-9\nlocked\n";

    fn wt(path: &str, branch: Option<&str>) -> Worktree {
        Worktree { path: path.into(), branch: branch.map(Into::into) }
    }

    #[test]
    fn parse_reads_every_entry_in_order_with_its_branch() {
        let w = Worktrees::parse(LISTING).expect("a listing with entries parses");
        assert_eq!(
            w.all(),
            [
                wt("/src/repo", Some("main")),
                wt("/src/repo/.claude/worktrees/implement-7", Some("implement-7")),
                wt("/src/repo/.scratch/verify", None),
                wt("/elsewhere/locked", Some("spec-9")),
            ]
        );
        assert_eq!(w.primary(), "/src/repo");
        assert_eq!(w.linked(), &w.all()[1..]);
    }

    #[test]
    fn parse_of_text_naming_no_worktree_is_none() {
        assert!(Worktrees::parse("").is_none());
        assert!(Worktrees::parse("warning: something\n").is_none());
    }

    #[test]
    fn a_trailing_stderr_line_is_not_an_entry() {
        let w = Worktrees::parse("worktree /src/repo\nbranch refs/heads/main\nwarning: a stderr line").unwrap();
        assert_eq!(w.all(), [wt("/src/repo", Some("main"))]);
    }

    #[test]
    fn a_path_holding_spaces_is_kept_whole() {
        let w = Worktrees::parse("worktree /src/my repo\nbranch refs/heads/main\n").unwrap();
        assert_eq!(w.primary(), "/src/my repo");
    }

    #[test]
    fn holding_finds_the_primary_checkout_and_linked_holding_never_does() {
        let w = Worktrees::parse(LISTING).unwrap();
        assert_eq!(w.holding("main"), Some("/src/repo"));
        assert_eq!(w.linked_holding("main"), None);
        assert_eq!(w.holding("implement-7"), Some("/src/repo/.claude/worktrees/implement-7"));
        assert_eq!(w.linked_holding("implement-7"), Some("/src/repo/.claude/worktrees/implement-7"));
        assert_eq!(w.linked_holding("spec-9"), Some("/elsewhere/locked"));
    }

    #[test]
    fn a_branch_name_is_matched_whole() {
        let w = Worktrees::parse(LISTING).unwrap();
        assert_eq!(w.holding("implement"), None);
        assert_eq!(w.holding("refs/heads/main"), None);
    }
}
