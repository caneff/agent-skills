//! A command runner that reports a failed command's output, standing in for
//! the bash idiom `out=$(cmd 2>&1) || fail "$what" "$out"`. stdout and stderr
//! are captured separately (no pty) and concatenated stdout-then-stderr: every
//! caller here writes to exactly one of the two on any given run, so order
//! never matters in practice.

use std::path::Path;
use std::process::{Command, Stdio};

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
}
