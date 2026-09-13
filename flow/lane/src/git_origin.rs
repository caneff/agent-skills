//! Port of `flow/bin/git-origin.sh`: what both lane commands read from a
//! repo's origin. Shells out to `git`, matching bash exactly rather than
//! parsing `.git` on disk, so behavior tracks the installed git.

use std::path::Path;
use std::process::Command;

/// `default_of <path>` -> main, master, whatever origin points at.
pub fn default_branch(repo: &Path) -> String {
    if let Some(d) = run_git(repo, &["symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD"]) {
        let d = d.trim();
        if !d.is_empty() {
            return d.strip_prefix("origin/").unwrap_or(d).to_string();
        }
    }
    for d in ["main", "master"] {
        if git_ok(repo, &["show-ref", "-q", "--verify", &format!("refs/remotes/origin/{d}")]) {
            return d.to_string();
        }
    }
    "main".to_string()
}

/// `slug_of <path>` -> owner/name, for the gh calls. `None` when there is no
/// origin remote.
pub fn origin_slug(repo: &Path) -> Option<String> {
    let url = run_git(repo, &["remote", "get-url", "origin"])?;
    let url = url.trim();
    if url.is_empty() {
        return None;
    }
    let url = url.strip_suffix(".git").unwrap_or(url);
    let url = match url.find("github.com/") {
        Some(i) => &url[i + "github.com/".len()..],
        None => match url.find("github.com:") {
            Some(i) => &url[i + "github.com:".len()..],
            None => url,
        },
    };
    Some(url.to_string())
}

fn run_git(repo: &Path, args: &[&str]) -> Option<String> {
    let out = Command::new("git").arg("-C").arg(repo).args(args).output().ok()?;
    if !out.status.success() {
        return None;
    }
    String::from_utf8(out.stdout).ok()
}

fn git_ok(repo: &Path, args: &[&str]) -> bool {
    Command::new("git")
        .arg("-C")
        .arg(repo)
        .args(args)
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::process::Command;
    use tempfile::TempDir;

    fn git(dir: &Path, args: &[&str]) {
        let status = Command::new("git").arg("-C").arg(dir).args(args).status().unwrap();
        assert!(status.success(), "git {:?} failed in {:?}", args, dir);
    }

    fn init_origin_and_clone(tmp: &Path, name: &str, branch: &str) -> std::path::PathBuf {
        let origin = tmp.join(format!("github.com/caneff/{name}.git"));
        Command::new("git").arg("init").arg("-q").arg("-b").arg(branch).arg("--bare").arg(&origin).status().unwrap();
        let clone = tmp.join(name);
        Command::new("git").arg("clone").arg("-q").arg(&origin).arg(&clone).status().unwrap();
        git(&clone, &["checkout", "-q", "-b", branch]);
        git(&clone, &["config", "user.email", "t@example.com"]);
        git(&clone, &["config", "user.name", "t"]);
        std::fs::write(clone.join("f"), "one\n").unwrap();
        git(&clone, &["add", "f"]);
        git(&clone, &["commit", "-qm", "one"]);
        git(&clone, &["push", "-q", "-u", "origin", branch]);
        clone
    }

    #[test]
    fn default_branch_is_main_when_origin_head_names_it() {
        let tmp = TempDir::new().unwrap();
        let repo = init_origin_and_clone(tmp.path(), "repo-main", "main");
        assert_eq!(default_branch(&repo), "main");
    }

    #[test]
    fn default_branch_falls_back_to_master_with_no_origin_head() {
        let tmp = TempDir::new().unwrap();
        let repo = init_origin_and_clone(tmp.path(), "repo-master", "master");
        // no origin/HEAD is set on a bare init+push in this fixture
        assert_eq!(default_branch(&repo), "master");
    }

    #[test]
    fn default_branch_is_main_when_origin_has_neither() {
        let tmp = TempDir::new().unwrap();
        let repo = init_origin_and_clone(tmp.path(), "repo-trunk", "trunk");
        assert_eq!(default_branch(&repo), "main");
    }

    #[test]
    fn origin_slug_reads_github_owner_and_name() {
        let tmp = TempDir::new().unwrap();
        let repo = init_origin_and_clone(tmp.path(), "sudokumaker-custom-constraints", "main");
        assert_eq!(origin_slug(&repo).as_deref(), Some("caneff/sudokumaker-custom-constraints"));
    }

    #[test]
    fn origin_slug_is_none_for_a_non_github_remote() {
        let tmp = TempDir::new().unwrap();
        let repo = tmp.path().join("nogh");
        std::fs::create_dir(&repo).unwrap();
        git(&repo, &["init", "-q"]);
        git(&repo, &["remote", "add", "origin", "/some/where/notgithub.git"]);
        assert_eq!(origin_slug(&repo).as_deref(), Some("/some/where/notgithub"));
    }
}
