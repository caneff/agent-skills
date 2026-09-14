//! Stdout writes that exit quietly instead of panicking when the pipe
//! closes early (#758). `println!`/`print!` panic on a write error because
//! Rust ignores SIGPIPE; piped into `head` or a `less` quit before EOF, the
//! next one panics with "failed printing to stdout: Broken pipe" and exits
//! 101. The bash predecessor this replaced died of SIGPIPE (exit 141)
//! silently at the same point — match that number, not the panic.

use std::io::Write;

/// Exit code for a write that failed because stdout closed underneath us:
/// 128 + SIGPIPE (13), what a shell reports for a process the pipe killed.
pub const BROKEN_PIPE_EXIT: i32 = 141;

/// Writes to stdout, or exits immediately if the write fails. A closed pipe
/// exits quietly with no panic text; any other write error (a full disk, a
/// disconnected terminal) is still worth a diagnostic, so it gets one on
/// stderr before exiting. Never call directly — use `safe_print!`/`safe_println!`.
pub fn write_stdout(args: std::fmt::Arguments) {
    if let Err(e) = std::io::stdout().lock().write_fmt(args) {
        if e.kind() != std::io::ErrorKind::BrokenPipe {
            eprintln!("stdout write failed: {e}");
        }
        std::process::exit(BROKEN_PIPE_EXIT);
    }
}

/// `print!`, but exits quietly instead of panicking on a closed stdout.
#[macro_export]
macro_rules! safe_print {
    ($($arg:tt)*) => {
        $crate::io_safe::write_stdout(format_args!($($arg)*))
    };
}

/// `println!`, but exits quietly instead of panicking on a closed stdout.
#[macro_export]
macro_rules! safe_println {
    () => {
        $crate::safe_print!("\n")
    };
    ($($arg:tt)*) => {
        $crate::io_safe::write_stdout(format_args!("{}\n", format_args!($($arg)*)))
    };
}
