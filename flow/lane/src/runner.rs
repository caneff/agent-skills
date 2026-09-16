//! A command runner that reports a failed command's output, standing in for
//! the bash idiom `out=$(cmd 2>&1) || fail "$what" "$out"`. stdout and stderr
//! are captured separately (no pty) and concatenated stdout-then-stderr: every
//! caller here writes to exactly one of the two on any given run, so order
//! never matters in practice.

use std::io::Read;
use std::path::Path;
use std::process::{Child, Command, ExitStatus, Stdio};
use std::thread;
use std::time::{Duration, Instant};

pub struct CommandOutput {
    pub success: bool,
    pub combined: String,
}

pub fn run(program: &str, args: &[&str]) -> std::io::Result<CommandOutput> {
    run_in(None, program, args)
}

pub fn run_in(dir: Option<&Path>, program: &str, args: &[&str]) -> std::io::Result<CommandOutput> {
    let mut cmd = Command::new(program);
    cmd.args(args).stdin(Stdio::null());
    if let Some(d) = dir {
        cmd.current_dir(d);
    }
    let out = cmd.output()?;
    let mut combined = String::from_utf8_lossy(&out.stdout).into_owned();
    combined.push_str(&String::from_utf8_lossy(&out.stderr));
    trim_trailing_newlines(&mut combined);
    Ok(CommandOutput { success: out.status.success(), combined })
}

/// Polling gap while waiting on a bounded child: coarse enough not to burn
/// CPU spinning, fine enough that a fast command's own timeout budget isn't
/// dominated by the poll granularity itself.
const TIMEOUT_POLL_INTERVAL: Duration = Duration::from_millis(20);

/// Runs `cmd` (stdin already the caller's concern; this always pipes stdout
/// and stderr) and kills it if it's still alive past `timeout` — the OS-level
/// bound none of the plain functions above have: a hung child otherwise
/// blocks `Command::output`/`status` forever, no matter what deadline the
/// caller thinks it's under. Reader threads drain both pipes concurrently so
/// a child that fills one pipe's buffer can't deadlock the wait.
fn run_bounded(mut cmd: Command, timeout: Duration) -> std::io::Result<(ExitStatus, Vec<u8>, Vec<u8>)> {
    cmd.stdout(Stdio::piped()).stderr(Stdio::piped());
    let mut child = cmd.spawn()?;
    let mut stdout_pipe = child.stdout.take().expect("stdout is piped above");
    let mut stderr_pipe = child.stderr.take().expect("stderr is piped above");
    let stdout_handle = thread::spawn(move || {
        let mut buf = Vec::new();
        let _ = stdout_pipe.read_to_end(&mut buf);
        buf
    });
    let stderr_handle = thread::spawn(move || {
        let mut buf = Vec::new();
        let _ = stderr_pipe.read_to_end(&mut buf);
        buf
    });

    let status = wait_bounded(&mut child, timeout)?;

    let stdout = stdout_handle.join().unwrap_or_default();
    let stderr = stderr_handle.join().unwrap_or_default();
    Ok((status, stdout, stderr))
}

/// Polls `try_wait` until the child exits or `timeout` elapses, killing and
/// reaping it on the latter. A killed child's status (never success on
/// Unix) is what callers see — there's no separate "timed out" signal
/// because none of today's callers need to tell that apart from any other
/// failure.
fn wait_bounded(child: &mut Child, timeout: Duration) -> std::io::Result<ExitStatus> {
    let start = Instant::now();
    loop {
        if let Some(status) = child.try_wait()? {
            return Ok(status);
        }
        if start.elapsed() >= timeout {
            let _ = child.kill();
            return child.wait();
        }
        thread::sleep(TIMEOUT_POLL_INTERVAL);
    }
}

/// `run`, bounded: kills the child and fails the call if it's still running
/// past `timeout`, instead of blocking forever on a hung subprocess.
pub fn run_timeout(program: &str, args: &[&str], timeout: Duration) -> std::io::Result<CommandOutput> {
    run_in_timeout(None, program, args, timeout)
}

/// `run_in`, bounded — see [`run_timeout`].
pub fn run_in_timeout(dir: Option<&Path>, program: &str, args: &[&str], timeout: Duration) -> std::io::Result<CommandOutput> {
    let mut cmd = Command::new(program);
    cmd.args(args).stdin(Stdio::null());
    if let Some(d) = dir {
        cmd.current_dir(d);
    }
    let (status, stdout, stderr) = run_bounded(cmd, timeout)?;
    let mut combined = String::from_utf8_lossy(&stdout).into_owned();
    combined.push_str(&String::from_utf8_lossy(&stderr));
    trim_trailing_newlines(&mut combined);
    Ok(CommandOutput { success: status.success(), combined })
}

/// `quiet_stdout`, bounded — see [`run_timeout`].
pub fn quiet_stdout_timeout(program: &str, args: &[&str], timeout: Duration) -> Option<String> {
    let mut cmd = Command::new(program);
    cmd.args(args).stdin(Stdio::null());
    let (status, stdout, _stderr) = run_bounded(cmd, timeout).ok()?;
    if !status.success() {
        return None;
    }
    let mut s = String::from_utf8_lossy(&stdout).into_owned();
    trim_trailing_newlines(&mut s);
    Some(s)
}

/// `quiet_ok`, bounded — see [`run_timeout`].
pub fn quiet_ok_timeout(program: &str, args: &[&str], timeout: Duration) -> bool {
    let mut cmd = Command::new(program);
    cmd.args(args).stdin(Stdio::null());
    run_bounded(cmd, timeout).map(|(status, _, _)| status.success()).unwrap_or(false)
}

fn trim_trailing_newlines(s: &mut String) {
    // Bash's `$(...)` strips trailing newlines; match that so callers that
    // parse or compare the captured text see what the bash port saw.
    while s.ends_with('\n') {
        s.pop();
    }
}

/// `out=$(cmd 2>/dev/null)`: stdout only, discarded on failure, trailing
/// newlines stripped. For calls whose bash original ignored stderr and
/// treated the result as absent on a nonzero exit.
pub fn quiet_stdout(program: &str, args: &[&str]) -> Option<String> {
    let out = Command::new(program).args(args).stdin(Stdio::null()).stderr(Stdio::null()).output().ok()?;
    if !out.status.success() {
        return None;
    }
    let mut s = String::from_utf8_lossy(&out.stdout).into_owned();
    trim_trailing_newlines(&mut s);
    Some(s)
}

/// `cmd >/dev/null 2>&1; rc=$?`: only whether it succeeded, for the bash
/// idiom `command -v x` / `git show-ref -q --verify ...`.
pub fn quiet_ok(program: &str, args: &[&str]) -> bool {
    Command::new(program)
        .args(args)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
}

/// `command -v <name>`: an executable file of that name on PATH.
pub fn on_path(name: &str) -> bool {
    use std::os::unix::fs::PermissionsExt;
    let Some(path) = std::env::var_os("PATH") else { return false };
    std::env::split_paths(&path).any(|dir| {
        std::fs::metadata(dir.join(name)).map(|m| m.is_file() && m.permissions().mode() & 0o111 != 0).unwrap_or(false)
    })
}

/// `cmd; rc=$?` with stdout and stderr passed through to this process's
/// own, for the steps whose git output the bash original let the operator
/// see. A command that cannot be spawned counts as failed.
pub fn status(program: &str, args: &[&str]) -> bool {
    Command::new(program).args(args).status().map(|s| s.success()).unwrap_or(false)
}

/// `cmd 2>/dev/null; rc=$?`: stdout passed through, stderr discarded.
pub fn quiet_stderr_ok(program: &str, args: &[&str]) -> bool {
    Command::new(program).args(args).stderr(Stdio::null()).status().map(|s| s.success()).unwrap_or(false)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn captures_stdout_on_success() {
        let out = run("printf", &["%s", "hello"]).unwrap();
        assert!(out.success);
        assert_eq!(out.combined, "hello");
    }

    #[test]
    fn captures_stderr_on_failure() {
        let out = run("sh", &["-c", "echo boom >&2; exit 1"]).unwrap();
        assert!(!out.success);
        assert_eq!(out.combined.trim(), "boom");
    }

    // These hang via a direct exec of `sleep`, not `sh -c "sleep 5"` — a
    // shell wrapper forks sleep as a grandchild it doesn't exec-replace, so
    // killing the shell leaves sleep holding the pipe open and the test
    // would still block on it. `herdr`/`git`/`gh`, the real callers, are
    // always direct execs with no shell in between, so this matches what
    // actually hangs in production.
    #[test]
    fn run_timeout_kills_a_hanging_child_instead_of_waiting_it_out() {
        use std::time::{Duration, Instant};
        let start = Instant::now();
        let out = run_timeout("sleep", &["5"], Duration::from_millis(200)).unwrap();
        assert!(start.elapsed() < Duration::from_secs(2), "waited {:?} past a 200ms timeout", start.elapsed());
        assert!(!out.success);
    }

    #[test]
    fn quiet_stdout_timeout_returns_none_on_a_hang_rather_than_the_bound_never_firing() {
        use std::time::{Duration, Instant};
        let start = Instant::now();
        let got = quiet_stdout_timeout("sleep", &["5"], Duration::from_millis(200));
        assert!(start.elapsed() < Duration::from_secs(2), "waited {:?} past a 200ms timeout", start.elapsed());
        assert_eq!(got, None);
    }

    #[test]
    fn quiet_ok_timeout_returns_false_on_a_hang() {
        use std::time::{Duration, Instant};
        let start = Instant::now();
        let got = quiet_ok_timeout("sleep", &["5"], Duration::from_millis(200));
        assert!(start.elapsed() < Duration::from_secs(2), "waited {:?} past a 200ms timeout", start.elapsed());
        assert!(!got);
    }

    #[test]
    fn run_timeout_still_captures_output_when_the_child_finishes_in_time() {
        use std::time::Duration;
        let out = run_timeout("printf", &["%s", "hello"], Duration::from_secs(5)).unwrap();
        assert!(out.success);
        assert_eq!(out.combined, "hello");
    }
}
