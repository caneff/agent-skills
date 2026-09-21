//! Typed `herdr agent list` and `herdr workspace list` output, standing in
//! for the bash port's `jq` filters over the same JSON.

use serde::Deserialize;

#[derive(Deserialize)]
struct AgentList {
    result: AgentResult,
}
#[derive(Deserialize)]
struct AgentResult {
    agents: Vec<Agent>,
}

#[derive(Deserialize)]
pub struct Agent {
    name: Option<String>,
    agent: Option<String>,
    agent_status: Option<String>,
    pane_id: Option<String>,
    cwd: Option<String>,
    agent_session: Option<AgentSession>,
}

#[derive(Deserialize)]
struct AgentSession {
    value: Option<String>,
}

impl Agent {
    /// `.name // .agent`.
    pub fn name(&self) -> &str {
        self.name.as_deref().or(self.agent.as_deref()).unwrap_or("")
    }
    /// The name the agent was started with; unlike `name()`, never the
    /// `agent` kind ("claude"), which names no one in particular.
    pub fn given_name(&self) -> Option<&str> {
        self.name.as_deref().filter(|n| !n.is_empty())
    }
    pub fn status(&self) -> &str {
        self.agent_status.as_deref().unwrap_or("")
    }
    pub fn cwd(&self) -> &str {
        self.cwd.as_deref().unwrap_or("")
    }
    pub fn pane(&self) -> &str {
        self.pane_id.as_deref().unwrap_or("")
    }
    /// `.agent_session.value`: the Claude sessionId running in the pane.
    pub fn session(&self) -> &str {
        self.agent_session.as_ref().and_then(|s| s.value.as_deref()).unwrap_or("")
    }
    /// idle or done: nothing running that a removal would interrupt.
    pub fn is_idle(&self) -> bool {
        matches!(self.status(), "idle" | "done")
    }
}

/// Parses `herdr agent list`. Empty output is no agents (jq read nothing and
/// exited 0); anything that is not the expected shape is `None`.
pub fn parse_agents(json: &str) -> Option<Vec<Agent>> {
    if json.trim().is_empty() {
        return Some(Vec::new());
    }
    serde_json::from_str::<AgentList>(json).ok().map(|l| l.result.agents)
}

#[derive(Deserialize)]
struct WorkspaceList {
    result: WorkspaceResult,
}
#[derive(Deserialize)]
struct WorkspaceResult {
    workspaces: Vec<Workspace>,
}
#[derive(Deserialize)]
struct Workspace {
    workspace_id: Option<String>,
    worktree: Option<WorkspaceWorktree>,
}
#[derive(Deserialize)]
struct WorkspaceWorktree {
    checkout_path: Option<String>,
}

/// The ids of the workspaces `herdr workspace list` reports at `checkout`;
/// empty when the output cannot be read.
pub fn workspaces_at(json: &str, checkout: &str) -> Vec<String> {
    let Ok(list) = serde_json::from_str::<WorkspaceList>(json) else { return Vec::new() };
    list.result
        .workspaces
        .into_iter()
        .filter(|w| w.worktree.as_ref().and_then(|t| t.checkout_path.as_deref()) == Some(checkout))
        .filter_map(|w| w.workspace_id)
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn an_agent_with_no_name_falls_back_to_its_agent_field() {
        let agents = parse_agents(r#"{"result":{"agents":[{"agent":"claude","cwd":"/w"}]}}"#).unwrap();
        assert_eq!(agents[0].name(), "claude");
    }

    #[test]
    fn output_of_another_shape_is_none_and_empty_output_is_no_agents() {
        assert!(parse_agents(r#"{"error":{"code":"x"}}"#).is_none());
        assert!(parse_agents("").unwrap().is_empty());
    }
}
