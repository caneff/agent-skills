//! The one place a Rust suite names a fixture git identity (#1144, #1728).
//!
//! `fixture_identity` writes `user.email`/`user.name` into `repo` only when its
//! toplevel sits under `root`, the caller's own temp dir: a bare `git config`
//! after a failed setup once wrote the real checkout's config. Included by
//! `tests/support/mod.rs` and, through `#[path]`, by `src/git_origin.rs`'s
//! unit tests; its own tests are `tests/fixture_identity.rs`.
//! `tests/fixture-identity-sites.test.sh` fails any other writer.
#![allow(dead_code)]

use std::path::Path;
use std::process::Command;

pub const NAME: &str = "t";
pub const EMAIL: &str = "t@example.invalid";

/// How the helper starts `git`: a suite that serialises its forks (`cleanup`'s
/// `output`, against "text file busy") passes its own runner, never a bare
/// `Command::output`.
pub type Runner<'a> = &'a dyn Fn(&mut Command) -> std::io::Result<std::process::Output>;

fn plain(cmd: &mut Command) -> std::io::Result<std::process::Output> {
    cmd.output()
}

fn git(run: Runner, repo: &Path, args: &[&str]) -> std::process::Output {
    run(Command::new("git").arg("-C").arg(repo).args(args)).expect("run git")
}

/// Err names why nothing was written: a root that does not resolve, or a repo
/// whose toplevel is not under it (a path that is no repo reads as "not under").
pub fn try_fixture_identity_via(run: Runner, repo: &Path, root: &Path) -> Result<(), String> {
    let root = root.canonicalize().map_err(|e| format!("fixture root {} does not resolve: {e}", root.display()))?;
    let top = git(run, repo, &["rev-parse", "--show-toplevel"]);
    let top = String::from_utf8_lossy(&top.stdout).trim().to_string();
    let top = Path::new(&top).canonicalize().ok().filter(|_| !top.is_empty());
    match top {
        Some(t) if t.starts_with(&root) && t != root => {}
        _ => return Err(format!("fixture repo {} is not under {}", repo.display(), root.display())),
    }
    for (key, value) in [("user.email", EMAIL), ("user.name", NAME)] {
        let out = git(run, repo, &["config", key, value]);
        if !out.status.success() {
            return Err(format!("git config {key} failed in {}", repo.display()));
        }
    }
    Ok(())
}

pub fn try_fixture_identity(repo: &Path, root: &Path) -> Result<(), String> {
    try_fixture_identity_via(&plain, repo, root)
}

pub fn fixture_identity(repo: &Path, root: &Path) {
    try_fixture_identity(repo, root).unwrap_or_else(|e| panic!("{e}"));
}

/// `fixture_identity` through a caller's own runner.
pub fn fixture_identity_via(run: Runner, repo: &Path, root: &Path) {
    try_fixture_identity_via(run, repo, root).unwrap_or_else(|e| panic!("{e}"));
}
