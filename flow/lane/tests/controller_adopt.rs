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

/// This test process as the adopting session.
fn adopter(f: &Fixture) -> (String, String) {
    let pid = std::process::id() as i32;
    f.live_session_at(pid, "controller-50", "sid-adopter");
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
    // Each `sh` records its adopt's exit status and then parks again: a
    // session that exited would be a dead controller, rightly adoptable by
    // the other, so both stay alive until both results are read. The lock
    // that makes one of them lose is witnessed in `workers.rs`'s
    // `adopt_moves_under_the_source_lock_...`; this is the end-to-end outcome.
    use std::io::Write;
    let f = Fixture::new();
    let (primary, ws) = f.repo_with_workspace("scroller", BRANCH);
    let dead = dead_pid().to_string();
    workers::append(&f.home(), &dead, &worker_record(AGENT, BRANCH, &ws, "12345")).unwrap();

    let status: Vec<std::path::PathBuf> = (0..2).map(|i| f.tmp.path().join(format!("adopt-{i}.status"))).collect();
    let mut sessions: Vec<std::process::Child> = status
        .iter()
        .map(|st| {
            cmd(&f, "sh", &primary)
                .args(["-c", r#"read _; "$0" "$1"; echo $? >"$2"; read _"#, env!("CARGO_BIN_EXE_controller-adopt"), AGENT, st.to_str().unwrap()])
                .stdin(Stdio::piped())
                .stdout(Stdio::piped())
                .stderr(Stdio::piped())
                .spawn()
                .unwrap()
        })
        .collect();
    let pids: Vec<String> = sessions.iter().map(|c| c.id().to_string()).collect();
    for (i, c) in sessions.iter().enumerate() {
        f.live_session_at(c.id() as i32, &format!("adopter-{i}"), &format!("sid-{i}"));
    }
    let mut stdins: Vec<std::process::ChildStdin> = sessions.iter_mut().map(|c| c.stdin.take().unwrap()).collect();
    for s in &mut stdins {
        s.write_all(b"go\n").unwrap();
    }
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(30);
    let codes: Vec<String> = status
        .iter()
        .map(|st| loop {
            if let Some(code) = std::fs::read_to_string(st).ok().filter(|c| c.ends_with('\n')) {
                break code.trim().to_string();
            }
            assert!(std::time::Instant::now() < deadline, "an adopt never finished");
            std::thread::sleep(std::time::Duration::from_millis(20));
        })
        .collect();
    let held: Vec<String> = holders(&f).into_iter().map(|(pid, _)| pid).collect();
    drop(stdins);
    let outs: Vec<Output> = sessions.into_iter().map(|c| c.wait_with_output().unwrap()).collect();

    let winners: Vec<usize> = (0..2).filter(|i| codes[*i] == "0").collect();
    assert_eq!(winners.len(), 1, "{codes:?}\n{}\n---\n{}", out_text(&outs[0]), out_text(&outs[1]));
    assert_eq!(held, vec![pids[winners[0]].clone()], "the record lives in the winner's sidecar alone");
}

#[test]
fn adopt_refuses_while_any_live_controller_holds_the_worker_beside_an_orphaned_copy() {
    // A stale copy (pid 1 is alive under another starttime, and its sidecar
    // sorts first) must not be adopted while a live controller holds the
    // same worker: that would be two controllers.
    let f = Fixture::new();
    adopter(&f);
    let (primary, ws) = f.repo_with_workspace("scroller", BRANCH);
    let stale = worker_record(AGENT, BRANCH, &ws, "not-init's-start");
    workers::append(&f.home(), "1", &stale).unwrap();
    let live = LiveProc::start();
    let held = worker_record(AGENT, BRANCH, &ws, &live.proc_start());
    workers::append(&f.home(), &live.pid().to_string(), &held).unwrap();

    let out = adopt(&f, &primary, AGENT);
    assert!(!out.status.success(), "{}", out_text(&out));
    assert!(out_text(&out).contains(&format!("controller, pid {}, is alive", live.pid())), "{}", out_text(&out));
    let mut got = holders(&f);
    got.sort_by(|a, b| a.0.cmp(&b.0));
    assert_eq!(got, vec![("1".to_string(), stale), (live.pid().to_string(), held)], "nothing moved");
}

#[test]
fn adopting_again_a_worker_this_session_already_controls_says_so_and_succeeds() {
    // #1098 review C2: the second run is not "another controller is alive" —
    // that controller is this session.
    let f = Fixture::new();
    let (own_pid, _) = adopter(&f);
    let (primary, ws) = f.repo_with_workspace("scroller", BRANCH);
    workers::append(&f.home(), &dead_pid().to_string(), &worker_record(AGENT, BRANCH, &ws, "12345")).unwrap();
    assert!(adopt(&f, &primary, AGENT).status.success());

    let out = adopt(&f, &primary, AGENT);
    assert!(out.status.success(), "{}", out_text(&out));
    assert!(stdout(&out).contains("this session already controls scroller-345"), "{}", out_text(&out));
    let held: Vec<String> = holders(&f).into_iter().map(|(pid, _)| pid).collect();
    assert_eq!(held, vec![own_pid]);
}

#[test]
fn adopt_refuses_before_moving_anything_when_herdr_cannot_be_asked() {
    // #1098 review S1: a failed listing is not "no herdr agent" — re-pointing
    // the worker at the session name then would brief an address a restart
    // ages, silently (implement-dispatch refuses the same case).
    let f = Fixture::new();
    adopter(&f);
    let (primary, ws) = f.repo_with_workspace("scroller", BRANCH);
    let dead = dead_pid().to_string();
    let record = worker_record(AGENT, BRANCH, &ws, "12345");
    workers::append(&f.home(), &dead, &record).unwrap();

    let out = cmd(&f, env!("CARGO_BIN_EXE_controller-adopt"), &primary).arg(AGENT).env("HERDR_LIST_FAIL", "true").output().unwrap();
    assert!(!out.status.success(), "{}", out_text(&out));
    assert!(out_text(&out).contains("herdr agent list failed"), "{}", out_text(&out));
    assert_eq!(holders(&f), vec![(dead, record)], "nothing moved");
}

#[test]
fn adopt_never_reaches_a_same_named_worker_under_another_checkout() {
    // #1098 review C6: only a workspace under this primary checkout is this
    // session's to adopt; another repo's orphan with the same agent name
    // stays where it is.
    let f = Fixture::new();
    adopter(&f);
    let (primary, _) = f.repo_with_workspace("scroller", BRANCH);
    let (_, elsewhere) = f.repo_with_workspace("other", BRANCH);
    let dead = dead_pid().to_string();
    let record = worker_record(AGENT, BRANCH, &elsewhere, "12345");
    workers::append(&f.home(), &dead, &record).unwrap();

    let out = adopt(&f, &primary, AGENT);
    assert!(!out.status.success(), "{}", out_text(&out));
    assert!(out_text(&out).contains("no worker record names scroller-345 under"), "{}", out_text(&out));
    assert_eq!(holders(&f), vec![(dead, record)], "nothing moved");
}

#[test]
fn an_adopt_killed_after_landing_leaves_the_worker_with_its_adopter_and_offered_to_no_one() {
    // #1098 Codex [high]: a process death mid-adopt must never strand the
    // worker in neither sidecar. The record lands in the adopter's sidecar
    // before it leaves the dead one, so a kill in between leaves a
    // duplicate: the adopter's copy restores, and the dead copy is inert,
    // neither offered nor adoptable while the adopter lives. The kill is a
    // real SIGABRT from the debug-build failpoint at exactly that window.
    let f = Fixture::new();
    let (own_pid, own_start) = adopter(&f);
    let (primary, ws) = f.repo_with_workspace("scroller", BRANCH);
    let dead = dead_pid().to_string();
    let record = worker_record(AGENT, BRANCH, &ws, "12345");
    workers::append(&f.home(), &dead, &record).unwrap();

    let out = cmd(&f, env!("CARGO_BIN_EXE_controller-adopt"), &primary)
        .arg(AGENT)
        .env("LANE_ADOPT_ABORT_AFTER_LANDING", "1")
        .output()
        .unwrap();
    use std::os::unix::process::ExitStatusExt;
    assert_eq!(out.status.signal(), Some(6), "the adopt must die at the failpoint: {}", out_text(&out));
    let mut got = holders(&f);
    got.sort_by(|a, b| a.0.cmp(&b.0));
    let mut expected = vec![(dead.clone(), record), (own_pid.clone(), worker_record(AGENT, BRANCH, &ws, &own_start))];
    expected.sort_by(|a, b| a.0.cmp(&b.0));
    assert_eq!(got, expected, "killed between landing and removal: a duplicate, never nothing");

    let text = stdout(&restore(&f, &primary));
    assert!(text.contains("You control implement-345 (scroller-345"), "the adopter restores it: {text}");
    assert!(!text.contains("Orphaned"), "the dead copy is not offered while its adopter lives: {text}");
    let again = adopt(&f, &primary, AGENT);
    assert!(stdout(&again).contains("this session already controls scroller-345"), "{}", out_text(&again));
    // The killed run printed nothing, so the retry is the only place the
    // worker's re-point message can come from (#1098 second Codex pass).
    assert!(stdout(&again).contains("Your controller is now controller-50"), "{}", out_text(&again));
}
