//! The sessions-registry reader: `~/.claude/sessions/<pid>.json`, one file
//! per Claude session. `implement-dispatch` walks `/proc` ancestry for its
//! controller's name; `merge-cleanup` lists the live sessions in a worktree.

use crate::proc_info::read_stat;
use std::path::Path;

/// A registry session whose pid is alive.
pub struct LiveSession {
    pub pid: String,
    /// The Claude sessionId, empty when the file has none.
    pub session_id: String,
    /// The Claude session name (`~/.claude/sessions/<pid>.json`'s `name`),
    /// empty when the file has none.
    pub name: String,
    /// The session's working directory, empty when the file has none.
    pub cwd: String,
}

/// Whether `path` is `root` or inside it.
pub fn in_tree(path: &str, root: &str) -> bool {
    format!("{path}/").starts_with(&format!("{root}/"))
}

/// Whether a registry record's `procStart` field matches `stat`, the pid's
/// own `/proc/<pid>/stat` — a record with no `procStart`, or one whose
/// starttime doesn't match, is stale: left by a dead session whose pid has
/// since been reused by an unrelated process.
fn proc_start_matches(record: &serde_json::Value, stat: &crate::proc_info::ProcStat) -> bool {
    record.get("procStart").and_then(|p| p.as_str()) == Some(stat.start.as_str())
}

/// Every registry file under `<home>/.claude/sessions` whose `cwd` is in
/// `worktree` and whose pid is alive with a `procStart` matching that pid's
/// own `/proc/<pid>/stat` starttime — a dead pid is a crashed session, and a
/// pid whose starttime doesn't match is a stale record whose pid has since
/// been reused by an unrelated process; both are ignored. Files in name
/// order; unreadable files are skipped.
pub fn live_in(home: &Path, worktree: &str) -> Vec<LiveSession> {
    live_all(home).into_iter().filter(|s| in_tree(&s.cwd, worktree)).collect()
}

/// Every live registry session, by the same liveness test as `live_in`.
pub fn live_all(home: &Path) -> Vec<LiveSession> {
    let Ok(dir) = std::fs::read_dir(home.join(".claude/sessions")) else { return Vec::new() };
    let mut files: Vec<_> = dir
        .filter_map(Result::ok)
        .map(|e| e.path())
        .filter(|p| p.extension().is_some_and(|x| x == "json") && !p.file_name().unwrap().to_string_lossy().starts_with('.'))
        .collect();
    files.sort();
    let mut live = Vec::new();
    for f in files {
        let Some(v) = std::fs::read_to_string(&f).ok().and_then(|raw| serde_json::from_str::<serde_json::Value>(&raw).ok()) else {
            continue;
        };
        let pid = match v.get("pid") {
            Some(serde_json::Value::Number(n)) => n.to_string(),
            Some(serde_json::Value::String(s)) => s.clone(),
            _ => continue,
        };
        let cwd = v.get("cwd").and_then(|c| c.as_str()).unwrap_or("").to_string();
        let alive = pid.parse::<i32>().is_ok_and(|p| p > 0 && read_stat(p).is_some_and(|stat| proc_start_matches(&v, &stat)));
        if !pid.is_empty() && alive {
            let session_id = v.get("sessionId").and_then(|s| s.as_str()).unwrap_or("").to_string();
            let name = v.get("name").and_then(|s| s.as_str()).unwrap_or("").to_string();
            live.push(LiveSession { pid, session_id, name, cwd });
        }
    }
    live
}

/// Walks up from `start_ancestor`, looking for `<home>/.claude/sessions/<pid>.json`
/// whose `procStart` matches that pid's own `/proc/<pid>/stat` starttime — a
/// file left by a dead session whose pid was reused has another procStart.
/// Stops (returns `None`) once `/proc/<pid>/stat` can no longer be read, or
/// once pid 1 is reached.
pub fn find_controller(home: &Path, start_ancestor: i32) -> Option<String> {
    find_controller_session(home, start_ancestor).map(|(_, name)| name)
}

/// `find_controller`, with the Claude sessionId beside the name (empty when
/// the record has none) — the key a herdr agent's `agent_session.value` joins on.
pub fn find_controller_session(home: &Path, start_ancestor: i32) -> Option<(String, String)> {
    let mut ancestor = start_ancestor;
    while ancestor > 1 {
        let stat = read_stat(ancestor)?;
        let session_file = home.join(".claude/sessions").join(format!("{ancestor}.json"));
        if let Ok(raw) = std::fs::read_to_string(&session_file) {
            if let Ok(v) = serde_json::from_str::<serde_json::Value>(&raw) {
                if proc_start_matches(&v, &stat) {
                    if let Some(name) = v.get("name").and_then(|n| n.as_str()) {
                        if !name.is_empty() {
                            let id = v.get("sessionId").and_then(|s| s.as_str()).unwrap_or("");
                            return Some((id.to_string(), name.to_string()));
                        }
                    }
                }
            }
        }
        ancestor = stat.ppid;
    }
    None
}

/// The current name of the live session `id`, the second hop of a herdr
/// agent name's resolution. `None` when no live record carries that id or
/// the record has no name.
pub fn name_of_session(home: &Path, id: &str) -> Option<String> {
    if id.is_empty() {
        return None;
    }
    live_all(home).into_iter().find(|s| s.session_id == id && !s.name.is_empty()).map(|s| s.name)
}

/// Whether a live session is currently named `name`.
pub fn is_live_name(home: &Path, name: &str) -> bool {
    live_all(home).iter().any(|s| s.name == name)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::proc_info::read_stat;
    use tempfile::TempDir;

    #[test]
    fn live_in_ignores_a_record_whose_pid_was_reused() {
        let tmp = TempDir::new().unwrap();
        let home = tmp.path();
        let pid = std::process::id() as i32;
        std::fs::create_dir_all(home.join(".claude/sessions")).unwrap();
        // pid is alive (it's this test process), but the recorded procStart
        // doesn't match this pid's actual starttime — the record is stale,
        // left by a dead session whose pid has since been reused.
        std::fs::write(
            home.join(".claude/sessions").join(format!("{pid}.json")),
            format!(r#"{{"pid":{pid},"procStart":"not-the-real-start","cwd":"/work/tree","name":"stale"}}"#),
        )
        .unwrap();
        let live = live_in(home, "/work/tree");
        assert!(live.is_empty(), "stale record with mismatched procStart must not count as live");
    }

    #[test]
    fn live_in_counts_a_record_whose_procstart_matches() {
        let tmp = TempDir::new().unwrap();
        let home = tmp.path();
        let pid = std::process::id() as i32;
        let stat = read_stat(pid).unwrap();
        std::fs::create_dir_all(home.join(".claude/sessions")).unwrap();
        std::fs::write(
            home.join(".claude/sessions").join(format!("{pid}.json")),
            format!(r#"{{"pid":{pid},"procStart":"{}","cwd":"/work/tree","name":"live"}}"#, stat.start),
        )
        .unwrap();
        let live = live_in(home, "/work/tree");
        assert_eq!(live.len(), 1);
        assert_eq!(live[0].name, "live");
    }

    #[test]
    fn finds_the_controller_named_by_its_own_procstart() {
        let tmp = TempDir::new().unwrap();
        let home = tmp.path();
        let pid = std::process::id() as i32;
        let stat = read_stat(pid).unwrap();
        std::fs::create_dir_all(home.join(".claude/sessions")).unwrap();
        std::fs::write(
            home.join(".claude/sessions").join(format!("{pid}.json")),
            format!(r#"{{"pid":{pid},"procStart":"{}","name":"skills-ctl"}}"#, stat.start),
        )
        .unwrap();
        assert_eq!(find_controller(home, pid).as_deref(), Some("skills-ctl"));
    }

    #[test]
    fn skips_a_session_file_whose_procstart_does_not_match() {
        let tmp = TempDir::new().unwrap();
        let home = tmp.path();
        let pid = std::process::id() as i32;
        std::fs::create_dir_all(home.join(".claude/sessions")).unwrap();
        std::fs::write(
            home.join(".claude/sessions").join(format!("{pid}.json")),
            r#"{"pid":1,"procStart":"1","name":"skills-ctl"}"#,
        )
        .unwrap();
        // Walking from pid climbs to pid 1 with no match anywhere.
        assert_eq!(find_controller(home, pid), None);
    }

    #[test]
    fn no_session_file_anywhere_is_none() {
        let tmp = TempDir::new().unwrap();
        let pid = std::process::id() as i32;
        assert_eq!(find_controller(tmp.path(), pid), None);
    }

    #[test]
    fn name_of_session_reads_the_current_name_of_a_live_session_id() {
        let tmp = TempDir::new().unwrap();
        let home = tmp.path();
        let pid = std::process::id() as i32;
        let stat = read_stat(pid).unwrap();
        std::fs::create_dir_all(home.join(".claude/sessions")).unwrap();
        std::fs::write(
            home.join(".claude/sessions").join(format!("{pid}.json")),
            format!(r#"{{"pid":{pid},"sessionId":"sid-1","procStart":"{}","name":"ctl-50"}}"#, stat.start),
        )
        .unwrap();
        assert_eq!(name_of_session(home, "sid-1").as_deref(), Some("ctl-50"));
        assert_eq!(name_of_session(home, "sid-2"), None);
        assert_eq!(name_of_session(home, ""), None);
        assert!(is_live_name(home, "ctl-50") && !is_live_name(home, "ctl-47"));
    }
}
