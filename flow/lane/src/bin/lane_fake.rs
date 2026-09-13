//! A test-only fake standing in for `gh` and `herdr`, invoked through PATH
//! entries named `gh` and `herdr` that point at this same binary — it picks
//! its role from argv[0]. Every call is appended to `$CALL_LOG` (when set)
//! as `<role> <args...>`, then checked against a typed allowlist of real
//! subcommands (from `gh --help` and herdr 0.9.0's `--help`) before any
//! scenario logic runs: a subcommand missing from that list is refused,
//! the #745 lesson (a stub that accepted `herdr agent stop`, which does not
//! exist, hid a command that fails on the real machine). Scenario behavior
//! is driven by env vars, matching the bash stubs it replaces: GH_STATE,
//! GH_LABELS, HERDR_RUNNING, HERDR_NO_ROOT_PANE, HERDR_AGENT_TAKEN,
//! HERDR_STALL. Never installed — see install.sh.

use std::env;
use std::fs::OpenOptions;
use std::io::Write;
use std::path::Path;
use std::process::ExitCode;

const GH_TOP: &[&str] = &[
    "auth", "browse", "codespace", "discussion", "gist", "issue", "org", "pr", "project",
    "release", "repo", "skill", "cache", "run", "workflow", "co", "agent-task", "alias", "api",
    "attestation", "completion", "config", "copilot", "extension", "gpg-key", "label",
    "licenses", "preview", "ruleset", "search", "secret", "ssh-key", "status", "variable",
];
const GH_ISSUE_VERBS: &[&str] = &[
    "create", "list", "status", "close", "comment", "delete", "develop", "edit", "lock", "pin",
    "reopen", "transfer", "unlock", "unpin", "view",
];
const GH_PR_VERBS: &[&str] = &[
    "create", "list", "status", "checkout", "checks", "close", "comment", "diff", "edit",
    "lock", "merge", "ready", "reopen", "revert", "review", "unlock", "update-branch", "view",
];

const HERDR_TOP: &[&str] = &[
    "session", "status", "update", "channel", "server", "machine", "api", "workspace",
    "worktree", "tab", "notification", "agent", "pane", "integration", "completion", "config",
];
const HERDR_AGENT_VERBS: &[&str] = &[
    "list", "get", "read", "send-keys", "prompt", "rename", "focus", "wait", "attach", "start",
    "explain",
];
const HERDR_WORKTREE_VERBS: &[&str] = &["list", "create", "open", "remove"];
const HERDR_PANE_VERBS: &[&str] = &[
    "list", "current", "get", "layout", "process-info", "neighbor", "edges", "focus", "resize",
    "zoom", "read", "rename", "input", "split", "swap", "move", "close", "send-text",
    "send-keys", "wait-output", "run", "report-agent", "report-agent-session", "release-agent",
    "report-metadata",
];
const HERDR_STATUS_VERBS: &[&str] = &["server", "client"];

fn role_of(arg0: &str) -> String {
    Path::new(arg0).file_name().and_then(|f| f.to_str()).unwrap_or(arg0).to_string()
}

fn log(role: &str, args: &[String]) {
    let Ok(path) = env::var("CALL_LOG") else { return };
    let line = if args.is_empty() { role.to_string() } else { format!("{role} {}", args.join(" ")) };
    if let Ok(mut f) = OpenOptions::new().create(true).append(true).open(path) {
        let _ = writeln!(f, "{line}");
    }
}

fn gh_allowed(args: &[String]) -> bool {
    let Some(noun) = args.first() else { return true };
    if !GH_TOP.contains(&noun.as_str()) {
        return false;
    }
    match noun.as_str() {
        "issue" => args.get(1).is_some_and(|v| GH_ISSUE_VERBS.contains(&v.as_str())),
        "pr" => args.get(1).is_some_and(|v| GH_PR_VERBS.contains(&v.as_str())),
        _ => true,
    }
}

fn herdr_allowed(args: &[String]) -> bool {
    let Some(noun) = args.first() else { return true };
    if !HERDR_TOP.contains(&noun.as_str()) {
        return false;
    }
    match noun.as_str() {
        "agent" => args.get(1).is_some_and(|v| HERDR_AGENT_VERBS.contains(&v.as_str())),
        "worktree" => args.get(1).is_some_and(|v| HERDR_WORKTREE_VERBS.contains(&v.as_str())),
        "pane" => args.get(1).is_some_and(|v| HERDR_PANE_VERBS.contains(&v.as_str())),
        "status" => match args.get(1) {
            None => true,
            Some(v) if v.starts_with("--") => true,
            Some(v) => HERDR_STATUS_VERBS.contains(&v.as_str()),
        },
        _ => true,
    }
}

fn env_flag(name: &str) -> bool {
    env::var(name).is_ok_and(|v| !v.is_empty())
}

fn run_gh(args: &[String]) -> ExitCode {
    let a0 = args.first().map(String::as_str).unwrap_or("");
    let a1 = args.get(1).map(String::as_str).unwrap_or("");
    if (a0, a1) == ("issue", "view") {
        let state = env::var("GH_STATE").unwrap_or_default();
        if state.is_empty() {
            eprintln!("no issue");
            return ExitCode::FAILURE;
        }
        let labels = env::var("GH_LABELS").unwrap_or_default();
        println!("{state} {labels}");
    }
    ExitCode::SUCCESS
}

fn run_herdr(args: &[String]) -> ExitCode {
    let a0 = args.first().map(String::as_str).unwrap_or("");
    let a1 = args.get(1).map(String::as_str).unwrap_or("");
    match (a0, a1) {
        ("status", _) => {
            let running = if env::var("HERDR_RUNNING").as_deref() == Ok("true") { "true" } else { "false" };
            println!("{{\"server\":{{\"running\":{running}}}}}");
        }
        ("worktree", "open") => {
            if env_flag("HERDR_NO_ROOT_PANE") {
                println!("{{\"result\":{{\"workspace\":{{\"workspace_id\":\"w8\"}}}}}}");
            } else {
                println!(
                    "{{\"result\":{{\"workspace\":{{\"workspace_id\":\"w7\"}},\"root_pane\":{{\"pane_id\":\"w7:p1\"}}}}}}"
                );
            }
        }
        ("agent", "get") => {
            if env_flag("HERDR_AGENT_TAKEN") {
                println!("{{\"result\":{{\"agent\":{{\"name\":\"taken\"}}}}}}");
            } else {
                println!("{{\"error\":{{\"code\":\"agent_not_found\",\"message\":\"not found\"}}}}");
                return ExitCode::FAILURE;
            }
        }
        ("pane", "list") => {
            println!("{{\"result\":{{\"panes\":[{{\"pane_id\":\"w8:p3\"}}]}}}}");
        }
        ("agent", "prompt") => {
            if env_flag("HERDR_STALL") {
                println!(
                    "{{\"error\":{{\"code\":\"agent_prompt_stalled\",\"message\":\"no activity observed\"}},\"id\":\"cli:agent:prompt\"}}"
                );
                return ExitCode::FAILURE;
            }
        }
        _ => {}
    }
    ExitCode::SUCCESS
}

fn main() -> ExitCode {
    let mut argv = env::args();
    let arg0 = argv.next().unwrap_or_default();
    let args: Vec<String> = argv.collect();
    let role = role_of(&arg0);
    log(&role, &args);

    let allowed = match role.as_str() {
        "gh" => gh_allowed(&args),
        "herdr" => herdr_allowed(&args),
        _ => {
            eprintln!("lane-fake: invoked as unknown role '{role}' (expected gh or herdr)");
            return ExitCode::FAILURE;
        }
    };
    if !allowed {
        eprintln!("lane-fake: {role} has no subcommand '{}'", args.join(" "));
        return ExitCode::FAILURE;
    }

    match role.as_str() {
        "gh" => run_gh(&args),
        "herdr" => run_herdr(&args),
        _ => unreachable!(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn herdr_agent_stop_is_not_a_real_subcommand() {
        assert!(!herdr_allowed(&["agent".into(), "stop".into()]));
    }

    #[test]
    fn herdr_agent_prompt_is_allowed() {
        assert!(herdr_allowed(&["agent".into(), "prompt".into()]));
    }

    #[test]
    fn herdr_unknown_top_level_is_rejected() {
        assert!(!herdr_allowed(&["frobnicate".into()]));
    }

    #[test]
    fn gh_issue_view_is_allowed_and_repo_delete_is_not_confused_with_it() {
        assert!(gh_allowed(&["issue".into(), "view".into()]));
        assert!(!gh_allowed(&["issue".into(), "vaporize".into()]));
    }

    #[test]
    fn gh_unknown_top_level_is_rejected() {
        assert!(!gh_allowed(&["nonexistent".into()]));
    }
}
