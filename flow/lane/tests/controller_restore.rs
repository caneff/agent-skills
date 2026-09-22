//! Contract tests for `controller-restore` (#1042, filed from #964's spec
//! axis): the only tests `controller-restore` had before this were unit
//! tests on its pure helpers (`restore_line`, `describe_pr`,
//! `parse_pr_status`, `is_subagent`, `agent_status`) — `main()` itself, the
//! `is_subagent` stdin-JSON gate, `find_own_pid` resolution, and the real
//! `herdr`/`gh` subprocess invocations were never exercised. These tests run
//! the real binary as a subprocess against the fake `gh`/`herdr` from
//! `lane-fake` and a scratch `~/.claude/sessions`, the same seam
//! `resolve_controller.rs` and `merge_cleanup.rs` test at.

mod support;
use support::{out_text, Fixture};

/// This test process stands in for the resuming controller session — the
/// binary under test is spawned as this process's child, so
/// `parent_pid(self_pid)` inside it resolves to this process's own pid, and
/// that pid's session file is what `find_own_pid`'s ancestor walk must find
/// (the same trick `resolve_controller.rs`'s `live_session` uses).
fn live_session(f: &Fixture, name: &str) {
    let pid = std::process::id() as i32;
    let stat = lane::proc_info::read_stat(pid).unwrap();
    std::fs::create_dir_all(f.home().join(".claude/sessions")).unwrap();
    std::fs::write(
        f.session_file(),
        format!(r#"{{"pid":{pid},"sessionId":"sid-1","procStart":"{}","name":"{name}"}}"#, stat.start),
    )
    .unwrap();
}

/// This test process's own real `/proc/<pid>/stat` starttime — what a fresh
/// `WorkerRecord.proc_start` must carry to survive `drop_stale`.
fn own_start() -> String {
    let pid = std::process::id() as i32;
    lane::proc_info::read_stat(pid).unwrap().start
}

fn worker(branch: &str, agent: &str, proc_start: &str) -> lane::workers::WorkerRecord {
    lane::workers::WorkerRecord {
        agent: agent.into(),
        tickets: vec!["1042".into()],
        branch: branch.into(),
        workspace: format!("/repo/.claude/worktrees/{branch}"),
        repo: "caneff/agent-skills".into(),
        cleanup: format!("cd /repo && merge-cleanup {branch} --repo /repo"),
        chris_merges: false,
        dispatched_at: "2026-09-22T00:00:00Z".into(),
        proc_start: proc_start.into(),
    }
}

/// Appends `record` under this test process's own session pid — the pid
/// `find_own_pid` will resolve to.
fn append_worker(f: &Fixture, record: &lane::workers::WorkerRecord) {
    let pid = std::process::id().to_string();
    lane::workers::append(&f.home(), &pid, record).unwrap();
}

/// Runs the real binary with `stdin` on its stdin and `extra_env` layered
/// over a base env that always carries `GH_PR_STATUS` (#1042 review, S5):
/// every test goes through the new `gh pr list --json number,state` fake by
/// default, not only the three that used to opt in — the no-PR tests below
/// exercise its missing-file branch precisely because nothing wrote into
/// `pr_status_dir()` for their branch (P1: this is what makes "no PR yet"
/// mean the new fake's own "nothing recorded" case, not a fallback to a
/// different fake entirely).
fn run(f: &Fixture, stdin: &str, extra_env: &[(&str, &str)]) -> std::process::Output {
    use std::io::Write;
    let mut cmd = std::process::Command::new(env!("CARGO_BIN_EXE_controller-restore"));
    cmd.env_clear()
        .env("PATH", f.path_env())
        .env("HOME", f.home())
        .env("CALL_LOG", f.call_log())
        .env("HERDR_AGENTS", f.agents_file())
        .env("GH_PR_STATUS", f.pr_status_dir())
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped());
    for (k, v) in extra_env {
        cmd.env(k, v);
    }
    let mut child = cmd.spawn().unwrap();
    child.stdin.take().unwrap().write_all(stdin.as_bytes()).unwrap();
    child.wait_with_output().unwrap()
}

fn stdout(out: &std::process::Output) -> String {
    String::from_utf8_lossy(&out.stdout).trim().to_string()
}

// --- silent when there is nothing to restore ---------------------------------

#[test]
fn no_session_start_hook_json_and_no_workers_file_is_silent() {
    let f = Fixture::new();
    live_session(&f, "controller-50");
    let out = run(&f, r#"{"hook_event_name":"SessionStart"}"#, &[]);
    assert!(out.status.success(), "{}", out_text(&out));
    assert_eq!(stdout(&out), "", "a session that never dispatched a worker must print nothing");
}

#[test]
fn a_session_record_whose_procstart_does_not_match_is_never_resolved_as_this_sessions_own() {
    // #1042 review, C1 (correctness, CONFIRMED): the test above is silent
    // whether or not `find_own_pid`'s ancestor walk ever succeeds — a
    // session that never dispatched a worker and a session `find_own_pid`
    // fails to resolve both print nothing, so that test alone cannot tell
    // the two apart, and stripping the match check would leave it green
    // (defect-classes class 1). This one plants a worker record under this
    // pid, then a session record for the same pid whose `procStart` does
    // not match — a mismatch that must make `find_own_pid` fail to resolve
    // it, so the record's existence must never leak into the printed line.
    let f = Fixture::new();
    let pid = std::process::id() as i32;
    std::fs::create_dir_all(f.home().join(".claude/sessions")).unwrap();
    std::fs::write(
        f.session_file(),
        format!(r#"{{"pid":{pid},"sessionId":"sid-1","procStart":"not-the-real-start","name":"controller-50"}}"#),
    )
    .unwrap();
    f.set_agents(r#"[{"name":"sudokupad-art-1042","agent_status":"working"}]"#);
    append_worker(&f, &worker("implement-1042", "sudokupad-art-1042", &own_start()));
    let out = run(&f, "{}", &[]);
    assert!(out.status.success(), "{}", out_text(&out));
    assert_eq!(
        stdout(&out),
        "",
        "a session record whose procStart does not match this pid's own /proc/<pid>/stat must never be treated as this session's own"
    );
}

#[test]
fn a_subagents_own_session_start_is_silent_even_with_workers_present() {
    let f = Fixture::new();
    live_session(&f, "controller-50");
    append_worker(&f, &worker("implement-1042", "sudokupad-art-1042", &own_start()));
    let out = run(&f, r#"{"agent_id":"sub-1"}"#, &[]);
    assert!(out.status.success(), "{}", out_text(&out));
    assert_eq!(stdout(&out), "", "a subagent's own SessionStart controls nothing of its own to restore");
}

// --- a fresh worker record is restored ----------------------------------------

#[test]
fn a_worker_with_no_pr_yet_and_a_live_agent_prints_the_restore_line() {
    let f = Fixture::new();
    live_session(&f, "controller-50");
    f.set_agents(r#"[{"name":"sudokupad-art-1042","agent_status":"working"}]"#);
    append_worker(&f, &worker("implement-1042", "sudokupad-art-1042", &own_start()));
    let out = run(&f, "{}", &[]);
    assert!(out.status.success(), "{}", out_text(&out));
    let line = stdout(&out);
    assert!(line.contains("You control implement-1042 (sudokupad-art-1042, agent working)"), "{line}");
    assert!(line.contains("no PR yet — check on the worker"), "{line}");
    assert!(line.contains("cleanup: cd /repo && merge-cleanup implement-1042 --repo /repo"), "{line}");
}

#[test]
fn a_stale_worker_record_from_a_reused_pid_is_dropped_and_reported() {
    let f = Fixture::new();
    live_session(&f, "controller-50");
    append_worker(&f, &worker("implement-1042", "sudokupad-art-1042", "not-this-sessions-start"));
    let out = run(&f, "{}", &[]);
    assert!(out.status.success(), "{}", out_text(&out));
    let line = stdout(&out);
    assert!(line.contains("dropped 1 stale worker record"), "{line}");
    assert!(!line.contains("You control"), "a stale record must never be restored: {line}");
}

// --- gh pr list's OPEN/MERGED/CLOSED/no-PR branches, through the real binary --

#[test]
fn an_open_pr_is_reported_with_the_merge_pointer() {
    let f = Fixture::new();
    live_session(&f, "controller-50");
    f.set_agents(r#"[{"name":"sudokupad-art-1042","agent_status":"working"}]"#);
    append_worker(&f, &worker("implement-1042", "sudokupad-art-1042", &own_start()));
    f.set_pr_status("implement-1042", "152 OPEN");
    let out = run(&f, "{}", &[]);
    assert!(out.status.success(), "{}", out_text(&out));
    let line = stdout(&out);
    assert!(line.contains("PR #152 open, not merged — follow implement/SKILL.md \u{a7} The merge"), "{line}");
    // #1042 review, P2/C3: the output assertion above can't tell a right
    // answer from a lucky one if the invocation itself drifts — check the
    // actual argv the real gh/herdr calls carried, not only what they
    // printed back.
    let calls = f.calls();
    assert!(calls.contains("herdr agent list"), "{calls}");
    assert!(
        calls.contains("gh pr list --repo caneff/agent-skills --head implement-1042 --state all --json number,state"),
        "{calls}"
    );
}

#[test]
fn a_merged_pr_is_reported_as_run_cleanup() {
    let f = Fixture::new();
    live_session(&f, "controller-50");
    f.set_agents(r#"[{"name":"sudokupad-art-1042","agent_status":"working"}]"#);
    append_worker(&f, &worker("implement-1042", "sudokupad-art-1042", &own_start()));
    f.set_pr_status("implement-1042", "152 MERGED");
    let out = run(&f, "{}", &[]);
    assert!(out.status.success(), "{}", out_text(&out));
    assert!(stdout(&out).contains("PR #152 merged — run cleanup"), "{}", stdout(&out));
}

#[test]
fn a_closed_pr_is_reported_as_such() {
    let f = Fixture::new();
    live_session(&f, "controller-50");
    f.set_agents(r#"[{"name":"sudokupad-art-1042","agent_status":"working"}]"#);
    append_worker(&f, &worker("implement-1042", "sudokupad-art-1042", &own_start()));
    f.set_pr_status("implement-1042", "152 CLOSED");
    let out = run(&f, "{}", &[]);
    assert!(out.status.success(), "{}", out_text(&out));
    assert!(stdout(&out).contains("PR #152 closed without merging — check on the worker"), "{}", stdout(&out));
}

// --- a wedged herdr reads as unknown, never as "no live agent" ---------------

#[test]
fn a_failed_herdr_agent_list_reports_unknown_not_no_live_agent() {
    let f = Fixture::new();
    live_session(&f, "controller-50");
    append_worker(&f, &worker("implement-1042", "sudokupad-art-1042", &own_start()));
    let out = run(&f, "{}", &[("HERDR_LIST_FAIL", "true")]);
    assert!(out.status.success(), "{}", out_text(&out));
    let line = stdout(&out);
    assert!(line.contains("herdr status unknown — could not ask herdr"), "{line}");
    assert!(!line.contains("no live herdr agent"), "{line}");
}
