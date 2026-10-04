---
name: drain
description: Start a drain run (work the ready-for-agent queue unattended, one PR at a time) from a slash command.
disable-model-invocation: true
---

`/drain [--once] [--max <n>] [--anchor <n>] [--bundle-max <k>] [--repo <path>]`
starts `drain`. What a run does, picks, merges and refuses is
the docstring of `drain/drain.py` (#1403); this skill restates none of it.

`/drain status` starts nothing: it is `## Status`. So is a `/drain` with
no flags while `job-run --status drain-<repo-short>` says `alive` (that run's
batch is what it lists); with flags while one is alive, `job-run` refuses a
second run, and the refusal is reported as it stands. Neither case runs the
steps below.

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
3. **Wait for the first bundle in this turn, then print it.** The chooser is
   one headless `claude -p`, so the bundle line follows within minutes. Before
   step 2, read `date -u +%Y-%m-%dT%H:%M:%SZ` as `<start>`: the progress file
   holds the previous run's lines until `job-run` empties it, and only a line
   stamped at or after `<start>` is this run's. Arm the Monitor tool
   (`timeout_ms` 250000) on a command that ends at the first such line and at
   its own 240 seconds, with no `sleep` and no poll loop:

   ```
   awk -v s=<start> '$1 >= s && /bundle started:|nothing to drain|stopped:|drain\.py:/ {print; fflush(); exit}' < <(timeout 240 tail -n +1 -F ~/.cache/agent-jobs/drain-<repo-short>/progress)
   ```

   - A `bundle started:` line: print its tickets with their titles and the
     worker pane, as drain printed them, and say `/drain status` shows the
     batch from here on. Then end the turn.
   - `nothing to drain`, `stopped:` or `drain.py:`: drain ended first; report
     that line as it stands.
   - No line before the deadline, or the background command ends first (the
     `already live` refusal of step 2 never reaches the progress file): report
     it, quoting `job-run --status drain-<repo-short>` and the background
     command's output. Never wait a second time.

   Do not poll or wait on the run past this point; its completion wakes you.

Say where to watch it: each build is a herdr pane named
`<repo-short>-<anchor>` (`herdr agent list`), and
`job-run --status drain-<repo-short>` says whether the run is alive.

## Status

`/drain status`, or `/drain` with no flags while `job-run --status
drain-<repo-short>` says `alive`, starts nothing. Read the progress file
(`~/.cache/agent-jobs/drain-<repo-short>/progress`), `herdr agent list` and
`job-run --status drain-<repo-short>`, and print:

- the bundle in flight: the last `bundle started:` line with no
  `bundle ended:` after it, its tickets with titles, its pane, and that pane's
  herdr state;
- each bundle already ended in this run, with its `bundle ended:` outcome.

A run that is not alive has no batch to list: say so, quoting
`job-run --status`.

## On completion

Run `job-run --status drain-<repo-short>`. A line beginning `killed` means the
run died with no record: say so and quote its last progress line. Otherwise
read the background command's own output: a refusal (`already live`, an
argparse error, `drain.py: ...`) is reported verbatim as a start that never
ran, not as a crash. A run that ran ends with drain's summary, in
`~/.cache/agent-jobs/drain-<repo-short>/progress` after the timestamp on each
line, starting at the line `merged:`, `handed to Chris:`, `stopped:` or
`nothing to drain`:

Open the report with every bundle the run worked, one per `bundle started:`
line in the progress file with its `bundle ended:` outcome, then the summary:

- **merged**: each ticket set with its PR and squash sha.
- **handed to Chris**: each ticket set with the reason, as drain printed it.
- **stopped**: the reason, when drain printed one.
