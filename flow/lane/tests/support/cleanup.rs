//! Fixture for the merge-cleanup integration tests, ported from
//! `flow/bin/merge-cleanup.test.sh`: scratch origins and clones under a temp
//! dir, a temp HOME, and PATHs holding the fake `gh`/`herdr` plus only the
//! real tools the binary shells out to — so the gh- and herdr-absent branches
//! are reachable and nothing live is touched.

use std::os::unix::fs::symlink;
use std::path::{Path, PathBuf};
use std::process::{Command, Output, Stdio};

/// Which fake tools a run's PATH holds.
#[derive(Clone, Copy)]
pub enum Tools {
    Full,
    NoGh,
    NoHerdr,
}

pub struct Cleanup {
    pub tmp: tempfile::TempDir,
}

pub fn which(name: &str) -> PathBuf {
    let path = std::env::var_os("PATH").unwrap_or_default();
    std::env::split_paths(&path)
        .map(|d| d.join(name))
        .find(|p| p.is_file())
        .unwrap_or_else(|| panic!("{name} is not on PATH"))
}

impl Cleanup {
    pub fn new() -> Self {
        let tmp = tempfile::tempdir().unwrap();
        let c = Cleanup { tmp };
        std::fs::create_dir_all(c.home().join(".claude/sessions")).unwrap();
        std::fs::create_dir_all(c.pr_heads()).unwrap();
        let fake = PathBuf::from(env!("CARGO_BIN_EXE_lane-fake"));
        for (dir, stubs) in [("full", &["gh", "herdr"][..]), ("nogh", &["herdr"][..]), ("noherdr", &["gh"][..])] {
            let d = c.root().join(dir);
            std::fs::create_dir_all(&d).unwrap();
            for t in ["git", "bash", "sh", "cat", "env", "mkdir", "dirname"] {
                symlink(which(t), d.join(t)).unwrap();
            }
            for s in stubs {
                symlink(&fake, d.join(s)).unwrap();
            }
        }
        c.set_agents("[]");
        c.set_workspaces("[]");
        c
    }

    /// The temp dir with symlinks resolved, so paths compare equal to the
    /// ones git reports.
    pub fn root(&self) -> PathBuf {
        self.tmp.path().canonicalize().unwrap()
    }
    pub fn home(&self) -> PathBuf {
        self.root().join("home")
    }
    pub fn pr_heads(&self) -> PathBuf {
        self.root().join("gh-pr-heads")
    }
    pub fn call_log(&self) -> PathBuf {
        self.root().join("calls.log")
    }
    pub fn calls(&self) -> String {
        std::fs::read_to_string(self.call_log()).unwrap_or_default()
    }
    pub fn clear_calls(&self) {
        std::fs::write(self.call_log(), "").unwrap();
    }

    /// `herdr agent list`'s agents array, as JSON.
    pub fn set_agents(&self, agents: &str) {
        std::fs::write(self.root().join("agents.json"), format!(r#"{{"result":{{"agents":{agents}}}}}"#)).unwrap();
    }
    /// `herdr workspace list`: one workspace per `(id, checkout path)`.
    pub fn set_workspaces_at(&self, ws: &[(&str, &Path)]) {
        let items: Vec<String> = ws
            .iter()
            .map(|(id, p)| format!(r#"{{"workspace_id":"{id}","worktree":{{"checkout_path":"{}"}}}}"#, p.display()))
            .collect();
        self.set_workspaces(&format!("[{}]", items.join(",")));
    }
    fn set_workspaces(&self, ws: &str) {
        std::fs::write(self.root().join("workspaces.json"), format!(r#"{{"result":{{"workspaces":{ws}}}}}"#)).unwrap();
    }

    /// A registry file `<name>.json` in the scratch HOME.
    pub fn session(&self, name: &str, body: &str) {
        std::fs::write(self.home().join(".claude/sessions").join(format!("{name}.json")), body).unwrap();
    }

    pub fn git(&self, args: &[&str]) -> Output {
        Command::new("git")
            .args(args)
            .env("HOME", self.home())
            .env_remove("GIT_DIR")
            .env_remove("GIT_WORK_TREE")
            .env_remove("GIT_INDEX_FILE")
            .output()
            .unwrap()
    }
    pub fn git_ok(&self, args: &[&str]) {
        let out = self.git(args);
        assert!(out.status.success(), "git {args:?}: {}", String::from_utf8_lossy(&out.stderr));
    }
    pub fn git_out(&self, args: &[&str]) -> String {
        String::from_utf8_lossy(&self.git(args).stdout).trim().to_string()
    }
    pub fn has_branch(&self, repo: &Path, b: &str) -> bool {
        self.git(&["-C", repo.to_str().unwrap(), "show-ref", "-q", "--verify", &format!("refs/heads/{b}")]).status.success()
    }
    pub fn rev(&self, repo: &Path, r: &str) -> String {
        self.git_out(&["-C", repo.to_str().unwrap(), "rev-parse", r])
    }
    pub fn worktree_add(&self, repo: &Path, args: &[&str]) {
        let mut a = vec!["-C", repo.to_str().unwrap(), "worktree", "add", "-q"];
        a.extend_from_slice(args);
        self.git_ok(&a);
    }

    fn commit_line(&self, d: &str, line: &str, msg: &str) {
        let f = Path::new(d).join("f");
        let mut body = std::fs::read_to_string(&f).unwrap_or_default();
        body.push_str(line);
        body.push('\n');
        std::fs::write(&f, body).unwrap();
        self.git_ok(&["-C", d, "commit", "-qam", msg]);
    }

    /// A bare origin at `<rel>.origin.git` and a clone of it at `<rel>` on
    /// main, with a commit identity set.
    fn clone_origin(&self, rel: &str) -> PathBuf {
        let dir = self.root().join(rel);
        std::fs::create_dir_all(dir.parent().unwrap()).unwrap();
        let d = dir.to_str().unwrap();
        let origin = format!("{d}.origin.git");
        self.git_ok(&["init", "-q", "-b", "main", "--bare", &origin]);
        self.git_ok(&["clone", "-q", &origin, d]);
        self.git_ok(&["-C", d, "checkout", "-q", "-b", "main"]);
        self.git_ok(&["-C", d, "config", "user.email", "t@example.com"]);
        self.git_ok(&["-C", d, "config", "user.name", "t"]);
        dir
    }

    /// The bash suite's `mkfixture`: a scratch origin plus a clone where
    /// caneff/merged-one is squash-merged (a merged PR at its tip),
    /// caneff/merged-then-more had a PR merged then kept going,
    /// caneff/ff-merged is a real fast-forward merge, caneff/local-only was
    /// never pushed, caneff/open-one is open — and origin/main sits one
    /// commit ahead of the local main, so the fast-forward has work.
    pub fn mkfixture(&self, rel: &str) -> PathBuf {
        let dir = self.clone_origin(rel);
        let d = dir.to_str().unwrap();
        std::fs::write(dir.join("f"), "one\n").unwrap();
        self.git_ok(&["-C", d, "add", "f"]);
        self.git_ok(&["-C", d, "commit", "-qm", "one"]);
        self.git_ok(&["-C", d, "push", "-q", "-u", "origin", "main"]);
        for b in ["caneff/merged-one", "caneff/open-one"] {
            self.git_ok(&["-C", d, "checkout", "-q", "-b", b, "main"]);
            self.commit_line(d, b, b);
            self.git_ok(&["-C", d, "push", "-q", "-u", "origin", b]);
        }
        self.git_ok(&["-C", d, "checkout", "-q", "main"]);
        self.record_pr_head(&dir, "caneff/merged-one", "caneff/merged-one");
        self.git_ok(&["-C", d, "checkout", "-q", "-b", "caneff/merged-then-more", "main"]);
        self.commit_line(d, "landed", "landed via a PR");
        self.record_pr_head(&dir, "caneff/merged-then-more", "HEAD");
        self.commit_line(d, "unlanded", "kept going after the PR");
        self.git_ok(&["-C", d, "push", "-q", "-u", "origin", "caneff/merged-then-more"]);
        self.git_ok(&["-C", d, "checkout", "-q", "main"]);
        self.git_ok(&["-C", d, "checkout", "-q", "-b", "caneff/ff-merged", "main"]);
        self.commit_line(d, "ff", "ff");
        self.git_ok(&["-C", d, "push", "-q", "-u", "origin", "caneff/ff-merged"]);
        self.git_ok(&["-C", d, "checkout", "-q", "main"]);
        self.git_ok(&["-C", d, "merge", "-q", "--ff-only", "caneff/ff-merged"]);
        self.git_ok(&["-C", d, "checkout", "-q", "-b", "caneff/local-only", "main"]);
        self.commit_line(d, "local", "local");
        self.git_ok(&["-C", d, "checkout", "-q", "main"]);
        self.commit_line(d, "squashed", "squash of caneff/merged-one");
        self.git_ok(&["-C", d, "push", "-q", "origin", "main"]);
        self.git_ok(&["-C", d, "reset", "-q", "--hard", "HEAD~1"]);
        dir
    }

    /// Records that a merged PR's head for `branch` is `rev` in `repo`.
    pub fn record_pr_head(&self, repo: &Path, branch: &str, rev: &str) {
        std::fs::write(self.pr_heads().join(branch.replace('/', "__")), self.rev(repo, rev)).unwrap();
    }

    /// A merged `implement-<n>` branch in `repo`, for the #821 ticket-clearing
    /// tests: pushed, its tip recorded as a merged PR's head, main left
    /// checked out.
    pub fn mk_implement_branch(&self, repo: &Path, n: &str) {
        let d = repo.to_str().unwrap();
        let b = format!("implement-{n}");
        self.git_ok(&["-C", d, "checkout", "-q", "-b", &b, "main"]);
        self.commit_line(d, &b, &b);
        self.git_ok(&["-C", d, "push", "-q", "-u", "origin", &b]);
        self.git_ok(&["-C", d, "checkout", "-q", "main"]);
        self.record_pr_head(repo, &b, &b);
    }

    /// The bash suite's `mk_lane_repo`: caneff/trivial is merged into main,
    /// and origin/main is one commit ahead that touches flow/lane or not.
    pub fn mk_lane_repo(&self, rel: &str, touch_lane: bool) -> PathBuf {
        let dir = self.clone_origin(rel);
        let d = dir.to_str().unwrap();
        std::fs::create_dir_all(dir.join("flow/lane")).unwrap();
        std::fs::write(
            dir.join("flow/lane-install.sh"),
            "#!/usr/bin/env bash\nset -euo pipefail\nif [ -n \"${LANE_INSTALL_FAIL:-}\" ]; then\n  echo \"compile error: boom\" >&2\n  exit 1\nfi\necho ran >> \"$LANE_INSTALL_LOG\"\necho NEW > \"$LANE_INSTALLED_BIN\"\nhere=\"$(cd \"$(dirname \"${BASH_SOURCE[0]}\")\" && pwd)\"\nstate_dir=\"$HOME/.local/state/lane\"\nmkdir -p \"$state_dir\"\ngit -C \"$here/..\" rev-parse HEAD > \"$state_dir/build-sha\"\n",
        )
        .unwrap();
        std::fs::write(dir.join("flow/lane/main.rs"), "fn1\n").unwrap();
        self.git_ok(&["-C", d, "add", "-A"]);
        self.git_ok(&["-C", d, "commit", "-qm", "base"]);
        self.git_ok(&["-C", d, "checkout", "-q", "-b", "caneff/trivial", "main"]);
        std::fs::write(dir.join("trivial"), "x\n").unwrap();
        self.git_ok(&["-C", d, "add", "trivial"]);
        self.git_ok(&["-C", d, "commit", "-qam", "trivial"]);
        self.git_ok(&["-C", d, "checkout", "-q", "main"]);
        self.git_ok(&["-C", d, "merge", "-q", "--ff-only", "caneff/trivial"]);
        self.git_ok(&["-C", d, "push", "-q", "-u", "origin", "main"]);
        if touch_lane {
            std::fs::write(dir.join("flow/lane/main.rs"), "fn1\nfn2\n").unwrap();
        } else {
            std::fs::write(dir.join("unrelated"), "other\n").unwrap();
        }
        self.git_ok(&["-C", d, "add", "-A"]);
        self.git_ok(&["-C", d, "commit", "-qam", "further change"]);
        self.git_ok(&["-C", d, "push", "-q", "origin", "main"]);
        self.git_ok(&["-C", d, "reset", "-q", "--hard", "HEAD~1"]);
        dir
    }

    fn command(&self, tools: Tools, args: &[&str], env: &[(&str, &str)]) -> Command {
        let dir = match tools {
            Tools::Full => "full",
            Tools::NoGh => "nogh",
            Tools::NoHerdr => "noherdr",
        };
        let mut cmd = Command::new(env!("CARGO_BIN_EXE_merge-cleanup"));
        cmd.args(args)
            .env_clear()
            .env("PATH", self.root().join(dir))
            .env("HOME", self.home())
            .env("CALL_LOG", self.call_log())
            .env("GH_PR_HEADS", self.pr_heads())
            .env("HERDR_AGENTS", self.root().join("agents.json"))
            .env("HERDR_WORKSPACES", self.root().join("workspaces.json"));
        for (k, v) in env {
            cmd.env(k, v);
        }
        cmd
    }

    /// Runs merge-cleanup with stdin closed.
    pub fn mc(&self, tools: Tools, args: &[&str], env: &[(&str, &str)]) -> Run {
        let out = self.command(tools, args, env).stdin(Stdio::null()).output().unwrap();
        Run::from(out)
    }

    /// The same, from `cwd` — what a run started inside a workspace, rather
    /// than pointed at a repo with --repo, sees.
    pub fn mc_in(&self, tools: Tools, cwd: &Path, args: &[&str], env: &[(&str, &str)]) -> Run {
        let out = self.command(tools, args, env).current_dir(cwd).stdin(Stdio::null()).output().unwrap();
        Run::from(out)
    }

    /// Runs merge-cleanup with its stdout read one line then closed, the way
    /// `| head -n1` or quitting `less` early leaves it — for #758's broken
    /// pipe. Returns the exit code (`None` if killed by a signal) and
    /// stderr.
    pub fn mc_broken_pipe(&self, tools: Tools, args: &[&str]) -> (Option<i32>, String) {
        use std::io::Read;
        let mut child = self
            .command(tools, args, &[])
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap();
        let mut stdout = child.stdout.take().unwrap();
        let mut byte = [0u8; 1];
        while stdout.read(&mut byte).unwrap() != 0 && byte[0] != b'\n' {}
        drop(stdout);
        let mut stderr = String::new();
        child.stderr.take().unwrap().read_to_string(&mut stderr).unwrap();
        let status = child.wait().unwrap();
        (status.code(), stderr)
    }

    /// Runs merge-cleanup with `input` piped to its stdin.
    pub fn mc_piped(&self, tools: Tools, args: &[&str], input: &str) -> Run {
        use std::io::Write;
        let mut child = self
            .command(tools, args, &[])
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap();
        child.stdin.take().unwrap().write_all(input.as_bytes()).unwrap();
        Run::from(child.wait_with_output().unwrap())
    }
}

/// A run whose stdin is a real terminal (a pty from util-linux `script`),
/// with stdout piped through `cat` into a file — the `| tee` / `| less`
/// shape #733 is about.
pub struct TtyRun {
    pub ok: bool,
    /// What the terminal showed: stderr, and the typed answer's echo.
    pub terminal: String,
    /// What reached the pipe.
    pub stdout: String,
}

impl Cleanup {
    pub fn mc_tty(&self, tools: Tools, args: &[&str], typed: &str) -> TtyRun {
        let cmd = self.command(tools, args, &[]);
        let quote = |s: &str| format!("'{}'", s.replace('\'', "'\\''"));
        let mut line = String::from("set -o pipefail; env -i");
        for (k, v) in cmd.get_envs() {
            line.push_str(&format!(" {}={}", k.to_string_lossy(), quote(&v.unwrap_or_default().to_string_lossy())));
        }
        line.push(' ');
        line.push_str(&quote(&cmd.get_program().to_string_lossy()));
        for a in cmd.get_args() {
            line.push(' ');
            line.push_str(&quote(&a.to_string_lossy()));
        }
        let piped = self.root().join("tty-stdout.txt");
        line.push_str(&format!(" | cat > {}", quote(&piped.display().to_string())));
        let out = self.tty_command(&line, typed);
        TtyRun {
            ok: out.status.success(),
            terminal: String::from_utf8_lossy(&out.stdout).replace('\r', ""),
            stdout: std::fs::read_to_string(&piped).unwrap_or_default(),
        }
    }

    fn tty_command(&self, line: &str, typed: &str) -> Output {
        use std::io::Write;
        let mut child = Command::new("script")
            .args(["-qec", line, "/dev/null"])
            .env("SHELL", which("bash"))
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap();
        // The answer arrives after the prompt is up, as a person's would.
        std::thread::sleep(std::time::Duration::from_millis(1500));
        child.stdin.take().unwrap().write_all(typed.as_bytes()).unwrap();
        child.wait_with_output().unwrap()
    }
}

pub struct Run {
    pub ok: bool,
    pub stdout: String,
    pub stderr: String,
}

impl Run {
    fn from(out: Output) -> Self {
        Run {
            ok: out.status.success(),
            stdout: String::from_utf8_lossy(&out.stdout).into_owned(),
            stderr: String::from_utf8_lossy(&out.stderr).into_owned(),
        }
    }
    /// stdout then stderr, for the assertions the bash suite made on `2>&1`.
    pub fn text(&self) -> String {
        format!("{}{}", self.stdout, self.stderr)
    }
    pub fn has(&self, s: &str) -> bool {
        self.text().contains(s)
    }
    /// The indented lines under the "stale, not removed:" header.
    pub fn stale(&self) -> Vec<String> {
        let mut out = Vec::new();
        let mut on = false;
        for l in self.stdout.lines() {
            if l.starts_with("stale, not removed:") {
                on = true;
            } else if on && l.starts_with("  ") {
                out.push(l.trim_start().to_string());
            } else {
                on = false;
            }
        }
        out
    }
    /// The line index of the first line containing `s`, in stdout.
    pub fn line_of(&self, s: &str) -> Option<usize> {
        self.stdout.lines().position(|l| l.contains(s))
    }
}
