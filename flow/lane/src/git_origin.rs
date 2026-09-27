//! Port of `flow/bin/git-origin.sh`: what both lane commands read from a
//! repo's origin. Shells out to `git`, matching bash exactly rather than
//! parsing `.git` on disk, so behavior tracks the installed git.

use crate::runner::{quiet_ok, quiet_ok_bounded, quiet_stdout, quiet_stdout_bounded};
use std::path::Path;
use std::time::Duration;

/// `default_of <path>` -> main, master, whatever origin points at.
pub fn default_branch(repo: &Path) -> String {
    let repo_s = repo.to_string_lossy();
    if let Some(d) = quiet_stdout("git", &["-C", &repo_s, "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD"]) {
        let d = d.trim();
        if !d.is_empty() {
            return d.strip_prefix("origin/").unwrap_or(d).to_string();
        }
    }
    for d in ["main", "master"] {
        if quiet_ok("git", &["-C", &repo_s, "show-ref", "-q", "--verify", &format!("refs/remotes/origin/{d}")]) {
            return d.to_string();
        }
    }
    "main".to_string()
}

/// `slug_of <path>` -> owner/name, for the gh calls. `None` when there is no
/// origin remote.
pub fn origin_slug(repo: &Path) -> Option<String> {
    let repo_s = repo.to_string_lossy();
    let url = quiet_stdout("git", &["-C", &repo_s, "remote", "get-url", "origin"])?;
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

/// `default_branch`, bounded (#849): `implement-dispatch` is the only
/// caller of this variant, so a hang on any of the underlying `git` calls
/// fails loud — naming the command — rather than falling through to
/// `default_branch`'s own "main"/"master" guess, which is a legitimate
/// answer only when the calls that produced it actually ran.
pub fn default_branch_timeout(repo: &Path, timeout: Duration) -> Result<String, String> {
    let repo_s = repo.to_string_lossy();
    if let Some(d) =
        quiet_stdout_bounded("git", &["-C", &repo_s, "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD"], timeout)?
    {
        let d = d.trim();
        if !d.is_empty() {
            return Ok(d.strip_prefix("origin/").unwrap_or(d).to_string());
        }
    }
    for d in ["main", "master"] {
        if quiet_ok_bounded("git", &["-C", &repo_s, "show-ref", "-q", "--verify", &format!("refs/remotes/origin/{d}")], timeout)? {
            return Ok(d.to_string());
        }
    }
    Ok("main".to_string())
}

/// `origin_slug`, bounded (#849) — see [`default_branch_timeout`].
pub fn origin_slug_timeout(repo: &Path, timeout: Duration) -> Result<Option<String>, String> {
    let repo_s = repo.to_string_lossy();
    let Some(url) = quiet_stdout_bounded("git", &["-C", &repo_s, "remote", "get-url", "origin"], timeout)? else {
        return Ok(None);
    };
    let url = url.trim();
    if url.is_empty() {
        return Ok(None);
    }
    let url = url.strip_suffix(".git").unwrap_or(url);
    let url = match url.find("github.com/") {
        Some(i) => &url[i + "github.com/".len()..],
        None => match url.find("github.com:") {
            Some(i) => &url[i + "github.com:".len()..],
            None => url,
        },
    };
    Ok(Some(url.to_string()))
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

    // #849: the bounded variants match the unbounded ones on every case that
    // isn't about a hang — that behavior belongs to implement-dispatch's own
    // contract tests, which can make a real "git" hang; a unit test here
    // cannot without shadowing "git" process-wide for every parallel test.
    #[test]
    fn default_branch_timeout_matches_default_branch_when_origin_head_names_it() {
        let tmp = TempDir::new().unwrap();
        let repo = init_origin_and_clone(tmp.path(), "repo-main-b", "main");
        assert_eq!(default_branch_timeout(&repo, Duration::from_secs(5)), Ok("main".to_string()));
    }

    #[test]
    fn default_branch_timeout_falls_back_to_master_with_no_origin_head() {
        let tmp = TempDir::new().unwrap();
        let repo = init_origin_and_clone(tmp.path(), "repo-master-b", "master");
        assert_eq!(default_branch_timeout(&repo, Duration::from_secs(5)), Ok("master".to_string()));
    }

    #[test]
    fn origin_slug_timeout_reads_github_owner_and_name() {
        let tmp = TempDir::new().unwrap();
        let repo = init_origin_and_clone(tmp.path(), "sudokumaker-custom-constraints-b", "main");
        assert_eq!(
            origin_slug_timeout(&repo, Duration::from_secs(5)),
            Ok(Some("caneff/sudokumaker-custom-constraints-b".to_string()))
        );
    }

    #[test]
    fn origin_slug_timeout_is_none_for_no_origin_remote() {
        let tmp = TempDir::new().unwrap();
        let repo = tmp.path().join("norigin");
        std::fs::create_dir(&repo).unwrap();
        git(&repo, &["init", "-q"]);
        assert_eq!(origin_slug_timeout(&repo, Duration::from_secs(5)), Ok(None));
    }
}
