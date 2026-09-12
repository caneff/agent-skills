# Status of a dispatched agent

Read from the machine, not from the screen. Each question has one source,
quoted in the answer. `<name>` is the herdr agent name or its pane ID.

| Question | Source | Answer |
|---|---|---|
| working? | `herdr agent get <name>` | `agent_status` is `working` |
| blocked? | `herdr agent get <name>` | `agent_status` is `blocked` |
| idle? | `herdr agent get <name>` | `agent_status` is `idle` or `done` |
| dead? | sessions registry + `kill -0` | no live pid with `cwd` = the worktree |
| how far? | git, then `gh` | HEAD, pushed, PR |

```bash
herdr agent get <name>                                  # state
herdr agent read <name> --source visible --lines 40     # why idle is idle
for f in ~/.claude/sessions/*.json; do                  # liveness
  p=$(jq .pid "$f")
  [ "$(jq -r .cwd "$f")" = <worktree> ] && kill -0 "$p" 2>/dev/null \
    && [ "$(awk '{print $22}' /proc/$p/stat)" = "$(jq -r .procStart "$f")" ] \
    && jq -c '{pid,status,waitingFor}' "$f"
done
git -C <worktree> log --oneline -1                      # HEAD
git -C <worktree> status --porcelain                    # dirty?
git -C <worktree> ls-remote origin <branch>             # pushed? empty = no
gh pr list --repo <owner/name> --head <branch> --state all   # PR, branch alive
gh issue view <n> --repo <owner/name> \
  --json closedByPullRequestsReferences --jq '.closedByPullRequestsReferences[].number'
                                                        # PR, branch deleted
```

## The states

- **`working`** — herdr sees the agent mid-turn.
- **`blocked`** — herdr recognized an approval or question dialog. The agent
  needs an answer; `herdr agent prompt` refuses it with `agent_blocked`.
- **`idle`** / **`done`** — ready for input. `done` is an idle whose finished
  turn nobody has focused yet; reads do not mark it seen. Treat both as idle.
- **`unknown`** — an agent is present but herdr cannot classify it. It does
  not prove completion; re-check on the next poll.
- **dead** — no registry file for the worktree has a live pid. The registry
  decides; `herdr agent get` returning `agent_not_found` (the name clears
  when the agent exits) only corroborates it.
  A file whose pid fails `kill -0`, or whose `procStart` differs from field
  22 of `/proc/<pid>/stat` (the pid was reused), is stale — a crashed
  session leaves one. Ignore them.

## The registry and `waiting`

The sessions registry (`~/.claude/sessions/<pid>.json`) does write `waiting`
on a permission prompt. Observed 2026-09-12, Claude Code 2.1.270 under herdr
0.9.0, a Claude parked on a Bash approval dialog:

- registry: `"status":"waiting"`, `"waitingFor":"permission prompt"`
- `herdr agent get`: `"agent_status":"blocked"`

After the dialog was cancelled both went back together: registry `"idle"`
with `"waitingFor":null`, herdr `"idle"`. A mid-turn session shows `"busy"`
in the registry. When the pane closed, the process exited and its registry
file was removed.

Use the registry's `status` only to cross-check herdr, or when the session
runs outside herdr.

## The screen is never the source for "working"

`herdr agent read` returns terminal text. Unchanged text is not evidence of
work — an agent that printed "now the full gate" and then stopped to ask a
question prints nothing further, and the screen looks identical for hours.
Read the screen only to find out *why* an idle agent is idle, never to decide
whether it is working.

## Idle has three causes

An agent that is not `working` is idle in the loose sense: not running a
turn. That covers herdr `idle`, `done` and `blocked`, and a dead agent. It
has three causes:

- parked on a stop-and-ask — shows as `blocked` for a permission dialog, as
  `idle` for a question asked in plain prose (the turn ends at the input box;
  `herdr agent explain` names the rule, `live_prompt_box`). Needs an answer;
  `herdr agent read` is how you learn what it asked
- finished — shows as `idle` or `done`; HEAD, `ls-remote` and the PR lookup
  say how far it got
- dead — no live registry pid, which decides it (see **dead** above); resume with `claude --resume` in the worktree

## Poll; silence is not progress

A parked agent is invisible until someone looks. Notifications get lost. Poll
`herdr agent get` on a timer or arm `herdr agent wait <name> --until idle
--until blocked --until done --timeout <ms>`, and when an agent is
`blocked`, or `idle` with no PR, read its screen and act on what it is
waiting for.
