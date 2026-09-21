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
| 871 | (pending) | early | 2026-09-21T14:19:19-04:00 | 2026-09-21T14:20:15-04:00 | 0.9 | raced: launch 670d99c, completion c3a5733 — round-1 fixes pushed while Codex read; verdict discarded, rerun at the gate |
| 871 | #974 | gate-retry | 2026-09-21T14:24:37-04:00 | 2026-09-21T14:25:39-04:00 | 1.0 | collected-after-retry |
| 875+881+949 | (pending) | early | 2026-09-21T14:24:59-04:00 | 2026-09-21T14:26:05-04:00 | 1.1 | raced: launch bd4829e, completion 29d997f — round-1 fixes pushed while Codex read; verdict discarded, rerun at the gate |
| 871 | #974 | second | 2026-09-21T14:27:11-04:00 | 2026-09-21T14:28:01-04:00 | 0.8 | collected |
| 875+881+949 | #977 | gate-retry | 2026-09-21T14:27:57-04:00 | 2026-09-21T14:29:41-04:00 | 1.7 | collected-after-retry |
| 875+881+949 | #977 | second | 2026-09-21T14:31:40-04:00 | 2026-09-21T14:32:54-04:00 | 1.2 | collected |
| 905 | #978 | gate-retry | 2026-09-21T14:33:19-04:00 | 2026-09-21T14:34:55-04:00 | 1.6 | collected-after-retry (early held by controller ruling: four early launches this run had raced) |
| 900 | #979 | gate-retry | 2026-09-21T14:34:30-04:00 | 2026-09-21T14:35:42-04:00 | 1.2 | collected-after-retry (early held by controller ruling) |
| 900 | #979 | second | 2026-09-21T14:38:20-04:00 | 2026-09-21T14:39:05-04:00 | 0.8 | collected |
| 905 | #978 | second | 2026-09-21T14:37:45-04:00 | 2026-09-21T14:39:54-04:00 | 2.2 | collected |
| 880 | #980 | gate-retry | 2026-09-21T14:40:42-04:00 | 2026-09-21T14:41:38-04:00 | 0.9 | collected-after-retry (early held by controller ruling) |
| 903 | #984 | gate-retry | 2026-09-21T14:47:14-04:00 | 2026-09-21T14:48:18-04:00 | 1.1 | collected-after-retry (early held by controller ruling) |
| 915 | #985 | gate-retry | 2026-09-21T14:49:41-04:00 | 2026-09-21T14:51:20-04:00 | 1.7 | collected-after-retry (early held by controller ruling) |
| 915 | #985 | second | 2026-09-21T14:52:48-04:00 | 2026-09-21T14:53:58-04:00 | 1.2 | collected |
| 913 | #986 | gate-retry | 2026-09-21T14:54:28-04:00 | 2026-09-21T14:56:06-04:00 | 1.6 | collected-after-retry (early held by controller ruling) |
| 909+951+963 | #987 | gate-retry | 2026-09-21T14:55:53-04:00 | 2026-09-21T14:57:12-04:00 | 1.3 | collected-after-retry (early held by controller ruling) |
| 919 | #989 | gate-retry | 2026-09-21T14:58:43-04:00 | 2026-09-21T14:59:44-04:00 | 1.0 | collected-after-retry (early held by controller ruling) |
| 909+951+963 | #987 | second | 2026-09-21T14:59:03-04:00 | 2026-09-21T15:00:32-04:00 | 1.5 | collected |
| 913 | #986 | second | 2026-09-21T14:58:59-04:00 | 2026-09-21T15:01:23-04:00 | 2.4 | collected |
| 925 | #992 | gate-retry | 2026-09-21T15:14:29-04:00 | 2026-09-21T15:16:00-04:00 | 1.5 | collected-after-retry (early held by controller ruling) |
| 914 | #995 | gate-retry | 2026-09-21T15:17:36-04:00 | 2026-09-21T15:18:15-04:00 | 0.7 | collected-after-retry (early held by controller ruling) |
| 925 | #992 | second | 2026-09-21T15:17:41-04:00 | 2026-09-21T15:18:58-04:00 | 1.3 | collected |
