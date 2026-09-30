//! Replace a file so a reader, or a process that dies partway, sees the old
//! contents or the new ones and never a mix (#1254, folding the three
//! temp-and-rename writers the crate had grown: the worker sidecar, the
//! trust seed and the installed hooks).

use std::io::Write;
use std::os::unix::fs::PermissionsExt;
use std::path::Path;

/// Writes `bytes` to `tmp`, fsyncs them, optionally sets `mode`, renames
/// `tmp` over `path`, and fsyncs `path`'s directory so the rename itself
/// survives a crash. A failure before the rename removes `tmp` and leaves
/// `path` as it was. `before_write` sees the open temp file first: a test
/// failpoint's seam, a no-op everywhere else.
///
/// The rename has landed by the time the directory is synced, so a failed
/// directory fsync is noted on stderr rather than returned: a caller told a
/// landed write failed acts on a false answer (#1101 review C2).
pub fn replace(path: &Path, tmp: &Path, bytes: &[u8], mode: Option<u32>, before_write: impl FnOnce(&mut std::fs::File)) -> std::io::Result<()> {
    let written = (|| {
        let mut f = std::fs::File::create(tmp)?;
        before_write(&mut f);
        f.write_all(bytes)?;
        f.sync_all()?;
        if let Some(mode) = mode {
            std::fs::set_permissions(tmp, std::fs::Permissions::from_mode(mode))?;
        }
        std::fs::rename(tmp, path)
    })();
    if written.is_err() {
        let _ = std::fs::remove_file(tmp);
    }
    written?;
    if let Err(e) = std::fs::File::open(path.parent().unwrap_or(Path::new("."))).and_then(|d| d.sync_all()) {
        eprintln!("atomic: replaced {}, but could not fsync its directory: {e}", path.display());
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn replaces_the_contents_and_leaves_no_temp_file() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("f");
        let tmp = dir.path().join("f.tmp");
        std::fs::write(&path, "old").unwrap();
        replace(&path, &tmp, b"new", None, |_| {}).unwrap();
        assert_eq!(std::fs::read_to_string(&path).unwrap(), "new");
        assert!(!tmp.exists());
    }

    #[test]
    fn applies_the_requested_mode() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("hook");
        replace(&path, &dir.path().join("hook.tmp"), b"#!/bin/sh\n", Some(0o755), |_| {}).unwrap();
        assert_eq!(std::fs::metadata(&path).unwrap().permissions().mode() & 0o777, 0o755);
    }

    #[test]
    fn a_failed_rename_keeps_the_old_file_and_removes_the_temp() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("target");
        let tmp = dir.path().join("target.tmp");
        // A directory at `path` makes the rename fail after the temp file exists.
        std::fs::create_dir(&path).unwrap();
        std::fs::write(path.join("keep"), "x").unwrap();
        assert!(replace(&path, &tmp, b"new", None, |_| {}).is_err());
        assert!(path.join("keep").exists());
        assert!(!tmp.exists());
    }

    #[test]
    fn the_hook_sees_the_temp_file_before_any_bytes_are_written() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("f");
        let mut seen = None;
        replace(&path, &dir.path().join("f.tmp"), b"abc", None, |f| seen = Some(f.metadata().unwrap().len())).unwrap();
        assert_eq!(seen, Some(0));
    }
}
