# Status of a dispatched agent

Read from the machine, not from the screen. Four sources, quoted in the answer:

```bash
ps --ppid <agent-pid> -o pid,etime,args --no-headers   # children = work in flight
git -C <worktree> log --oneline -1                     # HEAD
git -C <worktree> status --porcelain                   # dirty?
git -C <worktree> ls-remote origin <branch>            # pushed? empty = no
gh pr list --repo <owner/name> --head <branch>         # PR? empty = none
```

## The terminal tail is never the source

`orca terminal read` returns a cached screen. Unchanged text is not evidence
of work — an agent that printed "now the full gate" and then stopped to ask a
question prints nothing further, and the tail looks identical for hours. Read
the screen only to find out *why* an idle agent is idle, never to decide
whether it is working.

## What "no children" proves

A gate run has children: `just`, `node`, `python3`, `uv`. An agent process
with no children other than its own MCP servers is **not running anything**.

That is all it proves. Idle has three causes, and the screen tells them apart:

- parked on a stop-and-ask or a permission prompt — needs an answer
- finished — HEAD, `ls-remote` and `gh pr list` say how far it got
- dead — the process is gone entirely

## Poll; silence is not progress

A parked agent is invisible until someone looks. Notifications get lost. Poll
the four sources on a timer, and when an agent has been idle with no PR, read
its screen and act on what it is waiting for.
