//! Port of `flow/bin/implement-dispatch`. What the dispatcher runs for the
//! `/implement` lane: turn a ticket number into a worker running in its own
//! workspace inside herdr, report, and stop. It never waits on the worker.
//!
//!   implement-dispatch [--repo <path>] [--model sonnet|opus] [--controller <name>]
//!                      <issue number>
//!
//! The brief is `/implement <n> --tier light|heavy --controller "<name>"`: light
//! when the issue carries the documentation label, heavy otherwise. The
//! controller is --controller, else the name in ~/.claude/sessions/<pid>.json of
//! the nearest ancestor process whose file is live (its procStart matches) — the
//! Claude session running this. Session names can hold spaces, hence the quotes.
//!
//! Refuses, with nothing claimed or created, when the issue is not open and
//! labelled ready-for-agent, no controller is named or found, the herdr server
//! is not running, claude onboarding is incomplete, the herdr agent name is
//! taken, or the workspace path or branch already exists. After the workspace
//! exists, any herdr failure exits non-zero with herdr's own error and leaves the
//! workspace in place for inspection. There is no bare-claude fallback.

use lane::{git_origin, proc_info, runner, sessions};
use serde_json::Value;
use std::env;
use std::path::{Path, PathBuf};
use std::process::{Command, ExitCode, Stdio};

const HELP: &str = r#"What the dispatcher runs for the /implement lane: turn a ticket number into a
worker running in its own workspace inside herdr, report, and stop. It never
waits on the worker.

  implement-dispatch [--repo <path>] [--model sonnet|opus] [--controller <name>]
                     <issue number>

The brief is `/implement <n> --tier light|heavy --controller "<name>"`: light
when the issue carries the documentation label, heavy otherwise. The
controller is --controller, else the name in ~/.claude/sessions/<pid>.json of
the nearest ancestor process whose file is live (its procStart matches) — the
Claude session running this. Session names can hold spaces, hence the quotes.

Refuses, with nothing claimed or created, when the issue is not open and
labelled ready-for-agent, no controller is named or found, the herdr server
is not running, claude onboarding is incomplete, the herdr agent name is
taken, or the workspace path or branch already exists. After the workspace
exists, any herdr failure exits non-zero with herdr's own error and leaves the
workspace in place for inspection. There is no bare-claude fallback.
"#;

fn die(msg: impl AsRef<str>) -> ExitCode {
    eprintln!("implement-dispatch: {}", msg.as_ref());
    ExitCode::FAILURE
}

fn command_on_path(name: &str) -> bool {
    let Some(path) = env::var_os("PATH") else { return false };
    env::split_paths(&path).any(|dir| dir.join(name).is_file())
}

struct Args {
    repo: Option<String>,
    model: String,
    controller: Option<String>,
    n: Option<String>,
}

enum Parsed {
    Help,
    Args(Args),
    Err(String),
}

fn parse_args(argv: Vec<String>) -> Parsed {
    let mut repo = None;
    let mut model = "sonnet".to_string();
    let mut controller = None;
    let mut n: Option<String> = None;
    let mut it = argv.into_iter();
    while let Some(a) = it.next() {
        match a.as_str() {
            "--repo" => match it.next() {
                Some(v) => repo = Some(v),
                None => return Parsed::Err("--repo needs a value".into()),
            },
            "--model" => match it.next() {
                Some(v) => model = v,
                None => return Parsed::Err("--model needs a value".into()),
            },
            "--controller" => match it.next() {
                Some(v) => controller = Some(v),
                None => return Parsed::Err("--controller needs a value".into()),
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
    Parsed::Args(Args { repo, model, controller, n })
}

/// Handles the hidden `--seed-trust <claude.json path> <workspace path>`
/// form: the critical section run under `flock`, standing in for the bash
/// subshell `{ ... } 9>"$lock"`. Sets `.projects[$wt].hasTrustDialogAccepted`
/// to true, preserving everything else in the file.
fn seed_trust(claude_json: &str, wt: &str) -> ExitCode {
    let raw = match std::fs::read_to_string(claude_json) {
        Ok(r) => r,
        Err(_) => {
            println!("jq could not rewrite {claude_json}");
            return ExitCode::FAILURE;
        }
    };
    let mut value: Value = match serde_json::from_str(&raw) {
        Ok(v) => v,
        Err(_) => {
            println!("jq could not rewrite {claude_json}");
            return ExitCode::FAILURE;
        }
    };
    let Some(obj) = value.as_object_mut() else {
        println!("jq could not rewrite {claude_json}");
        return ExitCode::FAILURE;
    };
    let projects = obj.entry("projects").or_insert_with(|| Value::Object(Default::default()));
    let Some(projects) = projects.as_object_mut() else {
        println!("jq could not rewrite {claude_json}");
        return ExitCode::FAILURE;
    };
    let entry = projects.entry(wt.to_string()).or_insert_with(|| Value::Object(Default::default()));
    let Some(entry) = entry.as_object_mut() else {
        println!("jq could not rewrite {claude_json}");
        return ExitCode::FAILURE;
    };
    entry.insert("hasTrustDialogAccepted".to_string(), Value::Bool(true));

    let tmp = format!("{claude_json}.tmp-{}-{}", std::process::id(), std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0));
    let write_ok = std::fs::write(&tmp, serde_json::to_string_pretty(&value).unwrap_or_default()).is_ok();
    if !write_ok || std::fs::rename(&tmp, claude_json).is_err() {
        let _ = std::fs::remove_file(&tmp);
        println!("jq could not rewrite {claude_json}");
        return ExitCode::FAILURE;
    }
    ExitCode::SUCCESS
}

fn quiet_stdout(program: &str, args: &[&str]) -> Option<String> {
    let out = Command::new(program).args(args).stdin(Stdio::null()).stderr(Stdio::null()).output().ok()?;
    if !out.status.success() {
        return None;
    }
    let mut s = String::from_utf8_lossy(&out.stdout).into_owned();
    // Bash's `$(...)` strips trailing newlines; match that.
    while s.ends_with('\n') {
        s.pop();
    }
    Some(s)
}

fn quiet_ok(program: &str, args: &[&str]) -> bool {
    Command::new(program)
        .args(args)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
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

fn fail(what: &str, out: &str, n: &str, slug: &str, wt: &Path) -> ExitCode {
    eprintln!("implement-dispatch: {what} failed: {out}");
    if wt.exists() {
        eprintln!("workspace left in place at {}", wt.display());
    }
    eprintln!(
        "release the ticket: gh issue edit {n} --repo {slug} --remove-label in-progress --add-label ready-for-agent"
    );
    ExitCode::FAILURE
}

fn main() -> ExitCode {
    let mut raw_args: Vec<String> = env::args().skip(1).collect();
    // Hidden critical-section entry point run under `flock`; never reached
    // through normal flag parsing.
    if raw_args.first().map(String::as_str) == Some("--seed-trust") {
        if raw_args.len() != 3 {
            eprintln!("implement-dispatch: --seed-trust needs a claude.json path and a workspace path");
            return ExitCode::FAILURE;
        }
        return seed_trust(&raw_args[1], &raw_args[2]);
    }

    let parsed = parse_args(std::mem::take(&mut raw_args));
    let args = match parsed {
        Parsed::Help => {
            print!("{HELP}");
            return ExitCode::SUCCESS;
        }
        Parsed::Err(e) => return die(e),
        Parsed::Args(a) => a,
    };

    let n = match &args.n {
        Some(n) if !n.is_empty() && n.chars().all(|c| c.is_ascii_digit()) => n.clone(),
        _ => return die("name one issue number"),
    };
    if args.model != "sonnet" && args.model != "opus" {
        return die(format!("--model must be sonnet or opus, not '{}'", args.model));
    }
    if !command_on_path("flock") {
        return die("flock is not on PATH");
    }

    let repo = args.repo.clone().unwrap_or_else(|| env::current_dir().map(|p| p.display().to_string()).unwrap_or_default());
    let Some(primary) = primary_worktree(&repo) else {
        return die(format!("not a git repo: {repo}"));
    };
    let slug = git_origin::origin_slug(Path::new(&primary)).unwrap_or_default();
    if !valid_slug(&slug) {
        return die(format!("origin in {primary} names no GitHub owner/name"));
    }
    let branch = format!("implement-{n}");
    let wt = PathBuf::from(&primary).join(".claude/worktrees").join(&branch);
    let suffix = format!("-{n}");
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
        return die(format!("#{n} is not an open issue"));
    }
    let labels = format!(",{labels_csv},");
    if !labels.contains(",ready-for-agent,") {
        return die(format!("#{n} is not labelled ready-for-agent"));
    }
    for held in ["in-progress", "needs-info", "ready-for-human"] {
        if labels.contains(&format!(",{held},")) {
            return die(format!("#{n} is labelled {held}"));
        }
    }
    let tier = if labels.contains(",documentation,") { "light" } else { "heavy" };

    let home = env::var("HOME").unwrap_or_default();
    let controller = match args.controller.clone() {
        Some(c) => c,
        None => {
            let self_pid = std::process::id() as i32;
            let start_ancestor = proc_info::parent_pid(self_pid).unwrap_or(0);
            match sessions::find_controller(Path::new(&home), start_ancestor) {
                Some(c) => c,
                None => {
                    return die(
                        "no controller: no live ancestor session has a ~/.claude/sessions/<pid>.json name; pass --controller",
                    );
                }
            }
        }
    };
    if controller.contains('"') || controller.contains('\n') {
        return die(format!("controller name cannot hold a double quote or newline: {controller}"));
    }

    let status_out = quiet_stdout("herdr", &["status", "--json"]).unwrap_or_default();
    let running = serde_json::from_str::<Value>(&status_out)
        .ok()
        .and_then(|v| v.get("server").and_then(|s| s.get("running")).and_then(Value::as_bool))
        .unwrap_or(false);
    if !running {
        return die("no herdr server is running (herdr status)");
    }

    let claude_json_path = format!("{home}/.claude.json");
    let onboarded = std::fs::read_to_string(&claude_json_path)
        .ok()
        .and_then(|s| serde_json::from_str::<Value>(&s).ok())
        .and_then(|v| v.get("hasCompletedOnboarding").and_then(Value::as_bool))
        .unwrap_or(false);
    if !onboarded {
        return die(format!(
            "claude onboarding is not complete in {claude_json_path}; a brief would land in its dialog"
        ));
    }

    if quiet_ok("herdr", &["agent", "get", &agent]) {
        return die(format!("herdr agent {agent} already exists"));
    }
    if !quiet_ok("git", &["-C", &primary, "fetch", "-q", "origin"]) {
        return die(format!("git fetch failed in {primary}"));
    }
    let registered_worktree = quiet_stdout("git", &["-C", &primary, "worktree", "list", "--porcelain"])
        .map(|out| out.lines().any(|l| l == format!("worktree {}", wt.display())))
        .unwrap_or(false);
    if wt.exists() || registered_worktree {
        return die(format!("{} already exists", wt.display()));
    }
    if quiet_ok("git", &["-C", &primary, "show-ref", "-q", "--verify", &format!("refs/heads/{branch}")]) {
        return die(format!("branch {branch} already exists"));
    }
    let default = git_origin::default_branch(Path::new(&primary));
    if !quiet_ok("git", &["-C", &primary, "show-ref", "-q", "--verify", &format!("refs/remotes/origin/{default}")]) {
        return die(format!("no origin/{default} to branch from"));
    }

    // Past here the ticket is claimed; a failure says how to release it.
    let claim = runner::run(
        "gh",
        &[
            "issue",
            "edit",
            &n,
            "--repo",
            &slug,
            "--remove-label",
            "ready-for-agent",
            "--add-label",
            "in-progress",
            "--add-assignee",
            "@me",
        ],
    );
    match claim {
        Ok(c) if c.success => {}
        _ => return die(format!("could not claim #{n}")),
    }

    let wa = runner::run_in(
        None,
        "git",
        &["-C", &primary, "worktree", "add", "-q", "--no-track", "-b", &branch, wt.to_str().unwrap_or(""), &format!("origin/{default}")],
    );
    match wa {
        Ok(o) if o.success => {}
        Ok(o) => return fail("git worktree add", &o.combined, &n, &slug, &wt),
        Err(e) => return fail("git worktree add", &e.to_string(), &n, &slug, &wt),
    }

    let lock = format!("{home}/.claude.json.implement-dispatch.lock");
    let self_exe = env::current_exe().map(|p| p.display().to_string()).unwrap_or_else(|_| "implement-dispatch".to_string());
    let seed = runner::run(
        "flock",
        &["-w", "30", &lock, &self_exe, "--seed-trust", &claude_json_path, wt.to_str().unwrap_or("")],
    );
    match seed {
        Ok(o) if o.success => {}
        Ok(o) => return fail("trust pre-seed", &o.combined, &n, &slug, &wt),
        Err(e) => return fail("trust pre-seed", &e.to_string(), &n, &slug, &wt),
    }

    // --cwd names the repo: without it herdr resolves the focused workspace's
    // repo and answers worktree_not_found.
    let open = runner::run(
        "herdr",
        &["worktree", "open", "--cwd", &primary, "--path", wt.to_str().unwrap_or(""), "--label", &branch, "--no-focus", "--trust-repository"],
    );
    let open_out = match open {
        Ok(o) if o.success => o.combined,
        Ok(o) => return fail("herdr worktree open", &o.combined, &n, &slug, &wt),
        Err(e) => return fail("herdr worktree open", &e.to_string(), &n, &slug, &wt),
    };
    let open_json: Option<Value> = serde_json::from_str(&open_out).ok();
    let mut pane = open_json
        .as_ref()
        .and_then(|v| v.get("result"))
        .and_then(|v| v.get("root_pane"))
        .and_then(|v| v.get("pane_id"))
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();
    if pane.is_empty() {
        let ws = open_json
            .as_ref()
            .and_then(|v| v.get("result"))
            .and_then(|v| v.get("workspace"))
            .and_then(|v| v.get("workspace_id"))
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string();
        if ws.is_empty() {
            return fail("herdr worktree open", &format!("no workspace in its response: {open_out}"), &n, &slug, &wt);
        }
        let panes = match runner::run("herdr", &["pane", "list", "--workspace", &ws]) {
            Ok(o) if o.success => o.combined,
            Ok(o) => return fail("herdr pane list", &o.combined, &n, &slug, &wt),
            Err(e) => return fail("herdr pane list", &e.to_string(), &n, &slug, &wt),
        };
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
            return fail("herdr pane list", &format!("no pane in workspace {ws}: {panes}"), &n, &slug, &wt);
        }
    }

    let start = runner::run("herdr", &["agent", "start", &agent, "--kind", "claude", "--pane", &pane, "--", "--model", &args.model]);
    match start {
        Ok(o) if o.success => {}
        Ok(o) => return fail("herdr agent start", &o.combined, &n, &slug, &wt),
        Err(e) => return fail("herdr agent start", &e.to_string(), &n, &slug, &wt),
    }

    let brief = format!("/implement {n} --tier {tier} --controller \"{controller}\"");
    let prompt = runner::run(
        "herdr",
        &["agent", "prompt", &agent, &brief, "--wait", "--until", "working", "--timeout", "120000"],
    );
    match prompt {
        Ok(o) if o.success => {}
        Ok(o) => return fail("herdr agent prompt", &o.combined, &n, &slug, &wt),
        Err(e) => return fail("herdr agent prompt", &e.to_string(), &n, &slug, &wt),
    }

    println!("dispatched #{n} ({}, {tier} tier, controller {controller})", args.model);
    println!("worktree: {}", wt.display());
    println!("branch:   {branch}");
    println!("agent:    {agent}");
    println!("cleanup:  cd {primary} && merge-cleanup {branch} --repo {primary}");
    ExitCode::SUCCESS
}
