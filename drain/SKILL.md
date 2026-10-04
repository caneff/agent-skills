---
name: drain
description: Start a drain run (work the ready-for-agent queue unattended, one PR at a time) from a slash command.
disable-model-invocation: true
---

`/drain [--once] [--max <n>] [--anchor <n>] [--bundle-max <k>] [--repo <path>]`
starts `drain` and ends the turn. What a run does, picks, merges and refuses is
the docstring of `drain/drain.py` (#1403); this skill restates none of it.

## Start

1. **Resolve the repo**: `--repo` if given, else this session's directory.
   Make it absolute.
2. **Refuse a linked worktree**: `cd <repo> && python3
   ~/.agents/skills/burndown/loop.py seat`. A non-zero exit is the answer:
   relay its message and stop. Inside a linked worktree `/implement` reads the
   session as a worker, and drain's workers are keyed on the primary checkout.
3. **Start it in the background** with the Bash tool's `run_in_background`:

   ```
   job-run --name drain-<repo-short> -- drain --repo <repo> <the other flags, unchanged>
   ```

   `<repo-short>` is the repo directory's name. `job-run` refuses a second run
   under the same name while one is alive, which is the guard against two
   drains on one repo. Pass the flags through as typed; do not add, drop or
   reinterpret one.
4. **End the turn.** Never poll, `sleep` or wait on the run; its completion
   wakes you.

Say where to watch it: each build is a herdr pane named
`<repo-short>-<anchor>` (`herdr agent list`), and
`job-run --status drain-<repo-short>` says whether the run is alive.

## On completion

Report drain's summary, which `job-run` captured in
`~/.cache/agent-jobs/drain-<repo-short>/progress` (its last lines):

- **merged**: each ticket set with its PR and squash sha.
- **handed to Chris**: each ticket set with the reason, as drain printed it.
- **stopped**: the reason, when drain printed one.

A run that exited non-zero with no summary was killed or crashed: say so, and
quote the last progress line.
