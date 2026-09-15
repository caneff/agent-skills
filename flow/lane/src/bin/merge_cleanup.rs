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

--sweep walks every git repo one level under <dir> (default ~/src), prints
the merged local branches it would clean — each with what proved it merged,
how many commits sit past that proof (0 is healthy), and the modified,
untracked, ignored and cache file counts of the worktree holding it — and
asks before touching anything: --yes answers for you, --dry-run never asks.
Then it runs the same six steps for each and prints a summary table with the
same count.

A linked worktree with modified, untracked or ignored files is never removed:
the single-branch form refuses, naming them, and --discard removes it anyway
(--force only skips the merged check); --sweep lists it "dirty, not removed"
even with --yes. Ignored files include .scratch/ and every other ignored name
except the regenerable caches: an ignored entry named node_modules,
__pycache__, target, .venv, .pytest_cache, .ruff_cache or .mypy_cache, or
inside one whose own .gitignore is `*`, never refuses — it is removed with the
worktree, and its count and first names are printed as cache file(s), distinct
from the ignored file(s) count above: the two never share a label, so a name
Chris approved losing under one count is never misread as counted by the
other. The list is fixed on purpose: an unknown ignored name is kept, since
a wrongly kept cache costs a --discard and a discarded note cannot be undone.

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

/// What proved a branch merged: the sha it is landed up to, and the proof.
struct Merged {
    at: String,
    by: String,
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
    /// Nothing the guard would refuse on: no unresolved session, and herdr
    /// absent or answering with idle agents only.
    fn is_clear(&self) -> bool {
        self.unresolved.is_empty()
            && match &self.herdr {
                HerdrAnswer::Absent => true,
                HerdrAnswer::Failed => false,
                HerdrAnswer::Agents(agents) => blockers(agents).is_empty(),
            }
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
/// `git status --porcelain --ignored` entries, by kind. An untracked or
/// ignored directory is one entry, as git collapses it.
#[derive(Default)]
struct WorktreeFiles {
    modified: Vec<String>,
    untracked: Vec<String>,
    /// Ignored entries that are not regenerable caches — `.scratch/` evidence.
    ignored: Vec<String>,
    /// Ignored entries `is_cache` accepts.
    caches: Vec<String>,
}

/// How many names a message lists before "and <n> more".
const NAMES_SHOWN: usize = 5;

/// The ignored directory names a removal may discard unasked. Deny by
/// default (#801): an unknown ignored name is kept, because a wrongly kept
/// cache costs a --discard and a wrongly discarded note cannot be undone.
const CACHE_DIRS: &[&str] = &["node_modules", "__pycache__", "target", ".venv", ".pytest_cache", ".ruff_cache", ".mypy_cache"];

/// An ignored entry in worktree `wt` is a cache when its own name is in
/// `CACHE_DIRS` (a directory, or a symlink git lists with no trailing
/// slash), or when it sits inside a directory so named that marks itself
/// wholly ignored with a `*` .gitignore — pytest, ruff, mypy and venv write
/// one, so git lists their contents rather than the directory. A file under
/// a directory merely named `target/` is not a cache.
fn is_cache(wt: &str, entry: &str) -> bool {
    let parts: Vec<&str> = entry.trim_end_matches('/').split('/').collect();
    let last = parts.len() - 1;
    parts.iter().enumerate().any(|(i, name)| {
        CACHE_DIRS.contains(name) && (i == last || ignores_all(&Path::new(wt).join(parts[..=i].join("/"))))
    })
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
            let (code, name) = (&line[..2], line[3..].to_string());
            match code {
                "??" => files.untracked.push(name),
                "!!" if is_cache(wt, &name) => files.caches.push(name),
                "!!" => files.ignored.push(name),
                _ => files.modified.push(name),
            }
        }
        Some(files)
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
    /// that are present, then their first names.
    fn dirty_text(&self) -> String {
        let kinds: Vec<String> = [("modified", &self.modified), ("untracked", &self.untracked), ("ignored", &self.ignored)]
            .iter()
            .filter(|(_, v)| !v.is_empty())
            .map(|(k, v)| format!("{} {k}", v.len()))
            .collect();
        let names: Vec<String> = self.modified.iter().chain(&self.untracked).chain(&self.ignored).cloned().collect();
        format!("{} file(s) would be lost: {}", kinds.join(", "), first_names(&names))
    }
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
    /// included (#801), empty or not: a process can fill it between the read
    /// and the removal, and an empty directory can be intentional, so
    /// emptiness earns no exemption (#823, reversed by a Codex pass on the
    /// PR). Caches (`is_cache`) never refuse; their count and first names
    /// are printed as "cache file(s)", since they go too — a label distinct
    /// from the non-cache "ignored file(s)" refusal above (#823), so a name
    /// approved for loss in one line is never misread as belonging to the
    /// other's.
    fn guard_files(&self, wt: &str) -> bool {
        let Some(files) = WorktreeFiles::read(wt) else {
            eprintln!("merge-cleanup: refusing to remove {wt} — git status failed there");
            return false;
        };
        if files.is_dirty() {
            if !self.discard {
                eprintln!("merge-cleanup: refusing to remove {wt} — {} (--discard overrides)", files.dirty_text());
                return false;
            }
            safe_println!("--discard: {wt} — {}", files.dirty_text());
        }
        if !files.caches.is_empty() {
            let would = if self.dry { "would discard" } else { "discarding" };
            safe_println!("{would} {} cache file(s) in {wt}: {}", files.caches.len(), first_names(&files.caches));
        }
        true
    }

    /// Other workspaces under <repo>/.claude/worktrees the guard would clear,
    /// no commits ahead of the default branch and nothing on disk git does
    /// not hold (ignored files and caches included — .scratch evidence is
    /// work too):
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

    /// #748: when the pull moves HEAD and the move touches flow/lane, the
    /// installed lane binaries would otherwise run behind main. Rebuilds from
    /// the freshly pulled checkout's own flow/lane-install.sh, so this works
    /// the same whether `primary` is this tooling's own repo or, for any other
    /// repo (no flow/lane there), is a no-op. A build failure is reported
    /// with the compiler's error and never fails the fast-forward that
    /// already happened — a dry run never pulls, so HEAD does not move and
    /// this is a no-op.
    fn fast_forward_and_rebuild(&self, primary: &str, default: &str) {
        let old_head = quiet_stdout("git", &["-C", primary, "rev-parse", "HEAD"]).unwrap_or_default();
        self.step(&format!("fast-forwarding {default} in {primary}"), "git", &["-C", primary, "pull", "--ff-only", "--quiet"]);
        let new_head = quiet_stdout("git", &["-C", primary, "rev-parse", "HEAD"]).unwrap_or_default();
        if old_head.is_empty() || new_head.is_empty() || old_head == new_head {
            return;
        }
        let install = format!("{primary}/flow/lane-install.sh");
        if !Path::new(&install).is_file() {
            return;
        }
        if quiet_ok("git", &["-C", primary, "diff", "--quiet", &old_head, &new_head, "--", "flow/lane"]) {
            return;
        }
        safe_println!("flow/lane changed: rebuilding the lane binaries");
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
            let verdict = if self.cleanup_branch(&row.repo, &row.branch) {
                "cleaned"
            } else {
                rc = ExitCode::FAILURE;
                "FAILED"
            };
            rows.push([row.name().to_string(), row.branch.clone(), verdict.to_string(), row.unlanded.clone()]);
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
                    return Some(Merged { at: h.to_string(), by: format!("PR #{n}") });
                }
            }
        }
        quiet_ok("git", &["-C", path, "fetch", "-q", "origin"]);
        let base = format!("origin/{}", default_branch(Path::new(path)));
        if !quiet_ok("git", &["-C", path, "merge-base", "--is-ancestor", b, &base]) {
            return None;
        }
        let at = quiet_stdout("git", &["-C", path, "rev-parse", &base]).unwrap_or_default();
        Some(Merged { at, by: base })
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
        let primary = primary_of(path);
        let default = default_branch(Path::new(path));
        if b == default {
            eprintln!("merge-cleanup: refusing to delete the default branch {b}");
            return false;
        }
        if self.force {
            safe_println!("--force: skipping the merged check for {b}");
        } else if self.is_merged(path, b).is_none() {
            eprintln!("merge-cleanup: {b} is not merged — nothing cleaned up (--force overrides)");
            return false;
        }

        // Step 3 — the workspace. A linked worktree holding the branch makes
        // `git branch -d` fail with "used by worktree", so it goes first, by
        // the path git itself reports — but never while a session is alive.
        if let Some(wt) = linked_worktree_holding(path, b) {
            // Before the live-session guard, which closes idle panes: a
            // removal refused for its files must not have touched herdr.
            if !self.guard_files(&wt) {
                return false;
            }
            if !self.guard_live(&wt) {
                return false;
            }
            self.removal_targets.push(wt.clone());
            if self.step(&format!("removing the linked worktree at {wt}"), "git", &["-C", path, "worktree", "remove", "--force", &wt]) {
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
        if quiet_ok("git", &["-C", path, "ls-remote", "--exit-code", "--heads", "origin", b]) {
            self.step(&format!("deleting remote branch {b}"), "git", &["-C", path, "push", "origin", "--delete", b]);
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
        // ticket, or reopened) is left alone.
        self.clear_ticket_if_closed(path, b);
        true
    }

    /// #821: on a plain `implement-<n>` branch whose issue is closed and
    /// still carries `in-progress`, remove the label and its actual
    /// assignees. No ticket number, no gh, no origin, the issue still open,
    /// or the label already gone (nothing to clear, and `gh issue edit`
    /// errors on a label a repo never defines): nothing to do. A `gh issue
    /// view` that fails is reported, not treated as an open issue — an
    /// outage must not silently reproduce the stale claim #821 was filed
    /// over. A failed edit (#829 Codex pass) is reported too, with the
    /// exact command to re-run — non-fatal, like this function's other
    /// post-cleanup courtesy steps (`fast_forward_and_rebuild`, the herdr
    /// workspace close), since the branch and worktree are already gone by
    /// this point and failing the whole run would misreport what happened.
    fn clear_ticket_if_closed(&self, path: &str, b: &str) {
        let Some(n) = ticket_number(b) else { return };
        let what = format!("clearing #{n}'s in-progress label and assignee");
        if !on_path("gh") {
            skip(&what, "gh is not on PATH");
            return;
        }
        let Some(slug) = origin_slug(Path::new(path)) else {
            skip(&what, "no origin remote");
            return;
        };
        let Some(issue) = quiet_stdout(
            "gh",
            &[
                "issue",
                "view",
                n,
                "--repo",
                &slug,
                "--json",
                "state,labels,assignees",
                "-q",
                ".state + \" \" + ([.labels[].name] | join(\",\")) + \" \" + ([.assignees[].login] | join(\",\"))",
            ],
        ) else {
            skip(&what, "gh issue view failed");
            return;
        };
        let mut fields = issue.splitn(3, ' ');
        let state = fields.next().unwrap_or("");
        let labels_csv = fields.next().unwrap_or("");
        let assignees_csv = fields.next().unwrap_or("");
        if state != "CLOSED" || !format!(",{labels_csv},").contains(",in-progress,") {
            return;
        }
        let mut edit = vec!["issue", "edit", n, "--repo", &slug, "--remove-label", "in-progress"];
        if !assignees_csv.is_empty() {
            edit.push("--remove-assignee");
            edit.push(assignees_csv);
        }
        if !self.step(&what, "gh", &edit) {
            eprintln!("merge-cleanup: could not clear #{n}'s in-progress label and assignee; re-run: gh {}", edit.join(" "));
        }
    }
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

/// The ticket a plain `implement-<n>` branch was cut for: the digits after
/// `implement-`. `implement-spec-<n>` and any other branch name have no
/// ticket to clear.
fn ticket_number(b: &str) -> Option<&str> {
    let n = b.strip_prefix("implement-")?;
    (!n.is_empty() && n.chars().all(|c| c.is_ascii_digit())).then_some(n)
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
            safe_print!("{HELP}");
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
    };

    if a.sweep {
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
        c.report_stale(&[repo]);
    }
    c.close_removed_herdr_workspaces();
    if ok { ExitCode::SUCCESS } else { ExitCode::FAILURE }
}
