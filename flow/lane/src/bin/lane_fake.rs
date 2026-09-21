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
//! HERDR_STALL for implement-dispatch; GH_PR_HEADS, HERDR_AGENTS,
//! HERDR_WORKSPACES, HERDR_LIST_FAIL (only `agent list` fails), HERDR_FAIL, HERDR_PANE_CLOSE_FAIL, GH_ASSIGNEES,
//! GH_ISSUE_EDIT_FAIL, GH_PR_CLOSES, GH_PR_CLOSES_FAIL for merge-cleanup.
//! Never installed — see install.sh.

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
const HERDR_WORKSPACE_VERBS: &[&str] = &["list", "create", "get", "focus", "rename", "report-metadata", "close"];
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
        "workspace" => args.get(1).is_some_and(|v| HERDR_WORKSPACE_VERBS.contains(&v.as_str())),
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

/// `GH_VIEW_BARRIER_DIR`: the first `issue view` of each dispatch (keyed by
/// its parent pid) waits until two dispatches have reached theirs, or 3s.
/// Independent of any lock the dispatches take, so a test can make two runs
/// read a ticket before either edits it, and see what the lock does to that.
fn view_barrier() {
    let Ok(dir) = env::var("GH_VIEW_BARRIER_DIR") else { return };
    let ppid = std::fs::read_to_string("/proc/self/stat")
        .ok()
        .and_then(|s| s.rsplit_once(')').and_then(|(_, r)| r.split_whitespace().nth(1).map(str::to_string)))
        .unwrap_or_default();
    let mine = std::path::Path::new(&dir).join(&ppid);
    if mine.exists() {
        return;
    }
    let _ = std::fs::write(&mine, "");
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(3);
    while std::fs::read_dir(&dir).map(|d| d.count()).unwrap_or(0) < 2 && std::time::Instant::now() < deadline {
        std::thread::sleep(std::time::Duration::from_millis(20));
    }
}

fn run_gh(args: &[String]) -> ExitCode {
    let a0 = args.first().map(String::as_str).unwrap_or("");
    let a1 = args.get(1).map(String::as_str).unwrap_or("");
    if (a0, a1) == ("issue", "view") {
        // A clump's tickets differ from each other, so GH_ISSUE_<n> gives
        // one ticket its own `<state>\t<labels>\t<assignees>` row; an empty
        // one is the fake's "no issue" failure for that ticket alone. The
        // GH_STATE/GH_LABELS/GH_ASSIGNEES trio still answers every ticket
        // with no row of its own.
        let n = args.get(2).map(String::as_str).unwrap_or("");
        view_barrier();
        let row = match env::var(format!("GH_ISSUE_{n}")) {
            Ok(row) => row,
            Err(_) => {
                let state = env::var("GH_STATE").unwrap_or_default();
                let labels = env::var("GH_LABELS").unwrap_or_default();
                let assignees = env::var("GH_ASSIGNEES").unwrap_or_default();
                format!("{state}\t{labels}\t{assignees}")
            }
        };
        if row.starts_with('\t') || row.is_empty() {
            eprintln!("no issue");
            return ExitCode::FAILURE;
        }
        // `GH_CLAIM_DIR` makes a claim stick: an edit adding in-progress
        // leaves `<dir>/<n>`, and a later view of that ticket carries the
        // label — what lets a test see two dispatches claim one ticket.
        // `GH_CLAIM_HIDE_UNTIL_EDIT=<n>` hides that ticket's claim from its
        // first view only, so the ticket reads free once and held after.
        let mut claimed = env::var("GH_CLAIM_DIR").is_ok_and(|d| std::path::Path::new(&d).join(n).exists());
        if let (Ok(dir), Ok(hide)) = (env::var("GH_CLAIM_DIR"), env::var("GH_CLAIM_HIDE_UNTIL_EDIT")) {
            let seen = std::path::Path::new(&dir).join(format!("{n}.viewed"));
            if hide == n && !seen.exists() {
                let _ = std::fs::write(&seen, "");
                claimed = false;
            }
        }
        let row = if claimed {
            let mut f: Vec<&str> = row.splitn(3, '\t').collect();
            f.resize(3, "");
            let labels = if f[1].is_empty() { "in-progress".to_string() } else { format!("{},in-progress", f[1]) };
            format!("{}\t{labels}\t{}", f[0], f[2])
        } else {
            row
        };
        // Tab-delimited, matching lane::issue_state::read's `-q` query: a
        // label or login can hold a space but never a tab.
        println!("{row}");
    }
    if (a0, a1) == ("issue", "edit") {
        // A comma-separated list of the ticket numbers whose edit fails, so
        // a clump test can fail one ticket's edit among several.
        let which = env::var("GH_ISSUE_EDIT_FAIL").unwrap_or_default();
        let n = args.get(2).map(String::as_str).unwrap_or("");
        if which.split(',').any(|t| !t.is_empty() && t == n) {
            eprintln!("gh: issue edit failed");
            return ExitCode::FAILURE;
        }
        if let Ok(dir) = env::var("GH_CLAIM_DIR") {
            if args.windows(2).any(|w| w[0] == "--add-label" && w[1] == "in-progress") {
                let _ = std::fs::write(std::path::Path::new(&dir).join(n), "");
            }
        }
    }
    if (a0, a1) == ("pr", "list") {
        return gh_pr_list(args);
    }
    if (a0, a1) == ("pr", "view") {
        let pr = args.get(2).map(String::as_str).unwrap_or("");
        if args.windows(2).any(|w| w[0] == "--json" && w[1].contains("closingIssuesReferences")) {
            let repo = args.windows(2).find(|w| w[0] == "--repo").map(|w| w[1].as_str()).unwrap_or("");
            return gh_pr_closes(pr, repo);
        }
        // PR 7 is caneff/merged-one, the bash stub's one resolvable PR.
        if pr != "7" {
            return ExitCode::FAILURE;
        }
        println!("caneff/merged-one");
    }
    ExitCode::SUCCESS
}

/// `pr list --head <b> --state merged --json ... --jq ...`: a merged PR #7
/// for each branch with a file under `$GH_PR_HEADS` (`/` spelled `__`)
/// holding the sha that PR merged at; nothing for any other branch.
/// The `closingIssuesReferences` form is answered separately, from
/// `$GH_PR_CLOSES`.
fn gh_pr_list(args: &[String]) -> ExitCode {
    let head = args.windows(2).find(|w| w[0] == "--head").map(|w| w[1].as_str()).unwrap_or("");
    let jq = args.iter().any(|a| a == "--jq");
    let dir = env::var("GH_PR_HEADS").unwrap_or_default();
    let Ok(body) = std::fs::read_to_string(Path::new(&dir).join(head.replace('/', "__"))) else {
        if !jq {
            println!("[]");
        }
        return ExitCode::SUCCESS;
    };
    // One merged PR per line, `<number> <oid>`. A line holding an oid alone
    // is PR 7, the one-PR shape every fixture but the branch-name-reuse one
    // records.
    let prs: Vec<(String, String)> = body
        .lines()
        .filter(|l| !l.trim().is_empty())
        .map(|l| match l.split_whitespace().collect::<Vec<_>>()[..] {
            [n, oid] => (n.to_string(), oid.to_string()),
            _ => ("7".to_string(), l.trim().to_string()),
        })
        .collect();
    if jq {
        for (n, oid) in &prs {
            println!("{n} {oid}");
        }
    } else {
        let items: Vec<String> = prs.iter().map(|(n, oid)| format!("{{\"number\":{n},\"headRefOid\":\"{oid}\"}}")).collect();
        println!("[{}]", items.join(","));
    }
    ExitCode::SUCCESS
}

/// `pr view <n> --json closingIssuesReferences`: PR `<n>` closes the tickets
/// listed in `$GH_PR_CLOSES/<n>`, one per line, each either `<number>` for a
/// ticket in the PR's own repo or `<owner>/<name>#<number>` for one
/// elsewhere. Keyed by PR number, not by branch: a branch name can carry
/// several merged PRs over its life, and only the one matching the landing
/// says what that landing closed. No file for the PR means it closes
/// nothing. A bare number's repository is `--repo`'s own slug, so the
/// caller's same-repo filter sees a match whatever the scratch origin is
/// named.
fn gh_pr_closes(pr: &str, repo: &str) -> ExitCode {
    // The ways the real call stops being an authoritative answer: it fails
    // outright, answers something that is not JSON, or answers JSON of the
    // wrong shape.
    match env::var("GH_PR_CLOSES_FAIL").unwrap_or_default().as_str() {
        "fail" => {
            eprintln!("gh: could not read the pull request");
            return ExitCode::FAILURE;
        }
        "garbage" => {
            println!("not json at all");
            return ExitCode::SUCCESS;
        }
        "wrong-shape" => {
            println!(r#"{{"closingIssuesReferences":"nope"}}"#);
            return ExitCode::SUCCESS;
        }
        "no-number" => {
            println!(r#"{{"closingIssuesReferences":[{{"repository":{{"name":"x","owner":{{"login":"y"}}}}}}]}}"#);
            return ExitCode::SUCCESS;
        }
        _ => {}
    }
    let dir = env::var("GH_PR_CLOSES").unwrap_or_default();
    let body = std::fs::read_to_string(Path::new(&dir).join(pr)).unwrap_or_default();
    let refs: Vec<String> = body
        .lines()
        .filter(|l| !l.trim().is_empty())
        .map(|line| {
            let (slug, n) = match line.trim().split_once('#') {
                Some((slug, n)) => (slug, n),
                None => (repo, line.trim()),
            };
            let (owner, name) = slug.rsplit_once('/').unwrap_or(("", slug));
            format!(r#"{{"number":{n},"repository":{{"name":"{name}","owner":{{"login":"{owner}"}}}}}}"#)
        })
        .collect();
    println!(r#"{{"closingIssuesReferences":[{}]}}"#, refs.join(","));
    ExitCode::SUCCESS
}

/// Prints the file an env var names; nothing when it is unset or unreadable.
fn cat_env_file(var: &str) {
    if let Some(body) = env::var(var).ok().and_then(|p| std::fs::read_to_string(p).ok()) {
        print!("{body}");
    }
}

fn run_herdr(args: &[String]) -> ExitCode {
    let a0 = args.first().map(String::as_str).unwrap_or("");
    let a1 = args.get(1).map(String::as_str).unwrap_or("");
    if env_flag("HERDR_FAIL") {
        return ExitCode::FAILURE;
    }
    match (a0, a1) {
        ("agent", "list") if env_flag("HERDR_LIST_FAIL") => return ExitCode::FAILURE,
        ("agent", "list") => cat_env_file("HERDR_AGENTS"),
        ("workspace", "list") => cat_env_file("HERDR_WORKSPACES"),
        ("pane", "close") => {
            if args.get(2).is_some_and(|p| env::var("HERDR_PANE_CLOSE_FAIL").is_ok_and(|f| &f == p)) {
                return ExitCode::FAILURE;
            }
        }
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
    fn herdr_workspace_close_is_allowed_and_an_invented_verb_is_not() {
        assert!(herdr_allowed(&["workspace".into(), "close".into()]));
        assert!(!herdr_allowed(&["workspace".into(), "delete".into()]));
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
