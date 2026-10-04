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
/// (#849 Codex gate on PR #1195): the read side was bounded only past a
/// timeout of the *direct* child — a child that exits on its own but backgrounds
/// a descendant still holding stdout/stderr open (a hook that forks a daemon,
/// e.g.) left `recv_drained`'s bare `rx.recv()` blocking forever, with no
/// timeout ever having fired to explain it. The drain deadline now applies
/// unconditionally, whether or not the direct child itself timed out — but
/// the process-group kill stays timeout-only: a child that exited on its own
/// may have legitimately started a long-lived process (`herdr` launched by a
/// hook) that is not this call's to kill just because its own pipe is still
/// open.
fn run_bounded(mut cmd: Command, timeout: Duration) -> std::io::Result<(ExitStatus, Vec<u8>, Vec<u8>, bool, bool)> {
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

    // One shared deadline (not READ_GRACE applied to each of the two reads in
    // turn) caps the total added wait at READ_GRACE, not 2x it — for either
    // path, timed out or not.
    let deadline = Instant::now() + READ_GRACE;
    let (stdout, stdout_eof) = recv_drained(stdout_rx, deadline);
    let (stderr, stderr_eof) = recv_drained(stderr_rx, deadline);
    Ok((status, stdout, stderr, timed_out, !(stdout_eof && stderr_eof)))
}

/// Spawns a thread draining `pipe`, sending each new chunk once — never the
/// whole buffer read so far — so the channel's queue stays linear in the
/// bytes read rather than quadratic (#849 Codex second pass on PR #1195:
/// sending `buf.clone()` per chunk, with nothing consuming the channel until
/// the child exits, queued O(n) snapshots of up to O(n) bytes each — roughly
/// 4 GiB queued for 8 MiB of real output). The receiver accumulates the
/// chunks itself. The bool is whether this is the final message (the pipe
/// reached EOF or errored); a pipe left stuck open past the receiver's
/// deadline leaks this one thread — accepted, since the alternative is the
/// caller blocking on it instead.
fn drain(mut pipe: impl Read + Send + 'static) -> mpsc::Receiver<(Vec<u8>, bool)> {
    let (tx, rx) = mpsc::channel();
    thread::spawn(move || {
        let mut chunk = [0u8; 8192];
        loop {
            match pipe.read(&mut chunk) {
                Ok(0) => {
                    let _ = tx.send((Vec::new(), true));
                    return;
                }
                Ok(n) => {
                    if tx.send((chunk[..n].to_vec(), false)).is_err() {
                        return; // receiver gave up past its deadline
                    }
                }
                Err(_) => {
                    let _ = tx.send((Vec::new(), true));
                    return;
                }
            }
        }
    });
    rx
}

/// Reads from `rx` until it reports EOF or `deadline` passes, accumulating
/// every chunk it sends, and returning what was read so far either way, plus
/// whether that read is complete (EOF reached) — `false` means a descendant
/// is still holding the pipe open past `deadline`, and the caller must say
/// so rather than silently returning a possibly-partial read as if it were
/// complete.
fn recv_drained(rx: mpsc::Receiver<(Vec<u8>, bool)>, deadline: Instant) -> (Vec<u8>, bool) {
    let mut buf = Vec::new();
    loop {
        // `recv_timeout(0)` still returns queued chunks, so a descendant that
        // keeps writing would hold this loop past the deadline: stop on the
        // clock, not on an empty queue.
        let now = Instant::now();
        if now >= deadline {
            return take_queued(rx, buf);
        }
        match rx.recv_timeout(deadline - now) {
            Ok((chunk, true)) => {
                buf.extend_from_slice(&chunk);
                return (buf, true);
            }
            Ok((chunk, false)) => buf.extend_from_slice(&chunk),
            Err(_) => return (buf, false), // deadline elapsed, or the sender is gone
        }
    }
}

/// At most this many chunks already queued are still taken once the deadline
/// has passed (`drain` sends 8 KiB at most, so 2 MiB): the two pipes share one
/// deadline and stdout is read first, so without it a slow stdout would cost
/// the direct child's stderr, its error message included. The cap is what
/// keeps a descendant that never stops writing from extending the read.
const POST_DEADLINE_CHUNKS: usize = 256;

fn take_queued(rx: mpsc::Receiver<(Vec<u8>, bool)>, mut buf: Vec<u8>) -> (Vec<u8>, bool) {
    for _ in 0..POST_DEADLINE_CHUNKS {
        match rx.try_recv() {
            Ok((chunk, eof)) => {
                buf.extend_from_slice(&chunk);
                if eof {
                    return (buf, true);
                }
            }
            Err(_) => break,
        }
    }
    (buf, false)
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
            // With no `kill` on PATH, or one that failed, `Child::kill` is the
            // fallback: the direct child at least, or the wait below has no
            // bound at all (#1406 C6).
            let grouped = Command::new("kill")
                .args(["-9", "--", &format!("-{}", child.id())])
                .status()
                .is_ok_and(|s| s.success());
            if !grouped {
                let _ = child.kill();
            }
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

/// `run_in`, bounded — see [`run_timeout`]. A timed-out call says so in
/// `combined`, with or without output, rather than reporting an ordinary
/// failure with no clue a bound ever fired.
pub fn run_in_timeout(dir: Option<&Path>, program: &str, args: &[&str], timeout: Duration) -> std::io::Result<CommandOutput> {
    let mut cmd = Command::new(program);
    cmd.args(args).stdin(Stdio::null());
    if let Some(d) = dir {
        cmd.current_dir(d);
    }
    let (status, stdout, stderr, timed_out, truncated) = run_bounded(cmd, timeout)?;
    let mut combined = String::from_utf8_lossy(&stdout).into_owned();
    combined.push_str(&String::from_utf8_lossy(&stderr));
    trim_trailing_newlines(&mut combined);
    if timed_out {
        if combined.is_empty() {
            combined = format!("(no output; timed out after {timeout:?})");
        } else {
            combined.push_str(&format!(" (timed out after {timeout:?})"));
        }
    }
    if truncated {
        // The direct child exited (or was killed on timeout) but a
        // descendant is still holding a pipe open past READ_GRACE — the
        // bytes above are whatever was read before that, not necessarily
        // everything the command would eventually have written.
        combined.push_str(&format!(" (output truncated: a descendant is still holding a pipe open past {READ_GRACE:?})"));
    }
    Ok(CommandOutput { success: status.success(), combined })
}

/// One bounded quiet run: what [`run_bounded`] returned for a command with
/// stdin closed, or the error naming the command when it could not start.
struct Quiet {
    status: ExitStatus,
    stdout: Vec<u8>,
    stderr: Vec<u8>,
    timed_out: bool,
    truncated: bool,
    /// `program arg arg`, and the bound it ran under: what an error names.
    command: String,
    timeout: Duration,
}

fn run_quiet(program: &str, args: &[&str], timeout: Duration) -> Result<Quiet, String> {
    let mut cmd = Command::new(program);
    cmd.args(args).stdin(Stdio::null());
    let command = format!("{program} {}", args.join(" "));
    let (status, stdout, stderr, timed_out, truncated) = run_bounded(cmd, timeout).map_err(|e| format!("{command}: {e}"))?;
    Ok(Quiet { status, stdout, stderr, timed_out, truncated, command, timeout })
}

impl Quiet {
    /// The error a caller that must tell a genuine "no" from the bound
    /// firing returns instead of an answer, or `None` when the run was
    /// complete. A child that exited while a descendant still held a pipe
    /// open past READ_GRACE (a hook backgrounding a daemon, e.g.) gives a
    /// possibly partial read, which must not be handed back as the
    /// command's real answer.
    fn incomplete(&self) -> Option<String> {
        if self.timed_out {
            return Some(format!("{} timed out after {:?}", self.command, self.timeout));
        }
        if self.truncated {
            return Some(format!(
                "{}: a descendant is still holding a pipe open past {READ_GRACE:?}; the read may be incomplete",
                self.command
            ));
        }
        None
    }

    fn text(&self) -> String {
        let mut s = String::from_utf8_lossy(&self.stdout).into_owned();
        trim_trailing_newlines(&mut s);
        s
    }
}

/// `quiet_stdout`, bounded — see [`run_timeout`].
pub fn quiet_stdout_timeout(program: &str, args: &[&str], timeout: Duration) -> Option<String> {
    let run = run_quiet(program, args, timeout).ok()?;
    run.status.success().then(|| run.text())
}

/// `quiet_ok`, bounded — see [`run_timeout`].
pub fn quiet_ok_timeout(program: &str, args: &[&str], timeout: Duration) -> bool {
    run_quiet(program, args, timeout).map(|run| run.status.success()).unwrap_or(false)
}

/// Bounded read whose caller must be able to tell a genuine "no" — the
/// command ran, exited non-zero or produced nothing — from the bound
/// firing: unlike [`quiet_stdout_timeout`], which folds both into `None`,
/// indistinguishable from a completed command's own negative answer.
/// `Ok(None)` is the real negative a caller may read as a fact (no such
/// ref, no origin remote); `Err` names the program and its arguments and
/// must never be read that way (#849).
pub fn quiet_stdout_bounded(program: &str, args: &[&str], timeout: Duration) -> Result<Option<String>, String> {
    let run = run_quiet(program, args, timeout)?;
    if let Some(err) = run.incomplete() {
        return Err(err);
    }
    Ok(run.status.success().then(|| run.text()))
}

/// [`quiet_stdout_bounded`] for a caller that has no negative answer to
/// read: a command that ran and exited non-zero is an `Err` too, carrying the
/// command's own stderr, so the refusal names why instead of a guess.
pub fn stdout_bounded(program: &str, args: &[&str], timeout: Duration) -> Result<String, String> {
    let run = run_quiet(program, args, timeout)?;
    if let Some(err) = run.incomplete() {
        return Err(err);
    }
    if !run.status.success() {
        return Err(format!("{} failed: {}", run.command, String::from_utf8_lossy(&run.stderr).trim()));
    }
    Ok(run.text())
}

/// Bounded existence-style check whose caller must be able to tell a
/// genuine "no" from the bound firing — see [`quiet_stdout_bounded`]. Only
/// the exit status is the answer here, but a pipe still open past READ_GRACE
/// means a descendant is still running: the same uncertainty applies.
pub fn quiet_ok_bounded(program: &str, args: &[&str], timeout: Duration) -> Result<bool, String> {
    let run = run_quiet(program, args, timeout)?;
    match run.incomplete() {
        Some(err) => Err(err),
        None => Ok(run.status.success()),
    }
}

/// [`quiet_ok_bounded`] for a caller that reads the exit code itself
/// (`git ls-remote --exit-code`, whose 2 is "no such ref"). `Ok(None)` is a
/// child killed by a signal it was not sent here.
pub fn quiet_code_bounded(program: &str, args: &[&str], timeout: Duration) -> Result<Option<i32>, String> {
    let run = run_quiet(program, args, timeout)?;
    match run.incomplete() {
        Some(err) => Err(err),
        None => Ok(run.status.code()),
    }
}

/// [`status`], bounded: stdin, stderr and (unless `drop_stdout`) stdout are
/// this process's own, so the operator sees the command's output as it runs,
/// and the child's process group is killed past `timeout`. Its own group
/// means a command reading the terminal (a credential prompt) is stopped
/// rather than answered, and so fails at the bound; and Ctrl-C reaches this
/// process but not the child, which is left running. Both are accepted
/// costs of a bound that can kill the whole group (#1406 C6). `Err` names
/// the command and why: it timed out, or it could not be spawned.
pub fn status_bounded(program: &str, args: &[&str], drop_stdout: bool, timeout: Duration) -> Result<bool, String> {
    let command = format!("{program} {}", args.join(" "));
    let mut cmd = Command::new(program);
    cmd.args(args).process_group(0);
    if drop_stdout {
        cmd.stdout(Stdio::null());
    }
    let mut child = cmd.spawn().map_err(|e| format!("{command}: {e}"))?;
    match wait_bounded(&mut child, timeout).map_err(|e| format!("{command}: {e}"))? {
        (_, true) => Err(format!("{command} timed out after {timeout:?}")),
        (status, false) => Ok(status.success()),
    }
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

    // Codex gate on PR #1195 (#849): the direct child here exits almost
    // immediately with status 0, but backgrounds a descendant that holds
    // stderr open for far longer than this call's own `timeout` — before
    // the fix, `recv_drained`'s unconditional `rx.recv()` on the
    // non-timed-out path blocked on that descendant forever. Bounded by
    // READ_GRACE now, whether or not the direct child itself timed out.
    #[test]
    fn run_timeout_does_not_hang_forever_when_a_normally_exiting_child_backgrounds_a_pipe_holding_descendant() {
        use std::time::{Duration, Instant};
        let start = Instant::now();
        let out = run_timeout("sh", &["-c", "sleep 60 >&2 & exit 0"], Duration::from_secs(5)).unwrap();
        assert!(start.elapsed() < Duration::from_secs(4), "waited {:?} for a child that exited on its own", start.elapsed());
        assert!(out.success, "the direct child's own successful exit must still be reported: {:?}", out.combined);
        assert!(out.combined.to_lowercase().contains("truncated"), "combined was {:?}", out.combined);
    }

    // #1209 codex-third-2: a child that printed something and then hung was
    // reported as an ordinary failure carrying only its output; the timeout
    // was named only when there was no output at all.
    #[test]
    fn run_timeout_names_the_timeout_even_when_the_child_printed_first() {
        use std::time::Duration;
        let out = run_timeout("sh", &["-c", "echo partial; sleep 5"], Duration::from_millis(200)).unwrap();
        assert!(!out.success);
        assert!(out.combined.contains("partial"), "captured output was dropped: {:?}", out.combined);
        assert!(out.combined.to_lowercase().contains("timed out"), "combined was {:?}", out.combined);
    }

    // #1209 codex-third-1: after the drain deadline `recv_timeout(0)` still
    // hands back every queued chunk, so a descendant that keeps writing kept
    // the loop running past READ_GRACE. Driven at the function, with the
    // deadline already past: an end-to-end writer fast enough to show it would
    // hold gigabytes in memory for the whole grace.
    #[test]
    fn recv_drained_reads_a_bounded_amount_past_the_deadline_however_much_is_queued() {
        use std::time::{Duration, Instant};
        let (tx, rx) = mpsc::channel();
        for _ in 0..(POST_DEADLINE_CHUNKS * 4) {
            tx.send((vec![b'x'; 8], false)).unwrap();
        }
        let past = Instant::now() - Duration::from_millis(1);
        let (buf, eof) = recv_drained(rx, past);
        assert!(!eof, "a read cut by the deadline must not claim EOF");
        assert_eq!(buf.len(), POST_DEADLINE_CHUNKS * 8, "the post-deadline read must stop at its cap");
        drop(tx);
    }

    // #1209 spec P1: stdout is read first and can spend the shared deadline;
    // what the direct child already wrote to stderr is still queued and kept.
    #[test]
    fn recv_drained_keeps_what_was_already_queued_when_the_deadline_has_passed() {
        use std::time::{Duration, Instant};
        let (tx, rx) = mpsc::channel();
        tx.send((b"boom: the error".to_vec(), false)).unwrap();
        let past = Instant::now() - Duration::from_millis(1);
        let (buf, eof) = recv_drained(rx, past);
        assert_eq!(buf, b"boom: the error");
        assert!(!eof);
        drop(tx);
    }

    // Codex second pass on PR #1195 (#849): `drain` used to send a clone of
    // the whole buffer-so-far on every 8 KiB chunk, and nothing consumed the
    // channel until the child exited — several MiB of real output queued
    // roughly its square in bytes. This drains within the timeout and gets
    // every byte back; the mutation check (revert `drain` to send
    // `buf.clone()`) is what actually proves the growth was quadratic, since
    // a small size alone wouldn't show it.
    #[test]
    fn run_timeout_drains_several_megabytes_without_quadratic_blowup() {
        use std::time::{Duration, Instant};
        let start = Instant::now();
        let out = run_timeout("sh", &["-c", "head -c 16777216 /dev/zero"], Duration::from_secs(10)).unwrap();
        assert!(out.success, "combined length was {}", out.combined.len());
        assert_eq!(out.combined.len(), 16_777_216, "expected exactly 16 MiB back");
        assert!(start.elapsed() < Duration::from_secs(5), "waited {:?} to drain 16 MiB", start.elapsed());
    }

    // #849: a bounded query must fail loud when the bound fires, never
    // fold that into the same `None`/`false` a completed command's own
    // negative answer produces.
    #[test]
    fn quiet_stdout_bounded_errs_on_a_hang_instead_of_returning_none() {
        use std::time::Duration;
        let got = quiet_stdout_bounded("sleep", &["5"], Duration::from_millis(200));
        assert!(got.is_err(), "expected Err on a hang, got {got:?}");
        assert!(got.unwrap_err().to_lowercase().contains("timed out"));
    }

    #[test]
    fn quiet_stdout_bounded_returns_none_on_a_real_failure() {
        use std::time::Duration;
        let got = quiet_stdout_bounded("sh", &["-c", "exit 1"], Duration::from_secs(5));
        assert_eq!(got, Ok(None));
    }

    #[test]
    fn quiet_stdout_bounded_returns_the_output_on_success() {
        use std::time::Duration;
        let got = quiet_stdout_bounded("printf", &["%s", "hello"], Duration::from_secs(5));
        assert_eq!(got, Ok(Some("hello".to_string())));
    }

    #[test]
    fn stdout_bounded_carries_the_commands_own_stderr_on_a_non_zero_exit() {
        let got = stdout_bounded("sh", &["-c", "echo boom >&2; exit 3"], Duration::from_secs(5));
        let err = got.unwrap_err();
        assert!(err.contains("failed: boom"), "{err}");
    }

    #[test]
    fn quiet_ok_bounded_errs_on_a_hang_instead_of_returning_false() {
        use std::time::Duration;
        let got = quiet_ok_bounded("sleep", &["5"], Duration::from_millis(200));
        assert!(got.is_err(), "expected Err on a hang, got {got:?}");
        assert!(got.unwrap_err().to_lowercase().contains("timed out"));
    }

    #[test]
    fn quiet_ok_bounded_returns_false_on_a_real_failure() {
        use std::time::Duration;
        assert_eq!(quiet_ok_bounded("sh", &["-c", "exit 1"], Duration::from_secs(5)), Ok(false));
    }

    #[test]
    fn quiet_ok_bounded_returns_true_on_success() {
        use std::time::Duration;
        assert_eq!(quiet_ok_bounded("true", &[], Duration::from_secs(5)), Ok(true));
    }
}
