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
    /// The registry's own `procStart`, empty when the file has none — a
    /// caller that needs to reject a stale file over a reused pid compares
    /// this to that pid's own `/proc/<pid>/stat` starttime, the same check
    /// `find_controller` makes.
    pub proc_start: String,
}

/// Whether `path` is `root` or inside it.
pub fn in_tree(path: &str, root: &str) -> bool {
    format!("{path}/").starts_with(&format!("{root}/"))
}

/// Every registry file under `<home>/.claude/sessions` whose `cwd` is in
/// `worktree` and whose pid is alive — a dead pid is a crashed session and
/// is ignored. Files in name order; unreadable files are skipped.
pub fn live_in(home: &Path, worktree: &str) -> Vec<LiveSession> {
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
        let cwd = v.get("cwd").and_then(|c| c.as_str()).unwrap_or("");
        let alive = pid.parse::<i32>().is_ok_and(|p| p > 0 && read_stat(p).is_some());
        if !pid.is_empty() && in_tree(cwd, worktree) && alive {
            let session_id = v.get("sessionId").and_then(|s| s.as_str()).unwrap_or("").to_string();
            let name = v.get("name").and_then(|s| s.as_str()).unwrap_or("").to_string();
            let proc_start = v.get("procStart").and_then(|s| s.as_str()).unwrap_or("").to_string();
            live.push(LiveSession { pid, session_id, name, proc_start });
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
    let mut ancestor = start_ancestor;
    while ancestor > 1 {
        let stat = read_stat(ancestor)?;
        let session_file = home.join(".claude/sessions").join(format!("{ancestor}.json"));
        if let Ok(raw) = std::fs::read_to_string(&session_file) {
            if let Ok(v) = serde_json::from_str::<serde_json::Value>(&raw) {
                let proc_start_matches = v.get("procStart").and_then(|p| p.as_str()) == Some(stat.start.as_str());
                if proc_start_matches {
                    if let Some(name) = v.get("name").and_then(|n| n.as_str()) {
                        if !name.is_empty() {
                            return Some(name.to_string());
                        }
                    }
                }
            }
        }
        ancestor = stat.ppid;
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::proc_info::read_stat;
    use tempfile::TempDir;

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
}
