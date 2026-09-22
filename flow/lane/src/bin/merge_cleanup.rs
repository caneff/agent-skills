//! Port of `flow/bin/merge-cleanup`. The tail the controller runs after
//! squash-merging a worker's PR: tear the workspace down, delete the branch
//! local and remote, fast-forward the primary checkout. The contract is
//! `--help` below.

use lane::git_origin::{default_branch, origin_slug};
use lane::herdr::{self, Agent};
use lane::runner::{on_path, quiet_ok, quiet_stderr_ok, quiet_stdout, status};
use lane::sessions::{self, in_tree};
use lane::{safe_print, safe_println};
use std::env;
use std::io::IsTerminal;
use std::path::Path;
use std::process::ExitCode;

const HELP: &str = r#"The tail the controller runs after squash-merging a worker's PR: tear the
workspace down, delete the branch local and remote, fast-forward the primary
checkout. This runs after the merge has already happened, and it refuses any
branch the tracker does not report as merged unless --force.

  merge-cleanup [--repo <path>] <branch|PR number|PR URL> [--force] [--discard] [--dry-run]
  merge-cleanup --sweep [--root <dir>] [--yes] [--dry-run]
  merge-cleanup --reap [--repo <path>] [--yes] [--dry-run]

--sweep walks every git repo one level under <dir> (default ~/src), prints
the merged local branches it would clean — each with what proved it merged,
how many commits sit past that proof (0 is healthy), and the modified,
untracked, ignored and cache file counts of the worktree holding it — and
asks before touching anything: --yes answers for you, --dry-run never asks.
Then it runs the same six steps for each and prints a summary table with the
same count.

--reap cleans up one repo's own implement-* workspaces — the linked worktrees
under <repo>/.claude/worktrees/ holding a branch named implement-*, and
nothing else on the machine: the --repo path, else the repo holding the cwd.
Each goes through the single-branch form above unchanged, so a branch the
tracker does not report merged, a worktree holding work and a live session
each refuse exactly as they do there. It prints one line per workspace with
its disposition, and a summary count. Unlike the two forms above, it is a
dry run by default: it removes nothing without --yes, and it has
no --discard and no --force to override a refusal with — a workspace those
guards refuse is named and skipped, which is the point of it. The workspace
this run's own directory is in is skipped the same way.

A linked worktree with modified, untracked or ignored files is never removed
— bar an ignored directory holding no file at all, which loses nothing and is
covered below. The single-branch form refuses, naming them, and
--discard removes it anyway (--force only skips the merged check); --sweep
lists it "dirty, not removed" even with --yes. Ignored files include .scratch/ and every other ignored name
except the regenerable caches: an ignored entry is one only when a path
component of it is named {cache_names} and, unless that component is the
entry itself, that directory's own .gitignore is `*`. Both are required: a `*`
.gitignore alone makes nothing a cache. A cache never refuses — it is removed with the
worktree, and its count and first names are printed as cache file(s), distinct
from the ignored file(s) count above: the two never share a label, so a name
Chris approved losing under one count is never misread as counted by the
other. The list is fixed on purpose: an unknown ignored name is kept, since
a wrongly kept cache costs a --discard and a discarded note cannot be undone.

An ignored directory is judged by what it holds, never by its entry: git
collapses one to a single line whether it is empty or holds hundreds. A
directory with no file anywhere beneath it loses nothing, so it never
refuses — it goes with the worktree, and the run prints one line naming it.
One holding files refuses with their true count and their real names, so
--discard is never approved against a number that understates the loss. A
directory the walk cannot read is not known to be empty, so it still
refuses.

The claim clears with the merge: every ticket the branch's merged PR closes
in this repo, plus the branch's own implement-<n>, loses its in-progress
label and its assignees once that issue is closed. A clump lands as one PR
closing several tickets, and its closingIssuesReferences is that list.

Every local branch delete first records the tip under
refs/deleted/<branch>@<short sha>, which
`git branch <branch> refs/deleted/<branch>@<short sha>` restores.

A linked worktree is never removed while a live session is in it: a sessions
registry session refuses unless its sessionId equals a herdr agent's
agent_session.value for that worktree, in which case the herdr agent's own
status decides it instead — working or blocked (or herdr cannot classify it)
refuses, idle (or done) this run closes its pane and the removal proceeds. A
registry session with no matching herdr agent always refuses. Other idle
entries under .claude/worktrees are listed as "stale, not removed". The
herdr workspaces of removed worktrees close at exit, after everything else.
"#;

fn die(msg: impl AsRef<str>) -> ExitCode {
    eprintln!("merge-cleanup: {}", msg.as_ref());
    ExitCode::FAILURE
}

fn skip(what: &str, why: &str) {
    safe_println!("skipped {what} ({why})");
}

#[derive(Default)]
struct Args {
    repo: String,
    branch: String,
    pr: String,
    sweep: bool,
    reap: bool,
    root: String,
    dry: bool,
    force: bool,
    discard: bool,
    yes: bool,
}

enum Parsed {
    Help,
    Args(Args),
    Err(String),
}

/// A flag's value; a flag with nothing after it reads as empty, which the
/// bash `${2:-}` gave before its `shift 2` looped forever.
fn value(it: &mut impl Iterator<Item = String>) -> String {
    it.next().unwrap_or_default()
}

fn parse_args(argv: impl IntoIterator<Item = String>) -> Parsed {
    let mut a = Args::default();
    let mut it = argv.into_iter();
    while let Some(arg) = it.next() {
        match arg.as_str() {
            "--repo" => a.repo = value(&mut it),
            "--pr" => a.pr = value(&mut it),
            "--sweep" => a.sweep = true,
            "--reap" => a.reap = true,
            "--root" => a.root = value(&mut it),
            "--force" => a.force = true,
            "--discard" => a.discard = true,
            "--yes" => a.yes = true,
            "--dry-run" => a.dry = true,
            "-h" | "--help" => return Parsed::Help,
            f if f.starts_with('-') => return Parsed::Err(format!("unknown flag: {f}")),
            _ => {
                if !a.branch.is_empty() || !a.pr.is_empty() {
                    return Parsed::Err("one branch at a time".into());
                }
                // A bare number or a PR URL is a PR; anything else is a branch.
                if arg.starts_with(|c: char| c.is_ascii_digit()) {
                    if arg.chars().all(|c| c.is_ascii_digit()) {
                        a.pr = arg;
                    } else {
                        a.branch = arg;
                    }
                } else if let Some(tail) = pr_url_tail(&arg) {
                    a.pr = tail.chars().take_while(char::is_ascii_digit).collect();
                } else {
                    a.branch = arg;
                }
            }
        }
    }
    Parsed::Args(a)
}

/// `*://*/pull/*`: the text after the last `/pull/` of a URL.
fn pr_url_tail(arg: &str) -> Option<&str> {
    let scheme = arg.find("://")?;
    let after = &arg[scheme + 3..];
    let i = after.rfind("/pull/")?;
    Some(&after[i + "/pull/".len()..])
}

/// The repo's primary (non-linked) worktree, or empty.
fn primary_of(path: &str) -> String {
    quiet_stdout("git", &["-C", path, "worktree", "list", "--porcelain"])
        .and_then(|o| o.lines().next().and_then(|l| l.strip_prefix("worktree ")).map(str::to_string))
        .unwrap_or_default()
}

fn head_of(path: &str) -> Option<String> {
    quiet_stdout("git", &["-C", path, "rev-parse", "--abbrev-ref", "HEAD"])
}

/// What proved a branch merged: the sha it is landed up to, the proof, and
/// the merged PR's number when a PR is what proved it. The number matters
/// past the display string (#889): a branch name can carry several merged
/// PRs over its life, and only the one whose head is this tip says which
/// tickets this landing closed.
struct Merged {
    at: String,
    by: String,
    pr: Option<String>,
}

struct Cleanup {
    dry: bool,
    force: bool,
    discard: bool,
    home: String,
    /// Worktrees this run passed the guard for, dry runs included.
    removal_targets: Vec<String>,
    /// Worktrees this run removed; their herdr workspaces close at exit.
    removed_worktrees: Vec<String>,
    /// #832: set by `clear_ticket_if_closed` when its `gh issue edit` fails,
    /// after the git cleanup it ran alongside already succeeded. Kept
    /// separate from `cleanup_branch`'s own bool, which callers read as
    /// "the branch and worktree are gone" — folding this into it made a
    /// fully cleaned branch look like a survivor, both in the sweep table
    /// and in the single-branch `report_stale` gate. `cleanup_branch` resets
    /// this itself at the start of every call, so a caller doing more than
    /// one branch reads it right after each call with no reset of its own.
    claim_clear_failed: bool,
    /// Codex pass on PR #842: same shape as `claim_clear_failed`, for a
    /// denied or failed `git push origin --delete`. The local branch and
    /// worktree are still gone by the time this can be true, so it does not
    /// make `cleanup_branch` return false either — it only fails the exit
    /// code and, via `clear_ticket_if_closed`'s wording, stops that
    /// function from calling git cleanup complete when it wasn't.
    remote_delete_failed: bool,
}

/// The herdr agents whose cwd is in `wt`; `Err` when `herdr agent list`
/// fails or answers something unreadable.
fn herdr_agents_in(wt: &str) -> Result<Vec<Agent>, ()> {
    let out = quiet_stdout("herdr", &["agent", "list"]).ok_or(())?;
    let agents = herdr::parse_agents(&out).ok_or(())?;
    Ok(agents.into_iter().filter(|a| in_tree(a.cwd(), wt)).collect())
}

/// What `herdr agent list` said about a worktree.
enum HerdrAnswer {
    /// herdr is not on PATH.
    Absent,
    /// `herdr agent list` failed or answered something unreadable.
    Failed,
    /// The herdr agents whose cwd is in the worktree.
    Agents(Vec<Agent>),
}

/// What `Cleanup::occupancy` found alive in a worktree.
struct Occupancy {
    /// Registry sessions no herdr agent explains, as "pid <n>".
    unresolved: Vec<String>,
    herdr: HerdrAnswer,
}

impl Occupancy {
    /// What a removal would be refused over, named the way `guard_live`
    /// names it: the unresolved registry sessions if there are any, else the
    /// herdr agents that are not idle — or herdr itself when it could not
    /// answer. Empty means the guard would clear the worktree.
    fn live_items(&self) -> Vec<String> {
        if !self.unresolved.is_empty() {
            return self.unresolved.clone();
        }
        match &self.herdr {
            HerdrAnswer::Absent => Vec::new(),
            HerdrAnswer::Failed => vec!["herdr agent list failed".into()],
            HerdrAnswer::Agents(agents) => blockers(agents),
        }
    }

    /// Nothing the guard would refuse on: no unresolved session, and herdr
    /// absent or answering with idle agents only.
    fn is_clear(&self) -> bool {
        self.live_items().is_empty()
    }
}

/// The agents that block a removal, as "herdr agent <name> (<pane>)": every
/// one that is not idle, and every one herdr gives no name — an agent that
/// cannot be named cannot be classified, so it never clears the worktree,
/// and a registry session it explains is refused through it instead.
fn blockers(agents: &[Agent]) -> Vec<String> {
    agents
        .iter()
        .filter(|a| !a.is_idle() || a.name().is_empty())
        .map(|a| match a.name() {
            "" => format!("an unnamed herdr agent ({})", a.pane()),
            name => format!("herdr agent {name} ({})", a.pane()),
        })
        .collect()
}

/// What `git worktree remove --force` would throw away: a worktree's
/// `git status --porcelain --ignored` entries, by kind. Git collapses an
/// untracked or ignored directory to one entry; `file_ignored` expands
/// the ignored ones by what is on disk beneath them.
#[derive(Default)]
struct WorktreeFiles {
    modified: Vec<String>,
    untracked: Vec<String>,
    /// Ignored entries that are not regenerable caches — `.scratch/` evidence.
    ignored: Vec<String>,
    /// Ignored entries `is_cache` accepts.
    caches: Vec<String>,
    /// Ignored directory paths, without the trailing slash, holding no file
    /// anywhere beneath them: the removal takes them and nothing is lost, so
    /// they are not work (#946).
    empty_dirs: Vec<String>,
}

/// One `!!` porcelain entry, decoded once at the boundary in
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
const NAMES_SHOWN: usize = 5;

/// The ignored directory names a removal may discard unasked. Deny by
/// default (#801): an unknown ignored name is kept, because a wrongly kept
/// cache costs a --discard and a wrongly discarded note cannot be undone.
const CACHE_DIRS: &[&str] = &["node_modules", "__pycache__", "target", ".venv", ".pytest_cache", ".ruff_cache", ".mypy_cache"];

/// `HELP` with its cache-name list filled from `CACHE_DIRS`, so the help
/// cannot name a set of caches the guard does not use (#875).
fn help_text() -> String {
    let (last, rest) = CACHE_DIRS.split_last().expect("CACHE_DIRS is not empty");
    HELP.replace("{cache_names}", &format!("{} or {last}", rest.join(", ")))
}

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

impl WorktreeFiles {
    /// `None` when git cannot read the status of a worktree that is on disk.
    /// A worktree whose directory is already gone holds nothing to lose. The
    /// untracked and ignored modes are spelled out, so a
    /// `status.showUntrackedFiles=no` config cannot hide files from the guard.
    /// `matching`, not `traditional`: a directory holding only an ignored
    /// cache is not collapsed to its parent (`sub/`), which `is_cache` could
    /// not tell from work.
    fn read(wt: &str) -> Option<Self> {
        let Some(out) = quiet_stdout("git", &["-C", wt, "status", "--porcelain", "--untracked-files=normal", "--ignored=matching"]) else {
            return (!Path::new(wt).exists()).then(Self::default);
        };
        let mut files = Self::default();
        for line in out.lines().filter(|l| l.len() > 3) {
            let (code, rest) = (&line[..2], &line[3..]);
            if code == "!!" {
                files.file_ignored(wt, IgnoredEntry::parse(rest));
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

    /// Files one ignored entry as cache, work or empty. A directory entry
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
    fn file_ignored(&mut self, wt: &str, entry: IgnoredEntry) {
        if is_cache(wt, &entry) {
            self.caches.push(entry.shown());
        } else if !entry.is_dir {
            self.ignored.push(entry.shown());
        } else {
            match files_under(&Path::new(wt).join(&entry.path)) {
                Some(f) if f.is_empty() => self.empty_dirs.push(entry.path),
                Some(f) => self.ignored.extend(f.into_iter().map(|rel| format!("{}/{rel}", entry.path))),
                None => self.ignored.push(entry.shown()),
            }
        }
    }

    /// Modified, untracked or non-cache ignored files: work a removal would
    /// lose. Caches are not — every worktree holds `.venv/` or `target/`
    /// after a merge.
    fn is_dirty(&self) -> bool {
        !self.modified.is_empty() || !self.untracked.is_empty() || !self.ignored.is_empty()
    }

    /// "1 modified, 2 untracked, 3 ignored, 4 cache".
    fn counts(&self) -> String {
        format!(
            "{} modified, {} untracked, {} ignored, {} cache",
            self.modified.len(),
            self.untracked.len(),
            self.ignored.len(),
            self.caches.len()
        )
    }

    /// "1 modified, 2 untracked file(s) would be lost: f, a, b" — the kinds
    /// that are present, then their first names. Ignored names are never
    /// capped, and lead the list: `--discard` destroys them unseen, so none
    /// may fall into `first_names`' "and N more" (#838, and the six-or-more
    /// case Codex caught on PR #847). Modified and untracked are capped.
    fn dirty_text(&self) -> String {
        let kinds: Vec<String> = [("modified", &self.modified), ("untracked", &self.untracked), ("ignored", &self.ignored)]
            .iter()
            .filter(|(_, v)| !v.is_empty())
            .map(|(k, v)| format!("{} {k}", v.len()))
            .collect();
        let others: Vec<String> = self.modified.iter().chain(&self.untracked).cloned().collect();
        let names: Vec<String> = self.ignored.iter().cloned().chain((!others.is_empty()).then(|| first_names(&others))).collect();
        format!("{} file(s) would be lost: {}", kinds.join(", "), names.join(", "))
    }
}

/// Every file anywhere beneath `dir`, as paths relative to it, or `None` when
/// any part of the walk cannot be read — the caller must not read an
/// unreadable directory as an empty one. A symlink counts as a file and is
/// never descended, so the walk cannot cycle.
fn files_under(dir: &Path) -> Option<Vec<String>> {
    let mut out = Vec::new();
    let mut stack = vec![(dir.to_path_buf(), String::new())];
    while let Some((d, prefix)) = stack.pop() {
        for entry in std::fs::read_dir(&d).ok()? {
            let entry = entry.ok()?;
            let rel = format!("{prefix}{}", entry.file_name().to_string_lossy());
            if entry.file_type().ok()?.is_dir() {
                stack.push((entry.path(), format!("{rel}/")));
            } else {
                out.push(rel);
            }
        }
    }
    out.sort();
    Some(out)
}

/// The first `NAMES_SHOWN` names, comma-separated, then "and <n> more".
fn first_names(names: &[String]) -> String {
    let shown = names[..names.len().min(NAMES_SHOWN)].join(", ");
    match names.len().saturating_sub(NAMES_SHOWN) {
        0 => shown,
        more => format!("{shown} and {more} more"),
    }
}

fn refuse_live(wt: &str, items: &[String]) -> bool {
    eprintln!("merge-cleanup: refusing to remove {wt} — a live session is in it: {}", items.join(", "));
    false
}

impl Cleanup {
    /// bash's `run <description> <cmd...>`: on a dry run, say what would run;
    /// otherwise announce it and run it with its output passed through.
    fn step(&self, what: &str, program: &str, args: &[&str]) -> bool {
        if self.dry {
            safe_println!("would {what}: {program} {}", args.join(" "));
            return true;
        }
        safe_println!("{what}");
        status(program, args)
    }

    /// What is alive in `wt`, classified once for both the guard and the
    /// stale report, so a worktree is listed as stale exactly when the guard
    /// would clear it (#746). Two sources: a sessions registry file whose cwd
    /// is in the workspace and whose pid is alive is unresolved — unless its
    /// sessionId equals a herdr agent's agent_session.value for that same
    /// worktree, in which case that session is the worker's own pane and the
    /// herdr agent's status decides it instead.
    fn occupancy(&self, wt: &str) -> Occupancy {
        let herdr = match on_path("herdr").then(|| herdr_agents_in(wt)) {
            None => HerdrAnswer::Absent,
            Some(Err(())) => HerdrAnswer::Failed,
            Some(Ok(agents)) => HerdrAnswer::Agents(agents),
        };
        // A registry session is explained away only by a herdr agent whose
        // own sessionId matches it — herdr agent list has to have answered.
        let herdr_sessions: Vec<&str> = match &herdr {
            HerdrAnswer::Agents(agents) => agents.iter().map(Agent::session).filter(|s| !s.is_empty()).collect(),
            _ => Vec::new(),
        };
        let unresolved = sessions::live_in(Path::new(&self.home), wt)
            .into_iter()
            .filter(|s| s.session_id.is_empty() || !herdr_sessions.contains(&s.session_id.as_str()))
            .map(|s| format!("pid {}", s.pid))
            .collect();
        Occupancy { unresolved, herdr }
    }

    /// The live-session guard. An unresolved registry session refuses. A
    /// herdr agent whose cwd is in the workspace refuses only while its
    /// agent_status is working or blocked (or herdr cannot classify it); an
    /// idle one (idle or done) has its pane closed by this run, then proceeds.
    fn guard_live(&self, wt: &str) -> bool {
        let occupancy = self.occupancy(wt);
        if !occupancy.unresolved.is_empty() {
            return refuse_live(wt, &occupancy.unresolved);
        }
        let agents = match occupancy.herdr {
            HerdrAnswer::Absent => {
                skip("the herdr agent check", "herdr is not on PATH");
                return true;
            }
            // A herdr that cannot answer cannot clear the workspace either.
            HerdrAnswer::Failed => {
                eprintln!("merge-cleanup: refusing to remove {wt} — herdr agent list failed");
                return false;
            }
            HerdrAnswer::Agents(agents) => agents,
        };
        // Classify every agent before closing any: a working or blocked
        // sibling must refuse the whole worktree before an idle one is
        // touched, so the outcome never depends on herdr agent list's order.
        let blockers = blockers(&agents);
        if !blockers.is_empty() {
            return refuse_live(wt, &blockers);
        }
        for a in agents {
            let (name, pane) = (a.name(), a.pane());
            if !self.step(&format!("closing idle herdr agent {name}'s pane ({pane})"), "herdr", &["pane", "close", pane]) {
                eprintln!("merge-cleanup: refusing to remove {wt} — failed to close herdr agent {name}'s pane ({pane})");
                return false;
            }
        }
        true
    }

    /// The uncommitted-files guard (#736). `git worktree remove --force`
    /// discards everything git does not hold, so modified, untracked or
    /// ignored files refuse the removal unless --discard — `.scratch/`
    /// included (#801). Caches (`is_cache`) never refuse; their count and
    /// first names are printed as "cache file(s)", since they go too — a
    /// label distinct from the non-cache "ignored file(s)" refusal above
    /// (#823), so a name approved for loss in one line is never misread as
    /// belonging to the other's.
    ///
    /// An ignored directory holding no file anywhere beneath it is not among
    /// them (#869, #946). #823 ruled the other way, and its reasoning was
    /// deny-by-default carried to its end: git reports an ignored directory
    /// as one entry whether or not it has contents, a process can fill it
    /// between this read and the removal, an empty directory can itself be
    /// intentional, and a caller who really means it has --discard. What
    /// beat that was not a preference but a cost nobody had counted: agents
    /// are denied --discard, so every such refusal spends one of Chris's
    /// hands, and `e2e-artifacts/` — recreated by every `npm test` run —
    /// spent six in a row on 2026-09-16. A guard that cries wolf on the case
    /// with nothing to lose is not stricter, it is noisier, and the noise is
    /// paid for in the attention the real refusals need. So the posture is
    /// narrowed, not abandoned: only a directory proved file-free by a walk
    /// is exempt, an unreadable one still refuses, and everything #823
    /// worried about for a directory with contents still holds.
    ///
    /// `None` refuses. Otherwise the empty ignored directories, for the
    /// caller to name once the removal has actually happened: the ruling
    /// asks that the output stay a full account of what cleanup touched, and
    /// this guard runs before `guard_live`, so a line printed here would
    /// announce a removal that a live session then goes on to refuse.
    fn guard_files(&self, wt: &str) -> Option<Vec<String>> {
        let Some(files) = WorktreeFiles::read(wt) else {
            eprintln!("merge-cleanup: refusing to remove {wt} — git status failed there");
            return None;
        };
        if files.is_dirty() {
            if !self.discard {
                eprintln!("merge-cleanup: refusing to remove {wt} — {} (--discard overrides)", files.dirty_text());
                return None;
            }
            safe_println!("--discard: {wt} — {}", files.dirty_text());
        }
        if !files.caches.is_empty() {
            let would = if self.dry { "would discard" } else { "discarding" };
            safe_println!("{would} {} cache file(s) in {wt}: {}", files.caches.len(), first_names(&files.caches));
        }
        Some(files.empty_dirs)
    }

    /// Other workspaces under <repo>/.claude/worktrees the guard would clear,
    /// no commits ahead of the default branch and nothing on disk git does
    /// not hold (ignored files and caches included — .scratch evidence is
    /// work too; an ignored directory with no file beneath it is not, so a
    /// sibling holding only one is listed here):
    /// listed for the owner, never removed. A folder there that git no
    /// longer tracks as a worktree is listed too, marked. This run's removal
    /// targets are not "other".
    fn stale_worktrees(&self, repo: &str) -> Vec<String> {
        let primary = primary_of(repo);
        let default = default_branch(Path::new(repo));
        let mut base = format!("origin/{default}");
        if !quiet_ok("git", &["-C", &primary, "show-ref", "-q", "--verify", &format!("refs/remotes/{base}")]) {
            base = default;
        }
        let mut stale = Vec::new();
        for e in subdirs(&format!("{primary}/.claude/worktrees")) {
            if self.removal_targets.contains(&e) {
                continue;
            }
            let mark = if quiet_stdout("git", &["-C", &e, "rev-parse", "--show-toplevel"]).as_deref() != Some(e.as_str()) {
                " (not a git worktree)"
            } else {
                if quiet_stdout("git", &["-C", &e, "rev-list", "--count", &format!("{base}..HEAD")]).as_deref() != Some("0") {
                    continue;
                }
                if !WorktreeFiles::read(&e).is_some_and(|f| !f.is_dirty() && f.caches.is_empty()) {
                    continue;
                }
                ""
            };
            if self.occupancy(&e).is_clear() {
                stale.push(format!("{e}{mark}"));
            }
        }
        stale
    }

    fn report_stale(&self, repos: &[String]) {
        let list: Vec<String> = repos.iter().flat_map(|r| self.stale_worktrees(r)).collect();
        if list.is_empty() {
            return;
        }
        safe_println!();
        safe_println!("stale, not removed:");
        for e in list {
            safe_println!("  {e}");
        }
    }

    /// herdr keeps its own workspace record per checkout. Once the checkout
    /// is gone, close the herdr workspace whose path matched, so herdr does
    /// not keep panes open on deleted directories. It closes every pane
    /// there, the one this runs in included, so this runs once, after
    /// everything else.
    fn close_removed_herdr_workspaces(&self) {
        for wt in &self.removed_worktrees {
            if !on_path("herdr") {
                skip("the herdr workspace close", "herdr is not on PATH");
                continue;
            }
            let ids = herdr::workspaces_at(&quiet_stdout("herdr", &["workspace", "list"]).unwrap_or_default(), wt);
            if ids.is_empty() {
                skip("the herdr workspace close", &format!("no herdr workspace at {wt}"));
                continue;
            }
            for id in ids {
                self.step(&format!("closing herdr workspace {id}"), "herdr", &["workspace", "close", &id]);
            }
        }
    }

    /// #834 (Codex re-run): compare against a recorded build sha, not this
    /// run's own pre-pull HEAD — a pull elsewhere can already have landed the
    /// tip before this run starts. `flow/lane-install.sh` records the sha it
    /// installed from on every successful install, run by hand or from here,
    /// so a missing record is untrusted rather than a fallback to this run's
    /// own HEAD: it rebuilds once regardless of whether this run's pull moved
    /// anything, the same failure shape the old old_head/new_head check
    /// missed.
    fn fast_forward_and_rebuild(&self, primary: &str, default: &str) {
        self.step(&format!("fast-forwarding {default} in {primary}"), "git", &["-C", primary, "pull", "--ff-only", "--quiet"]);
        // A dry run never pulls, so HEAD does not move; nothing past here can
        // fire without a real pull having happened first.
        if self.dry {
            return;
        }
        let new_head = quiet_stdout("git", &["-C", primary, "rev-parse", "HEAD"]).unwrap_or_default();
        if new_head.is_empty() {
            return;
        }
        let install = format!("{primary}/flow/lane-install.sh");
        if !Path::new(&install).is_file() {
            return;
        }
        let build_sha_file = format!("{}/.local/state/lane/build-sha", self.home);
        let recorded = std::fs::read_to_string(&build_sha_file).ok().map(|s| s.trim().to_string()).filter(|s| !s.is_empty());
        if let Some(baseline) = &recorded {
            if quiet_ok("git", &["-C", primary, "diff", "--quiet", baseline, &new_head, "--", "flow/lane"]) {
                return;
            }
        }
        let why = if recorded.is_some() { "flow/lane changed" } else { "no recorded build sha" };
        safe_println!("{why}: rebuilding the lane binaries");
        let failure = match lane::runner::run("bash", &[&install]) {
            Ok(out) if out.success => return,
            Ok(out) => out.combined,
            Err(e) => e.to_string(),
        };
        eprintln!("merge-cleanup: lane rebuild failed, keeping the installed binaries:");
        eprintln!("{failure}");
    }

    /// `--sweep`: plan every merged branch under `root`, ask, clean, report.
    fn sweep(&mut self, root: &str, yes: bool) -> ExitCode {
        let root_dir = root.trim_end_matches('/');
        let mut repos = Vec::new();
        let mut plan = Vec::new();
        // Pass 1 — the plan: every merged branch, with its distance past its
        // merge proof, before anything is touched.
        for d in subdirs(root_dir) {
            let d = format!("{root}/{}/", d.rsplit('/').next().unwrap_or(""));
            if !quiet_ok("git", &["-C", &d, "rev-parse", "--git-dir"]) {
                continue;
            }
            repos.push(d.clone());
            let default = default_branch(Path::new(&d));
            let heads = quiet_stdout("git", &["-C", &d, "for-each-ref", "--format=%(refname:short)", "refs/heads/"]).unwrap_or_default();
            for b in heads.lines().filter(|b| !b.is_empty() && *b != default) {
                if let Some(m) = self.is_merged(&d, b) {
                    let n = quiet_stdout("git", &["-C", &d, "rev-list", "--count", &format!("{}..{b}", m.at)]).unwrap_or_else(|| "?".into());
                    let (files, held) = worktree_plan(&d, b);
                    plan.push(PlanRow { repo: d.clone(), branch: b.to_string(), unlanded: unlanded_text(&n, &m.by), files, held });
                }
            }
        }
        if !plan.is_empty() {
            let header = if self.dry { "sweep plan (dry run)" } else { "sweep plan" };
            safe_println!("{header}: {} merged branch(es) under {root}", plan.len());
            for row in &plan {
                let files = match (&row.files, row.held) {
                    (None, _) => String::new(),
                    (Some(files), None) => format!("  worktree: {files}"),
                    (Some(files), Some(held)) => format!("  worktree: {files} ({held})"),
                };
                safe_println!("  {} {}  {}{files}", row.name(), row.branch, row.unlanded);
            }
            // Nothing is deleted until confirmed. A closed or non-terminal
            // stdin is not a yes: an unattended sweep needs --yes on the line,
            // and it is told so rather than asked a question nobody can
            // answer. The question goes to stderr, so a sweep piped into
            // `tee` or `less` still shows it (#733).
            if !self.dry && !yes {
                if !std::io::stdin().is_terminal() {
                    return die("stdin is not a terminal; pass --yes");
                }
                eprint!("delete these branches and their worktrees? [y/N] ");
                let mut ans = String::new();
                let _ = std::io::stdin().read_line(&mut ans);
                // A deliberate no is an answer, not a failure: the operator
                // who reads the plan and declines still gets the stale
                // report, and a wrapper sees success (#734).
                if !matches!(ans.trim(), "y" | "Y" | "yes" | "YES") {
                    eprintln!("merge-cleanup: nothing deleted (answer y, or pass --yes)");
                    self.report_stale(&repos);
                    return ExitCode::SUCCESS;
                }
            }
        }
        // Pass 2 — the cleanup.
        let mut rc = ExitCode::SUCCESS;
        let mut rows = Vec::new();
        for row in &plan {
            // A worktree with work in it is left for the single-branch form
            // with --discard; --yes answers the plan, not for those files.
            if let Some(held) = row.held {
                rows.push([row.name().to_string(), row.branch.clone(), held.to_string(), row.unlanded.clone()]);
                continue;
            }
            safe_println!("== {} {}", row.repo.trim_end_matches('/'), row.branch);
            let verdict = if !self.cleanup_branch(&row.repo, &row.branch) {
                rc = ExitCode::FAILURE;
                "FAILED".to_string()
            } else if self.claim_clear_failed || self.remote_delete_failed {
                rc = ExitCode::FAILURE;
                partly_done("cleaned", self.remote_delete_failed, self.claim_clear_failed)
            } else {
                "cleaned".to_string()
            };
            rows.push([row.name().to_string(), row.branch.clone(), verdict, row.unlanded.clone()]);
        }
        safe_println!();
        safe_println!("sweep summary");
        if rows.is_empty() {
            safe_println!("  nothing merged to clean up under {root}");
        } else {
            print_table(&rows);
        }
        self.report_stale(&repos);
        self.close_removed_herdr_workspaces();
        rc
    }

    /// `--reap` (#876): one repo's own `implement-*` workspaces, each torn
    /// down by the single-branch path above, unchanged. Dry run by default —
    /// the opposite of the other two forms — because it acts on workspaces
    /// nobody named. It never discards and never forces: a workspace the
    /// single-branch guards would refuse is named and skipped, which is the
    /// safety property, not an obstacle.
    fn reap(&mut self, repo: &str, yes: bool) -> ExitCode {
        // Every git call anchors at the primary checkout, never at the path
        // the run was pointed at: with no --repo that path is the cwd, and a
        // run started inside a workspace would `git -C` its way into the
        // directory it had just removed — reaping one workspace and then
        // calling every workspace after it unmerged (the correctness axis on
        // PR #876). A repo with no primary checkout git can name is left as
        // it was passed.
        let anchor = match primary_of(repo) {
            p if p.is_empty() => repo.to_string(),
            p => p,
        };
        let root = worktrees_root(repo);
        let candidates = implement_workspaces(repo);
        if candidates.is_empty() {
            safe_println!("nothing to reap under {root}");
            return ExitCode::SUCCESS;
        }
        // --dry-run wins over --yes: the safer of two answers about whether
        // to remove is the one a run that was given both should take.
        let act = yes && !self.dry;
        let header = if act { "reap plan" } else { "reap plan (dry run)" };
        safe_println!("{header}: {} implement-* workspace(s) under {root}", candidates.len());
        // Pass 1 — the plan: every workspace and its disposition, before any
        // of them is touched, so a removal never runs ahead of its own report.
        let mut plan = Vec::new();
        for (wt, branch) in candidates {
            let held = self.reap_hold(&anchor, &wt, &branch);
            safe_println!("  {wt}  {}", held.as_deref().unwrap_or(if act { "to reap" } else { "would reap" }));
            plan.push((wt, branch, held));
        }
        // Pass 2 — the cleanup, through the single-branch path unchanged: it
        // re-runs every guard the plan only read, so a workspace that went
        // live or dirty since pass 1 still refuses.
        let mut rc = ExitCode::SUCCESS;
        let (mut reaped, mut ready, mut skipped, mut failed) = (0, 0, 0, 0);
        let mut verdicts = Vec::new();
        for (wt, branch, held) in plan {
            let verdict: String = match held {
                Some(held) => {
                    skipped += 1;
                    held
                }
                None if !act => {
                    ready += 1;
                    continue;
                }
                None => {
                    safe_println!("== {anchor} {branch}");
                    match self.reap_one(&anchor, &wt, &branch) {
                        Reaped::Gone(word) => {
                            reaped += 1;
                            word
                        }
                        Reaped::PartlyGone(word) => {
                            reaped += 1;
                            rc = ExitCode::FAILURE;
                            word
                        }
                        // A guard that refused between the plan and the
                        // removal is an answer, not a failure — the same
                        // reading --sweep gives a "dirty, not removed" row.
                        Reaped::Refused(held) => {
                            skipped += 1;
                            format!("{held} (refused at removal)")
                        }
                        Reaped::Failed => {
                            failed += 1;
                            rc = ExitCode::FAILURE;
                            "FAILED".into()
                        }
                    }
                }
            };
            // A dry run's plan above already said this about every
            // workspace; only the run that acted has anything to repeat.
            if act {
                verdicts.push((wt, verdict));
            }
        }
        let counts = if act {
            format!("{reaped} reaped, {skipped} skipped")
        } else {
            format!("{ready} would be reaped, {skipped} skipped (dry run; --yes removes)")
        };
        let counts = if failed > 0 { format!("{counts}, {failed} failed") } else { counts };
        safe_println!();
        safe_println!("reap summary: {counts}");
        for (wt, verdict) in verdicts {
            safe_println!("  {wt}  {verdict}");
        }
        self.close_removed_herdr_workspaces();
        rc
    }

    /// One workspace through the single-branch path, and what became of it.
    fn reap_one(&mut self, anchor: &str, wt: &str, b: &str) -> Reaped {
        // The plan named this workspace, but `cleanup_branch` resolves the
        // branch for itself. A branch moved between the two would put a
        // worktree the plan never listed — one outside .claude/worktrees/
        // included — in reach of the removal, so the scope is proved again
        // here, at the destructive call, and not only at enumeration (the
        // Codex pass on PR #878). A branch whose worktree simply went away
        // still cleans up: there is nothing left to remove out of scope. The
        // primary checkout counts as a holder (#881): it is not a removal
        // target, but a branch moved into it is still not the branch the plan
        // named, and `cleanup_branch` would switch it off and delete it.
        let now = worktree_holding(anchor, b);
        if !now.is_empty() && now != wt {
            return Reaped::Refused(format!("moved since the plan, not removed: {now} now holds {b}"));
        }
        if !self.cleanup_branch(anchor, b) {
            // Which guard refused is on stderr already; ask again what holds
            // the workspace, so a refusal reads as one rather than as a
            // failure of the run.
            return match self.reap_hold(anchor, wt, b) {
                Some(held) => Reaped::Refused(held),
                None => Reaped::Failed,
            };
        }
        if self.claim_clear_failed || self.remote_delete_failed {
            return Reaped::PartlyGone(partly_done("reaped", self.remote_delete_failed, self.claim_clear_failed));
        }
        Reaped::Gone("reaped".into())
    }

    /// Why the reaper leaves a workspace alone, if it does: the three
    /// refusals the single-branch path makes, plus this run's own cwd, read
    /// before anything is removed so the disposition line says what a
    /// removal would do. It changes nothing on disk — `is_merged` does ask
    /// the tracker and fetch, so it is not free, only harmless.
    fn reap_hold(&self, anchor: &str, wt: &str, b: &str) -> Option<String> {
        if in_tree(&cwd_path(), &resolved(wt)) {
            return Some("this run's own directory, not removed".into());
        }
        if self.is_merged(anchor, b).is_none() {
            return Some("not merged, not removed".into());
        }
        match WorktreeFiles::read(wt) {
            None => return Some("unreadable, not removed: git status failed".into()),
            Some(files) if files.is_dirty() => return Some(format!("dirty, not removed: {}", files.dirty_text())),
            Some(_) => {}
        }
        let live = self.occupancy(wt).live_items();
        (!live.is_empty()).then(|| format!("live session, not removed: {}", live.join(", ")))
    }

    /// Step 2 — is this branch actually merged? The tracker is the
    /// authority: a squash merge leaves none of the branch's commits in the
    /// default branch, so an ancestor test alone would call every squashed
    /// branch unmerged. But a merged PR proves only the sha it merged at: a
    /// branch that kept going after its PR is merged up to that head and
    /// unlanded past it, so the tip must equal a merged PR's head.
    /// (2026-09-13: a sweep took "a PR from this branch once merged" as
    /// merged and deleted 87 unlanded commits.) Without gh, fall back to the
    /// ancestor test — fetching first, since it reads origin/<default> and a
    /// stale ref there deletes a branch that is not merged.
    fn is_merged(&self, path: &str, b: &str) -> Option<Merged> {
        if on_path("gh")
            && let Some(slug) = origin_slug(Path::new(path))
        {
            let tip = quiet_stdout("git", &["-C", path, "rev-parse", "--verify", "-q", &format!("refs/heads/{b}")])
                .unwrap_or_default();
            let prs = quiet_stdout(
                "gh",
                &[
                    "pr", "list", "--repo", &slug, "--head", b, "--state", "merged", "--json", "number,headRefOid", "--jq",
                    r#".[] | "\(.number) \(.headRefOid)""#,
                ],
            )
            .unwrap_or_default();
            for line in prs.lines() {
                let mut f = line.split_whitespace();
                let (n, h) = (f.next().unwrap_or(""), f.next().unwrap_or(""));
                if !h.is_empty() && h == tip {
                    return Some(Merged { at: h.to_string(), by: format!("PR #{n}"), pr: Some(n.to_string()) });
                }
            }
        }
        quiet_ok("git", &["-C", path, "fetch", "-q", "origin"]);
        let base = format!("origin/{}", default_branch(Path::new(path)));
        if !quiet_ok("git", &["-C", path, "merge-base", "--is-ancestor", b, &base]) {
            return None;
        }
        let at = quiet_stdout("git", &["-C", path, "rev-parse", &base]).unwrap_or_default();
        Some(Merged { at, by: base, pr: None })
    }

    /// Step 4's delete. `-d` first: it is the honest question, and it
    /// succeeds on a real merge. A squash merge leaves the branch unmerged in
    /// git's eyes, so fall back to `-D` — step 2 has already proved the merge.
    fn delete_local(&self, path: &str, b: &str) -> bool {
        if self.dry {
            safe_println!("would delete local branch {b}");
            return true;
        }
        // The tip goes under refs/deleted first, so a wrong verdict is undone
        // with `git branch` rather than reflog forensics. A ref, not a note,
        // so the objects stay reachable past reflog expiry and gc. Keyed by
        // the tip's short sha (#737): refs/deleted/foo would block a later
        // refs/deleted/foo/bar, and a second delete of the same name would
        // overwrite the tip the first record kept.
        let short = quiet_stdout("git", &["-C", path, "rev-parse", "--short", &format!("refs/heads/{b}")]).unwrap_or_default();
        let record = format!("refs/deleted/{b}@{short}");
        let failure = match lane::runner::run("git", &["-C", path, "update-ref", &record, &format!("refs/heads/{b}")]) {
            Ok(out) if out.success => None,
            Ok(out) => Some(out.combined),
            Err(e) => Some(e.to_string()),
        };
        if let Some(why) = failure {
            eprintln!("merge-cleanup: could not record the tip of {b} at {record}, so it was not deleted: {why}");
            return false;
        }
        safe_println!("recorded the tip of {b} at {record} (git branch {b} {record} restores it)");
        if quiet_stderr_ok("git", &["-C", path, "branch", "-d", b]) {
            safe_println!("deleted local branch {b}");
            return true;
        }
        safe_println!("deleting local branch {b} with -D (the squash merge left it unmerged)");
        status("git", &["-C", path, "branch", "-D", b])
    }

    /// Steps 3-6 for one branch.
    fn cleanup_branch(&mut self, path: &str, b: &str) -> bool {
        // Reset here, not by each caller: every path through this function
        // that reaches step 5 or 7 can set either flag, and a caller doing
        // several branches (the sweep) must not read a previous branch's
        // failure onto this one.
        self.claim_clear_failed = false;
        self.remote_delete_failed = false;
        let primary = primary_of(path);
        let default = default_branch(Path::new(path));
        if b == default {
            eprintln!("merge-cleanup: refusing to delete the default branch {b}");
            return false;
        }
        // Kept, not discarded: step 7 needs the PR this landing came from,
        // and by then the branch is deleted, so the tip it was matched on is
        // gone and the match cannot be redone.
        let merged = if self.force {
            safe_println!("--force: skipping the merged check for {b}");
            None
        } else {
            match self.is_merged(path, b) {
                None => {
                    eprintln!("merge-cleanup: {b} is not merged — nothing cleaned up (--force overrides)");
                    return false;
                }
                Some(m) => Some(m),
            }
        };

        // Step 3 — the workspace. A linked worktree holding the branch makes
        // `git branch -d` fail with "used by worktree", so it goes first, by
        // the path git itself reports — but never while a session is alive.
        if let Some(wt) = linked_worktree_holding(path, b) {
            // Before the live-session guard, which closes idle panes: a
            // removal refused for its files must not have touched herdr.
            let Some(empty_dirs) = self.guard_files(&wt) else {
                return false;
            };
            if !self.guard_live(&wt) {
                return false;
            }
            self.removal_targets.push(wt.clone());
            if self.step(&format!("removing the linked worktree at {wt}"), "git", &["-C", path, "worktree", "remove", "--force", &wt]) {
                // After the removal, never before it: these went with the
                // worktree, so the line accounts for what was actually taken.
                let verb = if self.dry { "would remove" } else { "removing" };
                for dir in &empty_dirs {
                    safe_println!("{verb} the empty ignored directory at {wt}/{}", dir);
                }
                // #964: a dispatch's controller/worker record is bookkeeping
                // alongside the workspace, not something worth its own
                // guard — a dry run announces the removal without doing it,
                // so it must not also announce clearing a record that is
                // still there.
                if !self.dry && lane::workers::remove_workspace(Path::new(&self.home), &wt) {
                    safe_println!("cleared the controller's worker record for {wt}");
                }
                self.removed_worktrees.push(wt);
            }
        }
        self.step("pruning stale worktree entries", "git", &["-C", path, "worktree", "prune"]);

        // Step 4 — the local branch. Git refuses to delete a branch a
        // checkout holds, so move the primary off it first.
        if !primary.is_empty() && head_of(&primary).as_deref() == Some(b) {
            let switched = if quiet_ok("git", &["-C", &primary, "show-ref", "-q", "--verify", &format!("refs/heads/{default}")]) {
                self.step(&format!("switching {primary} off {b} onto {default}"), "git", &["-C", &primary, "checkout", "-q", &default])
            } else {
                self.step(
                    &format!("switching {primary} off {b} onto a fresh {default}"),
                    "git",
                    &["-C", &primary, "checkout", "-q", "-b", &default, "--track", &format!("origin/{default}")],
                )
            };
            if !switched {
                return false;
            }
        }
        if quiet_ok("git", &["-C", path, "show-ref", "-q", "--verify", &format!("refs/heads/{b}")]) {
            if !self.delete_local(path, b) {
                return false;
            }
        } else {
            skip("the local branch delete", &format!("no local {b}"));
        }

        // Step 5 — the remote branch, if the merge did not already drop it.
        // A denied or failed delete (branch protection, a race) used to be
        // discarded here (#842 Codex pass), so it neither failed the run
        // nor said the remote branch was still there.
        if quiet_ok("git", &["-C", path, "ls-remote", "--exit-code", "--heads", "origin", b]) {
            if !self.step(&format!("deleting remote branch {b}"), "git", &["-C", path, "push", "origin", "--delete", b]) {
                self.remote_delete_failed = true;
                eprintln!("merge-cleanup: could not delete remote branch {b}; re-run: git -C {path} push origin --delete {b}");
            }
        } else {
            skip("the remote branch delete", &format!("origin has no {b}"));
        }

        // Step 6 — fast-forward the primary checkout, so the next branch
        // starts from the merge rather than from behind it.
        if !primary.is_empty() && head_of(&primary).as_deref() == Some(default.as_str()) {
            self.fast_forward_and_rebuild(&primary, &default);
        } else {
            skip("the fast-forward", &format!("{primary} is not on {default}"));
        }

        // Step 7 (#821) — the ticket. `merge-cleanup` was the only place in
        // the lane that never cleared a landed claim, so a closed ticket kept
        // showing in-progress and assigned. An open issue (part of a bigger
        // ticket, or reopened) is left alone. Still runs on a failed step 5
        // (#842 Codex pass): the PR merged either way, so the claim clears
        // regardless of whether the remote branch did. #832: a failed clear
        // does not make this call return false — the git cleanup above it
        // already succeeded (or, per step 5, mostly did), and `false` here
        // means "the branch and worktree are still there" to both callers
        // (the sweep table's "cleaned" word, and `main`'s gate on
        // `report_stale`). It sets `claim_clear_failed` instead, for the
        // caller to fold into its own exit code, same as `remote_delete_failed`.
        self.claim_clear_failed = !self.clear_landed_claims(path, b, merged.as_ref().and_then(|m| m.pr.as_deref()));
        true
    }

    /// #821, widened for clumps by #889: clear `in-progress` and the
    /// assignee from every ticket this branch's merge landed. A clump is
    /// one worker, one branch, one PR closing several tickets, so the PR's
    /// `closingIssuesReferences` is the list — the branch's own ticket
    /// alone left the rest of a clump showing a stale claim, hand-cleared
    /// six times on one trial clump. The branch must still be a plain
    /// `implement-<n>`: a branch the lane did not cut is not a claim this
    /// command owns. No gh or no origin: nothing to do, and `true`. A
    /// failed edit (#829 Codex pass found it discarded) is different: git
    /// cleanup already succeeded by then, so #832 makes this return
    /// `false` — `cleanup_branch` reads that into `self.claim_clear_failed`,
    /// which is what actually fails the run's exit code — with the exact
    /// re-run command on stderr, since that command is the only record of
    /// the edit that still needs to happen.
    fn clear_landed_claims(&self, path: &str, b: &str, pr: Option<&str>) -> bool {
        let Some(n) = ticket_number(b) else { return true };
        let what = format!("clearing #{n}'s in-progress label and assignee");
        if !on_path("gh") {
            skip(&what, "gh is not on PATH");
            return true;
        }
        let Some(slug) = origin_slug(Path::new(path)) else {
            skip(&what, "no origin remote");
            return true;
        };
        // The union, ascending and each once: the tickets the merged PR
        // closes, plus the branch's own. The PR's closingIssuesReferences is
        // the clump's list and needs no bookkeeping of its own; keeping the
        // branch's ticket in the set whatever the PR says is what makes a PR
        // whose closing keyword never registered, and a --force run with no
        // merged PR to read, clear exactly what they cleared before #889.
        // Sorted by length then text rather than by parsed number: these are
        // digit strings straight from a branch name, and a number too long
        // for u64 must not silently drop out of the set.
        let mut tickets: Vec<String> = vec![n.to_string()];
        let mut ok = true;
        match pr_closed_tickets(&slug, pr) {
            Ok(closed) => tickets.extend(closed.iter().map(u64::to_string)),
            // A lookup that failed is not a PR that closed nothing. Read as
            // one, it clears the branch's ticket, prints success and leaves
            // the rest of the clump claimed — the exact stale state #889
            // exists to end. So the run fails, and the message names the
            // read to redo, because by now the branch is gone and re-running
            // merge-cleanup cannot repeat it.
            Err(why) => {
                ok = false;
                let pr = pr.unwrap_or("?");
                eprintln!(
                    "merge-cleanup: could not read which tickets PR #{pr} closes ({why}); any other ticket in \
                     its clump is still claimed — re-run: gh pr view {pr} --repo {slug} --json closingIssuesReferences"
                );
            }
        }
        tickets.sort_by(|a, b| a.len().cmp(&b.len()).then_with(|| a.cmp(b)));
        tickets.dedup();

        let mut cleared: Vec<String> = Vec::new();
        for t in &tickets {
            match self.clear_one(&slug, t) {
                Cleared::Done => cleared.push(format!("#{t}")),
                Cleared::Failed => ok = false,
                Cleared::Nothing => {}
            }
        }
        // Only a clump gets the summary: on a one-ticket PR the per-ticket
        // line above is already the whole report, and it is the line #821's
        // callers and tests read.
        if tickets.len() > 1 && !cleared.is_empty() {
            safe_println!("cleared {}", cleared.join(", "));
        }
        ok
    }

    /// One ticket's claim. A `gh issue view` that fails is reported, not
    /// treated as an open issue — an outage must not silently reproduce the
    /// stale claim #821 was filed over — but is still `Nothing`, since there
    /// was never a known edit to lose.
    fn clear_one(&self, slug: &str, n: &str) -> Cleared {
        let what = format!("clearing #{n}'s in-progress label and assignee");
        let Some(issue) = lane::issue_state::read(slug, n) else {
            skip(&what, "gh issue view failed");
            return Cleared::Nothing;
        };
        if issue.state != "CLOSED" || !issue.has_label("in-progress") {
            return Cleared::Nothing;
        }
        let mut edit = vec!["issue", "edit", n, "--repo", slug, "--remove-label", "in-progress"];
        if !issue.assignees_csv.is_empty() {
            edit.push("--remove-assignee");
            edit.push(&issue.assignees_csv);
        }
        if !self.step(&what, "gh", &edit) {
            // #842 Codex pass: "git cleanup completed" is only true when
            // step 5 also succeeded — said unconditionally, it would tell an
            // operator the branch was gone from origin when it wasn't.
            let cleanup_status =
                if self.remote_delete_failed { "git cleanup did not fully complete (the remote branch delete also failed)" } else { "git cleanup completed" };
            eprintln!(
                "merge-cleanup: {cleanup_status}, but could not clear #{n}'s in-progress label and assignee; re-run: gh {}",
                edit.join(" ")
            );
            return Cleared::Failed;
        }
        Cleared::Done
    }
}

/// What `clear_one` did with one ticket's claim.
enum Cleared {
    /// Nothing to do: the issue is still open (part of a bigger ticket, or
    /// reopened), it no longer carries `in-progress` (already cleared, and
    /// `gh issue edit` errors on a label a repo never defines), or it could
    /// not be read.
    Nothing,
    /// The label and the issue's assignees came off.
    Done,
    /// The edit failed. The caller folds this into the run's exit code; the
    /// re-run command is already on stderr.
    Failed,
}

/// One merged branch the sweep will clean.
struct PlanRow {
    repo: String,
    branch: String,
    unlanded: String,
    /// The file counts of the linked worktree holding the branch, if any.
    files: Option<String>,
    /// Why the sweep leaves this branch and its worktree alone, if it does.
    held: Option<&'static str>,
}

/// A sweep plan row's worktree counts and hold: the modified, untracked and
/// ignored counts of the linked worktree holding `b`, and a hold when it has
/// work a removal would lose — or when git cannot say whether it does.
fn worktree_plan(repo: &str, b: &str) -> (Option<String>, Option<&'static str>) {
    let Some(wt) = linked_worktree_holding(repo, b) else { return (None, None) };
    match WorktreeFiles::read(&wt) {
        None => (Some("git status failed".into()), Some("unreadable, not removed")),
        Some(f) => (Some(f.counts()), f.is_dirty().then_some("dirty, not removed")),
    }
}

impl PlanRow {
    fn name(&self) -> &str {
        self.repo.trim_end_matches('/').rsplit('/').next().unwrap_or("")
    }
}

/// How far a branch is past the sha its merge proof covers — printed beside
/// every sweep deletion. Zero is the healthy case (a squash merge lands the
/// whole branch, so counting against main would show a number on every
/// row); anything else is a branch the proof does not cover, and must be
/// read. `n` is `?` when git cannot say.
fn unlanded_text(n: &str, by: &str) -> String {
    let plural = if n == "1" { "" } else { "s" };
    format!("{n} commit{plural} past {by}")
}

/// `printf '  %s\n' rows | column -t -s '|'`: each column padded to its
/// widest cell, two spaces between columns, the last column unpadded.
fn print_table(rows: &[[String; 4]]) {
    let mut widths = [0usize; 4];
    for row in rows {
        for (i, cell) in row.iter().enumerate() {
            let w = cell.chars().count() + if i == 0 { 2 } else { 0 };
            widths[i] = widths[i].max(w);
        }
    }
    for row in rows {
        let mut line = String::new();
        for (i, cell) in row.iter().enumerate() {
            let cell = if i == 0 { format!("  {cell}") } else { cell.clone() };
            if i == row.len() - 1 {
                line.push_str(&cell);
            } else {
                line.push_str(&format!("{cell:<width$}  ", width = widths[i]));
            }
        }
        safe_println!("{line}");
    }
}

/// The issues the merged PR `pr` closes, restricted to `slug`'s own repo. A
/// reference elsewhere is dropped and named on its own skip line: every edit
/// here goes out with `--repo <slug>`, so acting on that number would edit
/// an unrelated issue that happens to share it — and a claim this run is
/// leaving alone has to say so, or a cross-repo clump reads as cleared when
/// it is not.
///
/// One PR, named by the caller, not every merged PR the branch name ever
/// carried: a name is reused, and an earlier landing's tickets are not this
/// one's to unclaim. `is_merged` already picked the PR whose head is this
/// tip; this reads that one.
///
/// `Ok(vec![])` is GitHub's own answer that the PR closes nothing, and
/// `pr: None` — a `--force` run, or a merge proved by the ancestor test with
/// no PR to name — is the same: the caller falls back to the branch's own
/// ticket, as it did before #889. `Err` is not that. The call failed, the
/// answer is not JSON, or it is JSON of the wrong shape: a
/// `closingIssuesReferences` that is not an array, or a reference with no
/// number. Those must not collapse into the empty answer — a cleanup that
/// cannot read the clump's list must not report success.
fn pr_closed_tickets(slug: &str, pr: Option<&str>) -> Result<Vec<u64>, String> {
    let Some(pr) = pr else { return Ok(Vec::new()) };
    // No owner/name to compare against means the same-repo filter below
    // cannot run, and every reference would be dropped in silence — the
    // same failure as an unreadable answer, so it is reported the same way.
    let Some((owner, name)) = slug.rsplit_once('/') else {
        return Err(format!("origin slug {slug} names no owner/name"));
    };
    let Some(out) = quiet_stdout("gh", &["pr", "view", pr, "--repo", slug, "--json", "closingIssuesReferences"]) else {
        return Err("gh pr view failed".into());
    };
    let Ok(body) = serde_json::from_str::<serde_json::Value>(&out) else {
        return Err("gh pr view answered something that is not JSON".into());
    };
    let Some(refs) = body.get("closingIssuesReferences").and_then(serde_json::Value::as_array) else {
        return Err("gh pr view answered no closingIssuesReferences array".into());
    };
    let mut tickets = Vec::new();
    for r in refs {
        let repo = r.get("repository");
        let r_name = repo.and_then(|v| v.get("name")).and_then(serde_json::Value::as_str).unwrap_or("");
        let r_owner = repo.and_then(|v| v.get("owner")).and_then(|v| v.get("login")).and_then(serde_json::Value::as_str).unwrap_or("");
        let Some(number) = r.get("number").and_then(serde_json::Value::as_u64) else {
            return Err("a closing reference has no issue number".into());
        };
        if (r_owner, r_name) != (owner, name) {
            skip(&format!("clearing {r_owner}/{r_name}#{number}"), &format!("another repo; this run only edits {slug}"));
            continue;
        }
        tickets.push(number);
    }
    Ok(tickets)
}

/// The ticket a plain `implement-<n>` branch was cut for: the digits after
/// `implement-`. `implement-spec-<n>` and any other branch name have no
/// ticket to clear.
fn ticket_number(b: &str) -> Option<&str> {
    let n = b.strip_prefix("implement-")?;
    (!n.is_empty() && n.chars().all(|c| c.is_ascii_digit())).then_some(n)
}

/// What became of one workspace the reaper put through the cleanup.
enum Reaped {
    /// Gone.
    Gone(String),
    /// Gone, but a step after the removal did not run — `partly_done` words it.
    PartlyGone(String),
    /// A guard refused, and names itself.
    Refused(String),
    /// The cleanup failed with no guard holding the workspace.
    Failed,
}

/// The word for a branch whose git cleanup succeeded — the branch and
/// worktree are gone — but whose remote delete or claim clear did not
/// (#832, and the #842 Codex pass), `verb` being the caller's own past
/// tense for the cleanup. Shared by --sweep and --reap so a half-done
/// cleanup can never be called one thing in one form's table and another in
/// the other's, and so neither ever reads like the branch survived; the
/// exit code fails the run either way.
fn partly_done(verb: &str, remote_failed: bool, claim_failed: bool) -> String {
    match (remote_failed, claim_failed) {
        (true, true) => format!("{verb}, remote branch and claim not cleared"),
        (true, false) => format!("{verb}, remote branch not deleted"),
        (false, true) => format!("{verb}, claim not cleared"),
        (false, false) => unreachable!(),
    }
}

/// This process's working directory, symlinks resolved. Empty when there is
/// none to read — a cwd that has itself been deleted — which `in_tree` then
/// matches nothing against.
fn cwd_path() -> String {
    env::current_dir().and_then(|p| p.canonicalize()).map(|p| p.display().to_string()).unwrap_or_default()
}

/// A path with its symlinks resolved, or as given when it cannot be. Both
/// sides of the cwd comparison go through this: git reports a worktree by
/// the path it was added under, which a repo reached through a symlink
/// spells differently from the cwd's resolved form.
fn resolved(p: &str) -> String {
    resolved_under(p).unwrap_or_else(|| p.to_string())
}

/// A path resolved for a containment test: symlinks followed, and a
/// directory that is already gone resolved through its parent — git still
/// registers a workspace whose folder was deleted, and that one is still a
/// candidate. `None` when not even the parent resolves, which is a path
/// this run cannot prove is inside anything.
fn resolved_under(p: &str) -> Option<String> {
    if let Ok(r) = std::fs::canonicalize(p) {
        return Some(r.display().to_string());
    }
    let path = Path::new(p);
    let parent = std::fs::canonicalize(path.parent()?).ok()?;
    Some(parent.join(path.file_name()?).display().to_string())
}

/// Where one repo keeps its workspaces: `<primary>/.claude/worktrees`.
fn worktrees_root(repo: &str) -> String {
    format!("{}/.claude/worktrees", primary_of(repo))
}

/// The reaper's candidates: this repo's linked worktrees that sit under its
/// own `.claude/worktrees/` and hold a branch named `implement-*`, as
/// (worktree path, branch), in path order. Nothing outside the repo can
/// appear — `git worktree list` only ever reports the repo's own — and a
/// worktree elsewhere on disk is left out however its branch is named.
fn implement_workspaces(repo: &str) -> Vec<(String, String)> {
    let primary = primary_of(repo);
    let Some(root) = resolved_under(&worktrees_root(repo)) else { return Vec::new() };
    let out = quiet_stdout("git", &["-C", repo, "worktree", "list", "--porcelain"]).unwrap_or_default();
    let mut found = Vec::new();
    let mut current = "";
    for line in out.lines() {
        if let Some(p) = line.strip_prefix("worktree ") {
            current = p;
        } else if let Some(b) = line.strip_prefix("branch refs/heads/")
            // The primary checkout cannot sit under its own
            // .claude/worktrees, so this is belt and braces on top of
            // in_tree — kept, and deliberately unwitnessed, because the
            // cost of being wrong is a repo's own checkout's branch.
            && current != primary
            // Both sides resolved, the same way the cwd hold resolves them:
            // a path that cannot be proved inside the root is not a
            // candidate. git records a worktree by its resolved path, so
            // this is the class closed rather than a hole plugged (the
            // Codex pass on PR #878).
            && resolved_under(current).is_some_and(|here| in_tree(&here, &root))
            && b.starts_with("implement-")
        {
            found.push((current.to_string(), b.to_string()));
        }
    }
    found.sort();
    found
}

/// The linked worktree — not the primary checkout — that has `b` checked out.
fn linked_worktree_holding(path: &str, b: &str) -> Option<String> {
    let wt = worktree_holding(path, b);
    (!wt.is_empty() && wt != primary_of(path)).then_some(wt)
}

/// The path of the worktree that has `b` checked out, or empty.
fn worktree_holding(path: &str, b: &str) -> String {
    let want = format!("branch refs/heads/{b}");
    let mut current = "";
    let out = quiet_stdout("git", &["-C", path, "worktree", "list", "--porcelain"]).unwrap_or_default();
    for line in out.lines() {
        if let Some(p) = line.strip_prefix("worktree ") {
            current = p;
        } else if line == want {
            return current.to_string();
        }
    }
    String::new()
}

/// `"$dir"/*/`: the non-hidden directories in `dir`, sorted, as paths. A
/// listing, not a glob, so a missing `dir` yields nothing rather than the
/// unexpanded pattern (#735).
fn subdirs(dir: &str) -> Vec<String> {
    let Ok(entries) = std::fs::read_dir(dir) else { return Vec::new() };
    let mut names: Vec<String> = entries
        .filter_map(Result::ok)
        .filter(|e| std::fs::metadata(e.path()).is_ok_and(|m| m.is_dir()))
        .map(|e| e.file_name().to_string_lossy().into_owned())
        .filter(|n| !n.starts_with('.'))
        .collect();
    names.sort();
    names.into_iter().map(|n| format!("{dir}/{n}")).collect()
}

fn main() -> ExitCode {
    let a = match parse_args(env::args().skip(1)) {
        Parsed::Help => {
            safe_print!("{}", help_text());
            return ExitCode::SUCCESS;
        }
        Parsed::Err(e) => return die(e),
        Parsed::Args(a) => a,
    };
    let mut c = Cleanup {
        dry: a.dry,
        force: a.force,
        discard: a.discard,
        home: env::var("HOME").unwrap_or_default(),
        removal_targets: Vec::new(),
        removed_worktrees: Vec::new(),
        claim_clear_failed: false,
        remote_delete_failed: false,
    };

    if a.sweep {
        // One reach per run: --sweep walks every repo under a root, --reap
        // one repo's own workspaces, and a line asking for both has not said
        // which (#876).
        if a.reap {
            return die("--reap and --sweep are different forms");
        }
        if !a.branch.is_empty() || !a.pr.is_empty() {
            return die("--sweep takes no branch or PR");
        }
        if a.discard {
            return die("--discard takes one branch, not --sweep");
        }
        let root = if a.root.is_empty() { format!("{}/src", c.home) } else { a.root.clone() };
        if !Path::new(&root).is_dir() {
            return die(format!("no such root: {root}"));
        }
        return c.sweep(&root, a.yes);
    }

    let repo = if a.repo.is_empty() { env::current_dir().map(|p| p.display().to_string()).unwrap_or_default() } else { a.repo.clone() };
    if !quiet_ok("git", &["-C", &repo, "rev-parse", "--git-dir"]) {
        return die(format!("not a git repo: {repo}"));
    }

    if a.reap {
        if !a.branch.is_empty() || !a.pr.is_empty() {
            return die("--reap takes no branch or PR");
        }
        // The reaper has no override and never gains one: these two are the
        // ways the single-branch form skips a guard, and a run that acts on
        // workspaces nobody named must not be able to reach either (#876).
        if a.discard {
            return die("--discard takes one branch, not --reap");
        }
        if a.force {
            return die("--force takes one branch, not --reap");
        }
        // --root is --sweep's reach. Silently ignored here, it would read as
        // a reaper pointed somewhere it never looks.
        if !a.root.is_empty() {
            return die("--root takes --sweep, not --reap");
        }
        return c.reap(&repo, a.yes);
    }

    let mut branch = a.branch.clone();
    if branch.is_empty() && !a.pr.is_empty() {
        let Some(slug) = origin_slug(Path::new(&repo)) else {
            return die(format!("no origin remote in {repo}"));
        };
        let pr = &a.pr;
        let out = std::process::Command::new("gh")
            .args(["pr", "view", pr, "--repo", &slug, "--json", "headRefName", "-q", ".headRefName"])
            .stderr(std::process::Stdio::inherit())
            .output();
        match out {
            Ok(o) if o.status.success() => branch = String::from_utf8_lossy(&o.stdout).trim_end_matches('\n').to_string(),
            _ => return die(format!("could not read PR #{pr}")),
        }
        if branch.is_empty() {
            return die(format!("PR #{pr} has no head branch"));
        }
        safe_println!("PR #{pr} is {branch}");
    }
    if branch.is_empty() {
        return die("name a branch, a PR number or URL, or pass --sweep");
    }
    let ok = c.cleanup_branch(&repo, &branch);
    if ok {
        // #832 / #842: report_stale is about this repo's other worktrees,
        // not whether the ticket's claim or its remote branch got cleared —
        // it still runs when git cleanup succeeded, even if
        // claim_clear_failed or remote_delete_failed will fail the exit.
        c.report_stale(&[repo]);
    }
    c.close_removed_herdr_workspaces();
    if ok && !c.claim_clear_failed && !c.remote_delete_failed { ExitCode::SUCCESS } else { ExitCode::FAILURE }
}
