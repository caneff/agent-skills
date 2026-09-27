//! The `gh issue view` read both `merge_cleanup`'s `clear_ticket_if_closed`
//! and `implement_dispatch`'s claim-refusal check need: an issue's state,
//! labels and assignees, in one shell-out, with one parse. Filed from the
//! Standards review of #821 (over-engineering lens, yagni) — a change to
//! the gh contract or the parse now lands once.

use crate::runner::{quiet_stdout, quiet_stdout_bounded};
use std::time::Duration;

/// One issue's state, labels and assignees, as `gh issue view` answers it.
pub struct IssueState {
    pub state: String,
    pub labels_csv: String,
    pub assignees_csv: String,
}

impl IssueState {
    /// Whether `label` is one of this issue's labels.
    pub fn has_label(&self, label: &str) -> bool {
        self.labels_csv.split(',').any(|l| l == label)
    }
}

/// Parses one line of `gh issue view`'s
/// `.state + "\t" + ([.labels[].name] | join(",")) + "\t" + ([.assignees[].login] | join(","))`
/// output into its three fields. Tab-delimited, not space-delimited: a
/// GitHub label or login can contain a space (`good first issue`) but never
/// a tab, so a space-bearing label can't be split across fields. Missing
/// trailing fields come back empty, matching `gh` on an issue with no
/// labels or no assignees.
fn parse(line: &str) -> IssueState {
    let mut fields = line.splitn(3, '\t');
    IssueState {
        state: fields.next().unwrap_or("").to_string(),
        labels_csv: fields.next().unwrap_or("").to_string(),
        assignees_csv: fields.next().unwrap_or("").to_string(),
    }
}

/// Reads issue `n`'s state, labels and assignees from `gh`. `None` when the
/// call fails (gh not on PATH, no such issue, network error) — the same
/// shape both call sites already skip or refuse on.
pub fn read(slug: &str, n: &str) -> Option<IssueState> {
    let out = quiet_stdout(
        "gh",
        &[
            "issue",
            "view",
            n,
            "--repo",
            slug,
            "--json",
            "state,labels,assignees",
            "-q",
            ".state + \"\\t\" + ([.labels[].name] | join(\",\")) + \"\\t\" + ([.assignees[].login] | join(\",\"))",
        ],
    )?;
    Some(parse(&out))
}

/// Reads issue `n`'s body. `None` when the call fails; the caller decides
/// what an unreadable body means, since silence must not read as "names no
/// code".
pub fn body(slug: &str, n: &str) -> Option<String> {
    quiet_stdout("gh", &["issue", "view", n, "--repo", slug, "--json", "body", "-q", ".body"])
}

/// `read`, bounded (#849): `implement-dispatch` is the only caller of this
/// variant. `Ok(None)` is `gh`'s own real "no such issue"/call-failed
/// answer, which a caller may still read as "not an open issue"; `Err`
/// names the command and must never be read as "no labels" or any other
/// fact about the issue — the bound firing says nothing about the issue at
/// all.
pub fn read_timeout(slug: &str, n: &str, timeout: Duration) -> Result<Option<IssueState>, String> {
    let out = quiet_stdout_bounded(
        "gh",
        &[
            "issue",
            "view",
            n,
            "--repo",
            slug,
            "--json",
            "state,labels,assignees",
            "-q",
            ".state + \"\\t\" + ([.labels[].name] | join(\",\")) + \"\\t\" + ([.assignees[].login] | join(\",\"))",
        ],
        timeout,
    )?;
    Ok(out.map(|s| parse(&s)))
}

/// `body`, bounded (#849) — see [`read_timeout`]. A timed-out read must
/// never be read as "empty body" the way a real call failure already is.
pub fn body_timeout(slug: &str, n: &str, timeout: Duration) -> Result<Option<String>, String> {
    quiet_stdout_bounded("gh", &["issue", "view", n, "--repo", slug, "--json", "body", "-q", ".body"], timeout)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_state_labels_and_assignees() {
        let issue = parse("OPEN\tready-for-agent,in-progress\tcaneff");
        assert_eq!(issue.state, "OPEN");
        assert_eq!(issue.labels_csv, "ready-for-agent,in-progress");
        assert_eq!(issue.assignees_csv, "caneff");
        assert!(issue.has_label("in-progress"));
        assert!(!issue.has_label("ready-for-human"));
    }

    #[test]
    fn parses_empty_labels_and_assignees() {
        let issue = parse("CLOSED");
        assert_eq!(issue.state, "CLOSED");
        assert_eq!(issue.labels_csv, "");
        assert_eq!(issue.assignees_csv, "");
        assert!(!issue.has_label("in-progress"));
    }

    #[test]
    fn a_label_containing_a_space_does_not_bleed_into_assignees() {
        let issue = parse("OPEN\thelp wanted,ready-for-agent\tcaneff");
        assert_eq!(issue.labels_csv, "help wanted,ready-for-agent");
        assert_eq!(issue.assignees_csv, "caneff");
        assert!(issue.has_label("ready-for-agent"));
    }

    #[test]
    fn has_label_does_not_match_a_substring_of_another_label() {
        let issue = parse("OPEN\tready-for-agent,in-progress\t");
        assert!(!issue.has_label("progress"));
    }
}
