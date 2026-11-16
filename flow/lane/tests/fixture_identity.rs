//! Tests for the fixture-identity helper (#1728): the refusal path no caller
//! provokes, so neutralising the containment check goes red here.
mod support;

use std::path::Path;
use std::process::Command;
use support::identity::{fixture_identity, try_fixture_identity, EMAIL, NAME};

fn git(repo: &Path, args: &[&str]) -> std::process::Output {
    Command::new("git").arg("-C").arg(repo).args(args).output().expect("run git")
}

fn init(p: &Path) {
    std::fs::create_dir_all(p).unwrap();
    assert!(Command::new("git").arg("init").arg("-q").arg(p).status().unwrap().success());
}

fn local(p: &Path, key: &str) -> String {
    String::from_utf8_lossy(&git(p, &["config", "--local", key]).stdout).trim().to_string()
}

#[test]
fn writes_the_identity_inside_the_root() {
    let tmp = tempfile::tempdir().unwrap();
    let repo = tmp.path().join("repo");
    init(&repo);
    fixture_identity(&repo, tmp.path());
    assert_eq!(local(&repo, "user.email"), EMAIL);
    assert_eq!(local(&repo, "user.name"), NAME);
}

#[test]
fn refuses_a_repo_outside_the_root_and_writes_nothing() {
    let (root, outside) = (tempfile::tempdir().unwrap(), tempfile::tempdir().unwrap());
    init(&outside.path().join("repo"));
    let err = try_fixture_identity(&outside.path().join("repo"), root.path()).unwrap_err();
    assert!(err.contains("not under"), "{err}");
    assert_eq!(local(&outside.path().join("repo"), "user.email"), "");
}

#[test]
fn refuses_a_path_that_is_no_repo_and_a_root_that_does_not_resolve() {
    let tmp = tempfile::tempdir().unwrap();
    assert!(try_fixture_identity(&tmp.path().join("missing"), tmp.path()).unwrap_err().contains("not under"));
    let repo = tmp.path().join("repo");
    init(&repo);
    assert!(try_fixture_identity(&repo, &tmp.path().join("no-such-root")).unwrap_err().contains("root"));
    assert_eq!(local(&repo, "user.email"), "");
}
