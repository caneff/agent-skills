# Codex adversarial-review pass durations (#942)

One row per `codex-companion.mjs adversarial-review` run the `/implement`
lane launches, written by the controller at the merge gate — collected runs
and discarded ones alike (`implement/SKILL.md` § The merge step 3). The
numbers come from the run's own record file,
`~/.cache/agent-reviews/<repo>/codex-adversarial-<n>.json`, which stamps
`started` and `completed` around the node call itself; nothing here is read
off a shell's scrollback or an output file's mtime.

Why the file exists: five passes ran on 2026-09-20 and not one of them was
timed, so the argument about where the pass belongs in the lane — #942's
whole subject — had output-file timestamps and impressions to go on. The
five are not reconstructed here; a bound taken from an mtime is not a
measurement, and writing it into a table would launder it into one. The
table starts at the first pass run under #942's shape.

`pass` is `first` or `second` (#888's conditional re-run). `outcome` is
`collected`, or the reason the gate refused the verdict — `errored`,
`raced`, `stale`, `unreadable`, or `absent` when no record was written at
all — in which case the row still counts, because a refused run spent the
same wall clock and the same tokens. An `absent` row is the one the
controller writes from what it knows, the record being the thing that is
missing.

## Table

| ticket | PR | pass | launched | completed | duration (min) | outcome |
|---|---|---|---|---|---|---|
