//! Shared test support. This file is the implement-dispatch fixture: a
//! scratch origin plus a clone under a temp dir, and the fake `gh`/`herdr`
//! from `lane-fake` on a scratch PATH, mirroring the bash suite's own
//! fixture. `cleanup` is the merge-cleanup fixture.
#![allow(dead_code)]

pub mod cleanup;

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};

pub fn bin_path() -> PathBuf {
    PathBuf::from(env!("CARGO_BIN_EXE_implement-dispatch"))
}
fn fake_path() -> PathBuf {
    PathBuf::from(env!("CARGO_BIN_EXE_lane-fake"))
}

pub struct Fixture {
    pub tmp: tempfile::TempDir,
}

impl Fixture {
    pub fn new() -> Self {
        let tmp = tempfile::tempdir().unwrap();
        std::fs::create_dir_all(tmp.path().join("home")).unwrap();
        std::fs::create_dir_all(tmp.path().join("bin")).unwrap();
        let fake = fake_path();
        std::os::unix::fs::symlink(&fake, tmp.path().join("bin/gh")).unwrap();
        std::os::unix::fs::symlink(&fake, tmp.path().join("bin/herdr")).unwrap();
        let f = Fixture { tmp };
        f.set_agents("[]");
        f
    }

    pub fn home(&self) -> PathBuf {
        self.tmp.path().join("home")
    }
    pub fn call_log(&self) -> PathBuf {
        self.tmp.path().join("calls.log")
    }
    pub fn agents_file(&self) -> PathBuf {
        self.tmp.path().join("agents.json")
    }
    /// `herdr agent list`'s agents array, as JSON — what #819's session
    /// lookup reads to find the sessionId herdr attached to the agent it
    /// just started.
    pub fn set_agents(&self, agents: &str) {
        std::fs::write(self.agents_file(), format!(r#"{{"result":{{"agents":{agents}}}}}"#)).unwrap();
    }

    /// Fresh ~/.claude.json with one other project, and an empty call log —
    /// the bash suite's `reset_home`.
    pub fn reset_home(&self, onboarding: bool) {
        std::fs::write(
            self.home().join(".claude.json"),
            format!(r#"{{"hasCompletedOnboarding":{onboarding},"projects":{{"/elsewhere":{{"hasTrustDialogAccepted":false}}}}}}"#),
        )
        .unwrap();
        std::fs::write(&self.call_log(), "").unwrap();
        // The controller: this test process stands in for the dispatching
        // Claude session, an ancestor of every dispatch it runs.
        let pid = std::process::id() as i32;
        let stat = lane::proc_info::read_stat(pid).unwrap();
        std::fs::create_dir_all(self.home().join(".claude/sessions")).unwrap();
        self.set_session("skills-ctl", &stat.start);
    }

    pub fn set_session(&self, name: &str, proc_start: &str) {
        let pid = std::process::id();
        std::fs::write(
            self.home().join(".claude/sessions").join(format!("{pid}.json")),
            format!(r#"{{"pid":{pid},"procStart":"{proc_start}","name":"{name}"}}"#),
        )
        .unwrap();
    }
    pub fn session_file(&self) -> PathBuf {
        let pid = std::process::id();
        self.home().join(".claude/sessions").join(format!("{pid}.json"))
    }
    pub fn own_proc_start(&self) -> String {
        let pid = std::process::id() as i32;
        lane::proc_info::read_stat(pid).unwrap().start
    }

    /// A scratch origin under github.com/caneff/<name>.git plus a clone whose
    /// local HEAD lags one commit behind origin/<branch> and has no
    /// origin/HEAD — the base must be origin/<default>, not local HEAD.
    pub fn mkfixture(&self, name: &str, branch: &str) -> PathBuf {
        let origin = self.tmp.path().join("github.com/caneff").join(format!("{name}.git"));
        std::fs::create_dir_all(origin.parent().unwrap()).unwrap();
        run_ok("git", &["init", "-q", "-b", branch, "--bare", origin.to_str().unwrap()], None);
        let dir = self.tmp.path().join(name);
        run_ok("git", &["clone", "-q", origin.to_str().unwrap(), dir.to_str().unwrap()], None);
        run_ok("git", &["-C", dir.to_str().unwrap(), "checkout", "-q", "-b", branch], None);
        run_ok("git", &["-C", dir.to_str().unwrap(), "config", "user.email", "t@example.com"], None);
        run_ok("git", &["-C", dir.to_str().unwrap(), "config", "user.name", "t"], None);
        std::fs::write(dir.join("f"), "one\n").unwrap();
        run_ok("git", &["-C", dir.to_str().unwrap(), "add", "f"], None);
        run_ok("git", &["-C", dir.to_str().unwrap(), "commit", "-qm", "one"], None);
        std::fs::write(dir.join("f"), "one\ntwo\n").unwrap();
        run_ok("git", &["-C", dir.to_str().unwrap(), "commit", "-qam", "two"], None);
        run_ok("git", &["-C", dir.to_str().unwrap(), "push", "-q", "-u", "origin", branch], None);
        run_ok("git", &["-C", dir.to_str().unwrap(), "reset", "-q", "--hard", "HEAD~1"], None);
        dir
    }

    pub fn path_env(&self) -> String {
        let real = std::env::var("PATH").unwrap_or_default();
        format!("{}:{}", self.tmp.path().join("bin").display(), real)
    }

    /// Runs implement-dispatch with the given args and scenario env vars,
    /// against the fake on PATH and a scratch HOME.
    pub fn dispatch(&self, args: &[&str], scenario: &[(&str, &str)]) -> Output {
        let mut cmd = Command::new(bin_path());
        cmd.args(args);
        cmd.env_clear();
        cmd.env("PATH", self.path_env());
        cmd.env("HOME", self.home());
        cmd.env("CALL_LOG", self.call_log());
        cmd.env("HERDR_AGENTS", self.agents_file());
        for (k, v) in scenario {
            cmd.env(k, v);
        }
        cmd.output().unwrap()
    }

    pub fn calls(&self) -> String {
        std::fs::read_to_string(self.call_log()).unwrap_or_default()
    }

    /// Runs implement-dispatch with its stdout closed before the process
    /// gets to write anything — the limit of `| head -n1` closing early,
    /// for #758's broken pipe. All of dispatch's real work (git, the fake
    /// gh/herdr) happens before its first `println!`, so dropping the read
    /// end right after spawn reliably beats it there. Returns the exit code
    /// (`None` if killed by a signal) and stderr.
    pub fn dispatch_broken_pipe(&self, args: &[&str], scenario: &[(&str, &str)]) -> (Option<i32>, String) {
        use std::io::Read;
        let mut cmd = Command::new(bin_path());
        cmd.args(args);
        cmd.env_clear();
        cmd.env("PATH", self.path_env());
        cmd.env("HOME", self.home());
        cmd.env("CALL_LOG", self.call_log());
        cmd.env("HERDR_AGENTS", self.agents_file());
        for (k, v) in scenario {
            cmd.env(k, v);
        }
        let mut child = cmd
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::piped())
            .spawn()
            .unwrap();
        drop(child.stdout.take().unwrap());
        let mut stderr = String::new();
        child.stderr.take().unwrap().read_to_string(&mut stderr).unwrap();
        let status = child.wait().unwrap();
        (status.code(), stderr)
    }
}

fn run_ok(program: &str, args: &[&str], cwd: Option<&Path>) {
    let mut cmd = Command::new(program);
    cmd.args(args);
    if let Some(c) = cwd {
        cmd.current_dir(c);
    }
    let status = cmd.status().unwrap();
    assert!(status.success(), "{program} {:?} failed", args);
}

pub fn out_text(out: &Output) -> String {
    let mut s = String::from_utf8_lossy(&out.stdout).into_owned();
    s.push_str(&String::from_utf8_lossy(&out.stderr));
    s
}

pub fn default_scenario() -> Vec<(&'static str, &'static str)> {
    vec![("GH_STATE", "OPEN"), ("GH_LABELS", "enhancement,ready-for-agent"), ("HERDR_RUNNING", "true")]
}

pub fn with<'a>(base: &[(&'a str, &'a str)], extra: &[(&'a str, &'a str)]) -> Vec<(&'a str, &'a str)> {
    let mut m: HashMap<&str, &str> = base.iter().cloned().collect();
    for (k, v) in extra {
        m.insert(k, v);
    }
    m.into_iter().collect()
}
