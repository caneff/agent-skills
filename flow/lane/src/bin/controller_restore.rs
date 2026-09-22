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
use std::time::{Duration, Instant};

/// The single deadline every query this run makes shares (#964 fix round 1,
/// Codex medium), kept under the hook's own 15s timeout in
/// `flow/claude/settings.json` — the old fixed 10s-per-call budget (one herdr
/// call plus one gh call per worker) could outlive that timeout with two or
/// more workers, and the hook's `|| true` swallowed the kill silently.
const HOOK_BUDGET: Duration = Duration::from_secs(12);

/// The rest of `deadline`, or `None` once it has passed.
fn time_left(deadline: Instant) -> Option<Duration> {
    let now = Instant::now();
    (deadline > now).then(|| deadline - now)
}

/// What running `program` came to, budgeted against a shared `deadline`
/// (#964 fix round 1, Codex medium): `NoBudget` means the deadline was
/// already gone and the process was never started at all — kept distinct
/// from `Ran(None)`, which means it started, and either failed or ran out
/// the OS-level timeout given the time that was left. Conflating the two
/// would print a worker whose query never ran the same as one whose query
/// ran and got nothing, which is what `describe_agent`/`describe_pr`'s
/// `unchecked` wording exists not to do.
#[derive(Debug)]
enum Budgeted {
    Ran(Option<String>),
    NoBudget,
}

fn call_budgeted(deadline: Instant, program: &str, args: &[&str]) -> Budgeted {
    match time_left(deadline) {
        Some(budget) => Budgeted::Ran(quiet_stdout_timeout(program, args, budget)),
        None => Budgeted::NoBudget,
    }
}

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
/// none", "could not be asked at all" (off PATH, timed out, unparseable
/// output), or "never asked at all" (the shared deadline was already gone —
/// #964 fix round 1, Codex medium). No two of these may ever print the same:
/// conflating `Unknown` and `Answered(None)` was #964's own correctness-axis
/// C2/standards-axis S1 finding — a wedged herdr made every worker read "no
/// live herdr agent" as if that were a fact about the agent rather than about
/// herdr — and conflating `Unchecked` with either would make a worker whose
/// query never ran under a blown budget look like one that ran and answered.
enum Asked<T> {
    Answered(T),
    Unknown,
    Unchecked,
}

/// herdr's answer to "is `name`'s agent alive, and what's its status" —
/// `Answered(None)` is a real "no such agent"; `Unknown` is "herdr could not
/// be asked"; `Unchecked` is "herdr was never asked, the budget was gone".
fn agent_status<'a>(agents: &'a Asked<Vec<Agent>>, name: &str) -> Asked<Option<&'a str>> {
    match agents {
        Asked::Unknown => Asked::Unknown,
        Asked::Unchecked => Asked::Unchecked,
        Asked::Answered(agents) => Asked::Answered(agents.iter().find(|a| a.name() == name).map(Agent::status)),
    }
}

/// What to say about a worker's herdr agent.
fn describe_agent(agent: &str, status: &Asked<Option<&str>>) -> String {
    match status {
        Asked::Unknown => format!("{agent}, herdr status unknown — could not ask herdr"),
        Asked::Unchecked => format!("{agent}, herdr status unchecked — the restore hook's time budget ran out"),
        Asked::Answered(Some(s)) => format!("{agent}, agent {s}"),
        Asked::Answered(None) => format!("{agent}, no live herdr agent"),
    }
}

/// What to say about a worker's PR: the state, and the guidance that follows
/// from it. `Answered(None)` is "no PR yet" — the worker may still be
/// building; `Unknown` is "gh could not be asked"; `Unchecked` is "gh was
/// never asked, the budget was gone" — each worded distinctly.
fn describe_pr(pr: &Asked<Option<PrStatus>>) -> String {
    match pr {
        Asked::Unknown => "PR status unknown — could not ask gh".to_string(),
        Asked::Unchecked => "PR status unchecked — the restore hook's time budget ran out".to_string(),
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

/// One line for a worker whose controller at `pid` is gone (#1098), naming
/// the command that makes this session its controller.
fn orphan_line(pid: &str, record: &WorkerRecord) -> String {
    format!(
        "Orphaned worker {} ({}): its controller, pid {pid}, is gone — adopt it with: controller-adopt {}",
        record.branch, record.agent, record.agent
    )
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

/// Splits `records` into (fresh, stale count) by `WorkerRecord::proc_start`
/// against `own_start`, the resuming session's own `/proc/<pid>/stat`
/// starttime (#964 fix round 1, Codex high). Pids are small and get reused,
/// especially across a WSL restart, so a `<pid>.workers.jsonl` left behind by
/// a dead controller would otherwise restore its workers into whatever
/// unrelated session now holds that pid. A record with no `proc_start`
/// (written before this field existed) or one recorded under `own_start`
/// itself unknown (the resuming session's own starttime could not be read)
/// never counts as fresh either — the conservative direction, since
/// restoring a stale worker's state into the wrong session is worse than
/// restoring nothing.
fn drop_stale(records: Vec<WorkerRecord>, own_start: &str) -> (Vec<WorkerRecord>, usize) {
    let (fresh, stale): (Vec<WorkerRecord>, Vec<WorkerRecord>) =
        records.into_iter().partition(|r| !own_start.is_empty() && r.proc_start == own_start);
    (fresh, stale.len())
}

fn ask_agents(deadline: Instant) -> Asked<Vec<Agent>> {
    match call_budgeted(deadline, "herdr", &["agent", "list"]) {
        Budgeted::NoBudget => Asked::Unchecked,
        Budgeted::Ran(Some(out)) => match herdr::parse_agents(&out) {
            Some(agents) => Asked::Answered(agents),
            None => Asked::Unknown,
        },
        Budgeted::Ran(None) => Asked::Unknown,
    }
}

fn ask_pr(repo: &str, branch: &str, deadline: Instant) -> Asked<Option<PrStatus>> {
    match call_budgeted(
        deadline,
        "gh",
        &["pr", "list", "--repo", repo, "--head", branch, "--state", "all", "--json", "number,state", "--jq", r#".[0] // empty | "\(.number) \(.state)""#, "--limit", "1"],
    ) {
        Budgeted::NoBudget => Asked::Unchecked,
        Budgeted::Ran(Some(out)) => Asked::Answered(parse_pr_status(&out)),
        Budgeted::Ran(None) => Asked::Unknown,
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

    // #1098: a dead controller's workers, offered to this session when their
    // workspaces sit under its cwd. Printed only; `controller-adopt` does the
    // move.
    let cwd = std::env::current_dir().map(|p| p.display().to_string()).unwrap_or_default();
    if !cwd.is_empty() {
        let cwd = workers::canonical_workspace_path(&cwd);
        for (pid, record) in workers::orphans(home).iter().filter(|(_, r)| sessions::in_tree(&r.workspace, &cwd)) {
            safe_println!("{}", orphan_line(pid, record));
        }
    }

    let records = workers::read(home, &own_pid);
    if records.is_empty() {
        return;
    }
    // #964 fix round 1 (Codex high): `find_own_pid` already proved `own_pid`
    // alive with a matching starttime, so re-reading it here gets the exact
    // string every fresh record must carry — a pid whose `/proc` entry is
    // gone between that check and this one reads as `own_start` empty, which
    // `drop_stale` treats as "prove nothing", not "trust everything".
    let own_start = own_pid.parse::<i32>().ok().and_then(proc_info::read_stat).map(|s| s.start).unwrap_or_default();
    let (records, dropped) = drop_stale(records, &own_start);
    if dropped > 0 {
        safe_println!("dropped {dropped} stale worker record(s): recorded under a pid this session does not own");
    }
    if records.is_empty() {
        return;
    }

    // One deadline shared across every query below (#964 fix round 1, Codex
    // medium), not a fixed timeout per call: the hook's own 15s timeout in
    // flow/claude/settings.json is shorter than one herdr call plus one gh
    // call per worker at the old fixed 10s each, so two or more workers
    // could get killed mid-output with the failure hidden behind `|| true`.
    let deadline = Instant::now() + HOOK_BUDGET;
    let agents = ask_agents(deadline);

    for record in &records {
        let status = agent_status(&agents, &record.agent);
        let pr = ask_pr(&record.repo, &record.branch, deadline);
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
            proc_start: "1000".into(),
        }
    }

    #[test]
    fn call_budgeted_returns_no_budget_without_running_the_command_when_the_deadline_has_passed() {
        // #964 fix round 1 (Codex medium): the hook's own 15s timeout is
        // shorter than the sum of one herdr call plus one gh call per
        // worker at the old fixed 10s each, so two workers on a slow gh
        // could be killed mid-output. A single shared deadline instead: a
        // query whose budget is already gone must never even start — proven
        // here by pointing it at a command that would sleep for 5s and
        // checking it returns almost instantly, not after (most of) that 5s.
        std::thread::sleep(Duration::from_millis(5));
        let past = Instant::now() - Duration::from_millis(1);
        let start = Instant::now();
        let result = call_budgeted(past, "sleep", &["5"]);
        assert!(matches!(result, Budgeted::NoBudget), "expected NoBudget");
        assert!(start.elapsed() < Duration::from_millis(500), "a 5s sleep must never have been spawned once the deadline had passed");
    }

    #[test]
    fn call_budgeted_runs_with_whatever_time_remains_and_reports_ran_none_on_a_timeout() {
        let deadline = Instant::now() + Duration::from_millis(200);
        let result = call_budgeted(deadline, "sleep", &["5"]);
        assert!(matches!(result, Budgeted::Ran(None)), "a command that outlives its own share of the budget ran, and gave nothing back — distinct from never having run at all");
    }

    #[test]
    fn call_budgeted_runs_and_returns_output_when_there_is_time() {
        let deadline = Instant::now() + Duration::from_secs(5);
        let result = call_budgeted(deadline, "printf", &["%s", "hello"]);
        assert!(matches!(result, Budgeted::Ran(Some(ref s)) if s == "hello"), "{result:?}");
    }

    #[test]
    fn ask_agents_reports_unchecked_when_the_shared_deadline_is_already_gone() {
        let past = Instant::now() - Duration::from_millis(1);
        assert!(matches!(ask_agents(past), Asked::Unchecked));
    }

    #[test]
    fn describe_agent_and_describe_pr_word_unchecked_distinctly_from_unknown() {
        let agent_line = describe_agent("a", &Asked::Unchecked);
        assert!(agent_line.contains("unchecked"), "{agent_line}");
        assert_ne!(agent_line, describe_agent("a", &Asked::Unknown));
        let pr_line = describe_pr(&Asked::Unchecked);
        assert!(pr_line.contains("unchecked"), "{pr_line}");
        assert_ne!(pr_line, describe_pr(&Asked::Unknown));
    }

    #[test]
    fn drop_stale_keeps_a_matching_proc_start_and_drops_a_mismatched_or_empty_one() {
        let mut fresh = record();
        fresh.proc_start = "1000".into();
        let mut stale = record();
        stale.proc_start = "999".into(); // a reused pid's earlier, now-dead controller
        let mut pre_fix = record();
        pre_fix.proc_start = String::new(); // written before this field existed
        let (kept, dropped) = drop_stale(vec![fresh.clone(), stale, pre_fix], "1000");
        assert_eq!(kept, vec![fresh]);
        assert_eq!(dropped, 2);
    }

    #[test]
    fn drop_stale_against_an_unknown_own_start_drops_everything() {
        // The resuming session's own starttime could not be read: nothing can
        // be proven fresh, so the conservative reading is to drop it all
        // rather than restore into a session that cannot prove it is the
        // one that dispatched these workers.
        let (kept, dropped) = drop_stale(vec![record()], "");
        assert!(kept.is_empty());
        assert_eq!(dropped, 1);
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
