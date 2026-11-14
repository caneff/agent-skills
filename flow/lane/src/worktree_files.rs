//! What `git worktree remove --force` would throw away from one worktree,
//! read once at the boundary and classified: modified, untracked, ignored
//! work, regenerable caches, names the repo declares discardable, empty
//! ignored directories and nested linked worktrees. `merge-cleanup`'s guards,
//! dry-run blockers, reaper and sweep all judge a worktree through this one
//! read.

use crate::runner::quiet_stdout;
use crate::worktree::Worktrees;
use std::path::Path;

/// What `git worktree remove --force` would throw away: a worktree's
/// `git status --porcelain --ignored` entries, by kind. Git collapses an
/// untracked or ignored directory to one entry; `file_ignored` expands
/// the ignored ones by what is on disk beneath them.
#[derive(Default)]
pub struct WorktreeFiles {
    pub modified: Vec<String>,
    pub untracked: Vec<String>,
    /// Ignored entries that are not regenerable caches — `.scratch/` evidence —
    /// and the modified, untracked and ignored files of a nested worktree,
    /// prefixed by its path.
    pub ignored: Vec<String>,
    /// Ignored entries `is_cache` accepts.
    pub caches: Vec<String>,
    /// Ignored directory paths, without the trailing slash, holding no file
    /// anywhere beneath them: the removal takes them and nothing is lost, so
    /// they are not work (#946).
    pub empty_dirs: Vec<String>,
    /// Ignored entries the repo's own AGENTS.md declares discardable (#1326),
    /// listed apart from `caches` so the output says who approved the loss.
    pub declared: Vec<String>,
    /// Registered linked worktrees nested anywhere beneath this one, outer
    /// before inner. `git worktree remove --force` on the parent deletes their
    /// files and leaves each registered, so they are removed first, inner
    /// first (#1326). Their own uncommitted work is in `ignored`, prefixed.
    pub nested: Vec<NestedWorktree>,
}

/// A linked worktree found inside another worktree's files.
pub struct NestedWorktree {
    pub path: String,
    /// The git directory of the repo it is registered with, which may not be
    /// the parent's: `git worktree remove` has to run against that one.
    pub common_dir: String,
    /// That repo's primary checkout, whose AGENTS.md says what in this
    /// worktree is discardable.
    primary: String,
}

/// One `!!` or `??` porcelain entry, decoded once at the boundary in
/// `WorktreeFiles::read` (#949): the path git means, with the trailing `/`
/// git appends to a directory taken off and recorded as `is_dir`. Nothing
/// downstream re-derives either from the shape of a string — a quoted
/// directory ends in `"` on the wire, so a slash test on the raw text
/// misread it as a file (#946).
struct IgnoredEntry {
    path: String,
    is_dir: bool,
}

impl IgnoredEntry {
    /// `raw` is the text after the status code, quoted or not.
    fn parse(raw: &str) -> Self {
        let decoded = unquote(raw);
        match decoded.strip_suffix('/') {
            Some(dir) => Self { path: dir.to_string(), is_dir: true },
            None => Self { path: decoded, is_dir: false },
        }
    }

    /// The name as printed: a directory keeps its trailing slash.
    fn shown(&self) -> String {
        if self.is_dir { format!("{}/", self.path) } else { self.path.clone() }
    }
}

/// How many names a message lists before "and <n> more".
pub const NAMES_SHOWN: usize = 5;

/// The ignored directory names a removal may discard unasked. Deny by
/// default (#801): an unknown ignored name is kept, because a wrongly kept
/// cache costs a --discard and a wrongly discarded note cannot be undone.
pub const CACHE_DIRS: &[&str] = &["node_modules", "__pycache__", "target", ".venv", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".hypothesis", ".pants.d"];

/// An ignored entry in worktree `wt` is a cache when its own name is in
/// `CACHE_DIRS` (a directory, or a symlink git lists with no trailing
/// slash), or when it sits inside a directory so named that marks itself
/// wholly ignored with a `*` .gitignore — pytest, ruff, mypy and venv write
/// one, so git lists their contents rather than the directory. A file under
/// a directory merely named `target/` is not a cache.
fn is_cache(wt: &str, entry: &IgnoredEntry) -> bool {
    let parts: Vec<&str> = entry.path.split('/').collect();
    let last = parts.len() - 1;
    parts.iter().enumerate().any(|(i, name)| {
        CACHE_DIRS.contains(name) && (i == last || ignores_all(&Path::new(wt).join(parts[..=i].join("/"))))
    })
}

/// Git quotes a porcelain path holding a non-ASCII byte, a `"`, a backslash
/// or a control character (`core.quotePath`, on by default): it wraps the
/// path in `"` and C-escapes the inside, so a quoted directory entry ends
/// with `"` rather than `/` and reads as a plain file to anything matching on
/// the slash. Left encoded, an ignored `café/` holding hundreds of files was
/// never walked and still refused as "1 ignored file(s)" — both of the bugs
/// #946 fixes, surviving for every name git quotes. Decode once here, at the
/// boundary, so `is_cache`, the walk and every printed name see the path git
/// means rather than its transport encoding. Bytes that are not UTF-8 decode
/// lossily: the replacement character names no file on disk, so the walk
/// cannot open it and the entry stays `ignored` — fail closed, the same
/// answer #801 wants for any directory we cannot read. A string git did not
/// quote is returned untouched.
fn unquote(entry: &str) -> String {
    let Some(inner) = entry.strip_prefix('"').and_then(|s| s.strip_suffix('"')) else {
        return entry.to_string();
    };
    let mut out: Vec<u8> = Vec::with_capacity(inner.len());
    let mut bytes = inner.bytes().peekable();
    while let Some(b) = bytes.next() {
        if b != b'\\' {
            out.push(b);
            continue;
        }
        match bytes.next() {
            Some(b'n') => out.push(b'\n'),
            Some(b't') => out.push(b'\t'),
            Some(b'r') => out.push(b'\r'),
            Some(b'b') => out.push(0x08),
            Some(b'f') => out.push(0x0c),
            Some(b'v') => out.push(0x0b),
            Some(b'a') => out.push(0x07),
            // Up to three octal digits: how git writes any byte it has to
            // escape, one escape per byte of a multi-byte character.
            Some(d @ b'0'..=b'7') => {
                let mut v = u32::from(d - b'0');
                for _ in 0..2 {
                    let Some(n @ b'0'..=b'7') = bytes.peek().copied() else { break };
                    bytes.next();
                    v = v * 8 + u32::from(n - b'0');
                }
                out.push(v as u8);
            }
            // An escaped quote or backslash, and anything else: the byte.
            Some(c) => out.push(c),
            // A trailing backslash is malformed; keep it rather than guess.
            None => out.push(b'\\'),
        }
    }
    String::from_utf8_lossy(&out).into_owned()
}

/// `dir/.gitignore` has a `*` line: the tool that made `dir` ignores it whole.
fn ignores_all(dir: &Path) -> bool {
    std::fs::read_to_string(dir.join(".gitignore")).is_ok_and(|s| s.lines().any(|l| l.trim() == "*"))
}

/// The names the repo declares discardable (#1326): the backtick spans on the
/// `**Discardable**:` line of `primary`'s AGENTS.md, a trailing `/`
/// dropped. One path component each, with at most a leading or trailing `*`;
/// `.git`, `.scratch` and a bare `*` are never honoured, since a declaration
/// that reached them would discard the evidence this guard exists to keep.
/// An unreadable file or a missing line declares nothing.
fn declared_discardable(primary: &str) -> Vec<String> {
    let Ok(text) = std::fs::read_to_string(Path::new(primary).join("AGENTS.md")) else { return Vec::new() };
    let Some(line) = text.lines().find_map(|l| l.strip_prefix("**Discardable**:")) else { return Vec::new() };
    line.split('`')
        .skip(1)
        .step_by(2)
        .map(|n| n.trim_end_matches('/').to_string())
        .filter(|n| !n.is_empty() && !n.contains('/') && !matches!(n.as_str(), ".git" | ".scratch" | "*" | "." | ".."))
        .collect()
}

/// A path component of `entry` matches a declared name, which covers
/// everything beneath it. Unlike a cache, no `.gitignore` is required: the
/// repo's own word is the approval.
fn is_declared(names: &[String], entry: &IgnoredEntry) -> bool {
    // A glob can match a name the parse refused (`.*` matches `.scratch`), so
    // the evidence and git directories are excluded here too, at any depth.
    if entry.path.split('/').any(|c| matches!(c, ".git" | ".scratch")) {
        return false;
    }
    entry.path.split('/').any(|c| {
        names.iter().any(|n| match (n.strip_prefix('*'), n.strip_suffix('*')) {
            (Some(suffix), _) => c.ends_with(suffix),
            (_, Some(prefix)) => c.starts_with(prefix),
            _ => c == n,
        })
    })
}

/// `dir` is the root of a linked worktree registered with some repo: its
/// `.git` is a file and git can name that repo's git directory. A directory
/// with a made-up `.git` file, or a full clone, is not.
fn nested_worktree(dir: &Path) -> Option<NestedWorktree> {
    if !dir.join(".git").is_file() {
        return None;
    }
    let path = dir.to_str()?;
    let common_dir = quiet_stdout("git", &["-C", path, "rev-parse", "--path-format=absolute", "--git-common-dir"])?;
    // Registered with that repo: a byte copy of a worktree keeps a `.git`
    // pointer that resolves, but is listed nowhere, and `worktree remove`
    // refuses it.
    let here = dir.canonicalize().ok()?;
    let listed = Worktrees::parse(&quiet_stdout("git", &["--git-dir", &common_dir, "worktree", "list", "--porcelain"])?)?;
    let registered = listed.all().iter().any(|w| Path::new(&w.path).canonicalize().is_ok_and(|p| p == here));
    registered.then(|| NestedWorktree { path: path.to_string(), common_dir, primary: listed.primary().to_string() })
}

impl WorktreeFiles {
    /// `None` when git cannot read the status of a worktree that is on disk.
    /// A worktree whose directory is already gone holds nothing to lose. The
    /// untracked and ignored modes are spelled out, so a
    /// `status.showUntrackedFiles=no` config cannot hide files from the guard.
    /// Untracked files one by one, so `recheck` sees a file new inside `dir/`.
    /// `matching`, not `traditional`: a directory holding only an ignored
    /// cache is not collapsed to its parent (`sub/`), which `is_cache` could
    /// not tell from work. `primary` is the primary checkout of the repo `wt`
    /// belongs to, read off the caller's listing: its AGENTS.md says which
    /// ignored names are discardable.
    pub fn read(wt: &str, primary: &str) -> Option<Self> {
        let Some(out) = quiet_stdout("git", &["-C", wt, "status", "--porcelain", "--untracked-files=all", "--ignored=matching"]) else {
            return (!Path::new(wt).exists()).then(Self::default);
        };
        let declared_names = declared_discardable(primary);
        let mut files = Self::default();
        for line in out.lines().filter(|l| l.len() > 3) {
            let (code, rest) = (&line[..2], &line[3..]);
            if code == "??" {
                let entry = IgnoredEntry::parse(rest);
                if entry.is_dir && files.take_nested(wt, &Path::new(wt).join(&entry.path)) {
                    continue;
                }
            }
            if code == "!!" {
                files.file_ignored(wt, &declared_names, IgnoredEntry::parse(rest));
                continue;
            }
            // Porcelain v1 writes a rename or a copy as `<orig> -> <new>`,
            // each path quoted on its own, so those decode by halves:
            // unquoting the line whole strips the outer pair and strands the
            // inner quotes. Only for R and C — in any other entry ` -> ` is
            // just part of a filename, and splitting on it would corrupt one.
            let name = match code.as_bytes()[0] {
                b'R' | b'C' => rest
                    .split_once(" -> ")
                    .map_or_else(|| unquote(rest), |(from, to)| format!("{} -> {}", unquote(from), unquote(to))),
                _ => unquote(rest),
            };
            match code {
                "??" => files.untracked.push(name),
                _ => files.modified.push(name),
            }
        }
        Some(files)
    }

    /// Files one ignored entry as cache, declared-discardable (`declared_names`,
    /// the repo's AGENTS.md list), a nested worktree, work or empty. A directory entry
    /// stands for whatever is inside it:
    /// `--ignored=matching` collapses it to one line whether it holds nothing
    /// or hundreds of files, and counting entries was wrong both ways (#946)
    /// — an empty directory forced a needless `--discard`, and a full one
    /// reported "1 file(s) would be lost" against hundreds, so `--discard`
    /// was approved against a count that understated the loss. Classify by
    /// contents, not by the entry: zero files is `empty` and not work; one or
    /// more land in `ignored` under their real names, so the refusal states
    /// the true count and the true loss. A non-directory entry, and a
    /// directory the walk cannot read, stay `ignored` as themselves — an
    /// unreadable directory fails closed (#801), never read as "nothing in
    /// there".
    fn file_ignored(&mut self, wt: &str, declared_names: &[String], entry: IgnoredEntry) {
        if is_cache(wt, &entry) {
            self.caches.push(entry.shown());
        } else if is_declared(declared_names, &entry) {
            // Discarded unasked, but a registered worktree beneath it is
            // found first, so it is removed properly and its uncommitted
            // work is not discarded by a declaration about build output.
            if entry.is_dir {
                self.find_nested(wt, &Path::new(wt).join(&entry.path));
            }
            self.declared.push(entry.shown());
        } else if !entry.is_dir {
            self.ignored.push(entry.shown());
        } else if !self.take_nested(wt, &Path::new(wt).join(&entry.path)) {
            match files_under(&Path::new(wt).join(&entry.path), &mut |d| self.take_nested(wt, d)) {
                Some(f) if f.is_empty() => self.empty_dirs.push(entry.path),
                Some(f) => self.ignored.extend(f.into_iter().map(|rel| format!("{}/{rel}", entry.path))),
                None => self.ignored.push(entry.shown()),
            }
        }
    }

    /// When `dir` is the root of a registered linked worktree, file it under
    /// `nested` (and anything nested inside it after it), put its own
    /// uncommitted work into `ignored` under its path from `wt`, and say so:
    /// the walk then skips it. Its checkout is not work; what git does not
    /// hold in it is, and `--discard` covers that like any other ignored file.
    fn take_nested(&mut self, wt: &str, dir: &Path) -> bool {
        let Some(nested) = nested_worktree(dir) else { return false };
        let prefix = dir.strip_prefix(wt).unwrap_or(dir).display().to_string();
        let inner = Self::read(&nested.path, &nested.primary);
        self.nested.push(nested);
        match inner {
            // Unreadable: not known clean, so it refuses under its own name.
            None => self.ignored.push(format!("{prefix}/")),
            Some(inner) => {
                let held = inner.modified.iter().chain(&inner.untracked).chain(&inner.ignored);
                self.ignored.extend(held.map(|f| format!("{prefix}/{f}")));
                self.caches.extend(inner.caches.iter().map(|f| format!("{prefix}/{f}")));
                self.declared.extend(inner.declared.iter().map(|f| format!("{prefix}/{f}")));
                self.nested.extend(inner.nested);
            }
        }
        true
    }

    /// `take_nested` for every directory beneath `dir` (and `dir`), looking at
    /// directories only and not descending into a worktree it takes.
    fn find_nested(&mut self, wt: &str, dir: &Path) {
        let mut stack = vec![dir.to_path_buf()];
        while let Some(d) = stack.pop() {
            if self.take_nested(wt, &d) {
                continue;
            }
            let Ok(entries) = std::fs::read_dir(&d) else { continue };
            stack.extend(entries.flatten().filter(|e| e.file_type().is_ok_and(|t| t.is_dir())).map(|e| e.path()));
        }
    }

    /// Modified, untracked or non-cache ignored files: work a removal would
    /// lose. Caches are not — every worktree holds `.venv/` or `target/`
    /// after a merge.
    pub fn is_dirty(&self) -> bool {
        !self.modified.is_empty() || !self.untracked.is_empty() || !self.ignored.is_empty()
    }

    /// The modified, untracked and non-cache ignored entries of `self` that
    /// `earlier` did not have: what appeared between two reads.
    pub fn since(&self, earlier: &WorktreeFiles) -> WorktreeFiles {
        let new = |now: &[String], then: &[String]| now.iter().filter(|e| !then.contains(e)).cloned().collect();
        WorktreeFiles {
            modified: new(&self.modified, &earlier.modified),
            untracked: new(&self.untracked, &earlier.untracked),
            ignored: new(&self.ignored, &earlier.ignored),
            ..WorktreeFiles::default()
        }
    }

    /// "1 modified, 2 untracked, 3 ignored, 4 cache".
    pub fn counts(&self) -> String {
        format!(
            "{} modified, {} untracked, {} ignored, {} cache",
            self.modified.len(),
            self.untracked.len(),
            self.ignored.len(),
            self.caches.len()
        )
    }

    /// The standing fix for a regenerable ignored name that stopped the run
    /// (#1545): declare it on the repo's `**Discardable**:` line. Empty when
    /// nothing ignored sits outside `.scratch/`, which is evidence and is
    /// never offered for declaring.
    pub fn declare_hint(&self) -> &'static str {
        if self.ignored.iter().any(|n| n.split('/').next() != Some(".scratch")) {
            "; if it is regenerable, a `**Discardable**:` line in the repo's AGENTS.md naming it stops this for good"
        } else {
            ""
        }
    }

    /// "1 modified, 2 untracked file(s) would be lost: f, a, b" — the kinds
    /// that are present, then their first names. Ignored names are never
    /// capped, and lead the list: `--discard` destroys them unseen, so none
    /// may fall into `first_names`' "and N more" (#838, and the six-or-more
    /// case Codex caught on PR #847). Modified and untracked are capped.
    pub fn dirty_text(&self) -> String {
        let kinds: Vec<String> = [("modified", &self.modified), ("untracked", &self.untracked), ("ignored", &self.ignored)]
            .iter()
            .filter(|(_, v)| !v.is_empty())
            .map(|(k, v)| format!("{} {k}", v.len()))
            .collect();
        // One list of modified and untracked names, capped as `Modified` is.
        let others: Vec<String> = self.modified.iter().chain(&self.untracked).cloned().collect();
        let names: Vec<String> = (!self.ignored.is_empty())
            .then(|| names_shown(DirtyKind::Ignored, &self.ignored))
            .into_iter()
            .chain((!others.is_empty()).then(|| names_shown(DirtyKind::Modified, &others)))
            .collect();
        format!("{} file(s) would be lost: {}", kinds.join(", "), names.join(", "))
    }
}

/// Every file anywhere beneath `dir`, as paths relative to it, or `None` when
/// any part of the walk cannot be read — the caller must not read an
/// unreadable directory as an empty one. A symlink counts as a file and is
/// never descended, so the walk cannot cycle.
fn files_under(dir: &Path, skip: &mut dyn FnMut(&Path) -> bool) -> Option<Vec<String>> {
    let mut out = Vec::new();
    let mut stack = vec![(dir.to_path_buf(), String::new())];
    while let Some((d, prefix)) = stack.pop() {
        for entry in std::fs::read_dir(&d).ok()? {
            let entry = entry.ok()?;
            let rel = format!("{prefix}{}", entry.file_name().to_string_lossy());
            if entry.file_type().ok()?.is_dir() {
                // A registered worktree is handed to `skip`, which owns it.
                if !skip(&entry.path()) {
                    stack.push((entry.path(), format!("{rel}/")));
                }
            } else {
                out.push(rel);
            }
        }
    }
    out.sort();
    Some(out)
}

/// `names`, relative to `wt`, with every file under a nested git worktree
/// replaced by that directory once, as `dir/`: a verification subagent's
/// checkout is one fact, not thousands. The outermost `.git` wins. A bare
/// `.git` stat, not `is_worktree_root`'s `git rev-parse` per directory: this
/// runs on every prefix of every scratch file, and a wrong guess only
/// changes how a name is shown, never whether it blocks.
pub fn collapse_nested_worktrees(wt: &str, names: &[String]) -> Vec<String> {
    let mut seen = std::collections::HashSet::new();
    let mut out = Vec::new();
    for name in names {
        let parts: Vec<&str> = name.split('/').collect();
        let nested = (1..parts.len()).map(|n| parts[..n].join("/")).find(|dir| Path::new(wt).join(dir).join(".git").exists());
        let shown = nested.map_or_else(|| name.clone(), |dir| format!("{dir}/"));
        if seen.insert(shown.clone()) {
            out.push(shown);
        }
    }
    out
}

/// A kind of file a removal would lose, as the refusal and the dry run's
/// blocker lines name it. An enum, not a string, so a new call site cannot
/// misspell `Ignored` into the capped branch (#838).
#[derive(Clone, Copy)]
pub enum DirtyKind {
    Modified,
    Untracked,
    Ignored,
    Scratch,
}

impl DirtyKind {
    pub fn label(self) -> &'static str {
        match self {
            DirtyKind::Modified => "modified",
            DirtyKind::Untracked => "untracked",
            DirtyKind::Ignored => "ignored",
            DirtyKind::Scratch => "scratch",
        }
    }

    /// Whether `names_shown` may cut this kind's names to "and N more".
    /// Ignored names never are: `--discard` destroys them unseen (#838). No
    /// wildcard arm, so a new kind must answer this before it compiles.
    fn capped(self) -> bool {
        match self {
            DirtyKind::Ignored => false,
            DirtyKind::Modified | DirtyKind::Untracked | DirtyKind::Scratch => true,
        }
    }
}

/// How the refusal and the dry run's blocker lines show the `names` of one
/// `kind` of dirty file — the one place the capping rule lives: a capped kind
/// shows its first `NAMES_SHOWN`, an uncapped one all of them.
pub fn names_shown(kind: DirtyKind, names: &[String]) -> String {
    if kind.capped() { first_names(names) } else { names.join(", ") }
}

/// The first `NAMES_SHOWN` names, comma-separated, then "and <n> more".
pub fn first_names(names: &[String]) -> String {
    let shown = names[..names.len().min(NAMES_SHOWN)].join(", ");
    match names.len().saturating_sub(NAMES_SHOWN) {
        0 => shown,
        more => format!("{shown} and {more} more"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn names(n: usize) -> Vec<String> {
        (1..=n).map(|i| format!("f{i}")).collect()
    }

    #[test]
    fn names_shown_caps_every_kind_but_ignored() {
        let seven = names(NAMES_SHOWN + 2);
        assert_eq!(names_shown(DirtyKind::Ignored, &seven), "f1, f2, f3, f4, f5, f6, f7");
        for kind in [DirtyKind::Modified, DirtyKind::Untracked, DirtyKind::Scratch] {
            assert_eq!(names_shown(kind, &seven), "f1, f2, f3, f4, f5 and 2 more", "{}", kind.label());
        }
    }
}
