//! The `gh issue view` read both `merge_cleanup`'s `clear_ticket_if_closed`
//! and `implement_dispatch`'s claim-refusal check need: an issue's state,
//! labels and assignees, in one shell-out, with one parse. Filed from the
//! Standards review of #821 (over-engineering lens, yagni) — a change to
//! the gh contract or the parse now lands once.

use crate::runner::quiet_stdout;

/// One issue's state, labels and assignees, as `gh issue view` answers it.
pub struct IssueState {
    pub state: String,
    pub labels_csv: String,
    pub assignees_csv: String,
}

impl IssueState {
    /// Whether `label` is one of this issue's labels.
    pub fn has_label(&self, label: &str) -> bool {
        format!(",{},", self.labels_csv).contains(&format!(",{label},"))
    }
}

/// Parses one line of `gh issue view`'s
/// `.state + " " + ([.labels[].name] | join(",")) + " " + ([.assignees[].login] | join(","))`
/// output into its three fields. Missing trailing fields come back empty,
/// matching `gh` on an issue with no labels or no assignees.
fn parse(line: &str) -> IssueState {
    let mut fields = line.splitn(3, ' ');
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
            ".state + \" \" + ([.labels[].name] | join(\",\")) + \" \" + ([.assignees[].login] | join(\",\"))",
        ],
    )?;
    Some(parse(&out))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_state_labels_and_assignees() {
        let issue = parse("OPEN ready-for-agent,in-progress caneff");
        assert_eq!(issue.state, "OPEN");
        assert_eq!(issue.labels_csv, "ready-for-agent,in-progress");
        assert_eq!(issue.assignees_csv, "caneff");
        assert!(issue.has_label("in-progress"));
        assert!(!issue.has_label("ready-for-human"));
    }

    #[test]
    fn parses_empty_labels_and_assignees() {
        let issue = parse("CLOSED  ");
        assert_eq!(issue.state, "CLOSED");
        assert_eq!(issue.labels_csv, "");
        assert_eq!(issue.assignees_csv, "");
        assert!(!issue.has_label("in-progress"));
    }
}
