//! Controller→worker pairs (#964): `implement-dispatch` appends one record
//! per worker it starts, keyed to the controller's own session pid, so a
//! `SessionStart` hook can restore what a `/clear` wipes from context. A
//! `/clear` kills the context, not the process — the session's pid, and this
//! sibling file beside its `~/.claude/sessions/<pid>.json` record, survive it.
//! `merge-cleanup` removes the record for a workspace once it tears it down.

use serde::{Deserialize, Serialize};
use std::io::Write;
use std::path::{Path, PathBuf};

/// One dispatched worker, as the controller needs it back after a `/clear`:
/// enough to say what it is, what state to check, and how to clean it up —
/// never enough to re-send a brief, which this record plays no part in.
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct WorkerRecord {
    /// The herdr agent name the worker runs under.
    pub agent: String,
    /// Every ticket the brief named, lowest first — a clump's whole list.
    pub tickets: Vec<String>,
    pub branch: String,
    /// Absolute path to the worker's linked worktree.
    pub workspace: String,
    /// `owner/name` — what `gh pr list --repo` takes.
    pub repo: String,
    /// The full `cd ... && merge-cleanup ...` line, exactly as dispatch
    /// printed it in its own report.
    pub cleanup: String,
    pub chris_merges: bool,
    /// `date -u +%Y-%m-%dT%H:%M:%SZ` at dispatch time, or empty when that
    /// call failed — never fails the write over a clock it can't reach.
    pub dispatched_at: String,
}

/// The sibling file beside `<home>/.claude/sessions/<pid>.json` this
/// controller's dispatched workers are recorded in.
fn path_for(home: &Path, pid: &str) -> PathBuf {
    home.join(".claude/sessions").join(format!("{pid}.workers.jsonl"))
}

/// `date -u +%Y-%m-%dT%H:%M:%SZ`, or empty on any failure — `dispatched_at`
/// is informational, never worth failing a dispatch over.
pub fn now_iso8601() -> String {
    std::process::Command::new("date")
        .args(["-u", "+%Y-%m-%dT%H:%M:%SZ"])
        .output()
        .ok()
        .filter(|o| o.status.success())
        .map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string())
        .unwrap_or_default()
}

/// Appends one record for the controller session at `pid`. The file is
/// append-only JSONL, one record per dispatch — never rewritten here, so two
/// dispatches racing on the same controller each add their own line rather
/// than clobbering the other's.
/// One `write_all` call, not `writeln!`'s separate write of the line and
/// its `"\n"` (#964 correctness C4): a regular file opened with `O_APPEND`
/// gives each single `write(2)` call its own atomic offset bump on Linux, so
/// two dispatches racing on one controller each land their whole line
/// whole — two writes per append could interleave a line from each process
/// between the two, corrupting both, which `read`'s per-line parse would
/// then have silently dropped.
pub fn append(home: &Path, pid: &str, record: &WorkerRecord) -> std::io::Result<()> {
    let path = path_for(home, pid);
    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir)?;
    }
    let mut line = serde_json::to_string(record).map_err(std::io::Error::other)?;
    line.push('\n');
    let mut f = std::fs::OpenOptions::new().create(true).append(true).open(&path)?;
    f.write_all(line.as_bytes())
}

/// Every well-formed record for the controller session at `pid`, in the
/// order dispatch appended them. A malformed line is skipped rather than
/// failing the whole read — one bad line must not hide every other worker.
/// No file at all reads as no workers, the ordinary case for a session that
/// has never dispatched one.
pub fn read(home: &Path, pid: &str) -> Vec<WorkerRecord> {
    let path = path_for(home, pid);
    let Ok(raw) = std::fs::read_to_string(&path) else { return Vec::new() };
    raw.lines().filter(|l| !l.trim().is_empty()).filter_map(|l| serde_json::from_str(l).ok()).collect()
}

/// Removes every record naming `workspace`, across every controller's
/// `<pid>.workers.jsonl` under `<home>/.claude/sessions` — `merge-cleanup`
/// knows only the workspace path it just tore down, not which controller
/// dispatched it, or whether that controller's session is even still alive.
/// Returns whether anything was removed. A file with records left reads back
/// as those records, in their original order; a file rewritten empty is left
/// in place, not deleted, since another dispatch may still append to it. A
/// directory that cannot be listed removes nothing rather than erroring —
/// this is best-effort bookkeeping alongside the workspace's own removal, not
/// a step `merge-cleanup` can fail over.
pub fn remove_workspace(home: &Path, workspace: &str) -> bool {
    let dir = home.join(".claude/sessions");
    let Ok(entries) = std::fs::read_dir(&dir) else { return false };
    let mut removed_any = false;
    for entry in entries.filter_map(Result::ok) {
        let path = entry.path();
        if !path.file_name().and_then(|n| n.to_str()).is_some_and(|n| n.ends_with(".workers.jsonl")) {
            continue;
        }
        let Ok(raw) = std::fs::read_to_string(&path) else { continue };
        let mut kept: Vec<&str> = Vec::new();
        let mut changed = false;
        for line in raw.lines() {
            if line.trim().is_empty() {
                continue;
            }
            match serde_json::from_str::<WorkerRecord>(line) {
                Ok(r) if r.workspace == workspace => changed = true,
                _ => kept.push(line),
            }
        }
        if !changed {
            continue;
        }
        let mut out = kept.join("\n");
        if !out.is_empty() {
            out.push('\n');
        }
        if std::fs::write(&path, out).is_ok() {
            removed_any = true;
        }
    }
    removed_any
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    fn record(workspace: &str) -> WorkerRecord {
        WorkerRecord {
            agent: "sudokupad-art-143".into(),
            tickets: vec!["143".into()],
            branch: "implement-143".into(),
            workspace: workspace.into(),
            repo: "caneff/sudokupad-art".into(),
            cleanup: "cd /repo && merge-cleanup implement-143 --repo /repo".into(),
            chris_merges: false,
            dispatched_at: "2026-09-21T10:00:00Z".into(),
        }
    }

    #[test]
    fn append_then_read_round_trips() {
        let tmp = TempDir::new().unwrap();
        let home = tmp.path();
        append(home, "123", &record("/repo/.claude/worktrees/implement-143")).unwrap();
        let got = read(home, "123");
        assert_eq!(got, vec![record("/repo/.claude/worktrees/implement-143")]);
    }

    #[test]
    fn a_second_append_adds_a_second_line_rather_than_overwriting() {
        let tmp = TempDir::new().unwrap();
        let home = tmp.path();
        append(home, "123", &record("/repo/.claude/worktrees/implement-143")).unwrap();
        append(home, "123", &record("/repo/.claude/worktrees/implement-200")).unwrap();
        let got = read(home, "123");
        assert_eq!(got.len(), 2);
        assert_eq!(got[0].branch, "implement-143");
        assert_eq!(got[1].workspace, "/repo/.claude/worktrees/implement-200");
    }

    #[test]
    fn read_with_no_file_is_empty_and_a_malformed_line_is_skipped_not_fatal() {
        let tmp = TempDir::new().unwrap();
        let home = tmp.path();
        assert!(read(home, "999").is_empty());

        let path = path_for(home, "123");
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(&path, "not json\n{\"agent\":\"a\",\"tickets\":[\"1\"],\"branch\":\"implement-1\",\"workspace\":\"/w\",\"repo\":\"o/n\",\"cleanup\":\"c\",\"chris_merges\":false,\"dispatched_at\":\"\"}\n")
            .unwrap();
        let got = read(home, "123");
        assert_eq!(got.len(), 1);
        assert_eq!(got[0].agent, "a");
    }

    #[test]
    fn different_controllers_read_only_their_own_records() {
        let tmp = TempDir::new().unwrap();
        let home = tmp.path();
        append(home, "111", &record("/a")).unwrap();
        append(home, "222", &record("/b")).unwrap();
        assert_eq!(read(home, "111").len(), 1);
        assert_eq!(read(home, "222").len(), 1);
        assert_eq!(read(home, "111")[0].workspace, "/a");
    }

    #[test]
    fn remove_workspace_finds_and_removes_across_controllers() {
        let tmp = TempDir::new().unwrap();
        let home = tmp.path();
        append(home, "111", &record("/a")).unwrap();
        append(home, "111", &record("/b")).unwrap();
        append(home, "222", &record("/c")).unwrap();

        assert!(remove_workspace(home, "/b"));
        let left = read(home, "111");
        assert_eq!(left.len(), 1);
        assert_eq!(left[0].workspace, "/a");
        assert_eq!(read(home, "222").len(), 1, "an unrelated controller's records are untouched");
    }

    #[test]
    fn remove_workspace_with_no_match_is_false_and_leaves_files_untouched() {
        let tmp = TempDir::new().unwrap();
        let home = tmp.path();
        append(home, "111", &record("/a")).unwrap();
        assert!(!remove_workspace(home, "/nope"));
        assert_eq!(read(home, "111").len(), 1);
    }

    #[test]
    fn remove_workspace_with_no_sessions_dir_is_false() {
        let tmp = TempDir::new().unwrap();
        assert!(!remove_workspace(tmp.path(), "/anything"));
    }
}
