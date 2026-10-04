---
name: drain
description: Start a drain run (work the ready-for-agent queue unattended, one PR at a time) from a slash command.
disable-model-invocation: true
---

`/drain [--once] [--max <n>] [--anchor <n>] [--bundle-max <k>] [--repo <path>]`
starts `drain` and ends the turn. What a run does, picks, merges and refuses is
the docstring of `drain/drain.py` (#1403); this skill restates none of it.

## Start

1. **Resolve the primary checkout.** `<dir>` is `--repo` if given, else this
   session's directory:

   ```
   git -C <dir> rev-parse --absolute-git-dir
   git -C <dir> rev-parse --path-format=absolute --git-common-dir
   ```

   The two differing means `<dir>` is in a linked worktree: relay that and
   stop, because inside one `/implement` reads the session as a worker and
   drain's workers are keyed on the primary checkout. Otherwise `<repo>` is the
   common dir's parent, and `<repo-short>` its directory name, never `<dir>`'s:
   drain names its panes and its run after the primary checkout.
2. **Start it in the background** with the Bash tool's `run_in_background`:

   ```
   job-run --name drain-<repo-short> -- drain --repo <repo> <the other flags, unchanged>
   ```

   `job-run` refuses a second run under the same name while one is alive,
   which is the guard against two drains on one repo. Pass the flags through
   as typed; do not add, drop or reinterpret one.
3. **End the turn.** Never poll, `sleep` or wait on the run; its completion
   wakes you.

Say where to watch it: each build is a herdr pane named
`<repo-short>-<anchor>` (`herdr agent list`), and
`job-run --status drain-<repo-short>` says whether the run is alive.

## On completion

Run `job-run --status drain-<repo-short>`. A line beginning `killed` means the
run died with no record: say so and quote its last progress line. Otherwise
read the background command's own output: a refusal (`already live`, an
argparse error, `drain.py: ...`) is reported verbatim as a start that never
ran, not as a crash. A run that ran ends with drain's summary, in
`~/.cache/agent-jobs/drain-<repo-short>/progress` after the timestamp on each
line, starting at the line `merged:`, `handed to Chris:`, `stopped:` or
`nothing to drain`:

- **merged**: each ticket set with its PR and squash sha.
- **handed to Chris**: each ticket set with the reason, as drain printed it.
- **stopped**: the reason, when drain printed one.
