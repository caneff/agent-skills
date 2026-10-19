//! Contract tests for `resolve-controller` (#923): a herdr agent name is
//! resolved to the live Claude session name at send time, through the fake
//! `herdr agent list` and a scratch `~/.claude/sessions`.

mod support;
use std::os::unix::net::UnixListener;
use support::{out_text, Fixture};

fn resolve(f: &Fixture, arg: &str) -> std::process::Output {
    resolve_with_env(f, arg, &[])
}

/// The one place that builds the `resolve-controller` `Command`: every test
/// that needs an extra environment variable (`HERDR_LIST_FAIL`, say) adds it
/// here instead of re-inlining the base environment (#1011 V1).
fn resolve_with_env(f: &Fixture, arg: &str, extra_env: &[(&str, &str)]) -> std::process::Output {
    let mut cmd = std::process::Command::new(env!("CARGO_BIN_EXE_resolve-controller"));
    cmd.arg(arg)
        .env_clear()
        .env("PATH", f.path_env())
        .env("HOME", f.home())
        .env("CALL_LOG", f.call_log())
        .env("HERDR_AGENTS", f.agents_file());
    for (k, v) in extra_env {
        cmd.env(k, v);
    }
    cmd.output().unwrap()
}

/// This test process stands in for the live session `name` / `id`, with its
/// messaging socket listening: the returned listener is the session's inbox.
fn live_session(f: &Fixture, id: &str, name: &str) -> UnixListener {
    let sock = f.tmp.path().join("cc-socks").join("controller.sock");
    std::fs::create_dir_all(sock.parent().unwrap()).unwrap();
    let _ = std::fs::remove_file(&sock);
    let listener = UnixListener::bind(&sock).unwrap();
    write_session(f, id, name, Some(&sock));
    listener
}

/// The session record alone, `socket` being its `messagingSocketPath` or none.
fn write_session(f: &Fixture, id: &str, name: &str, socket: Option<&std::path::Path>) {
    let pid = std::process::id() as i32;
    let stat = lane::proc_info::read_stat(pid).unwrap();
    std::fs::create_dir_all(f.home().join(".claude/sessions")).unwrap();
    let socket = socket.map_or(String::new(), |s| format!(r#","messagingSocketPath":"{}""#, s.display()));
    std::fs::write(
        f.session_file(),
        format!(r#"{{"pid":{pid},"sessionId":"{id}","procStart":"{}","name":"{name}"{socket}}}"#, stat.start),
    )
    .unwrap();
}

fn stdout(out: &std::process::Output) -> String {
    String::from_utf8_lossy(&out.stdout).trim().to_string()
}

#[test]
fn a_herdr_agent_name_resolves_to_the_sessions_current_name() {
    let f = Fixture::new();
    f.set_agents(r#"[{"name":"skills-dc","agent_session":{"value":"sid-1"}}]"#);
    let _inbox = live_session(&f, "sid-1", "controller-50");
    let out = resolve(&f, "skills-dc");
    assert!(out.status.success(), "{}", out_text(&out));
    assert_eq!(stdout(&out), "controller-50");
}

#[test]
fn the_same_agent_resolves_to_the_new_name_after_a_restart_renames_the_session() {
    let f = Fixture::new();
    f.set_agents(r#"[{"name":"skills-dc","agent_session":{"value":"sid-1"}}]"#);
    let _a = live_session(&f, "sid-1", "controller-47");
    assert_eq!(stdout(&resolve(&f, "skills-dc")), "controller-47");
    let _b = live_session(&f, "sid-1", "controller-50");
    assert_eq!(stdout(&resolve(&f, "skills-dc")), "controller-50");
}

#[test]
fn a_session_name_a_live_session_bears_resolves_to_itself() {
    let f = Fixture::new();
    let _inbox = live_session(&f, "sid-1", "skills-ctl");
    let out = resolve(&f, "skills-ctl");
    assert!(out.status.success(), "{}", out_text(&out));
    assert_eq!(stdout(&out), "skills-ctl");
}

#[test]
fn an_agent_whose_session_is_not_live_is_an_error_not_a_guess() {
    let f = Fixture::new();
    f.set_agents(r#"[{"name":"skills-dc","agent_session":{"value":"sid-gone"}}]"#);
    let _inbox = live_session(&f, "sid-1", "controller-50");
    let out = resolve(&f, "skills-dc");
    assert!(!out.status.success() && stdout(&out).is_empty(), "{}", out_text(&out));
}

#[test]
fn a_name_that_is_neither_an_agent_nor_a_live_session_is_an_error() {
    let f = Fixture::new();
    let _inbox = live_session(&f, "sid-1", "controller-50");
    let out = resolve(&f, "controller-47");
    assert!(!out.status.success() && stdout(&out).is_empty(), "{}", out_text(&out));
}

#[test]
fn an_unnamed_agent_is_not_addressable_by_its_kind() {
    let f = Fixture::new();
    f.set_agents(r#"[{"agent":"claude","agent_session":{"value":"sid-1"}}]"#);
    let _inbox = live_session(&f, "sid-1", "controller-50");
    let out = resolve(&f, "claude");
    assert!(!out.status.success(), "{}", out_text(&out));
}

#[test]
fn a_failed_agent_listing_is_reported_as_such_and_never_falls_through_to_a_session_name() {
    let f = Fixture::new();
    let _inbox = live_session(&f, "sid-1", "skills-dc");
    let out = resolve_with_env(&f, "skills-dc", &[("HERDR_LIST_FAIL", "true")]);
    assert!(!out.status.success() && stdout(&out).is_empty(), "{}", out_text(&out));
    assert!(String::from_utf8_lossy(&out.stderr).contains("herdr agent list failed"), "{}", out_text(&out));
}

#[test]
fn a_controller_whose_socket_accepts_connections_resolves_and_is_sent_nothing() {
    let f = Fixture::new();
    let inbox = live_session(&f, "sid-1", "skills-ctl");
    let out = resolve(&f, "skills-ctl");
    assert!(out.status.success(), "{}", out_text(&out));
    // The check connected, and wrote nothing before closing: a ping would cost
    // the controller a turn (#1540).
    inbox.set_nonblocking(true).unwrap();
    let (mut conn, _) = inbox.accept().expect("resolve-controller never connected to the socket");
    conn.set_nonblocking(false).unwrap();
    let mut got = Vec::new();
    std::io::Read::read_to_end(&mut conn, &mut got).unwrap();
    assert!(got.is_empty(), "resolve-controller sent {got:?} to the socket");
}

#[test]
fn a_live_record_with_no_socket_path_is_unreachable_and_says_so() {
    let f = Fixture::new();
    write_session(&f, "sid-1", "skills-ctl", None);
    let out = resolve(&f, "skills-ctl");
    assert_eq!(out.status.code(), Some(1), "{}", out_text(&out));
    assert!(stdout(&out).is_empty(), "{}", out_text(&out));
    let err = String::from_utf8_lossy(&out.stderr);
    // The ruling asks for the path: with no socket key, the record file is the path there is.
    let record = format!("{}.json", std::process::id());
    assert!(err.contains("messagingSocketPath") && err.contains(&record), "{err}");
}

#[test]
fn a_socket_directory_that_moved_is_unreachable_and_names_the_path_and_error() {
    let f = Fixture::new();
    let gone = f.tmp.path().join("cc-socks-moved/controller.sock");
    write_session(&f, "sid-1", "skills-ctl", Some(&gone));
    let out = resolve(&f, "skills-ctl");
    assert_eq!(out.status.code(), Some(1), "{}", out_text(&out));
    assert!(stdout(&out).is_empty(), "{}", out_text(&out));
    let err = String::from_utf8_lossy(&out.stderr);
    assert!(err.contains(&gone.display().to_string()) && err.contains("No such file"), "{err}");
}

#[test]
fn a_stale_socket_file_nobody_listens_on_is_unreachable() {
    let f = Fixture::new();
    // Bound, then the listener dropped: the file stays and refuses connections,
    // which an existence check would pass.
    let sock = f.tmp.path().join("cc-socks").join("controller.sock");
    drop(live_session(&f, "sid-1", "skills-dc"));
    assert!(sock.exists());
    f.set_agents(r#"[{"name":"skills-ctl","agent_session":{"value":"sid-1"}}]"#);
    let out = resolve(&f, "skills-ctl");
    assert_eq!(out.status.code(), Some(1), "{}", out_text(&out));
    assert!(stdout(&out).is_empty(), "{}", out_text(&out));
    let err = String::from_utf8_lossy(&out.stderr);
    assert!(err.contains(&sock.display().to_string()) && err.contains("refused"), "{err}");
}
