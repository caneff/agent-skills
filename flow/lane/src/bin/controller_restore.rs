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

const QUERY_TIMEOUT: Duration = Duration::from_secs(10);

/// A PR `gh pr list` reports for a worker's branch.
struct PrStatus {
    number: String,
    state: String,
}

/// Parses one `<number> <STATE>` line — the first is the branch's most
/// recent PR, which is all `gh pr list --head <branch>` can return (a
/// branch carries at most one open PR, and this hook does not care about a
/// closed-without-merging one past its own text). Empty output is no PR.
/// `null null` is also no PR, not a defensive guess: the `--jq` filter below
/// asks for `.[0] // empty`, which already turns a `null` first element into
/// no output — this is the same fact checked a second time at the Rust
/// boundary, in case a future edit to that filter (or a `gh` behaviour
/// change) drops the `// empty` and starts leaking `null` through again.
fn parse_pr_status(out: &str) -> Option<PrStatus> {
    let line = out.lines().find(|l| !l.trim().is_empty())?;
    let mut fields = line.split_whitespace();
    let number = fields.next()?.to_string();
    let state = fields.next()?.to_string();
    if number == "null" || state == "null" {
        return None;
    }
    Some(PrStatus { number, state })
}

/// What herdr or gh answered about one thing: a real value, a real "there is
/// none", or "could not be asked at all" (off PATH, timed out, unparseable
/// output) — the third must never print the same as the second. Conflating
/// them was #964's own correctness-axis C2/standards-axis S1 finding: a
/// wedged herdr made every worker read "no live herdr agent" as if that were
/// a fact about the agent rather than about herdr.
enum Asked<T> {
    Answered(T),
    Unknown,
}

/// herdr's answer to "is `name`'s agent alive, and what's its status" —
/// `Answered(None)` is a real "no such agent"; `Unknown` is "herdr could not
/// be asked".
fn agent_status<'a>(agents: &'a Asked<Vec<Agent>>, name: &str) -> Asked<Option<&'a str>> {
    match agents {
        Asked::Unknown => Asked::Unknown,
        Asked::Answered(agents) => Asked::Answered(agents.iter().find(|a| a.name() == name).map(Agent::status)),
    }
}

/// What to say about a worker's herdr agent.
fn describe_agent(agent: &str, status: &Asked<Option<&str>>) -> String {
    match status {
        Asked::Unknown => format!("{agent}, herdr status unknown — could not ask herdr"),
        Asked::Answered(Some(s)) => format!("{agent}, agent {s}"),
        Asked::Answered(None) => format!("{agent}, no live herdr agent"),
    }
}

/// What to say about a worker's PR: the state, and the guidance that follows
/// from it. `Answered(None)` is "no PR yet" — the worker may still be
/// building; `Unknown` is "gh could not be asked", never worded the same way.
fn describe_pr(pr: &Asked<Option<PrStatus>>) -> String {
    match pr {
        Asked::Unknown => "PR status unknown — could not ask gh".to_string(),
        Asked::Answered(None) => "no PR yet — check on the worker".to_string(),
        Asked::Answered(Some(p)) => match p.state.as_str() {
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
fn restore_line(record: &WorkerRecord, agent: &Asked<Option<&str>>, pr: &Asked<Option<PrStatus>>) -> String {
    let merges = if record.chris_merges { ", Chris merges" } else { "" };
    format!("You control {} ({}{merges}): {}; cleanup: {}", record.branch, describe_agent(&record.agent, agent), describe_pr(pr), record.cleanup)
}

/// Whether the hook's stdin JSON names a subagent run — a `Task` subagent's
/// own session start fires the same hook, and it controls nothing of its
/// own to restore. Checked under both spellings a hook payload might carry
/// (`agent_id`, and `agentId` as `~/.claude/hooks/worker-stop-alert.sh`
/// reads it from a transcript payload) — reading only one risked injecting
/// a parent session's "You control …" lines into every subagent's context
/// under the other.
fn is_subagent(stdin: &str) -> bool {
    let Ok(v) = serde_json::from_str::<Value>(stdin) else { return false };
    for key in ["agent_id", "agentId"] {
        if v.get(key).is_some_and(|v| !v.is_null() && v.as_str() != Some("")) {
            return true;
        }
    }
    false
}

fn ask_agents() -> Asked<Vec<Agent>> {
    match quiet_stdout_timeout("herdr", &["agent", "list"], QUERY_TIMEOUT).and_then(|out| herdr::parse_agents(&out)) {
        Some(agents) => Asked::Answered(agents),
        None => Asked::Unknown,
    }
}

fn ask_pr(repo: &str, branch: &str) -> Asked<Option<PrStatus>> {
    match quiet_stdout_timeout(
        "gh",
        &["pr", "list", "--repo", repo, "--head", branch, "--state", "all", "--json", "number,state", "--jq", r#".[0] // empty | "\(.number) \(.state)""#, "--limit", "1"],
        QUERY_TIMEOUT,
    ) {
        Some(out) => Asked::Answered(parse_pr_status(&out)),
        None => Asked::Unknown,
    }
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

    let agents = ask_agents();

    for record in &records {
        let status = agent_status(&agents, &record.agent);
        let pr = ask_pr(&record.repo, &record.branch);
        safe_println!("{}", restore_line(record, &status, &pr));
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
    fn a_null_first_element_is_no_pr_not_a_pr_number_null() {
        // What `.[0] | ...` (without `// empty`) actually prints for an
        // empty gh result — the bug the jq filter and this second check
        // both guard against (#964 correctness C1).
        assert!(parse_pr_status("null null").is_none());
    }

    #[test]
    fn agent_status_distinguishes_found_not_found_and_unknown() {
        let agents = Asked::Answered(herdr::parse_agents(r#"{"result":{"agents":[{"name":"sudokupad-art-143","agent_status":"working"}]}}"#).unwrap());
        assert!(matches!(agent_status(&agents, "sudokupad-art-143"), Asked::Answered(Some("working"))));
        assert!(matches!(agent_status(&agents, "someone-else"), Asked::Answered(None)));
        let unknown: Asked<Vec<Agent>> = Asked::Unknown;
        assert!(matches!(agent_status(&unknown, "sudokupad-art-143"), Asked::Unknown));
    }

    #[test]
    fn describe_pr_covers_open_merged_closed_none_and_unknown() {
        assert_eq!(describe_pr(&Asked::Answered(None)), "no PR yet — check on the worker");
        assert!(describe_pr(&Asked::Answered(Some(PrStatus { number: "9".into(), state: "OPEN".into() }))).starts_with("PR #9 open, not merged"));
        assert_eq!(describe_pr(&Asked::Answered(Some(PrStatus { number: "9".into(), state: "MERGED".into() }))), "PR #9 merged — run cleanup");
        assert!(describe_pr(&Asked::Answered(Some(PrStatus { number: "9".into(), state: "CLOSED".into() }))).starts_with("PR #9 closed without merging"));
        assert_eq!(describe_pr(&Asked::Unknown), "PR status unknown — could not ask gh");
    }

    #[test]
    fn restore_line_names_the_branch_agent_status_pr_and_cleanup() {
        let line = restore_line(&record(), &Asked::Answered(Some("working")), &Asked::Answered(Some(PrStatus { number: "152".into(), state: "OPEN".into() })));
        assert_eq!(
            line,
            "You control implement-143 (sudokupad-art-143, agent working): PR #152 open, not merged — follow implement/SKILL.md \u{a7} The merge; cleanup: cd /repo && merge-cleanup implement-143 --repo /repo"
        );
    }

    #[test]
    fn restore_line_notes_no_live_agent_and_chris_merges() {
        let mut r = record();
        r.chris_merges = true;
        let line = restore_line(&r, &Asked::Answered(None), &Asked::Answered(None));
        assert!(line.contains("no live herdr agent"), "{line}");
        assert!(line.contains("Chris merges"), "{line}");
        assert!(line.contains("no PR yet"), "{line}");
    }

    #[test]
    fn restore_line_says_unknown_rather_than_a_guessed_state_when_it_could_not_ask() {
        let line = restore_line(&record(), &Asked::Unknown, &Asked::Unknown);
        assert!(line.contains("herdr status unknown — could not ask herdr"), "{line}");
        assert!(line.contains("PR status unknown — could not ask gh"), "{line}");
        assert!(!line.contains("no live herdr agent"), "{line}");
        assert!(!line.contains("no PR yet"), "{line}");
    }

    #[test]
    fn is_subagent_true_for_either_spelling_of_a_non_empty_agent_id() {
        assert!(is_subagent(r#"{"agent_id":"sub-1"}"#));
        assert!(is_subagent(r#"{"agentId":"sub-1"}"#));
        assert!(!is_subagent(r#"{"agent_id":""}"#));
        assert!(!is_subagent(r#"{"agentId":""}"#));
        assert!(!is_subagent(r#"{"agent_id":null}"#));
        assert!(!is_subagent(r#"{"hook_event_name":"SessionStart"}"#));
        assert!(!is_subagent(""));
        assert!(!is_subagent("not json"));
    }
}
