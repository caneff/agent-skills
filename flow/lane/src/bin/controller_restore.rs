//! `controller-restore`: the `SessionStart` hook that restores what a
//! `/clear` wipes from a controller's context (#964). `/clear` kills the
//! context, not the process — the session's pid, and the sibling
//! `<pid>.workers.jsonl` file `implement-dispatch` appended a record to for
//! every worker it started under this session, both survive it. This hook
//! reads that file, asks herdr which of those workers' agents are still
//! alive and `gh` whether each branch has an open or merged PR, and prints
//! one line per worker naming what to do next. It never re-sends a brief,
//! never writes anything but its own stdout, and rearms nothing: the printed
//! state is what the resumed context acts on.
//!
//! Run with no arguments, fed the hook's JSON on stdin (as Claude Code's
//! `SessionStart` hook contract does); everything it prints becomes context
//! for the session that starts. Silent (exit 0, nothing on stdout) whenever
//! there is nothing to restore, so a session that has never dispatched a
//! worker is unaffected.

use lane::herdr::{self, Agent};
use lane::runner::quiet_stdout_timeout;
use lane::sessions;
use lane::workers::{self, WorkerRecord};
use lane::{proc_info, safe_println};
use serde_json::Value;
use std::io::Read;
use std::path::Path;
use std::time::Duration;

const HERDR_QUERY_TIMEOUT: Duration = Duration::from_secs(10);
const GH_QUERY_TIMEOUT: Duration = Duration::from_secs(10);

/// A PR `gh pr list` reports for a worker's branch.
struct PrStatus {
    number: String,
    state: String,
}

/// Parses one `<number> <STATE>` line — the first is the branch's most
/// recent PR, which is all `gh pr list --head <branch>` can return (a
/// branch carries at most one open PR, and this hook does not care about a
/// closed-without-merging one past its own text). Anything else, including
/// no output at all, is no PR.
fn parse_pr_status(out: &str) -> Option<PrStatus> {
    let line = out.lines().find(|l| !l.trim().is_empty())?;
    let mut fields = line.split_whitespace();
    let number = fields.next()?.to_string();
    let state = fields.next()?.to_string();
    Some(PrStatus { number, state })
}

/// The herdr status word for the agent named `name`, or `None` when herdr
/// lists no such agent (its pane closed, or herdr was never asked).
fn agent_status_word<'a>(agents: &'a [Agent], name: &str) -> Option<&'a str> {
    agents.iter().find(|a| a.name() == name).map(Agent::status)
}

/// What to say about a worker's PR: the state, and the guidance that follows
/// from it. `None` is "no PR yet" — the worker may still be building.
fn describe_pr(pr: Option<&PrStatus>) -> String {
    match pr {
        None => "no PR yet — check on the worker".to_string(),
        Some(p) => match p.state.as_str() {
            "MERGED" => format!("PR #{} merged — run cleanup", p.number),
            "OPEN" => format!("PR #{} open, not merged — follow implement/SKILL.md \u{a7} The merge", p.number),
            "CLOSED" => format!("PR #{} closed without merging — check on the worker", p.number),
            other => format!("PR #{} state {other}", p.number),
        },
    }
}

/// One restore line for `record`, e.g.:
/// `You control implement-143 (sudokupad-art-143, agent working): PR #152
/// open, not merged — follow implement/SKILL.md § The merge; cleanup: <line>`
fn restore_line(record: &WorkerRecord, agent_status: Option<&str>, pr: Option<&PrStatus>) -> String {
    let agent_clause = match agent_status {
        Some(status) => format!("{}, agent {status}", record.agent),
        None => format!("{}, no live herdr agent", record.agent),
    };
    let merges = if record.chris_merges { ", Chris merges" } else { "" };
    format!("You control {} ({agent_clause}{merges}): {}; cleanup: {}", record.branch, describe_pr(pr), record.cleanup)
}

/// Whether the hook's stdin JSON names a subagent run (`agent_id` set) — a
/// `Task` subagent's own session start fires the same hook, and it controls
/// nothing of its own to restore.
fn is_subagent(stdin: &str) -> bool {
    serde_json::from_str::<Value>(stdin)
        .ok()
        .and_then(|v| v.get("agent_id").cloned())
        .is_some_and(|v| !v.is_null() && v.as_str() != Some(""))
}

fn main() {
    let mut stdin = String::new();
    let _ = std::io::stdin().read_to_string(&mut stdin);
    if is_subagent(&stdin) {
        return;
    }

    let home = std::env::var("HOME").unwrap_or_default();
    let home = Path::new(&home);
    let self_pid = std::process::id() as i32;
    let Some(ancestor) = proc_info::parent_pid(self_pid) else { return };
    let Some(own_pid) = sessions::find_own_pid(home, ancestor) else { return };

    let records = workers::read(home, &own_pid);
    if records.is_empty() {
        return;
    }

    let agents: Vec<Agent> = quiet_stdout_timeout("herdr", &["agent", "list"], HERDR_QUERY_TIMEOUT)
        .and_then(|out| herdr::parse_agents(&out))
        .unwrap_or_default();

    for record in &records {
        let status = agent_status_word(&agents, &record.agent);
        let pr = quiet_stdout_timeout(
            "gh",
            &["pr", "list", "--repo", &record.repo, "--head", &record.branch, "--state", "all", "--json", "number,state", "--jq", r#".[0] | "\(.number) \(.state)""#, "--limit", "1"],
            GH_QUERY_TIMEOUT,
        )
        .as_deref()
        .and_then(parse_pr_status);
        safe_println!("{}", restore_line(record, status, pr.as_ref()));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn record() -> WorkerRecord {
        WorkerRecord {
            agent: "sudokupad-art-143".into(),
            tickets: vec!["143".into()],
            branch: "implement-143".into(),
            workspace: "/repo/.claude/worktrees/implement-143".into(),
            repo: "caneff/sudokupad-art".into(),
            cleanup: "cd /repo && merge-cleanup implement-143 --repo /repo".into(),
            chris_merges: false,
            dispatched_at: "2026-09-21T10:00:00Z".into(),
        }
    }

    #[test]
    fn parses_a_pr_status_line_and_ignores_blank_lines_before_it() {
        let p = parse_pr_status("\n152 OPEN\n").unwrap();
        assert_eq!(p.number, "152");
        assert_eq!(p.state, "OPEN");
    }

    #[test]
    fn empty_output_is_no_pr() {
        assert!(parse_pr_status("").is_none());
        assert!(parse_pr_status("\n\n").is_none());
    }

    #[test]
    fn agent_status_word_finds_by_name_and_is_none_when_absent() {
        let agents = herdr::parse_agents(r#"{"result":{"agents":[{"name":"sudokupad-art-143","agent_status":"working"}]}}"#).unwrap();
        assert_eq!(agent_status_word(&agents, "sudokupad-art-143"), Some("working"));
        assert_eq!(agent_status_word(&agents, "someone-else"), None);
    }

    #[test]
    fn describe_pr_covers_open_merged_closed_and_none() {
        assert_eq!(describe_pr(None), "no PR yet — check on the worker");
        assert!(describe_pr(Some(&PrStatus { number: "9".into(), state: "OPEN".into() })).starts_with("PR #9 open, not merged"));
        assert_eq!(describe_pr(Some(&PrStatus { number: "9".into(), state: "MERGED".into() })), "PR #9 merged — run cleanup");
        assert!(describe_pr(Some(&PrStatus { number: "9".into(), state: "CLOSED".into() })).starts_with("PR #9 closed without merging"));
    }

    #[test]
    fn restore_line_names_the_branch_agent_status_pr_and_cleanup() {
        let line = restore_line(&record(), Some("working"), Some(&PrStatus { number: "152".into(), state: "OPEN".into() }));
        assert_eq!(
            line,
            "You control implement-143 (sudokupad-art-143, agent working): PR #152 open, not merged — follow implement/SKILL.md \u{a7} The merge; cleanup: cd /repo && merge-cleanup implement-143 --repo /repo"
        );
    }

    #[test]
    fn restore_line_notes_no_live_agent_and_chris_merges() {
        let mut r = record();
        r.chris_merges = true;
        let line = restore_line(&r, None, None);
        assert!(line.contains("no live herdr agent"), "{line}");
        assert!(line.contains("Chris merges"), "{line}");
        assert!(line.contains("no PR yet"), "{line}");
    }

    #[test]
    fn is_subagent_true_only_for_a_non_empty_agent_id() {
        assert!(is_subagent(r#"{"agent_id":"sub-1"}"#));
        assert!(!is_subagent(r#"{"agent_id":""}"#));
        assert!(!is_subagent(r#"{"agent_id":null}"#));
        assert!(!is_subagent(r#"{"hook_event_name":"SessionStart"}"#));
        assert!(!is_subagent(""));
        assert!(!is_subagent("not json"));
    }
}
