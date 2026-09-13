//! Reads `/proc/<pid>/stat` for liveness and ancestry, replacing the bash
//! ancestor walk. No `nix`/`libc`: plain file reads, matching the ruling that
//! `/proc` answers liveness.

use std::fs;

pub struct ProcStat {
    pub ppid: i32,
    /// Field 22, starttime, kept as the raw string bash compares against
    /// (a session file's `procStart`).
    pub start: String,
}

/// Parses `/proc/<pid>/stat`, cutting through the `(comm)` field the same
/// way the bash version does (`${stat##*) }`) since a process name can hold
/// spaces or parentheses.
pub fn read_stat(pid: i32) -> Option<ProcStat> {
    let raw = fs::read_to_string(format!("/proc/{pid}/stat")).ok()?;
    let after_comm = raw.rsplit_once(") ")?.1;
    let fields: Vec<&str> = after_comm.split_whitespace().collect();
    // fields[0] is state; fields[1] ppid; fields[19] starttime.
    let ppid: i32 = fields.get(1)?.parse().ok()?;
    let start = fields.get(19)?.to_string();
    Some(ProcStat { ppid, start })
}

pub fn parent_pid(pid: i32) -> Option<i32> {
    read_stat(pid).map(|s| s.ppid)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reads_own_stat() {
        let pid = std::process::id() as i32;
        let stat = read_stat(pid).expect("read /proc/self equivalent");
        assert!(stat.ppid > 0);
        assert!(!stat.start.is_empty());
    }

    #[test]
    fn parent_pid_of_self_matches_getppid_via_proc_self_status() {
        let pid = std::process::id() as i32;
        let ppid = parent_pid(pid).unwrap();
        let status = fs::read_to_string("/proc/self/status").unwrap();
        let line = status.lines().find(|l| l.starts_with("PPid:")).unwrap();
        let expected: i32 = line.split_whitespace().nth(1).unwrap().parse().unwrap();
        assert_eq!(ppid, expected);
    }

    #[test]
    fn unknown_pid_is_none() {
        assert!(read_stat(i32::MAX).is_none());
    }
}
