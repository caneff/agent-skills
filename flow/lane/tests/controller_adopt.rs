//! Contract tests for `controller-adopt` (#1098): a live session on the
//! primary checkout takes over a worker whose controller session is gone.
//! The real binary runs as a child of this test process, which stands in
//! for the adopting session (its session record is what `find_own_pid`'s
//! ancestor walk finds), against the fake `herdr` from `lane-fake` and a
//! scratch `~/.claude/sessions` — the `controller_restore.rs` seam.

mod support;
use lane::workers::{self, WorkerRecord};
use std::process::{Command, Output, Stdio};
use support::{dead_pid, out_text, worker_record, Fixture, LiveProc};

const AGENT: &str = "scroller-345";
const BRANCH: &str = "implement-345";

/// Writes `<pid>.json` for a live session, as Claude Code does.
fn session(f: &Fixture, pid: i32, name: &str, session_id: &str) {
    let start = lane::proc_info::read_stat(pid).unwrap().start;
    std::fs::create_dir_all(f.home().join(".claude/sessions")).unwrap();
    std::fs::write(
        f.home().join(".claude/sessions").join(format!("{pid}.json")),
        format!(r#"{{"pid":{pid},"sessionId":"{session_id}","procStart":"{start}","name":"{name}"}}"#),
    )
    .unwrap();
}

/// This test process as the adopting session.
fn adopter(f: &Fixture) -> (String, String) {
    let pid = std::process::id() as i32;
    session(f, pid, "controller-50", "sid-adopter");
    (pid.to_string(), lane::proc_info::read_stat(pid).unwrap().start)
}

fn cmd(f: &Fixture, program: &str, cwd: &str) -> Command {
    let mut c = Command::new(program);
    c.current_dir(cwd)
        .env_clear()
        .env("PATH", f.path_env())
        .env("HOME", f.home())
        .env("CALL_LOG", f.call_log())
        .env("HERDR_AGENTS", f.agents_file())
        .env("GH_PR_STATUS", f.pr_status_dir())
        .stdin(Stdio::null());
    c
}

fn adopt(f: &Fixture, cwd: &str, agent: &str) -> Output {
    cmd(f, env!("CARGO_BIN_EXE_controller-adopt"), cwd).arg(agent).output().unwrap()
}

fn restore(f: &Fixture, cwd: &str) -> Output {
    cmd(f, env!("CARGO_BIN_EXE_controller-restore"), cwd).output().unwrap()
}

fn stdout(out: &Output) -> String {
    String::from_utf8_lossy(&out.stdout).into_owned()
}

/// Every record naming `AGENT`, across every sidecar, as (pid, record).
fn holders(f: &Fixture) -> Vec<(String, WorkerRecord)> {
    let dir = f.home().join(".claude/sessions");
    let mut out = Vec::new();
    for e in std::fs::read_dir(dir).unwrap().filter_map(Result::ok) {
        let name = e.file_name().to_string_lossy().into_owned();
        if let Some(pid) = name.strip_suffix(".workers.jsonl") {
            for r in workers::read(&f.home(), pid).into_iter().filter(|r| r.agent == AGENT) {
                out.push((pid.to_string(), r));
            }
        }
    }
    out
}

#[test]
fn adopt_moves_a_dead_controllers_record_and_a_later_restore_shows_it() {
    let f = Fixture::new();
    let (own_pid, own_start) = adopter(&f);
    f.set_agents(r#"[{"name":"skills-1b","agent_status":"idle","agent_session":{"value":"sid-adopter"}}]"#);
    let (primary, ws) = f.repo_with_workspace("scroller", BRANCH);
    let dead = dead_pid().to_string();
    workers::append(&f.home(), &dead, &worker_record(AGENT, BRANCH, &ws, "12345")).unwrap();

    let out = adopt(&f, &primary, AGENT);
    assert!(out.status.success(), "{}", out_text(&out));
    assert!(stdout(&out).contains("Your controller is now skills-1b"), "{}", out_text(&out));
    let expected = worker_record(AGENT, BRANCH, &ws, &own_start);
    assert_eq!(holders(&f), vec![(own_pid, expected)], "the record leaves the dead sidecar for the adopter's, under its starttime");

    let out = restore(&f, &primary);
    let text = stdout(&out);
    assert!(text.contains("You control implement-345 (scroller-345"), "{}", out_text(&out));
    assert!(!text.contains("Orphaned"), "an adopted worker is no orphan: {text}");
}

#[test]
fn adopt_names_the_session_when_it_has_no_herdr_agent() {
    let f = Fixture::new();
    adopter(&f);
    let (primary, ws) = f.repo_with_workspace("scroller", BRANCH);
    workers::append(&f.home(), &dead_pid().to_string(), &worker_record(AGENT, BRANCH, &ws, "12345")).unwrap();
    let out = adopt(&f, &primary, AGENT);
    assert!(out.status.success(), "{}", out_text(&out));
    assert!(stdout(&out).contains("Your controller is now controller-50"), "{}", out_text(&out));
}

#[test]
fn adopt_refuses_a_worker_whose_controller_is_alive() {
    let f = Fixture::new();
    adopter(&f);
    let (primary, ws) = f.repo_with_workspace("scroller", BRANCH);
    let live = LiveProc::start();
    let record = worker_record(AGENT, BRANCH, &ws, &live.proc_start());
    workers::append(&f.home(), &live.pid().to_string(), &record).unwrap();

    let out = adopt(&f, &primary, AGENT);
    assert!(!out.status.success(), "{}", out_text(&out));
    assert!(out_text(&out).contains(&format!("controller, pid {}, is alive", live.pid())), "{}", out_text(&out));
    assert_eq!(holders(&f), vec![(live.pid().to_string(), record)], "nothing moved");
}

#[test]
fn adopt_takes_a_worker_whose_pid_now_belongs_to_an_unrelated_session() {
    // The pid is alive, but not with the starttime the record was written
    // under: that live process is not the controller, and must not block.
    let f = Fixture::new();
    let (own_pid, _) = adopter(&f);
    let (primary, ws) = f.repo_with_workspace("scroller", BRANCH);
    let reused = LiveProc::start();
    workers::append(&f.home(), &reused.pid().to_string(), &worker_record(AGENT, BRANCH, &ws, "not-its-start")).unwrap();

    let out = adopt(&f, &primary, AGENT);
    assert!(out.status.success(), "{}", out_text(&out));
    let held: Vec<String> = holders(&f).into_iter().map(|(pid, _)| pid).collect();
    assert_eq!(held, vec![own_pid]);
}

#[test]
fn adopt_refuses_off_the_primary_checkout() {
    let f = Fixture::new();
    adopter(&f);
    let (_, ws) = f.repo_with_workspace("scroller", BRANCH);
    let dead = dead_pid().to_string();
    let record = worker_record(AGENT, BRANCH, &ws, "12345");
    workers::append(&f.home(), &dead, &record).unwrap();

    let out = adopt(&f, &ws, AGENT);
    assert!(!out.status.success(), "{}", out_text(&out));
    assert!(out_text(&out).contains("not the primary checkout"), "{}", out_text(&out));
    assert_eq!(holders(&f), vec![(dead, record)], "nothing moved");
}

#[test]
fn adopt_refuses_a_worker_whose_workspace_was_torn_down() {
    let f = Fixture::new();
    adopter(&f);
    let (primary, _) = f.repo_with_workspace("scroller", BRANCH);
    let gone = format!("{primary}/.claude/worktrees/implement-346");
    let dead = dead_pid().to_string();
    let record = worker_record(AGENT, BRANCH, &gone, "12345");
    workers::append(&f.home(), &dead, &record).unwrap();

    let out = adopt(&f, &primary, AGENT);
    assert!(!out.status.success(), "{}", out_text(&out));
    assert!(out_text(&out).contains("torn down"), "{}", out_text(&out));
    assert_eq!(holders(&f), vec![(dead, record)], "nothing moved");
}

#[test]
fn two_sessions_adopting_one_worker_at_once_exactly_one_wins() {
    // Two adopting sessions: a `sh` each, parked on `read` until both have
    // a session record, then released together. `sh` forks the adopt (a
    // command follows it), so each adopt's ancestor walk finds its own `sh`.
    use std::io::Write;
    let f = Fixture::new();
    let (primary, ws) = f.repo_with_workspace("scroller", BRANCH);
    let dead = dead_pid().to_string();
    workers::append(&f.home(), &dead, &worker_record(AGENT, BRANCH, &ws, "12345")).unwrap();

    let mut sessions: Vec<std::process::Child> = (0..2)
        .map(|_| {
            cmd(&f, "sh", &primary)
                .args(["-c", r#"read _; "$0" "$1"; exit $?"#, env!("CARGO_BIN_EXE_controller-adopt"), AGENT])
                .stdin(Stdio::piped())
                .stdout(Stdio::piped())
                .stderr(Stdio::piped())
                .spawn()
                .unwrap()
        })
        .collect();
    let pids: Vec<String> = sessions.iter().map(|c| c.id().to_string()).collect();
    for (i, c) in sessions.iter().enumerate() {
        session(&f, c.id() as i32, &format!("adopter-{i}"), &format!("sid-{i}"));
    }
    for c in &mut sessions {
        c.stdin.take().unwrap().write_all(b"go\n").unwrap();
    }
    let outs: Vec<Output> = sessions.into_iter().map(|c| c.wait_with_output().unwrap()).collect();

    let winners: Vec<usize> = (0..2).filter(|i| outs[*i].status.success()).collect();
    assert_eq!(winners.len(), 1, "{}\n---\n{}", out_text(&outs[0]), out_text(&outs[1]));
    let held: Vec<String> = holders(&f).into_iter().map(|(pid, _)| pid).collect();
    assert_eq!(held, vec![pids[winners[0]].clone()], "the record lives in the winner's sidecar alone");
}
