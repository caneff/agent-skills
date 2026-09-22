//! Contract tests for `resolve-controller` (#923): a herdr agent name is
//! resolved to the live Claude session name at send time, through the fake
//! `herdr agent list` and a scratch `~/.claude/sessions`.

mod support;
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

/// This test process stands in for the live session `name` / `id`.
fn live_session(f: &Fixture, id: &str, name: &str) {
    let pid = std::process::id() as i32;
    let stat = lane::proc_info::read_stat(pid).unwrap();
    std::fs::create_dir_all(f.home().join(".claude/sessions")).unwrap();
    std::fs::write(
        f.session_file(),
        format!(r#"{{"pid":{pid},"sessionId":"{id}","procStart":"{}","name":"{name}"}}"#, stat.start),
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
    live_session(&f, "sid-1", "controller-50");
    let out = resolve(&f, "skills-dc");
    assert!(out.status.success(), "{}", out_text(&out));
    assert_eq!(stdout(&out), "controller-50");
}

#[test]
fn the_same_agent_resolves_to_the_new_name_after_a_restart_renames_the_session() {
    let f = Fixture::new();
    f.set_agents(r#"[{"name":"skills-dc","agent_session":{"value":"sid-1"}}]"#);
    live_session(&f, "sid-1", "controller-47");
    assert_eq!(stdout(&resolve(&f, "skills-dc")), "controller-47");
    live_session(&f, "sid-1", "controller-50");
    assert_eq!(stdout(&resolve(&f, "skills-dc")), "controller-50");
}

#[test]
fn a_session_name_a_live_session_bears_resolves_to_itself() {
    let f = Fixture::new();
    live_session(&f, "sid-1", "skills-ctl");
    let out = resolve(&f, "skills-ctl");
    assert!(out.status.success(), "{}", out_text(&out));
    assert_eq!(stdout(&out), "skills-ctl");
}

#[test]
fn an_agent_whose_session_is_not_live_is_an_error_not_a_guess() {
    let f = Fixture::new();
    f.set_agents(r#"[{"name":"skills-dc","agent_session":{"value":"sid-gone"}}]"#);
    live_session(&f, "sid-1", "controller-50");
    let out = resolve(&f, "skills-dc");
    assert!(!out.status.success() && stdout(&out).is_empty(), "{}", out_text(&out));
}

#[test]
fn a_name_that_is_neither_an_agent_nor_a_live_session_is_an_error() {
    let f = Fixture::new();
    live_session(&f, "sid-1", "controller-50");
    let out = resolve(&f, "controller-47");
    assert!(!out.status.success() && stdout(&out).is_empty(), "{}", out_text(&out));
}

#[test]
fn an_unnamed_agent_is_not_addressable_by_its_kind() {
    let f = Fixture::new();
    f.set_agents(r#"[{"agent":"claude","agent_session":{"value":"sid-1"}}]"#);
    live_session(&f, "sid-1", "controller-50");
    let out = resolve(&f, "claude");
    assert!(!out.status.success(), "{}", out_text(&out));
}

#[test]
fn a_failed_agent_listing_is_reported_as_such_and_never_falls_through_to_a_session_name() {
    let f = Fixture::new();
    live_session(&f, "sid-1", "skills-dc");
    let out = resolve_with_env(&f, "skills-dc", &[("HERDR_LIST_FAIL", "true")]);
    assert!(!out.status.success() && stdout(&out).is_empty(), "{}", out_text(&out));
    assert!(String::from_utf8_lossy(&out.stderr).contains("herdr agent list failed"), "{}", out_text(&out));
}
