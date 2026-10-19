//! `resolve-controller <name>`: prints the address `SendMessage` takes for a
//! controller named in a brief (#923). The brief carries the controller's herdr
//! agent name, which survives a restart; the Claude session name, which does
//! not, is resolved here, at send time: herdr agent name -> `agent_session`
//! id -> the live `~/.claude/sessions/*.json` record's current `name`. A name
//! that is no herdr agent is accepted only if a live session bears it now.
//! Nothing resolves -> exit 1 with the reason, never a guess. A name that
//! resolves is then connected to on the live record's `messagingSocketPath`
//! (nothing sent): a missing path, a refused connection or one not accepted
//! within 3 s is exit 1, naming the path and the error (#1540).

use lane::herdr::HERDR_QUERY_TIMEOUT;
use lane::sessions::LiveSession;
use lane::{herdr, runner::quiet_stdout_timeout, sessions};
use std::path::Path;
use std::os::unix::net::UnixStream;
use std::process::ExitCode;
use std::sync::mpsc;
use std::time::Duration;

/// How long a connect may take before the socket counts as unreachable: a
/// full listen backlog blocks `connect` forever otherwise.
const CONNECT_TIMEOUT: Duration = Duration::from_secs(3);

fn fail(msg: &str) -> ExitCode {
    eprintln!("resolve-controller: {msg}");
    ExitCode::from(1)
}

/// Opens a connection to `session`'s `messagingSocketPath` and closes it,
/// sending nothing (#1540): the test runs from the sender's side, where a
/// moved socket directory or a stale socket file shows up as an error. `Err`
/// is the sentence naming the path and why it cannot be reached; a record
/// with no socket key names its own file, the only path there is.
fn reachable(home: &Path, session: &LiveSession) -> Result<(), String> {
    let name = &session.name;
    if session.socket.is_empty() {
        let record = home.join(".claude/sessions").join(format!("{}.json", session.pid));
        return Err(format!("{name}'s session record {} has no messagingSocketPath, so nothing can deliver to it", record.display()));
    }
    let path = session.socket.clone();
    let (tx, rx) = mpsc::channel();
    let target = path.clone();
    std::thread::spawn(move || {
        let _ = tx.send(UnixStream::connect(&target).map(drop));
    });
    match rx.recv_timeout(CONNECT_TIMEOUT) {
        Ok(Ok(())) => Ok(()),
        Ok(Err(e)) => Err(format!("{name}'s messaging socket {path} is unreachable: {e}")),
        Err(_) => Err(format!("{name}'s messaging socket {path} did not accept a connection within {}s", CONNECT_TIMEOUT.as_secs())),
    }
}

/// Prints the session's name when its socket is reachable, else exits 1 with why.
fn print_if_reachable(home: &Path, session: &LiveSession) -> ExitCode {
    match reachable(home, session) {
        Ok(()) => {
            println!("{}", session.name);
            ExitCode::SUCCESS
        }
        Err(why) => fail(&why),
    }
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.iter().any(|a| a == "--help" || a == "-h") {
        println!(
            "usage: resolve-controller <name>\n\
             Prints the live Claude session name SendMessage takes for <name>, which is\n\
             either a herdr agent name (herdr agent list -> agent_session.value ->\n\
             ~/.claude/sessions/*.json name) or a session name a live session bears now.\n\
             Exit 1, naming the path and the error, when that session's messagingSocketPath\n\
             is missing, refuses a connection or does not accept one within 3 s (the\n\
             connection sends nothing)."
        );
        return ExitCode::SUCCESS;
    }
    let [target] = args.as_slice() else { return fail("exactly one argument: a herdr agent name (the controller from the brief, or a worker)") };
    let home = std::env::var("HOME").unwrap_or_default();
    let home = Path::new(&home);

    // A listing that failed is not "herdr has no agents": say so, and never fall
    // through to the session-name branch on an answer herdr never gave.
    let Some(listing) = quiet_stdout_timeout("herdr", &["agent", "list"], HERDR_QUERY_TIMEOUT) else {
        return fail("herdr agent list failed or timed out; nothing was resolved");
    };
    let agents = match herdr::parse_agents(&listing) {
        Some(a) => a,
        None => return fail("herdr agent list gave output of an unexpected shape"),
    };
    if let Some(agent) = agents.iter().find(|a| a.given_name() == Some(target.as_str())) {
        return match sessions::named_session_of(home, agent.session()) {
            Some(session) => print_if_reachable(home, &session),
            None => fail(&format!("herdr agent {target} runs session {:?}, which no live session record names", agent.session())),
        };
    }
    if let Some(session) = sessions::find_live_by_name(home, target) {
        return print_if_reachable(home, &session);
    }
    fail(&format!("{target} is neither a herdr agent name nor the name of a live session"))
}
