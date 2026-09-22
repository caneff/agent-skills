//! Controller→worker pairs (#964): `implement-dispatch` appends one record
//! per worker it starts, keyed to the controller's own session pid, so a
//! `SessionStart` hook can restore what a `/clear` wipes from context. A
//! `/clear` kills the context, not the process — the session's pid, and this
//! sibling file beside its `~/.claude/sessions/<pid>.json` record, survive it.
//! `merge-cleanup` removes the record for a workspace once it tears it down.

use serde::{Deserialize, Serialize};
use std::io::{Read, Seek, SeekFrom, Write};
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
    /// The controller session's own `/proc/<pid>/stat` starttime at dispatch
    /// time (#964 fix round 1, Codex high): pids are small and get reused,
    /// especially across a WSL restart, so a stale record from a dead
    /// controller must never restore into whatever session now holds that
    /// pid. `controller-restore` drops any record whose value here does not
    /// match the resuming session's own starttime. `#[serde(default)]` so a
    /// record written before this field existed decodes as empty rather than
    /// failing to parse — empty never matches a live starttime, so such a
    /// record is dropped as stale too, the conservative direction.
    #[serde(default)]
    pub proc_start: String,
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
///
/// Takes the same exclusive `File::lock()` as `remove_workspace`'s rewrite
/// (#964 fix round 1, Codex high): `O_APPEND` alone only protects one
/// `write(2)` from another; it does nothing against `remove_workspace`'s
/// read-filter-`fs::write` on the same file, which can land between this
/// call's open and its write and then get overwritten whole by the rewrite,
/// silently losing this record. The lock releases when `f` drops at the end
/// of this function.
pub fn append(home: &Path, pid: &str, record: &WorkerRecord) -> std::io::Result<()> {
    let path = path_for(home, pid);
    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir)?;
    }
    let mut line = serde_json::to_string(record).map_err(std::io::Error::other)?;
    line.push('\n');
    let mut f = std::fs::OpenOptions::new().create(true).append(true).open(&path)?;
    f.lock()?;
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

/// Normalizes a workspace path for storage in, or a query against, a
/// `WorkerRecord` (#1040). `implement-dispatch` builds this path itself with
/// `PathBuf::join`; `merge-cleanup` reads one back from `git worktree list`.
/// The two are independent construction sites, and a symlinked repo root
/// makes them spell the same directory two different ways, so
/// `remove_workspace`'s exact string compare misses the match and the
/// record survives cleanup silently. Both call sites run their path through
/// this shared normalizer instead of comparing raw strings. Falls back to
/// `path` verbatim when canonicalization fails — a workspace already torn
/// down (or one that never existed) still needs a usable compare key rather
/// than losing the value.
pub fn canonical_workspace_path(path: &str) -> String {
    std::fs::canonicalize(path).ok().map(|p| p.display().to_string()).unwrap_or_else(|| path.to_string())
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
///
/// Reads through the same exclusive `File::lock()` `append` takes, held for
/// the whole read-filter-rewrite (#964 fix round 1, Codex high): reading with
/// `fs::read_to_string` and writing with a separate `fs::write`, as an
/// earlier version of this did, opens a window between the two where a
/// concurrent `append` can land and then be silently discarded by this call's
/// rewrite. One `File` handle, locked before the read, holds that window
/// shut; the lock releases when the handle drops at the end of each loop
/// iteration. A file this run cannot open, lock or read is skipped rather
/// than erroring, matching every other best-effort failure mode here.
pub fn remove_workspace(home: &Path, workspace: &str) -> bool {
    let dir = home.join(".claude/sessions");
    let Ok(entries) = std::fs::read_dir(&dir) else { return false };
    let mut removed_any = false;
    for entry in entries.filter_map(Result::ok) {
        let path = entry.path();
        if !path.file_name().and_then(|n| n.to_str()).is_some_and(|n| n.ends_with(".workers.jsonl")) {
            continue;
        }
        let Ok(mut f) = std::fs::OpenOptions::new().read(true).write(true).open(&path) else { continue };
        if f.lock().is_err() {
            continue;
        }
        let mut raw = String::new();
        if f.read_to_string(&mut raw).is_err() {
            continue;
        }
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
        if f.set_len(0).is_ok() && f.seek(SeekFrom::Start(0)).is_ok() && f.write_all(out.as_bytes()).is_ok() {
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
            proc_start: "1234567".into(),
        }
    }

    /// #1040: `implement-dispatch` builds a workspace path itself
    /// (`PathBuf::join`), `merge-cleanup` reads one back from `git worktree
    /// list`, and a symlinked repo root makes the two spellings differ even
    /// though they name the same directory. `canonical_workspace_path` is
    /// the shared normalizer both call sites run through so they converge.
    #[test]
    fn canonical_workspace_path_matches_across_a_symlinked_root() {
        let tmp = TempDir::new().unwrap();
        let real = tmp.path().join("real");
        std::fs::create_dir_all(real.join("wt")).unwrap();
        let link = tmp.path().join("link");
        std::os::unix::fs::symlink(&real, &link).unwrap();

        let via_real = real.join("wt").display().to_string();
        let via_link = link.join("wt").display().to_string();
        assert_ne!(via_real, via_link, "the two spellings must differ for this test to mean anything");
        assert_eq!(canonical_workspace_path(&via_real), canonical_workspace_path(&via_link));
    }

    /// A path that does not exist (already torn down, or never real) is
    /// still usable as a compare key: canonicalization falls back to the
    /// string as given rather than losing the value.
    #[test]
    fn canonical_workspace_path_falls_back_when_the_path_is_gone() {
        assert_eq!(canonical_workspace_path("/no/such/path/at/all"), "/no/such/path/at/all");
    }

    /// The end-to-end case #1040 was filed over: a record stored under one
    /// spelling of a symlinked workspace is still found and removed when
    /// queried under the other spelling, once both sides canonicalize.
    #[test]
    fn remove_workspace_matches_a_symlinked_spelling_when_canonicalized() {
        let tmp = TempDir::new().unwrap();
        let real = tmp.path().join("real");
        std::fs::create_dir_all(real.join("wt")).unwrap();
        let link = tmp.path().join("link");
        std::os::unix::fs::symlink(&real, &link).unwrap();

        let home = tmp.path();
        let stored = canonical_workspace_path(&link.join("wt").display().to_string());
        append(home, "1", &record(&stored)).unwrap();

        let queried_raw = real.join("wt").display().to_string();
        assert!(remove_workspace(home, &canonical_workspace_path(&queried_raw)));
        assert!(read(home, "1").is_empty());
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
    fn a_record_written_before_proc_start_existed_decodes_with_it_empty() {
        let tmp = TempDir::new().unwrap();
        let home = tmp.path();
        let path = path_for(home, "123");
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(&path, "{\"agent\":\"a\",\"tickets\":[\"1\"],\"branch\":\"implement-1\",\"workspace\":\"/w\",\"repo\":\"o/n\",\"cleanup\":\"c\",\"chris_merges\":false,\"dispatched_at\":\"\"}\n").unwrap();
        let got = read(home, "123");
        assert_eq!(got.len(), 1);
        assert_eq!(got[0].proc_start, "", "a pre-#964-fix record has no proc_start to be stale-checked against");
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

    /// #964 fix round 1 (Codex high): `remove_workspace`'s read/filter/write
    /// and `append`'s write must serialize on the same file lock, or an
    /// append landing between the read and the write is silently lost. Holds
    /// an exclusive lock externally, proves neither call can finish while it
    /// is held — that is what makes the earlier version of both unlocked —
    /// then releases it and checks the racing append survived the rewrite.
    #[test]
    fn append_and_remove_serialize_on_the_file_lock_so_a_racing_append_is_never_lost() {
        let tmp = TempDir::new().unwrap();
        let home = tmp.path().to_path_buf();
        append(&home, "111", &record("/a")).unwrap();
        append(&home, "111", &record("/b")).unwrap();

        let path = path_for(&home, "111");
        let held = std::fs::OpenOptions::new().read(true).write(true).open(&path).unwrap();
        held.lock().unwrap();

        let (remove_done_tx, remove_done_rx) = std::sync::mpsc::channel();
        let h1 = home.clone();
        let remover = std::thread::spawn(move || {
            let removed = remove_workspace(&h1, "/b");
            let _ = remove_done_tx.send(());
            removed
        });

        let (append_done_tx, append_done_rx) = std::sync::mpsc::channel();
        let h2 = home.clone();
        let appender = std::thread::spawn(move || {
            append(&h2, "111", &record("/c")).unwrap();
            let _ = append_done_tx.send(());
        });

        // Neither can finish while this test holds the lock — proof both
        // the rewrite and the append go through it, not just one of them.
        assert!(remove_done_rx.recv_timeout(std::time::Duration::from_millis(300)).is_err(), "remove_workspace ran without the lock");
        assert!(append_done_rx.recv_timeout(std::time::Duration::from_millis(50)).is_err(), "append ran without the lock");

        drop(held);
        assert!(remover.join().unwrap());
        appender.join().unwrap();

        let left = read(&home, "111");
        let workspaces: Vec<&str> = left.iter().map(|r| r.workspace.as_str()).collect();
        assert!(workspaces.contains(&"/a"), "{workspaces:?}");
        assert!(workspaces.contains(&"/c"), "a racing append must survive a concurrent remove: {workspaces:?}");
        assert!(!workspaces.contains(&"/b"), "{workspaces:?}");
    }
}
