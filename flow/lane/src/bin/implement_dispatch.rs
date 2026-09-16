//! Port of `flow/bin/implement-dispatch`. What the dispatcher runs for the
//! `/implement` lane: turn a ticket number into a worker running in its own
//! workspace inside herdr, report, and stop. It never waits on the worker.
//! The contract is `--help` below.

use lane::runner::{self, quiet_ok, quiet_ok_timeout, quiet_stdout, quiet_stdout_timeout, run_timeout, CommandOutput};
use lane::{git_origin, herdr, proc_info, safe_print, safe_println, sessions};
use serde_json::Value;
use std::env;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::process::ExitCode;
use std::time::Duration;

/// OS-level bound for the herdr calls that are plain queries or short
/// mutations (status, agent get/list, worktree open, pane list, agent
/// start): a herdr server that answers at all answers within this, so a
/// hang past it means the subprocess itself is stuck, not that the work is
/// legitimately slow.
const HERDR_QUERY_TIMEOUT: Duration = Duration::from_secs(10);
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
                     <issue number>
  implement-dispatch [--repo <path>] [--model sonnet|opus] [--controller <name>]
                     --spec <n> --slots <k>

Plain mode: the brief is `/implement <n> --tier light|heavy --controller
"<name>"`, light when the issue carries the documentation label, heavy
otherwise. A ready-for-human ticket's brief ends with --chris-merges: the
worker builds it and Chris merges its PR. Branch and workspace are
implement-<n>; --model defaults to sonnet.

Spec mode (--spec): the brief is `/implement-spec <n> --slots <k> --controller
"<name>"`, a nested run over a spec issue. Branch and workspace are spec-<n>,
the herdr agent is <repo>-spec-<n>, and --model defaults to opus. --slots is a
positive integer, required with --spec and refused without it.

The controller is --controller, else the name in ~/.claude/sessions/<pid>.json
of the nearest ancestor process whose file is live (its procStart matches) —
the Claude session running this. Session names can hold spaces, hence the
quotes.

The claim swaps ready-for-agent for in-progress. A ready-for-human ticket
keeps ready-for-human and adds in-progress beside it, so the live labels
still show Chris-merges after the claim, and a second dispatch still refuses
on the held in-progress label. Release on a failed claim undoes only what the
claim did: in-progress off, plus the ready label back on for ready-for-agent.

Refuses, with nothing claimed or created, when the issue is not open and
labelled exactly one of ready-for-agent and ready-for-human, it carries a
held label (in-progress, needs-info), spec mode names an issue without the
spec label or with ready-for-human, plain mode names one with the spec
label, no controller is named or found, the herdr server is not running,
claude onboarding is incomplete, the herdr agent name is taken, or the
workspace path or branch already exists.
After the workspace exists, any herdr failure exits non-zero with herdr's own
error and leaves the workspace in place for inspection. There is no
bare-claude fallback.
"#;

fn die(msg: impl AsRef<str>) -> ExitCode {
    eprintln!("implement-dispatch: {}", msg.as_ref());
    ExitCode::FAILURE
}

struct Args {
    repo: Option<String>,
    model: Option<String>,
    controller: Option<String>,
    n: Option<String>,
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
    let mut n: Option<String> = None;
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
                Some(_) if n.is_some() => return Parsed::Err("one ticket at a time".into()),
                Some(v) => {
                    spec = true;
                    n = Some(v);
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
                if n.is_some() {
                    return Parsed::Err("one ticket at a time".into());
                }
                n = Some(a);
            }
        }
    }
    Parsed::Args(Args { repo, model, controller, n, spec, slots })
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

/// The claimed ticket: what a failure past the claim needs to say how to
/// release it, and where the workspace would be if it exists.
struct Claim<'a> {
    n: &'a str,
    slug: &'a str,
    ready: &'a str,
    chris_merges: bool,
    wt: &'a Path,
}

impl Claim<'_> {
    fn fail(&self, what: &str, out: &str) -> ExitCode {
        eprintln!("implement-dispatch: {what} failed: {out}");
        if self.wt.exists() {
            eprintln!("workspace left in place at {}", self.wt.display());
        }
        // A ready-for-human claim never removed its ready label, so release
        // only undoes the in-progress side of it.
        if self.chris_merges {
            eprintln!("release the ticket: gh issue edit {} --repo {} --remove-label in-progress", self.n, self.slug);
        } else {
            eprintln!(
                "release the ticket: gh issue edit {} --repo {} --remove-label in-progress --add-label {}",
                self.n, self.slug, self.ready
            );
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

    let n = match &args.n {
        Some(n) if !n.is_empty() && n.chars().all(|c| c.is_ascii_digit()) => n.clone(),
        _ => return Err(die("name one issue number")),
    };
    let mode = match (&args.slots, args.spec) {
        (None, false) => Mode::Plain,
        (None, true) => return Err(die("--spec needs --slots <k>")),
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

    // Refusals first, so a refused run leaves nothing claimed or created.
    let issue = quiet_stdout(
        "gh",
        &[
            "issue",
            "view",
            &n,
            "--repo",
            &slug,
            "--json",
            "state,labels",
            "-q",
            ".state + \" \" + ([.labels[].name] | join(\",\"))",
        ],
    )
    .unwrap_or_default();
    let (state, labels_csv) = issue.split_once(' ').unwrap_or((issue.as_str(), ""));
    if state != "OPEN" {
        return Err(die(format!("#{n} is not an open issue")));
    }
    let labels = format!(",{labels_csv},");
    // The ready label the claim swaps for in-progress. A ready-for-human
    // ticket is built the same way, but its brief says Chris merges it.
    let (ready, chris_merges) = match (labels.contains(",ready-for-agent,"), labels.contains(",ready-for-human,")) {
        (true, false) => ("ready-for-agent", false),
        (false, true) => ("ready-for-human", true),
        (true, true) => return Err(die(format!("#{n} is labelled both ready-for-agent and ready-for-human"))),
        (false, false) => return Err(die(format!("#{n} is not labelled ready-for-agent or ready-for-human"))),
    };
    for held in ["in-progress", "needs-info"] {
        if labels.contains(&format!(",{held},")) {
            return Err(die(format!("#{n} is labelled {held}")));
        }
    }
    match (mode, labels.contains(",spec,")) {
        (Mode::Spec { .. }, false) => return Err(die(format!("#{n} is not labelled spec"))),
        (Mode::Plain, true) => return Err(die(format!("#{n} is labelled spec; dispatch it with --spec {n} --slots <k>"))),
        (Mode::Spec { .. }, true) if chris_merges => {
            return Err(die(format!("#{n} is labelled ready-for-human; a spec run has no Chris-merges brief")));
        }
        _ => {}
    }
    let tier = if labels.contains(",documentation,") { "light" } else { "heavy" };

    let home = env::var("HOME").unwrap_or_default();
    // An empty --controller is bash's `[ -z "$controller" ]`: absent, not a
    // literal empty name, so it still falls through to the session lookup.
    let controller_flag = args.controller.as_deref().filter(|c| !c.is_empty());
    let controller = match controller_flag {
        Some(c) => c.to_string(),
        None => {
            let self_pid = std::process::id() as i32;
            let start_ancestor = proc_info::parent_pid(self_pid).unwrap_or(0);
            match sessions::find_controller(Path::new(&home), start_ancestor) {
                Some(c) => c,
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
    if !quiet_ok("git", &["-C", &primary, "fetch", "-q", "origin"]) {
        return Err(die(format!("git fetch failed in {primary}")));
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

    // Past here the ticket is claimed; a failure says how to release it. A
    // ready-for-human ticket keeps its ready label through the build, so the
    // live labels stay a Chris-merges signal that outlives this session; a
    // ready-for-agent ticket still swaps its ready label for in-progress.
    let mut claim_args: Vec<&str> = vec!["issue", "edit", &n, "--repo", &slug];
    if !chris_merges {
        claim_args.extend(["--remove-label", ready]);
    }
    claim_args.extend(["--add-label", "in-progress", "--add-assignee", "@me"]);
    let claimed = runner::run("gh", &claim_args);
    match claimed {
        Ok(c) if c.success => {}
        _ => return Err(die(format!("could not claim #{n}"))),
    }
    let claim = Claim { n: &n, slug: &slug, ready, chris_merges, wt: &wt };

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
        HERDR_QUERY_TIMEOUT,
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
        run_timeout("herdr", &["agent", "start", &agent, "--kind", "claude", "--pane", &pane, "--", "--model", &model], HERDR_QUERY_TIMEOUT),
        None,
    )?;

    let (brief, described) = match mode {
        Mode::Plain => {
            let (marker, merger) = if chris_merges { (" --chris-merges", ", Chris merges") } else { ("", "") };
            (format!("/implement {n} --tier {tier} --controller \"{controller}\"{marker}"), format!("{tier} tier{merger}"))
        }
        Mode::Spec { slots } => (format!("/implement-spec {n} --slots {slots} --controller \"{controller}\""), format!("spec, {slots} slots")),
    };
    claim.step(
        "herdr agent prompt",
        run_timeout("herdr", &["agent", "prompt", &agent, &brief, "--wait", "--until", "working", "--timeout", "120000"], HERDR_PROMPT_TIMEOUT),
        None,
    )?;

    let session = worker_session_name(&home, wt.to_str().unwrap_or(""), &agent);

    safe_println!("dispatched #{n} ({model}, {described}, controller {controller})");
    safe_println!("worktree: {}", wt.display());
    safe_println!("branch:   {branch}");
    safe_println!("agent:    {agent}");
    safe_println!("session:  {session}");
    safe_println!("cleanup:  cd {primary} && merge-cleanup {branch} --repo {primary}");
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
        std::fs::write(
            home.join(".claude/sessions").join(format!("{pid}.json")),
            format!(r#"{{"pid":{pid},"cwd":"{}","sessionId":"sess-1","name":"skills-worker"}}"#, wt.display()),
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
            std::fs::write(&session_file, format!(r#"{{"pid":{pid},"cwd":"{cwd}","sessionId":"sess-1","name":"skills-worker"}}"#)).unwrap();
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
