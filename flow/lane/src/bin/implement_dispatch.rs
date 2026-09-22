//! Port of `flow/bin/implement-dispatch`. What the dispatcher runs for the
//! `/implement` lane: turn a ticket number into a worker running in its own
//! workspace inside herdr, report, and stop. It never waits on the worker.
//! The contract is `--help` below.

use lane::herdr::HERDR_QUERY_TIMEOUT;
use lane::runner::{self, quiet_ok, quiet_ok_timeout, quiet_stdout, quiet_stdout_timeout, run_timeout, CommandOutput};
use lane::{git_origin, herdr, proc_info, safe_print, safe_println, sessions};
use serde_json::Value;
use std::env;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::process::ExitCode;
use std::time::Duration;

/// Slot budget a `--spec` dispatch briefs when `--slots` is omitted; the same
/// default as `DEFAULT_SLOTS` in burndown/runfile.py.
const DEFAULT_SPEC_SLOTS: u32 = 5;

/// OS-level bound for the two herdr calls that mutate state (`worktree
/// open`, `agent start`) rather than just read it — looser than
/// `HERDR_QUERY_TIMEOUT` because registering a workspace or spawning a
/// claude process on a loaded box can legitimately take longer than a
/// status query, and killing one mid-mutation risks a half-registered
/// agent that the next retry then trips over (`herdr agent <n> already
/// exists`) instead of cleanly retrying.
const HERDR_MUTATION_TIMEOUT: Duration = Duration::from_secs(30);
/// OS-level bound for `herdr agent prompt --wait --timeout 120000`: herdr's
/// own `--timeout` is an internal flag it enforces itself, not an OS-level
/// bound on the subprocess — this is the backstop for herdr's own wait
/// logic hanging past the deadline it was told to keep.
const HERDR_PROMPT_TIMEOUT: Duration = Duration::from_secs(130);
/// Per-call bound inside `poll_worker_session_name`'s loop: short enough
/// that one hung `herdr agent list` call can't eat the whole
/// `SESSION_POLL_DEADLINE` by itself, since the loop's own elapsed check
/// only runs between calls, not during one.
const HERDR_POLL_CALL_TIMEOUT: Duration = Duration::from_secs(2);

const HELP: &str = r#"What the dispatcher runs for the /implement lane: turn a ticket number into a
worker running in its own workspace inside herdr, report, and stop. It never
waits on the worker.

  implement-dispatch [--repo <path>] [--model sonnet|opus] [--controller <name>]
                     <issue number> [<issue number>...]
  implement-dispatch [--repo <path>] [--model sonnet|opus] [--controller <name>]
                     --spec <n> [--slots <k>]

Plain mode: the brief is `/implement <n>... --tier light|heavy --controller
"<name>"`, light when one issue is named and it carries the documentation
label, heavy otherwise — a clump is always heavy, because light tier lands
without a PR and a merged PR's closingIssuesReferences is the only record
merge-cleanup can clear a clump's claims from. A ready-for-human issue among
them ends the brief with --chris-merges: the worker builds the clump and
Chris merges its PR. --model defaults to sonnet.

Several issue numbers are one clump: one worker, one workspace, one branch
and one PR that closes all of them. Branch and workspace are implement-<n>
for the lowest number named, whatever order they are typed in, and the brief
carries the whole list, lowest first. The same number twice is refused.

Spec mode (--spec): the brief is `/implement-spec <n> --slots <k> --controller
"<name>"`, a nested run over a spec issue. Branch and workspace are spec-<n>,
the herdr agent is <repo>-spec-<n>, and --model defaults to opus. --slots is a
positive integer, 5 when omitted, and refused without --spec.

The controller is --controller, else the herdr agent name of the Claude
session running this (the nearest ancestor process whose
~/.claude/sessions/<pid>.json is live, its procStart matching; its sessionId
looked up in herdr agent list), else that session's name when its agent has
none. The worker resolves the brief's name to a live session name with
resolve-controller before every send. Names can hold spaces, hence the quotes.

The claim swaps ready-for-agent for in-progress on every ticket in the clump.
A ready-for-human ticket keeps ready-for-human and adds in-progress beside it,
so the live labels still show Chris-merges after the claim, and a second
dispatch still refuses on the held in-progress label. Release on a failed
claim undoes only what the claim did: in-progress off, the ready label back on
for ready-for-agent, and the assignee removed. A claim that fails partway
through a clump releases the tickets it had already claimed, so nothing is
left half-claimed.

Dispatches of one repository serialize on a lock held from the first ticket
read to the last claim edit (~/.implement-dispatch-claim-<owner>__<name>.lock,
an OS flock: a run that dies drops it, so no stale lock wedges dispatch). A
dispatch that cannot get it in 30s refuses, printing the holder's pid and
tickets. Each ticket is read again just before its edit, and one taken since
the first read refuses the run and releases only what this run claimed. The
lock is under $HOME, so it serializes dispatches sharing a HOME; a hand claim
or a run under another HOME is caught only by that re-read, which narrows the
window and does not close it.

Refuses, with nothing claimed or created, when any named issue is not open and
labelled exactly one of ready-for-agent and ready-for-human, it carries a held
label (in-progress, needs-info), the same number is named twice, spec mode
names an issue without the spec label or with ready-for-human or names more
than one, plain mode names one with the spec label, no controller is named or
found, the herdr server is not running, claude onboarding is incomplete, the
herdr agent name is taken, or the workspace path or branch already exists.
After the workspace exists, any herdr failure exits non-zero with herdr's own
error and leaves the workspace in place for inspection. There is no
bare-claude fallback.
"#;

fn die(msg: impl AsRef<str>) -> ExitCode {
    eprintln!("implement-dispatch: {}", msg.as_ref());
    ExitCode::FAILURE
}

/// What a clump's worker is told beyond `/implement`'s own text (#901). One
/// line, because the brief is one herdr prompt. The per-ticket `Closes #n`
/// wording lives in `implement/SKILL.md` (#889) and is not repeated here.
const CLUMP_NOTE: &str = " -- Clump: a blocker that is another ticket of this clump is ignored, so build them in dependency order and do not park; \
per-ticket shas do not survive the squash merge, so pin nothing to a sha of yours; \
the PR-up report is one report for the clump, not one per ticket.";

struct Args {
    repo: Option<String>,
    model: Option<String>,
    controller: Option<String>,
    /// The clump: every ticket named on the command line, in the order
    /// typed. Spec mode's one ticket arrives here too.
    ns: Vec<String>,
    spec: bool,
    slots: Option<String>,
}

/// Which run the worker is briefed for: a plain `/implement` ticket, or a
/// nested `/implement-spec` run over a spec issue with its slot count.
#[derive(Clone, Copy)]
enum Mode {
    Plain,
    Spec { slots: u32 },
}

impl Mode {
    fn default_model(self) -> &'static str {
        match self {
            Mode::Plain => "sonnet",
            Mode::Spec { .. } => "opus",
        }
    }

    fn branch_prefix(self) -> &'static str {
        match self {
            Mode::Plain => "implement",
            Mode::Spec { .. } => "spec",
        }
    }
}

enum Parsed {
    Help,
    Args(Args),
    Err(String),
}

fn parse_args(argv: Vec<String>) -> Parsed {
    let mut repo = None;
    let mut model = None;
    let mut controller = None;
    let mut ns: Vec<String> = Vec::new();
    let mut spec = false;
    let mut slots = None;
    let mut it = argv.into_iter();
    while let Some(a) = it.next() {
        match a.as_str() {
            "--repo" => match it.next() {
                Some(v) => repo = Some(v),
                None => return Parsed::Err("--repo needs a value".into()),
            },
            "--model" => match it.next() {
                Some(v) => model = Some(v),
                None => return Parsed::Err("--model needs a value".into()),
            },
            "--controller" => match it.next() {
                Some(v) => controller = Some(v),
                None => return Parsed::Err("--controller needs a value".into()),
            },
            "--spec" => match it.next() {
                Some(_) if !ns.is_empty() => return Parsed::Err("one ticket at a time".into()),
                Some(v) => {
                    spec = true;
                    ns.push(v);
                }
                None => return Parsed::Err("--spec needs a value".into()),
            },
            "--slots" => match it.next() {
                Some(v) => slots = Some(v),
                None => return Parsed::Err("--slots needs a value".into()),
            },
            "-h" | "--help" => return Parsed::Help,
            s if s.starts_with('-') => return Parsed::Err(format!("unknown flag: {s}")),
            _ => {
                // A clump is several tickets in plain mode; a spec run is
                // one nested run over one spec issue, and never a clump.
                if spec {
                    return Parsed::Err("one ticket at a time".into());
                }
                ns.push(a);
            }
        }
    }
    Parsed::Args(Args { repo, model, controller, ns, spec, slots })
}

/// Handles the hidden `--seed-trust <claude.json path> <workspace path>`
/// form: the critical section run under `flock`, standing in for the bash
/// subshell `{ ... } 9>"$lock"`. Sets `.projects[$wt].hasTrustDialogAccepted`
/// to true, preserving everything else in the file and its permissions —
/// bash's `mktemp` starts a replacement file at 0600, so the replacement
/// here matches the original file's mode instead of leaving `fs::write`'s
/// default, which would otherwise widen a 0600 `~/.claude.json` to 0644.
/// `LANE_SEED_TRUST_DELAY_MS`, set only by the concurrency test, holds the
/// critical section open long enough to prove two overlapping dispatches
/// actually serialize on the lock rather than through luck.
fn seed_trust(claude_json: &str, wt: &str) -> ExitCode {
    let fail = || {
        safe_println!("jq could not rewrite {claude_json}");
        ExitCode::FAILURE
    };
    let Ok(raw) = std::fs::read_to_string(claude_json) else { return fail() };
    let mode = std::fs::metadata(claude_json).ok().map(|m| m.permissions().mode());
    let Ok(mut value) = serde_json::from_str::<Value>(&raw) else { return fail() };
    if let Ok(ms) = env::var("LANE_SEED_TRUST_DELAY_MS") {
        if let Ok(ms) = ms.parse() {
            std::thread::sleep(std::time::Duration::from_millis(ms));
        }
    }
    let Some(obj) = value.as_object_mut() else { return fail() };
    let projects = obj.entry("projects").or_insert_with(|| Value::Object(Default::default()));
    let Some(projects) = projects.as_object_mut() else { return fail() };
    let entry = projects.entry(wt.to_string()).or_insert_with(|| Value::Object(Default::default()));
    let Some(entry) = entry.as_object_mut() else { return fail() };
    entry.insert("hasTrustDialogAccepted".to_string(), Value::Bool(true));

    let Ok(rendered) = serde_json::to_string_pretty(&value) else { return fail() };
    let tmp = format!(
        "{claude_json}.tmp-{}-{}",
        std::process::id(),
        std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_nanos()).unwrap_or(0)
    );
    if std::fs::write(&tmp, rendered).is_err() {
        let _ = std::fs::remove_file(&tmp);
        return fail();
    }
    if let Some(mode) = mode {
        let _ = std::fs::set_permissions(&tmp, std::fs::Permissions::from_mode(mode));
    }
    if std::fs::rename(&tmp, claude_json).is_err() {
        let _ = std::fs::remove_file(&tmp);
        return fail();
    }
    ExitCode::SUCCESS
}

/// How long a dispatch waits for another dispatch of the same repository to
/// finish claiming before it refuses. `LANE_CLAIM_LOCK_WAIT_MS` shortens it
/// for the test that holds the lock.
fn claim_lock_wait() -> std::time::Duration {
    let ms = env::var("LANE_CLAIM_LOCK_WAIT_MS").ok().and_then(|v| v.parse().ok()).unwrap_or(30_000);
    std::time::Duration::from_millis(ms)
}

/// OS-level bound for the `git fetch` inside the claim lock (#976): unlike
/// the plain git calls around it — rev-parse, worktree list, branch checks,
/// all local and fast — fetch hits the network, and a stalled remote pinned
/// the claim lock for this run's whole life, refusing every other dispatch
/// of the repo past the 30s lock wait. `LANE_FETCH_TIMEOUT_MS` shortens it
/// for tests.
fn fetch_timeout() -> std::time::Duration {
    let ms = env::var("LANE_FETCH_TIMEOUT_MS").ok().and_then(|v| v.parse().ok()).unwrap_or(120_000);
    std::time::Duration::from_millis(ms)
}

/// The per-repository claim lock: held from the first read of a clump's
/// tickets to the last claim edit, so two dispatches naming one ticket
/// serialize and the second reads the first's claim. An OS `flock` on the
/// file, so a run that dies — killed, crashed — drops it and never leaves a
/// lock behind to wedge later dispatches; the file's text is only the note
/// a refused run prints to say who holds it.
struct ClaimLock {
    _file: std::fs::File,
}

impl ClaimLock {
    fn acquire(path: &str, note: &str) -> Result<ClaimLock, String> {
        use std::io::Write;
        let file = std::fs::OpenOptions::new()
            .create(true)
            .truncate(false)
            .read(true)
            .write(true)
            .open(path)
            .map_err(|e| format!("cannot open the claim lock {path}: {e}"))?;
        let deadline = std::time::Instant::now() + claim_lock_wait();
        loop {
            match file.try_lock() {
                Ok(()) => break,
                Err(std::fs::TryLockError::WouldBlock) if std::time::Instant::now() < deadline => {
                    std::thread::sleep(std::time::Duration::from_millis(50));
                }
                Err(std::fs::TryLockError::WouldBlock) => {
                    let holder = std::fs::read_to_string(path).unwrap_or_default();
                    let holder = if holder.trim().is_empty() { "holder's note not written" } else { holder.trim() };
                    return Err(format!("another dispatch holds the claim lock {path} ({holder}); it releases when that run exits"));
                }
                Err(std::fs::TryLockError::Error(e)) => return Err(format!("cannot lock {path}: {e}")),
            }
        }
        let mut f = &file;
        let _ = file.set_len(0);
        let _ = writeln!(f, "{note}");
        Ok(ClaimLock { _file: file })
    }
}

const IDENTITY_GUARD: &str = include_str!("../../hooks/commit-identity-guard.sh");
const GUARD_NAME: &str = "commit-identity-guard";
/// The stable name a displaced foreign `pre-commit` is moved to — the one
/// source for this name; the wrapper text below is built from it rather than
/// hard-coding a second copy, so the two can never drift apart (#1009 S1).
const PRE_COMMIT_FOREIGN: &str = "pre-commit.foreign";

/// The pre-push half of the guard (#1006): the pre-commit guard above only
/// fires on `git commit`, so a rebase or cherry-pick that replays a commit
/// under a different identity — exactly what the lane's mandated
/// rebase-onto-default before every push can do — never goes through
/// `git commit` at all, and slips past it. This re-checks every commit about
/// to be pushed, on the same checkout-configured-email rule and the same
/// `COMMIT_IDENTITY_OVERRIDE` escape.
const PUSH_GUARD: &str = include_str!("../../hooks/commit-identity-guard-pre-push.sh");
const PUSH_GUARD_NAME: &str = "commit-identity-guard-pre-push";
/// The stable name a displaced foreign `pre-push` is moved to, same role as
/// `PRE_COMMIT_FOREIGN` above but for the push hook slot.
const PRE_PUSH_FOREIGN: &str = "pre-push.foreign";

/// What the lane installs as a hook slot (`pre-commit`, `pre-push`). Never a
/// substring or a text match on the *foreign* hook it replaces (#1009: a
/// hook that only echoed the guard's name, called it on an unreachable
/// branch, or suppressed its exit with `|| true` all read as "invokes the
/// guard" under the old substring check). The wrapper runs whatever it
/// displaced first — preserving that hook's own behavior — then always runs
/// the guard itself, outside the displaced hook's own text, so nothing in
/// that text can suppress the guard's exit code. Ownership of the slot is
/// byte-identity with this exact text — never a marker or any other text
/// match on the *current* file either (#934's original ruling, reaffirmed on
/// the Codex gate for PR #1053): a marker-based check reopens the very hole
/// #1009 closes, since a foreign hook that merely carries the marker phrase
/// in a comment would then read as "ours" and skip the takeover — the guard
/// installs nowhere and never runs. A stale prior version of this text (from
/// an earlier build of the lane) is therefore foreign too and gets displaced
/// like any other hook; running it via the wrapper is harmless, since the
/// pre-#1009 pre-commit wrapper's only body was `exec ".../commit-identity-guard"`.
/// Both hook slots share this one wrapper shape (#1006) — the guard name and
/// the foreign-displacement name are its only per-slot parameters, plus
/// `buffer_stdin` for pre-push. A `pre-push` hook's ref list arrives on
/// stdin, not in `"$@"` (git pre-push protocol) — sharing that one stream
/// naively between a displaced foreign hook and the guard means a foreign
/// hook that reads stdin (a real check, not only a spoof) drains it before
/// the guard ever sees a line, and the guard's empty `while read` then exits
/// 0 having refused nothing (#1006 Codex/review finding S1: verified with a
/// stdin-reading foreign hook — the guard saw 0 refs). `buffer_stdin` copies
/// stdin to a temp file first and feeds that file to both, so draining one
/// read cannot starve the other. `pre-commit` never gets this treatment: git
/// does not feed it anything on stdin, and reading stdin there risks hanging
/// an interactive `git commit` on the open terminal — so its wrapper, and
/// its exec of the guard, stay exactly the pre-#1006 two-argument-free shape
/// (byte-identical to the pre-#1006 build, which matters for `is_ours` below
/// on an already-dispatched repo: #1006 Codex/review finding P1).
fn hook_wrapper(guard_name: &str, foreign_name: &str, buffer_stdin: bool) -> String {
    if buffer_stdin {
        format!(
            "#!/bin/sh\n# lane commit-identity guard wrapper (#934, hardened against a foreign hook that only appears to call the guard — #1009). The ref list this hook receives arrives on stdin (#1006): buffered to a temp file first so a foreign hook that reads it cannot starve the guard of it. Never `exec`s the guard here (unlike the pre-commit branch below) — `exec` replaces the shell image, so the `trap ... EXIT` cleaning up the buffer would never fire on the success path and every push would leak one file in $TMPDIR. The buffering copy's own exit status is checked (#1006 Codex gate finding): a copy that fails partway (disk full, an I/O error) after writing one or more complete ref lines would otherwise hand both the foreign hook and the guard a truncated-but-nonempty ref list — the guard's zero-ref refusal never fires on that, and a replayed commit on the ref that got cut off pushes through unchecked. Fail closed instead.\ndir=\"$(dirname \"$0\")\"\nstdin_buf=\"$(mktemp)\" || exit 1\ntrap 'rm -f \"$stdin_buf\"' EXIT\ncat >\"$stdin_buf\" || {{ echo \"commit-identity-guard: could not buffer the pre-push ref list; refusing the push\" >&2; exit 1; }}\nif [ -e \"$dir/{foreign_name}\" ]; then\n  \"$dir/{foreign_name}\" \"$@\" <\"$stdin_buf\" || exit $?\nfi\n\"$dir/{guard_name}\" \"$@\" <\"$stdin_buf\"\n"
        )
    } else {
        format!(
            "#!/bin/sh\n# lane commit-identity guard wrapper (#934, hardened against a foreign hook that only appears to call the guard — #1009)\ndir=\"$(dirname \"$0\")\"\nif [ -e \"$dir/{foreign_name}\" ]; then\n  \"$dir/{foreign_name}\" \"$@\" || exit $?\nfi\nexec \"$dir/{guard_name}\"\n"
        )
    }
}

/// Writes `text` to `path` as an executable, via temp file + rename so a
/// commit racing the write never runs a truncated script, and never a window
/// where `path` is briefly absent (#1009 C4): `rename` replaces it in one
/// step, whatever was there before. Verifies the bit stuck rather than
/// assuming `set_permissions` and the filesystem agree.
fn write_executable(path: &Path, text: &str) -> Result<(), String> {
    let tmp = path.with_file_name(format!("{}.lane-{}", path.file_name().and_then(|n| n.to_str()).unwrap_or("hook"), std::process::id()));
    std::fs::write(&tmp, text).map_err(|e| format!("cannot write {}: {e}", tmp.display()))?;
    std::fs::set_permissions(&tmp, std::fs::Permissions::from_mode(0o755)).map_err(|e| format!("cannot chmod {}: {e}", tmp.display()))?;
    std::fs::rename(&tmp, path).map_err(|e| format!("cannot install {}: {e}", path.display()))?;
    let mode = std::fs::metadata(path).map_err(|e| format!("cannot stat {}: {e}", path.display()))?.permissions().mode();
    if mode & 0o111 == 0 {
        return Err(format!("installed {} but it is not executable (mode {mode:o})", path.display()));
    }
    Ok(())
}

/// Installs one half of the commit-identity guard (#934 pre-commit, #1006
/// pre-push) into the hooks dir `dir`, which the caller has already created.
/// The guard script always goes to `<dir>/<guard_name>` (refreshed in place,
/// and verified executable). `<dir>/<slot>` becomes the lane's own wrapper
/// unconditionally: whatever is there when it is not already byte-identical
/// to `hook_wrapper(guard_name, foreign_name, buffer_stdin)` is foreign — trusted by its
/// presence, never by parsing or matching its source — and is copied aside
/// to `<dir>/<foreign_name>` (the original left in place until
/// `write_executable`'s atomic rename replaces it, so there is never a
/// moment with no hook at that slot at all), forced executable (git silently
/// ignores a hook without the bit, and the pre-#1009 accepted-hook path
/// never checked it), and left for the wrapper to run before it always runs
/// the guard itself. A `<foreign_name>` slot already holding a *different*
/// foreign hook refuses rather than silently overwriting whatever it held
/// (#1009 C3) — that can only mean something installed a new hook over the
/// lane's wrapper since the last dispatch, and only a human can say which
/// one should survive. Worktrees share the primary's hooks dir, so one
/// install covers them all, and the call site holds the claim lock so two
/// dispatches of the same repo can't race each other's takeover (#1009 C2).
/// Ownership is taken once: a slot that is already byte-identical to the
/// current wrapper is left alone, so a repeat dispatch does not re-displace
/// an already-displaced hook.
fn install_hook_slot(dir: &str, slot: &str, foreign_name: &str, guard_name: &str, guard_content: &str, buffer_stdin: bool) -> Result<(), String> {
    let path = Path::new(dir).join(slot);
    let foreign_path = Path::new(dir).join(foreign_name);
    let wrapper = hook_wrapper(guard_name, foreign_name, buffer_stdin);
    let current = std::fs::read(&path);
    let exists = match &current {
        Ok(_) => true,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => false,
        Err(e) => return Err(format!("cannot read {}: {e}", path.display())),
    };
    let is_ours = current.as_ref().is_ok_and(|b| b.as_slice() == wrapper.as_bytes());
    if exists && !is_ours {
        let foreign_bytes = current.as_ref().expect("exists implies Ok");
        match std::fs::read(&foreign_path) {
            Ok(already_there) if &already_there != foreign_bytes => {
                return Err(format!(
                    "{} already holds a different foreign hook than the one now at {}; something installed a new {slot} here since the last dispatch — resolve by hand (merge or remove {}) before dispatching again",
                    foreign_path.display(),
                    path.display(),
                    foreign_path.display()
                ));
            }
            Ok(_) => {}
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {}
            Err(e) => return Err(format!("cannot read {}: {e}", foreign_path.display())),
        }
        std::fs::write(&foreign_path, foreign_bytes).map_err(|e| format!("cannot copy {} aside to {}: {e}", path.display(), foreign_path.display()))?;
        let mut perms =
            std::fs::metadata(&foreign_path).map_err(|e| format!("cannot stat {}: {e}", foreign_path.display()))?.permissions();
        perms.set_mode(0o755);
        std::fs::set_permissions(&foreign_path, perms).map_err(|e| format!("cannot chmod {}: {e}", foreign_path.display()))?;
        safe_println!(
            "implement-dispatch: took ownership of {} — the foreign hook that was there is preserved, executable, at {}",
            path.display(),
            foreign_path.display()
        );
    }
    write_executable(&Path::new(dir).join(guard_name), guard_content)?;
    if !is_ours {
        write_executable(&path, &wrapper)?;
    }
    Ok(())
}

/// Installs both halves of the commit-identity guard: pre-commit (#934) and
/// pre-push (#1006). The pre-commit guard alone never fires on a rebase or
/// cherry-pick that replays a commit under a different identity, and the
/// lane rebases onto the default branch before every push — so the pre-push
/// half is what actually stops a replayed foreign-email commit from ever
/// reaching `git push`, where #909's failure mode began.
fn install_identity_guard(primary: &str) -> Result<(), String> {
    let dir = quiet_stdout("git", &["-C", primary, "rev-parse", "--path-format=absolute", "--git-path", "hooks"])
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
        .ok_or_else(|| format!("cannot resolve the hooks dir of {primary}"))?;
    std::fs::create_dir_all(&dir).map_err(|e| format!("cannot create {dir}: {e}"))?;
    // (slot, foreign_name, guard_name, guard_content, buffer_stdin) — one row
    // per hook slot the lane owns. `buffer_stdin` is true only for pre-push,
    // whose ref list arrives on stdin; see `hook_wrapper`.
    let slots: [(&str, &str, &str, &str, bool); 2] = [
        ("pre-commit", PRE_COMMIT_FOREIGN, GUARD_NAME, IDENTITY_GUARD, false),
        ("pre-push", PRE_PUSH_FOREIGN, PUSH_GUARD_NAME, PUSH_GUARD, true),
    ];
    for (slot, foreign_name, guard_name, guard_content, buffer_stdin) in slots {
        install_hook_slot(&dir, slot, foreign_name, guard_name, guard_content, buffer_stdin)?;
    }
    Ok(())
}

fn primary_worktree(repo: &str) -> Option<String> {
    let out = quiet_stdout("git", &["-C", repo, "worktree", "list", "--porcelain"])?;
    let first = out.lines().next()?;
    first.strip_prefix("worktree ").map(str::to_string)
}

fn valid_slug(s: &str) -> bool {
    let mut parts = s.splitn(2, '/');
    let (Some(a), Some(b)) = (parts.next(), parts.next()) else { return false };
    !a.is_empty() && !b.is_empty() && !a.contains(':') && !b.contains(':') && !b.contains('/')
}

/// One ticket of the clump, as the refusal pass read it: which ready label
/// its claim swaps (a `ready-for-human` one keeps its own), and whether its
/// label makes this a docs-only build.
struct Ticket {
    n: String,
    ready: &'static str,
    chris_merges: bool,
    documentation: bool,
}

/// The `gh issue edit` that undoes one ticket's claim: in-progress off, the
/// ready label back on for a `ready-for-agent` ticket — a `ready-for-human`
/// one never lost it — and the assignee the claim added removed. Both the
/// automatic rollback of a half-made claim and the release line a failure
/// past the claim prints are this, so the two can never drift.
fn release_args<'a>(t: &'a Ticket, slug: &'a str) -> Vec<&'a str> {
    let mut args = vec!["issue", "edit", &t.n, "--repo", slug, "--remove-label", "in-progress"];
    if !t.chris_merges {
        args.extend(["--add-label", t.ready]);
    }
    args.extend(["--remove-assignee", "@me"]);
    args
}

/// Undoes the claims this run made, one `gh issue edit` per ticket, saying
/// how to re-run any release that fails. Only tickets in `claimed` — never
/// one this run did not set.
fn release_claimed(claimed: &[&Ticket], slug: &str) {
    for done in claimed {
        let release = release_args(done, slug);
        if !matches!(runner::run("gh", &release), Ok(o) if o.success) {
            eprintln!("implement-dispatch: could not release #{}; re-run: gh {}", done.n, release.join(" "));
        }
    }
}

/// The claimed clump: what a failure past the claim needs to say how to
/// release it, and where the workspace would be if it exists.
struct Claim<'a> {
    tickets: &'a [Ticket],
    slug: &'a str,
    wt: &'a Path,
}

impl Claim<'_> {
    fn fail(&self, what: &str, out: &str) -> ExitCode {
        eprintln!("implement-dispatch: {what} failed: {out}");
        if self.wt.exists() {
            eprintln!("workspace left in place at {}", self.wt.display());
        }
        // One line per ticket: the whole clump was claimed, so the whole
        // clump has to be released.
        for t in self.tickets {
            eprintln!("release the ticket: gh {}", release_args(t, self.slug).join(" "));
        }
        ExitCode::FAILURE
    }

    /// Runs one post-claim step: on success, the combined output; on
    /// failure, prints via `fail` and returns it as the process exit code.
    /// A `flock` timeout exits non-zero with nothing on either stream —
    /// bash's own subshell said so explicitly, so an empty failure here
    /// gets the same wording instead of a silent trailing colon.
    fn step(&self, what: &str, res: std::io::Result<CommandOutput>, empty_timeout: Option<&str>) -> Result<String, ExitCode> {
        match res {
            Ok(o) if o.success => Ok(o.combined),
            Ok(o) if o.combined.is_empty() => {
                Err(self.fail(what, empty_timeout.unwrap_or("(no output)")))
            }
            Ok(o) => Err(self.fail(what, &o.combined)),
            Err(e) => Err(self.fail(what, &e.to_string())),
        }
    }
}

fn json_str<'a>(v: &'a Value, path: &[&str]) -> Option<&'a str> {
    let mut cur = v;
    for p in path {
        cur = cur.get(p)?;
    }
    cur.as_str()
}

/// The worker's own Claude session name. herdr's own record of which
/// sessionId is attached to the agent this run just started
/// (`agent_session.value`) is the one authoritative link — matching on cwd
/// or pid alone, as an earlier version of this did, can be fooled by
/// another live session sharing the worktree, or by a stale registry file
/// left behind on a reused pid; sessionId can't collide that way. A short
/// retry covers herdr's own read-after-write lag before it reports the
/// session. "(unavailable)" on a miss — the report stays total, no dispatch
/// failure over it.
fn worker_session_name(home: &str, wt: &str, agent: &str) -> String {
    poll_worker_session_name(home, wt, agent, SESSION_POLL_DEADLINE, SESSION_POLL_INTERVAL, || {
        quiet_stdout_timeout("herdr", &["agent", "list"], HERDR_POLL_CALL_TIMEOUT)
    })
}

/// Bound on how long `worker_session_name` polls for herdr's and the
/// session registry's records to appear — well inside the prompt wait's own
/// 120s timeout, so a slow session name never becomes a slow dispatch.
const SESSION_POLL_DEADLINE: std::time::Duration = std::time::Duration::from_secs(5);
/// Gap between polls. Wide enough that a genuine miss (the agent never gets
/// a session, not just late) doesn't spend the whole deadline hammering
/// `herdr agent list` — on a loaded box that spam is the exact problem this
/// poll exists to not make worse.
const SESSION_POLL_INTERVAL: std::time::Duration = std::time::Duration::from_millis(200);

/// The polling core of `worker_session_name`, with the herdr read injected
/// so a test can make it appear late without a real subprocess or a real
/// multi-second wait.
fn poll_worker_session_name(
    home: &str,
    wt: &str,
    agent: &str,
    deadline: std::time::Duration,
    interval: std::time::Duration,
    herdr_list: impl Fn() -> Option<String>,
) -> String {
    let start = std::time::Instant::now();
    loop {
        let name = herdr_list()
            .and_then(|out| herdr::parse_agents(&out))
            .and_then(|agents| agents.iter().find(|a| a.name() == agent).map(|a| a.session().to_string()).filter(|s| !s.is_empty()))
            .and_then(|session_id| sessions::live_in(Path::new(home), wt).into_iter().find(|s| s.session_id == session_id).map(|s| s.name).filter(|n| !n.is_empty()));
        if let Some(name) = name {
            return name;
        }
        if start.elapsed() >= deadline {
            return "(unavailable)".to_string();
        }
        std::thread::sleep(interval);
    }
}

/// The pid of the controller's own session record, to write its
/// `<pid>.workers.jsonl` sidecar (#964). Three ways, cheapest first: the
/// sessionId captured while deriving the controller from this process's own
/// ancestry (set only when `--controller` was not passed); a live session
/// already named `controller` (an explicit `--controller <session name>`, or
/// a derived controller with no herdr agent); or, last, the same herdr-agent
/// hop `resolve-controller` makes — `herdr agent list` for `controller`'s
/// `agent_session.value`, then that session's own live record. `None` when
/// none of the three finds a live session: the worker is still dispatched,
/// the record is just not written, and a `/clear` on that controller session
/// restores nothing for it.
fn resolve_controller_pid(home: &Path, controller_session: &str, controller: &str) -> Option<String> {
    if let Some(s) = sessions::find_live_by_session_id(home, controller_session) {
        return Some(s.pid);
    }
    if let Some(s) = sessions::find_live_by_name(home, controller) {
        return Some(s.pid);
    }
    let listing = quiet_stdout_timeout("herdr", &["agent", "list"], HERDR_QUERY_TIMEOUT)?;
    let agents = herdr::parse_agents(&listing)?;
    let agent = agents.iter().find(|a| a.given_name() == Some(controller))?;
    sessions::find_live_by_session_id(home, agent.session()).map(|s| s.pid)
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(code) => code,
    }
}

fn run() -> Result<(), ExitCode> {
    let mut raw_args: Vec<String> = env::args().skip(1).collect();
    // Hidden critical-section entry point run under `flock`; never reached
    // through normal flag parsing.
    if raw_args.first().map(String::as_str) == Some("--seed-trust") {
        if raw_args.len() != 3 {
            eprintln!("implement-dispatch: --seed-trust needs a claude.json path and a workspace path");
            return Err(ExitCode::FAILURE);
        }
        let code = seed_trust(&raw_args[1], &raw_args[2]);
        return if code == ExitCode::SUCCESS { Ok(()) } else { Err(code) };
    }

    let args = match parse_args(std::mem::take(&mut raw_args)) {
        Parsed::Help => {
            safe_print!("{HELP}");
            return Ok(());
        }
        Parsed::Err(e) => return Err(die(e)),
        Parsed::Args(a) => a,
    };

    if args.ns.is_empty() {
        return Err(die("name one issue number"));
    }
    // Parsed, not just digit-checked, and then rendered back: an issue
    // number is the number, so `007` and `7` are one ticket. Compared as
    // text they are two, and the clump would claim and brief the same issue
    // twice — the outcome the repeat check below exists to prevent — while
    // `007` also named the branch, the workspace and the agent.
    let mut numbers: Vec<u64> = Vec::new();
    for n in &args.ns {
        match n.parse::<u64>() {
            Ok(v) if n.chars().all(|c| c.is_ascii_digit()) => numbers.push(v),
            _ => return Err(die("name one issue number")),
        }
    }
    // Ascending, so the lowest names the branch, the workspace and the
    // agent however the clump was typed.
    numbers.sort_unstable();
    if let Some(dup) = numbers.windows(2).find(|w| w[0] == w[1]) {
        return Err(die(format!("#{} is named twice", dup[0])));
    }
    let ns: Vec<String> = numbers.iter().map(u64::to_string).collect();
    let n = ns[0].clone();
    let mode = match (&args.slots, args.spec) {
        (None, false) => Mode::Plain,
        (None, true) => Mode::Spec { slots: DEFAULT_SPEC_SLOTS },
        (Some(_), false) => return Err(die("--slots only goes with --spec")),
        (Some(k), true) => match k.parse::<u32>() {
            Ok(slots) if slots > 0 => Mode::Spec { slots },
            _ => return Err(die(format!("--slots must be a positive integer, not '{k}'"))),
        },
    };
    let model = args.model.clone().unwrap_or_else(|| mode.default_model().to_string());
    if model != "sonnet" && model != "opus" {
        return Err(die(format!("--model must be sonnet or opus, not '{model}'")));
    }
    if !runner::on_path("flock") {
        return Err(die("flock is not on PATH"));
    }

    let repo = args.repo.clone().unwrap_or_else(|| env::current_dir().map(|p| p.display().to_string()).unwrap_or_default());
    let Some(primary) = primary_worktree(&repo) else {
        return Err(die(format!("not a git repo: {repo}")));
    };
    let slug = git_origin::origin_slug(Path::new(&primary)).unwrap_or_default();
    if !valid_slug(&slug) {
        return Err(die(format!("origin in {primary} names no GitHub owner/name")));
    }
    let branch = format!("{}-{n}", mode.branch_prefix());
    let wt = PathBuf::from(&primary).join(".claude/worktrees").join(&branch);
    let suffix = match mode {
        Mode::Plain => format!("-{n}"),
        Mode::Spec { .. } => format!("-spec-{n}"),
    };
    let repo_name = Path::new(&primary).file_name().and_then(|f| f.to_str()).unwrap_or("");
    let cut = (32usize).saturating_sub(suffix.len());
    let repo_part: String = repo_name.chars().take(cut).collect();
    let agent = format!("{repo_part}{suffix}");

    // One dispatch at a time per repository from the first read to the last
    // claim edit: without it, two runs naming one ticket both read it free
    // and both claim it, and a rollback would then remove the other run's
    // label and assignee.
    let claim_lock_path = format!("{}/.implement-dispatch-claim-{}.lock", env::var("HOME").unwrap_or_default(), slug.replace('/', "__"));
    let claim_lock = ClaimLock::acquire(
        &claim_lock_path,
        &format!("pid {} claiming {}", std::process::id(), ns.iter().map(|n| format!("#{n}")).collect::<Vec<_>>().join(" ")),
    )
    .map_err(die)?;

    // Inside the claim lock (#1009 C2): two dispatches of the same repo can
    // both find a foreign pre-commit and both try to take ownership of it —
    // serialized here, the second sees the first's wrapper already in place
    // and does nothing, instead of renaming the first dispatch's own install
    // over the user's real hook.
    if let Err(e) = install_identity_guard(&primary) {
        return Err(die(e));
    }

    // Refusals first, so a refused run leaves nothing claimed or created —
    // and every ticket of the clump is read before any of them is claimed,
    // which is what makes the claim all-or-nothing.
    let mut tickets: Vec<Ticket> = Vec::new();
    for n in &ns {
        let Some(issue) = lane::issue_state::read(&slug, n) else {
            return Err(die(format!("#{n} is not an open issue")));
        };
        if issue.state != "OPEN" {
            return Err(die(format!("#{n} is not an open issue")));
        }
        // The ready label the claim swaps for in-progress. A ready-for-human
        // ticket is built the same way, but its brief says Chris merges it.
        let (ready, chris_merges) = match (issue.has_label("ready-for-agent"), issue.has_label("ready-for-human")) {
            (true, false) => ("ready-for-agent", false),
            (false, true) => ("ready-for-human", true),
            (true, true) => return Err(die(format!("#{n} is labelled both ready-for-agent and ready-for-human"))),
            (false, false) => return Err(die(format!("#{n} is not labelled ready-for-agent or ready-for-human"))),
        };
        for held in ["in-progress", "needs-info"] {
            if issue.has_label(held) {
                return Err(die(format!("#{n} is labelled {held}")));
            }
        }
        match (mode, issue.has_label("spec")) {
            (Mode::Spec { .. }, false) => return Err(die(format!("#{n} is not labelled spec"))),
            (Mode::Plain, true) => return Err(die(format!("#{n} is labelled spec; dispatch it with --spec {n} --slots <k>"))),
            (Mode::Spec { .. }, true) if chris_merges => {
                return Err(die(format!("#{n} is labelled ready-for-human; a spec run has no Chris-merges brief")));
            }
            _ => {}
        }
        tickets.push(Ticket { n: n.clone(), ready, chris_merges, documentation: issue.has_label("documentation") });
    }
    // The clump lands as one diff. Light is the docs-only tier, so one
    // ticket that is not docs-only makes the whole diff code — the same
    // reading as a worker raising light to heavy the moment its diff turns
    // out to hold code.
    let chris_merges = tickets.iter().any(|t| t.chris_merges);
    // A clump is always heavy, whatever its labels say. Light tier pushes
    // straight to the default branch with no PR, and the merged PR's
    // closingIssuesReferences is the only authoritative record of which
    // tickets a landing closed — so a light clump lands with nothing for
    // merge-cleanup to read, and every ticket but the branch's own keeps its
    // claim. That is the state #889 exists to end, so the tier that cannot
    // carry a clump does not get one. The cost is real and small: a
    // docs-only clump gets a PR it would not have had alone. One ticket is
    // unchanged — its documentation label still decides its tier.
    let tier = if tickets.len() == 1 && tickets[0].documentation { "light" } else { "heavy" };

    let home = env::var("HOME").unwrap_or_default();
    // An empty --controller is bash's `[ -z "$controller" ]`: absent, not a
    // literal empty name, so it still falls through to the session lookup.
    let controller_flag = args.controller.as_deref().filter(|c| !c.is_empty());
    let mut controller_session = String::new();
    let controller = match controller_flag {
        Some(c) => c.to_string(),
        None => {
            let self_pid = std::process::id() as i32;
            let start_ancestor = proc_info::parent_pid(self_pid).unwrap_or(0);
            match sessions::find_controller_session(Path::new(&home), start_ancestor) {
                Some((id, c)) => {
                    controller_session = id;
                    c
                }
                None => {
                    return Err(die(
                        "no controller: no live ancestor session has a ~/.claude/sessions/<pid>.json name; pass --controller",
                    ));
                }
            }
        }
    };
    if controller.contains('"') || controller.contains('\n') {
        return Err(die(format!("controller name cannot hold a double quote or newline: {controller}")));
    }

    let status_out = quiet_stdout_timeout("herdr", &["status", "--json"], HERDR_QUERY_TIMEOUT).unwrap_or_default();
    let running = serde_json::from_str::<Value>(&status_out)
        .ok()
        .and_then(|v| v.get("server").and_then(|s| s.get("running")).and_then(Value::as_bool))
        .unwrap_or(false);
    if !running {
        return Err(die("no herdr server is running (herdr status)"));
    }

    // A derived controller is briefed by its herdr agent name when it has one:
    // a restart renames the session, not the agent, and the worker resolves the
    // name to a session at send time (`resolve-controller`, #923). A controller
    // that is no named herdr agent keeps its session name, which the same
    // resolver still accepts while a live session bears it.
    // A derived controller record with no sessionId cannot be looked up, and a
    // missing field is registry skew, not proof the controller has no herdr
    // agent: refuse rather than brief the restart-volatile session name.
    if controller_flag.is_none() && controller_session.is_empty() {
        return Err(die(format!(
            "the controller's ~/.claude/sessions record ({controller}) has no sessionId, so its herdr agent name cannot be found; pass --controller <herdr agent name>"
        )));
    }
    let controller = if controller_flag.is_none() {
        // A listing that failed is not "no agents": briefing the session name
        // then would write the address a restart ages, silently.
        let Some(listing) = quiet_stdout_timeout("herdr", &["agent", "list"], HERDR_QUERY_TIMEOUT) else {
            return Err(die("herdr agent list failed or timed out, so the controller's herdr agent name is unknown; pass --controller"));
        };
        let Some(agents) = herdr::parse_agents(&listing) else {
            return Err(die("herdr agent list gave output of an unexpected shape; pass --controller"));
        };
        match agents.iter().find(|a| a.session() == controller_session).and_then(|a| a.given_name()) {
            Some(n) if n.contains('"') || n.contains('\n') => {
                return Err(die(format!("controller herdr agent name cannot hold a double quote or newline: {n}")));
            }
            Some(n) => n.to_string(),
            None => controller,
        }
    } else {
        controller
    };

    let claude_json_path = format!("{home}/.claude.json");
    let onboarded = std::fs::read_to_string(&claude_json_path)
        .ok()
        .and_then(|s| serde_json::from_str::<Value>(&s).ok())
        .and_then(|v| v.get("hasCompletedOnboarding").and_then(Value::as_bool))
        .unwrap_or(false);
    if !onboarded {
        return Err(die(format!("claude onboarding is not complete in {claude_json_path}; a brief would land in its dialog")));
    }

    if quiet_ok_timeout("herdr", &["agent", "get", &agent], HERDR_QUERY_TIMEOUT) {
        return Err(die(format!("herdr agent {agent} already exists")));
    }
    let fetch_timeout = fetch_timeout();
    if !quiet_ok_timeout("git", &["-C", &primary, "fetch", "-q", "origin"], fetch_timeout) {
        return Err(die(format!("git fetch failed or exceeded its {fetch_timeout:?} bound in {primary}")));
    }
    let registered_worktree = quiet_stdout("git", &["-C", &primary, "worktree", "list", "--porcelain"])
        .map(|out| out.lines().any(|l| l == format!("worktree {}", wt.display())))
        .unwrap_or(false);
    if wt.exists() || registered_worktree {
        return Err(die(format!("{} already exists", wt.display())));
    }
    if quiet_ok("git", &["-C", &primary, "show-ref", "-q", "--verify", &format!("refs/heads/{branch}")]) {
        return Err(die(format!("branch {branch} already exists")));
    }
    let default = git_origin::default_branch(Path::new(&primary));
    if !quiet_ok("git", &["-C", &primary, "show-ref", "-q", "--verify", &format!("refs/remotes/origin/{default}")]) {
        return Err(die(format!("no origin/{default} to branch from")));
    }

    // Past here the clump is claimed; a failure says how to release it. A
    // ready-for-human ticket keeps its ready label through the build, so the
    // live labels stay a Chris-merges signal that outlives this session; a
    // ready-for-agent ticket still swaps its ready label for in-progress.
    // A claim is one gh call per ticket, so a call that fails after its
    // siblings succeeded rolls them back: the clump is claimed whole or not
    // at all, and a half-claimed clump is the state nobody can dispatch
    // from and nobody thinks to clear.
    let mut claimed: Vec<&Ticket> = Vec::new();
    for t in &tickets {
        // Read again right before the edit: the lock keeps other dispatches
        // out, not a hand claim or a run that predates the lock, and a
        // ticket taken since the refusal pass must not be claimed over —
        // or released by our rollback, which removes labels and an
        // assignee this run would then never have set.
        let refusal = match lane::issue_state::read(&slug, &t.n) {
            Some(i) if i.state != "OPEN" || i.has_label("in-progress") => {
                Some(format!("#{} is labelled in-progress or no longer open; another dispatch took it", t.n))
            }
            Some(_) => None,
            None => Some(format!("could not re-read #{} before claiming it (gh failed)", t.n)),
        };
        if let Some(refusal) = refusal {
            release_claimed(&claimed, &slug);
            return Err(die(refusal));
        }
        let mut claim_args: Vec<&str> = vec!["issue", "edit", &t.n, "--repo", &slug];
        if !t.chris_merges {
            claim_args.extend(["--remove-label", t.ready]);
        }
        claim_args.extend(["--add-label", "in-progress", "--add-assignee", "@me"]);
        match runner::run("gh", &claim_args) {
            Ok(c) if c.success => claimed.push(t),
            _ => {
                release_claimed(&claimed, &slug);
                return Err(die(format!("could not claim #{}", t.n)));
            }
        }
    }
    drop(claim_lock);
    let claim = Claim { tickets: &tickets, slug: &slug, wt: &wt };

    let wa = runner::run_in(
        None,
        "git",
        &["-C", &primary, "worktree", "add", "-q", "--no-track", "-b", &branch, wt.to_str().unwrap_or(""), &format!("origin/{default}")],
    );
    claim.step("git worktree add", wa, None)?;

    let lock = format!("{home}/.claude.json.implement-dispatch.lock");
    let self_exe = env::current_exe().map(|p| p.display().to_string()).unwrap_or_else(|_| "implement-dispatch".to_string());
    let seed = runner::run("flock", &["-w", "30", &lock, &self_exe, "--seed-trust", &claude_json_path, wt.to_str().unwrap_or("")]);
    claim.step("trust pre-seed", seed, Some(&format!("timed out waiting for {lock}")))?;

    // --cwd names the repo: without it herdr resolves the focused workspace's
    // repo and answers worktree_not_found.
    let open = run_timeout(
        "herdr",
        &["worktree", "open", "--cwd", &primary, "--path", wt.to_str().unwrap_or(""), "--label", &branch, "--no-focus", "--trust-repository"],
        HERDR_MUTATION_TIMEOUT,
    );
    let open_out = claim.step("herdr worktree open", open, None)?;
    let open_json: Option<Value> = serde_json::from_str(&open_out).ok();
    let mut pane = open_json.as_ref().and_then(|v| json_str(v, &["result", "root_pane", "pane_id"])).unwrap_or("").to_string();
    if pane.is_empty() {
        let ws = open_json.as_ref().and_then(|v| json_str(v, &["result", "workspace", "workspace_id"])).unwrap_or("").to_string();
        if ws.is_empty() {
            return Err(claim.fail("herdr worktree open", &format!("no workspace in its response: {open_out}")));
        }
        let panes = claim.step("herdr pane list", run_timeout("herdr", &["pane", "list", "--workspace", &ws], HERDR_QUERY_TIMEOUT), None)?;
        let panes_json: Option<Value> = serde_json::from_str(&panes).ok();
        pane = panes_json
            .as_ref()
            .and_then(|v| v.get("result"))
            .and_then(|v| v.get("panes"))
            .and_then(|v| v.get(0))
            .and_then(|v| v.get("pane_id"))
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string();
        if pane.is_empty() {
            return Err(claim.fail("herdr pane list", &format!("no pane in workspace {ws}: {panes}")));
        }
    }

    claim.step(
        "herdr agent start",
        run_timeout("herdr", &["agent", "start", &agent, "--kind", "claude", "--pane", &pane, "--", "--model", &model], HERDR_MUTATION_TIMEOUT),
        None,
    )?;

    let (brief, described) = match mode {
        Mode::Plain => {
            let (marker, merger) = if chris_merges { (" --chris-merges", ", Chris merges") } else { ("", "") };
            // The whole clump, lowest first: the worker builds every ticket
            // in it and its one PR closes them all.
            // Only a clump carries the note: a lone ticket has no internal
            // blockers, no sibling shas and one report already (#901).
            let note = if ns.len() > 1 { CLUMP_NOTE } else { "" };
            (format!("/implement {} --tier {tier} --controller \"{controller}\"{marker}{note}", ns.join(" ")), format!("{tier} tier{merger}"))
        }
        Mode::Spec { slots } => (format!("/implement-spec {n} --slots {slots} --controller \"{controller}\""), format!("spec, {slots} slots")),
    };
    claim.step(
        "herdr agent prompt",
        run_timeout("herdr", &["agent", "prompt", &agent, &brief, "--wait", "--until", "working", "--timeout", "120000"], HERDR_PROMPT_TIMEOUT),
        None,
    )?;

    let session = worker_session_name(&home, wt.to_str().unwrap_or(""), &agent);

    // #964: the controller's own session survives a `/clear` (the process
    // does, only the context is wiped), so this record is what a
    // SessionStart hook reads back to restore what it controls. Best-effort:
    // a controller this run cannot resolve to a live session still gets its
    // worker dispatched, just with nothing to restore for it.
    let cleanup = format!("cd {primary} && merge-cleanup {branch} --repo {primary}");
    match resolve_controller_pid(Path::new(&home), &controller_session, &controller) {
        Some(pid) => {
            // #964 fix round 1 (Codex high): the controller session's own
            // starttime, read fresh here rather than trusted from whichever
            // registry lookup found `pid` — this is what lets
            // `controller-restore` tell "this session" from "a session that
            // now happens to reuse this pid" once the original controller is
            // gone. Empty on a read failure (the pid died in the gap since
            // resolution); an empty proc_start never matches a live one, so
            // the record is simply dropped as stale on restore rather than
            // failing this dispatch over it.
            let proc_start = pid.parse::<i32>().ok().and_then(proc_info::read_stat).map(|s| s.start).unwrap_or_default();
            let record = lane::workers::WorkerRecord {
                agent: agent.clone(),
                tickets: ns.clone(),
                branch: branch.clone(),
                workspace: wt.display().to_string(),
                repo: slug.clone(),
                cleanup: cleanup.clone(),
                chris_merges,
                dispatched_at: lane::workers::now_iso8601(),
                proc_start,
            };
            if let Err(e) = lane::workers::append(Path::new(&home), &pid, &record) {
                eprintln!("implement-dispatch: could not record this worker for the controller ({e}); a /clear there will not restore it");
            }
        }
        None => eprintln!("implement-dispatch: could not resolve the controller to a live session; a /clear there will not restore this worker"),
    }

    let dispatched: Vec<String> = ns.iter().map(|n| format!("#{n}")).collect();
    safe_println!("dispatched {} ({model}, {described}, controller {controller})", dispatched.join(" "));
    safe_println!("worktree: {}", wt.display());
    safe_println!("branch:   {branch}");
    safe_println!("agent:    {agent}");
    safe_println!("session:  {session}");
    safe_println!("cleanup:  {cleanup}");
    Ok(())
}

#[cfg(test)]
mod tests {

    use super::*;
    use std::time::{Duration, Instant};
    use tempfile::TempDir;

    #[test]
    fn polls_past_herdrs_read_after_write_lag_past_100ms() {
        let tmp = TempDir::new().unwrap();
        let home = tmp.path();
        let wt = tmp.path().join("wt");
        std::fs::create_dir_all(&wt).unwrap();
        std::fs::create_dir_all(home.join(".claude/sessions")).unwrap();
        let pid = std::process::id();
        let proc_start = lane::proc_info::read_stat(pid as i32).unwrap().start;
        std::fs::write(
            home.join(".claude/sessions").join(format!("{pid}.json")),
            format!(
                r#"{{"pid":{pid},"cwd":"{}","sessionId":"sess-1","name":"skills-worker","procStart":"{proc_start}"}}"#,
                wt.display()
            ),
        )
        .unwrap();

        let start = Instant::now();
        let herdr_json = r#"{"result":{"agents":[{"agent":"implement-836","agent_session":{"value":"sess-1"}}]}}"#;
        let herdr_list = move || {
            if start.elapsed() < Duration::from_millis(120) {
                None
            } else {
                Some(herdr_json.to_string())
            }
        };

        let name = poll_worker_session_name(
            home.to_str().unwrap(),
            wt.to_str().unwrap(),
            "implement-836",
            Duration::from_secs(2),
            Duration::from_millis(20),
            herdr_list,
        );
        assert_eq!(name, "skills-worker");
    }

    #[test]
    fn polls_past_the_session_registrys_own_write_lag_past_100ms() {
        let tmp = TempDir::new().unwrap();
        let home = tmp.path();
        let wt = tmp.path().join("wt");
        std::fs::create_dir_all(&wt).unwrap();
        std::fs::create_dir_all(home.join(".claude/sessions")).unwrap();
        let pid = std::process::id();
        let proc_start = lane::proc_info::read_stat(pid as i32).unwrap().start;
        // herdr answers immediately with the agent's sessionId; the
        // SessionStart hook that writes the registry file is the one that's
        // late here, not herdr.
        let herdr_json = r#"{"result":{"agents":[{"agent":"implement-836","agent_session":{"value":"sess-1"}}]}}"#;
        let herdr_list = move || Some(herdr_json.to_string());

        let start = Instant::now();
        let session_file = home.join(".claude/sessions").join(format!("{pid}.json"));
        let cwd = wt.display().to_string();
        let writer = std::thread::spawn(move || {
            while start.elapsed() < Duration::from_millis(120) {
                std::thread::sleep(Duration::from_millis(5));
            }
            std::fs::write(
                &session_file,
                format!(r#"{{"pid":{pid},"cwd":"{cwd}","sessionId":"sess-1","name":"skills-worker","procStart":"{proc_start}"}}"#),
            )
            .unwrap();
        });

        let name = poll_worker_session_name(
            home.to_str().unwrap(),
            wt.to_str().unwrap(),
            "implement-836",
            Duration::from_secs(2),
            Duration::from_millis(20),
            herdr_list,
        );
        writer.join().unwrap();
        assert_eq!(name, "skills-worker");
    }
}
