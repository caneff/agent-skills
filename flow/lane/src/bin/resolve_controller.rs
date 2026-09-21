//! `resolve-controller <name>`: prints the address `SendMessage` takes for a
//! controller named in a brief (#923). The brief carries the controller's herdr
//! agent name, which survives a restart; the Claude session name, which does
//! not, is resolved here, at send time: herdr agent name -> `agent_session`
//! id -> the live `~/.claude/sessions/*.json` record's current `name`. A name
//! that is no herdr agent is accepted only if a live session bears it now.
//! Nothing resolves -> exit 1 with the reason, never a guess.

use lane::{herdr, runner::quiet_stdout_timeout, sessions};
use std::path::Path;
use std::process::ExitCode;
use std::time::Duration;

fn fail(msg: &str) -> ExitCode {
    eprintln!("resolve-controller: {msg}");
    ExitCode::from(1)
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.iter().any(|a| a == "--help" || a == "-h") {
        println!(
            "usage: resolve-controller <controller>\n\
             Prints the live Claude session name SendMessage takes for <controller>, a\n\
             herdr agent name (herdr agent list -> agent_session.value ->\n\
             ~/.claude/sessions/*.json name) or a session name a live session bears now."
        );
        return ExitCode::SUCCESS;
    }
    let [target] = args.as_slice() else { return fail("exactly one argument: the controller name from the brief") };
    let home = std::env::var("HOME").unwrap_or_default();
    let home = Path::new(&home);

    let listing = quiet_stdout_timeout("herdr", &["agent", "list"], Duration::from_secs(20)).unwrap_or_default();
    let agents = match herdr::parse_agents(&listing) {
        Some(a) => a,
        None => return fail("herdr agent list gave output of an unexpected shape"),
    };
    if let Some(agent) = agents.iter().find(|a| a.given_name() == Some(target.as_str())) {
        return match sessions::name_of_session(home, agent.session()) {
            Some(name) => {
                println!("{name}");
                ExitCode::SUCCESS
            }
            None => fail(&format!("herdr agent {target} runs session {:?}, which no live session record names", agent.session())),
        };
    }
    if sessions::is_live_name(home, target) {
        println!("{target}");
        return ExitCode::SUCCESS;
    }
    fail(&format!("{target} is neither a herdr agent name nor the name of a live session"))
}
