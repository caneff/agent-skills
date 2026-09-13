//! The fake's own contract: it rejects any subcommand missing from its typed
//! allowlist, exiting non-zero (the #745 lesson — a stub that accepted a
//! herdr subcommand that does not exist hid a command that fails for real).

use std::process::Command;

fn run_as(role: &str, args: &[&str]) -> std::process::Output {
    let tmp = tempfile::tempdir().unwrap();
    let link = tmp.path().join(role);
    std::os::unix::fs::symlink(support_fake_path(), &link).unwrap();
    Command::new(link).args(args).output().unwrap()
}

fn support_fake_path() -> std::path::PathBuf {
    std::path::PathBuf::from(env!("CARGO_BIN_EXE_lane-fake"))
}

#[test]
fn herdr_agent_stop_is_rejected_it_is_not_a_real_subcommand() {
    let out = run_as("herdr", &["agent", "stop", "some-agent"]);
    assert!(!out.status.success(), "herdr agent stop should be refused");
}

#[test]
fn herdr_agent_prompt_is_accepted() {
    let out = run_as("herdr", &["agent", "prompt", "x", "hi"]);
    assert!(out.status.success());
}

#[test]
fn gh_issue_view_is_accepted_and_reports_the_scenario() {
    let tmp = tempfile::tempdir().unwrap();
    let link = tmp.path().join("gh");
    std::os::unix::fs::symlink(support_fake_path(), &link).unwrap();
    let out = Command::new(link)
        .args(["issue", "view", "1", "--repo", "x/y", "--json", "state,labels"])
        .env("GH_STATE", "OPEN")
        .env("GH_LABELS", "ready-for-agent")
        .output()
        .unwrap();
    assert!(out.status.success());
    assert_eq!(String::from_utf8_lossy(&out.stdout).trim(), "OPEN ready-for-agent");
}

#[test]
fn a_nonexistent_gh_noun_is_rejected() {
    let out = run_as("gh", &["frobnicate"]);
    assert!(!out.status.success());
}
