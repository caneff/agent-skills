//! `controller-adopt <agent>`: makes this session the controller of a worker
//! whose controller session is gone (#1098). A controller that exits (not a
//! `/clear`, which keeps the process) leaves its workers with no one to
//! report to and no one allowed to merge their PRs; `controller-restore`
//! restores only into the same process, so nothing else picks them up.
//! This moves the worker's record from the dead controller's
//! `<pid>.workers.jsonl` into this session's, so this session's own
//! `controller-restore` restores it after a `/clear`, and prints the message
//! that re-points the worker here. `controller-restore` names the orphans a
//! session may adopt on every session start.
//!
//! Runs from the adopting session, on the worker's repo's primary checkout.
//! Refuses a worker whose controller is still alive, one whose workspace was
//! torn down, and any cwd other than the primary checkout.

use lane::herdr::{self, HERDR_QUERY_TIMEOUT};
use lane::runner::{quiet_stdout, quiet_stdout_timeout};
use lane::workers::{self, AdoptRefusal};
use lane::{proc_info, safe_println, sessions};
use std::path::Path;
use std::process::ExitCode;

fn fail(msg: &str) -> ExitCode {
    eprintln!("controller-adopt: {msg}");
    ExitCode::from(1)
}

/// The primary checkout of the repo at `cwd`, when `cwd` is that checkout's
/// top level; `Err` names why not.
fn primary_checkout(cwd: &str) -> Result<String, String> {
    let top = quiet_stdout("git", &["-C", cwd, "rev-parse", "--show-toplevel"]).ok_or_else(|| format!("{cwd} is not in a git repo"))?;
    let list = quiet_stdout("git", &["-C", cwd, "worktree", "list", "--porcelain"]).ok_or_else(|| format!("git worktree list failed in {cwd}"))?;
    let primary = list.lines().next().and_then(|l| l.strip_prefix("worktree ")).ok_or_else(|| format!("git worktree list named no worktree in {cwd}"))?;
    let (top, primary) = (workers::canonical_workspace_path(top.trim()), workers::canonical_workspace_path(primary));
    if top != primary {
        return Err(format!("{top} is not the primary checkout ({primary}); adopt from there"));
    }
    Ok(primary)
}

/// The name the worker's brief-side `resolve-controller` takes for this
/// session: its herdr agent name when it has one, which a restart keeps,
/// else its session name — the same preference `implement-dispatch` briefs
/// with.
fn own_name(home: &Path, own_pid: &str) -> Option<String> {
    let me = sessions::live_all(home).into_iter().find(|s| s.pid == own_pid)?;
    let agent = quiet_stdout_timeout("herdr", &["agent", "list"], HERDR_QUERY_TIMEOUT)
        .and_then(|out| herdr::parse_agents(&out))
        .and_then(|agents| agents.iter().find(|a| !me.session_id.is_empty() && a.session() == me.session_id).and_then(|a| a.given_name()).map(str::to_string));
    agent.or_else(|| Some(me.name).filter(|n| !n.is_empty()))
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.iter().any(|a| a == "--help" || a == "-h") {
        safe_println!(
            "usage: controller-adopt <agent>\n\
             Makes this session the controller of the worker running as herdr agent <agent>,\n\
             whose controller session is gone. Run it on the worker's repo's primary checkout.\n\
             Refuses while the worker's controller is alive, or when its workspace is gone."
        );
        return ExitCode::SUCCESS;
    }
    let [agent] = args.as_slice() else { return fail("exactly one argument: the worker's herdr agent name") };
    let home = std::env::var("HOME").unwrap_or_default();
    let home = Path::new(&home);

    let Some(own_pid) = proc_info::parent_pid(std::process::id() as i32).and_then(|a| sessions::find_own_pid(home, a)) else {
        return fail("no live Claude session in this process's ancestry to adopt into");
    };
    let Some(own_start) = own_pid.parse::<i32>().ok().and_then(proc_info::read_stat).map(|s| s.start) else {
        return fail(&format!("cannot read this session's own starttime (pid {own_pid})"));
    };
    let cwd = std::env::current_dir().map(|p| p.display().to_string()).unwrap_or_default();
    let primary = match primary_checkout(&cwd) {
        Ok(p) => p,
        Err(e) => return fail(&e),
    };

    let adopted = match workers::adopt(home, agent, &primary, &own_pid, &own_start) {
        Ok(a) => a,
        Err(AdoptRefusal::NotFound) => return fail(&format!("no worker record names {agent} under {primary} (another session may have just adopted it)")),
        Err(AdoptRefusal::ControllerAlive(pid)) => {
            return fail(&format!("{agent}'s controller, pid {pid}, is alive; a worker has one controller"));
        }
        Err(AdoptRefusal::TornDown(ws)) => return fail(&format!("{agent}'s workspace {ws} was torn down; nothing is left to adopt")),
        Err(AdoptRefusal::Io(e)) => return fail(&format!("could not move {agent}'s record: {e}")),
    };

    let r = &adopted.record;
    safe_println!("adopted {} ({}) from controller pid {}, which is gone", r.agent, r.branch, adopted.from_pid);
    match own_name(home, &own_pid) {
        Some(name) => safe_println!(
            "tell the worker — SendMessage to the session `resolve-controller {}` prints: Your controller is now {name}",
            r.agent
        ),
        None => safe_println!("this session has no name to re-point the worker at: name it, then tell the worker: Your controller is now <name>"),
    }
    safe_println!("cleanup: {}", r.cleanup);
    ExitCode::SUCCESS
}
