# Dispatch-assigned scratch paths for batch subagents

The lane does not hand each parallel batch subagent a distinct `.scratch/<run>-<batch>` path.

## Why this is out of scope

Batch subagents are spawned by a worker or a controller with the Agent tool, in the middle of their own work. No dispatch path owns them: `implement-dispatch` starts workers, not the subagents a worker fans out. So there is no single place where a mechanism could assign the path. It would have to be written into every brief that fans out, which is the prose rule that already exists: scratch output lives in a git-ignored directory inside the worktree, with a filename unique to that worker, never in `/tmp` or the session scratchpad.

The evidence is one incident (#854's batch A, 2026-09-20). One run's pain earns a note, not a mechanism. If collisions recur, the fix belongs with whatever gains ownership of batch fan-out, not with dispatch.

## Prior requests

- #1037 — "Dispatch hands each parallel batch subagent a distinct .scratch/<run>-<batch> path"
