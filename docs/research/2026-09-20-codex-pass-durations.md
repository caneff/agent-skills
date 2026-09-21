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

`phase` is where the run launched: `early` (at the worker's "Round 1 out"),
`gate-retry` (at the merge gate, because the early record was refused) or
`second` (#888's conditional re-run). `outcome` is `collected`,
`collected-after-retry` for a `gate-retry` that was collected, or the reason
the gate refused the verdict — `errored`, `raced`, `stale`, `unreadable`, or
`absent` when no record was written at all. A refused run still gets its
row: it spent the same wall clock and the same tokens. An `absent` row is
the one the controller writes from what it knows, the record being the thing
that is missing.

The pair of columns is the measurement #942 exists for. `early` rows that
read `collected` are the passes where the overlap paid; an `early` row
refused `raced` or `stale` followed by a `gate-retry` row is a pass that
cost its wall clock twice. Counting the two tells you whether launching
early is worth it, which is why a `gate-retry` never reports as a plain
`collected`.

## Table

| ticket | PR | phase | launched | completed | duration (min) | outcome |
|---|---|---|---|---|---|---|
| 901 | #965 | early | — | — | — | absent: the controller never launched the pass at round 1 |
| 901 | #965 | gate-retry | 2026-09-21T09:19:19-04:00 | 2026-09-21T09:20:41-04:00 | 1.4 | collected-after-retry |
| 966 | #967 | early | — | — | — | held: the worker announced fix commits with its round-1 report, so an early run would have been refused as raced |
| 966 | #967 | gate-retry | 2026-09-21T11:05:07-04:00 | 2026-09-21T11:06:34-04:00 | 1.5 | collected-after-retry |
| 948+961 | (pending) | early | 2026-09-21T11:11:14-04:00 | 2026-09-21T11:13:06-04:00 | 1.9 | raced: launch 10216f0, completion 659eb87 — the worker pushed round-1 fixes while Codex read; verdict discarded, rerun at the gate |
| 948+961 | #968 | gate-retry | 2026-09-21T11:15:31-04:00 | 2026-09-21T11:17:03-04:00 | 1.5 | collected-after-retry |
| 948+961 | #968 | second | 2026-09-21T11:19:40-04:00 | 2026-09-21T11:22:26-04:00 | 2.8 | collected |
| 970 | (pending) | early | 2026-09-21T14:06:22-04:00 | 2026-09-21T14:07:27-04:00 | 1.1 | raced: launch e535e3d, completion 423b4d3 — round-1 fixes pushed while Codex read; verdict (approve) discarded, rerun at the gate |
| 970 | #972 | gate-retry | 2026-09-21T14:12:59-04:00 | 2026-09-21T14:14:02-04:00 | 1.1 | collected-after-retry |
