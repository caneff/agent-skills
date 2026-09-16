//! A command runner that reports a failed command's output, standing in for
//! the bash idiom `out=$(cmd 2>&1) || fail "$what" "$out"`. stdout and stderr
//! are captured separately (no pty) and concatenated stdout-then-stderr: every
//! caller here writes to exactly one of the two on any given run, so order
//! never matters in practice.

use std::io::Read;
use std::os::unix::process::CommandExt;
use std::path::Path;
use std::process::{Child, Command, ExitStatus, Stdio};
use std::sync::mpsc;
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

/// Extra grace given to the pipe-reading threads after the child itself is
/// bounded, on top of `timeout` — not part of it, since a well-behaved child
/// that exits in time still gets its full output read with no grace added.
/// Killing the direct child isn't enough to close its pipes: a child that
/// forks (rather than exec-replaces) leaves the fork holding the write end
/// open even after the direct child is dead, so `read_to_end` alone would
/// still block forever on it. Putting the child in its own process group and
/// killing the group on timeout handles that fork case; this grace is the
/// backstop for whatever still slips past that (a grandchild that further
/// escaped the group, e.g. via `setsid`).
const READ_GRACE: Duration = Duration::from_secs(2);

/// Runs `cmd` (stdin already the caller's concern; this always pipes stdout
/// and stderr) and kills it if it's still alive past `timeout` — the OS-level
/// bound none of the plain functions above have: a hung child otherwise
/// blocks `Command::output`/`status` forever, no matter what deadline the
/// caller thinks it's under. Reader threads drain both pipes concurrently so
/// a child that fills one pipe's buffer can't deadlock the wait; on timeout,
/// the child is placed in its own process group so the whole group (not
/// just the direct child) gets killed. Returns whether it timed out
/// alongside the exit status, since a killed child's status alone doesn't
/// say why it failed — a caller reporting to a person needs the "why."
fn run_bounded(mut cmd: Command, timeout: Duration) -> std::io::Result<(ExitStatus, Vec<u8>, Vec<u8>, bool)> {
    cmd.stdout(Stdio::piped()).stderr(Stdio::piped());
    // A new process group headed by the child's own pid: on timeout we can
    // signal the whole group, not just the one pid `Child::kill` reaches.
    cmd.process_group(0);
    let mut child = cmd.spawn()?;
    let stdout_pipe = child.stdout.take().expect("stdout is piped above");
    let stderr_pipe = child.stderr.take().expect("stderr is piped above");
    let stdout_rx = drain(stdout_pipe);
    let stderr_rx = drain(stderr_pipe);

    let (status, timed_out) = wait_bounded(&mut child, timeout)?;

    // Only past a timeout is there anything left in the group to still be
    // holding a pipe open; a child that exited on its own gets read with no
    // extra bound, however long that legitimately takes. One shared deadline
    // (not READ_GRACE applied to each of the two reads in turn) caps the
    // total added wait at READ_GRACE, not 2x it.
    let deadline = timed_out.then(|| Instant::now() + READ_GRACE);
    let stdout = recv_drained(stdout_rx, deadline);
    let stderr = recv_drained(stderr_rx, deadline);
    Ok((status, stdout, stderr, timed_out))
}

/// Spawns a thread draining `pipe` to EOF, handing the bytes back over a
/// channel rather than a `JoinHandle` so the receiver can bound how long it
/// waits without blocking on the thread's own lifetime. A pipe left stuck
/// open past that bound leaks this one thread — accepted, since the
/// alternative is the caller blocking on it instead.
fn drain(mut pipe: impl Read + Send + 'static) -> mpsc::Receiver<Vec<u8>> {
    let (tx, rx) = mpsc::channel();
    thread::spawn(move || {
        let mut buf = Vec::new();
        let _ = pipe.read_to_end(&mut buf);
        let _ = tx.send(buf);
    });
    rx
}

/// Reads the drained bytes, waiting at most until `deadline` —  `None` means
/// the child exited on its own, so there's no bound beyond the reader
/// thread's own EOF. A `Receiver` that never sends (a grandchild still
/// holding the pipe past `deadline`) yields empty rather than blocking the
/// caller forever. Called for stdout then stderr against the *same*
/// `deadline` (not a fresh `READ_GRACE` each time), so stdout using up the
/// whole grace leaves stderr's wait at zero rather than granting it another
/// full `READ_GRACE`.
fn recv_drained(rx: mpsc::Receiver<Vec<u8>>, deadline: Option<Instant>) -> Vec<u8> {
    match deadline {
        Some(d) => rx.recv_timeout(d.saturating_duration_since(Instant::now())).unwrap_or_default(),
        None => rx.recv().unwrap_or_default(),
    }
}

/// Polls `try_wait` until the child exits or `timeout` elapses, killing its
/// whole process group and reaping it on the latter. Returns whether it
/// timed out — a killed child's status alone is never success on Unix, but
/// nothing about the status itself says a bound fired rather than the
/// program simply failing.
fn wait_bounded(child: &mut Child, timeout: Duration) -> std::io::Result<(ExitStatus, bool)> {
    let start = Instant::now();
    loop {
        if let Some(status) = child.try_wait()? {
            return Ok((status, false));
        }
        if start.elapsed() >= timeout {
            // Negative pid signals the whole process group `process_group(0)`
            // above put this child in; `Child::kill` alone only reaches the
            // direct child, not anything it forked without exec-replacing.
            let _ = Command::new("kill").args(["-9", "--", &format!("-{}", child.id())]).status();
            return Ok((child.wait()?, true));
        }
        thread::sleep(TIMEOUT_POLL_INTERVAL);
    }
}

/// `run`, bounded: kills the child (and its process group) and fails the
/// call if it's still running past `timeout`, instead of blocking forever
/// on a hung subprocess.
pub fn run_timeout(program: &str, args: &[&str], timeout: Duration) -> std::io::Result<CommandOutput> {
    run_in_timeout(None, program, args, timeout)
}

/// `run_in`, bounded — see [`run_timeout`]. A timed-out call with nothing on
/// either stream says so in `combined`, rather than reporting "(no output)"
/// with no clue a bound ever fired.
pub fn run_in_timeout(dir: Option<&Path>, program: &str, args: &[&str], timeout: Duration) -> std::io::Result<CommandOutput> {
    let mut cmd = Command::new(program);
    cmd.args(args).stdin(Stdio::null());
    if let Some(d) = dir {
        cmd.current_dir(d);
    }
    let (status, stdout, stderr, timed_out) = run_bounded(cmd, timeout)?;
    let mut combined = String::from_utf8_lossy(&stdout).into_owned();
    combined.push_str(&String::from_utf8_lossy(&stderr));
    trim_trailing_newlines(&mut combined);
    if timed_out && combined.is_empty() {
        combined = format!("(no output; timed out after {timeout:?})");
    }
    Ok(CommandOutput { success: status.success(), combined })
}

/// `quiet_stdout`, bounded — see [`run_timeout`].
pub fn quiet_stdout_timeout(program: &str, args: &[&str], timeout: Duration) -> Option<String> {
    let mut cmd = Command::new(program);
    cmd.args(args).stdin(Stdio::null());
    let (status, stdout, _stderr, _timed_out) = run_bounded(cmd, timeout).ok()?;
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
    run_bounded(cmd, timeout).map(|(status, ..)| status.success()).unwrap_or(false)
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

    // Correctness review of #844: killing only the direct child leaves a
    // grandchild it forked (rather than exec-replaced) holding the pipe
    // open, so the reader thread's `read_to_end` never sees EOF and the
    // bound never actually fires. `sh -c "sleep 5 & wait"` reproduces that
    // shape on purpose (see the note above on why the other tests avoid it).
    #[test]
    fn run_timeout_does_not_hang_on_a_grandchild_still_holding_the_pipe_open() {
        use std::time::{Duration, Instant};
        let start = Instant::now();
        let out = run_timeout("sh", &["-c", "sleep 5 & wait"], Duration::from_millis(200)).unwrap();
        // Under 1s, not the READ_GRACE-sized 3s: a group kill that actually
        // reaches the grandchild closes the pipe almost immediately, so this
        // bound only passes when the process-group kill itself works —
        // loosening it to fit under READ_GRACE alone would let this test
        // keep passing with the group kill silently regressed to a no-op.
        assert!(start.elapsed() < Duration::from_secs(1), "waited {:?} past a 200ms timeout", start.elapsed());
        assert!(!out.success);
    }

    // Correctness review of #844: a killed child's combined output was
    // empty, so the operator saw "(no output)" with no clue a timeout ever
    // fired.
    #[test]
    fn run_timeout_says_it_timed_out_when_the_child_had_nothing_to_say() {
        use std::time::Duration;
        let out = run_timeout("sleep", &["5"], Duration::from_millis(200)).unwrap();
        assert!(!out.success);
        assert!(out.combined.to_lowercase().contains("timed out"), "combined was {:?}", out.combined);
    }

}
