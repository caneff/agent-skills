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

`phase` is where the run launched: `gate` (at PR-up, the merge gate) or
`second` (#888's conditional re-run) or `third` (#1028's, only after
a second-pass high was fixed in the round). `outcome` is `collected`, or the
reason the gate refused the verdict — `errored`, `raced`, `stale`,
`unreadable`, or `absent` when no record was written at all. A refused run
still gets its row: it spent the same wall clock and the same tokens. An
`absent` row is the one the controller writes from what it knows, the
record being the thing that is missing.

Retired by #1015: `early` (at the worker's "Round 1 out") and `gate-retry`
(at the merge gate, retrying a refused `early` verdict) were the phases
before 2026-09-22, and `collected-after-retry` (a `gate-retry` row that was
collected) was an outcome alongside them. The trio existed to measure
whether launching at round 1 paid off; it didn't — 4 early launches that
day, 4 raced against the worker's own round-1 fix commits, 0 banked, every
one refused and rerun at the gate, each costing its wall clock twice. Rows
dated before 2026-09-22 keep those phase and outcome names as recorded;
`gate` is what a `gate-retry` row would have been called, and plain
`collected` what a `collected-after-retry` row would have read, had the
rename landed sooner.

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
| 922 | #996 | gate-retry | 2026-09-21T15:20:04-04:00 | 2026-09-21T15:21:03-04:00 | 1.0 | collected-after-retry (early held by controller ruling) |
| 927 | #997 | gate-retry | 2026-09-21T15:20:15-04:00 | 2026-09-21T15:21:11-04:00 | 0.9 | collected-after-retry (early held by controller ruling) |
| 922 | #996 | second | 2026-09-21T15:26:52-04:00 | 2026-09-21T15:28:10-04:00 | 1.3 | collected |
| 928 | #1001 | gate-retry | 2026-09-21T15:32:01-04:00 | 2026-09-21T15:33:16-04:00 | 1.2 | collected-after-retry (early held by controller ruling) |
| 928 | #1001 | second | 2026-09-21T15:34:53-04:00 | 2026-09-21T15:35:43-04:00 | 0.8 | collected |
| 933 | #1002 | gate-retry | 2026-09-21T15:38:39-04:00 | 2026-09-21T15:39:48-04:00 | 1.2 | collected-after-retry (early held by controller ruling) |
| 933 | #1002 | second | 2026-09-21T15:44:44-04:00 | 2026-09-21T15:45:51-04:00 | 1.1 | collected |
| 955 | #1004 | gate-retry | 2026-09-21T15:50:08-04:00 | 2026-09-21T15:51:45-04:00 | 1.6 | collected-after-retry (early held by controller ruling) |
| 955 | #1004 | second | 2026-09-21T15:53:22-04:00 | 2026-09-21T15:55:00-04:00 | 1.6 | collected |
| 936 | #1008 | gate-retry | 2026-09-21T16:08:53-04:00 | 2026-09-21T16:09:24-04:00 | 0.5 | collected-after-retry (early held by controller ruling) |
| 934 | #1007 | gate-retry | 2026-09-21T16:08:24-04:00 | 2026-09-21T16:11:36-04:00 | 3.2 | collected-after-retry (early held by controller ruling) |
| 934 | #1007 | second | 2026-09-21T16:18:02-04:00 | 2026-09-21T16:19:48-04:00 | 1.8 | collected |
| 962 | #1010 | gate-retry | 2026-09-21T16:22:05-04:00 | 2026-09-21T16:23:02-04:00 | 1.0 | collected-after-retry (early held by controller ruling) |
| 962 | #1010 | second | 2026-09-21T16:24:25-04:00 | 2026-09-21T16:25:39-04:00 | 1.2 | collected |
| 923 | #1012 | gate-retry | 2026-09-21T16:45:32-04:00 | 2026-09-21T16:47:01-04:00 | 1.5 | collected-after-retry (early held by controller ruling) |
| 923 | #1012 | second | 2026-09-21T16:52:21-04:00 | 2026-09-21T16:53:59-04:00 | 1.6 | collected |
| 874 | #1018 | gate-retry | 2026-09-21T20:37:44-04:00 | 2026-09-21T20:39:15-04:00 | 1.5 | collected-after-retry (early held by controller ruling) |
| 874 | #1018 | second | 2026-09-21T20:45:46-04:00 | 2026-09-21T20:47:18-04:00 | 1.5 | collected |
| 964 | #1043 | gate | 2026-09-22T06:19:29-04:00 | 2026-09-22T06:20:45-04:00 | 1.3 | collected (launched at PR-up by controller ruling) |
| 964 | #1043 | second | 2026-09-22T06:33:16-04:00 | 2026-09-22T06:34:59-04:00 | 1.7 | collected |
| 973 | #1046 | gate | 2026-09-22T06:49:50-04:00 | 2026-09-22T06:50:18-04:00 | 0.5 | collected (launched at PR-up by controller ruling) |
| 973 | #1046 | second | 2026-09-22T06:52:08-04:00 | 2026-09-22T06:53:05-04:00 | 1.0 | collected |
| 969 | #1048 | gate | 2026-09-22T06:56:42-04:00 | 2026-09-22T06:57:12-04:00 | 0.5 | collected (launched at PR-up by controller ruling) |
| 975 | #1051 | gate | 2026-09-22T07:14:03-04:00 | 2026-09-22T07:15:04-04:00 | 1.0 | collected (launched at PR-up by controller ruling) |
| 971 | #1050 | gate | 2026-09-22T07:10:47-04:00 | 2026-09-22T07:11:38-04:00 | 0.9 | collected (launched at PR-up by controller ruling) |
| 971 | #1050 | second | 2026-09-22T07:17:00-04:00 | 2026-09-22T07:18:23-04:00 | 1.4 | collected |
| 976 | #1053 | gate | 2026-09-22T07:36:17-04:00 | 2026-09-22T07:37:01-04:00 | 0.7 | collected (launched at PR-up by controller ruling) |
| 976 | #1053 | second | 2026-09-22T07:41:13-04:00 | 2026-09-22T07:42:32-04:00 | 1.3 | collected |
| 990 | #1055 | gate | 2026-09-22T07:55:55-04:00 | 2026-09-22T07:57:10-04:00 | 1.3 | collected (launched at PR-up by controller ruling) |
| 993 | #1058 | gate | 2026-09-22T08:09:05-04:00 | 2026-09-22T08:09:35-04:00 | 0.5 | collected (launched at PR-up by controller ruling) |
| 981 | #1057 | gate | 2026-09-22T08:07:17-04:00 | 2026-09-22T08:08:15-04:00 | 1.0 | collected (launched at PR-up by controller ruling) |
| 981 | #1057 | second | 2026-09-22T08:15:47-04:00 | 2026-09-22T08:16:54-04:00 | 1.1 | collected |
| 982 | #1060 | gate | 2026-09-22T08:33:30-04:00 | 2026-09-22T08:34:18-04:00 | 0.8 | collected (launched at PR-up by controller ruling) |
| 982 | #1060 | second | 2026-09-22T08:43:59-04:00 | 2026-09-22T08:45:15-04:00 | 1.3 | collected |
| 998 | #1061 | gate | 2026-09-22T08:42:17-04:00 | 2026-09-22T08:43:18-04:00 | 1.0 | collected (launched at PR-up by controller ruling) |
| 998 | #1061 | second | 2026-09-22T08:49:35-04:00 | 2026-09-22T08:51:04-04:00 | 1.5 | collected |
| 999 | #1063 | gate | 2026-09-22T08:52:18-04:00 | 2026-09-22T08:53:50-04:00 | 1.5 | collected (launched at PR-up by controller ruling) |
| 999 | #1063 | second | 2026-09-22T09:01:44-04:00 | 2026-09-22T09:02:50-04:00 | 1.1 | collected |
| 991 | #1066 | gate | 2026-09-22T09:08:39-04:00 | 2026-09-22T09:09:57-04:00 | 1.3 | collected (launched at PR-up by controller ruling) |
| 991 | #1066 | second | 2026-09-22T09:13:51-04:00 | 2026-09-22T09:15:27-04:00 | 1.6 | collected |
| 1013 | #1067 | gate | 2026-09-22T09:28:07-04:00 | 2026-09-22T09:28:43-04:00 | 0.6 | collected (launched at PR-up by controller ruling) |
| 1006 | #1068 | gate | 2026-09-22T09:33:59-04:00 | 2026-09-22T09:35:45-04:00 | 1.8 | collected (launched at PR-up by controller ruling) |
| 1006 | #1068 | second | 2026-09-22T09:44:44-04:00 | 2026-09-22T09:47:07-04:00 | 2.4 | collected |
| 1015 | #1070 | gate | 2026-09-22T09:49:35-04:00 | 2026-09-22T09:50:34-04:00 | 1.0 | collected |
| 1016 | #1071 | gate | 2026-09-22T09:59:59-04:00 | 2026-09-22T10:00:50-04:00 | 0.9 | collected |
| 1016 | #1071 | second | 2026-09-22T10:09:17-04:00 | 2026-09-22T10:10:13-04:00 | 0.9 | collected |
| 1017 | #1072 | gate | 2026-09-22T10:12:59-04:00 | 2026-09-22T10:13:38-04:00 | 0.7 | collected |
| 1017 | #1072 | second | 2026-09-22T10:24:22-04:00 | 2026-09-22T10:25:06-04:00 | 0.7 | collected |
| 1011 | #1073 | gate | 2026-09-22T10:26:19-04:00 | 2026-09-22T10:27:42-04:00 | 1.4 | collected |
| 1025 | #1077 | gate | 2026-09-22T11:05:25-04:00 | 2026-09-22T11:06:54-04:00 | 1.5 | collected |
| 1026 | #1078 | gate | 2026-09-22T11:07:50-04:00 | 2026-09-22T11:08:56-04:00 | 1.1 | collected |
| 1028 | #1080 | gate | 2026-09-22T11:44:30-04:00 | 2026-09-22T11:45:33-04:00 | 1.1 | collected |
| 1028 | #1080 | second | 2026-09-22T11:54:57-04:00 | 2026-09-22T11:56:10-04:00 | 1.2 | collected |
| 1029 | #1083 | gate | 2026-09-22T12:07:05-04:00 | 2026-09-22T12:08:48-04:00 | 1.7 | collected |
| 1075 | #1081 | gate | 2026-09-22T11:56:25-04:00 | 2026-09-22T11:57:44-04:00 | 1.3 | collected |
| 1075 | #1081 | second | 2026-09-22T12:06:24-04:00 | 2026-09-22T12:07:51-04:00 | 1.5 | collected |
| 1075 | #1081 | third | 2026-09-22T12:18:09-04:00 | 2026-09-22T12:19:51-04:00 | 1.7 | collected |
| 1029 | #1083 | second | 2026-09-22T12:19:29-04:00 | 2026-09-22T12:20:52-04:00 | 1.4 | collected |
| 1040 | #1088 | gate | 2026-09-22T12:45:19-04:00 | 2026-09-22T12:46:04-04:00 | 0.8 | collected |
| 1030 | #1090 | gate | 2026-09-22T13:05:06-04:00 | 2026-09-22T13:06:34-04:00 | 1.5 | collected |
| 1044 | #1091 | gate | 2026-09-22T13:08:59-04:00 | 2026-09-22T13:10:43-04:00 | 1.7 | collected |
| 1042 | #1089 | gate | 2026-09-22T13:01:09-04:00 | 2026-09-22T13:02:35-04:00 | 1.4 | collected |
| 1042 | #1089 | second | 2026-09-22T13:12:30-04:00 | 2026-09-22T13:14:07-04:00 | 1.6 | collected |
| 1030 | #1090 | second | 2026-09-22T13:24:09-04:00 | 2026-09-22T13:25:55-04:00 | 1.8 | collected |
| 1033 | #1094 | gate | 2026-09-22T14:13:18-04:00 | 2026-09-22T14:14:26-04:00 | 1.1 | collected |
| 1033 | #1094 | second | 2026-09-22T14:24:42-04:00 | 2026-09-22T14:26:28-04:00 | 1.8 | collected |
| 1098 | #1099 | gate | 2026-09-22T19:21:37-04:00 | 2026-09-22T19:22:59-04:00 | 1.4 | collected |
| 1098 | #1099 | second | 2026-09-22T19:32:51-04:00 | 2026-09-22T19:34:51-04:00 | 2.0 | collected |
| 1098 | #1099 | third | 2026-09-22T19:41:53-04:00 | 2026-09-22T19:43:08-04:00 | 1.3 | collected |
| twitch-rules-scroller#345 | twitch-rules-scroller#375 | gate | 2026-09-22T12:26:54-04:00 | 2026-09-22T12:28:20-04:00 | 1.4 | collected (row backfilled by the adopting controller; the dispatching controller died before writing it) |
| twitch-rules-scroller#345 | twitch-rules-scroller#375 | second | 2026-09-22T19:46:43-04:00 | 2026-09-22T19:48:32-04:00 | 1.8 | collected |
| twitch-rules-scroller#345 | twitch-rules-scroller#375 | third | 2026-09-22T19:52:19-04:00 | 2026-09-22T19:54:13-04:00 | 1.9 | collected |
| 1049 | #1102 | gate | 2026-09-23T12:39:06-04:00 | 2026-09-23T12:39:44-04:00 | 0.6 | collected |
| 1047 | #1103 | gate | 2026-09-23T12:39:07-04:00 | 2026-09-23T12:39:41-04:00 | 0.6 | collected |
| 1000 | #1105 | gate | 2026-09-23T12:42:07-04:00 | 2026-09-23T12:44:12-04:00 | 2.1 | collected |
| 1097 | #1111 | gate | 2026-09-23T12:47:41-04:00 | 2026-09-23T12:49:10-04:00 | 1.5 | collected |
| 1045 | #1108 | gate | 2026-09-23T12:50:52-04:00 | 2026-09-23T12:52:12-04:00 | 1.3 | collected |
| 1059 | #1119 | gate | 2026-09-23T12:55:28-04:00 | 2026-09-23T12:55:55-04:00 | 0.5 | collected |
| 1056 | #1116 | gate | 2026-09-23T12:51:58-04:00 | 2026-09-23T12:54:22-04:00 | 2.4 | collected |
| 1056 | #1116 | second | 2026-09-23T12:59:36-04:00 | 2026-09-23T13:00:48-04:00 | 1.2 | collected |
| 1087 | #1121 | gate | 2026-09-23T13:04:52-04:00 | 2026-09-23T13:05:30-04:00 | 0.6 | collected |
| 1085 | #1123 | gate | 2026-09-23T13:06:09-04:00 | 2026-09-23T13:07:25-04:00 | 1.3 | collected |
| 1107 | #1127 | gate | 2026-09-23T13:10:26-04:00 | 2026-09-23T13:11:42-04:00 | 1.3 | collected |
| 1107 | #1127 | second | 2026-09-23T13:18:25-04:00 | 2026-09-23T13:19:25-04:00 | 1.0 | collected |
| 1096 | #1129 | gate | 2026-09-23T13:20:27-04:00 | 2026-09-23T13:21:58-04:00 | 1.5 | collected |
| 1096 | #1129 | second | 2026-09-23T13:23:18-04:00 | 2026-09-23T13:24:45-04:00 | 1.5 | collected |
| 1076 | #1131 | gate | 2026-09-23T13:26:10-04:00 | 2026-09-23T13:26:35-04:00 | 0.4 | collected |
| 1054 | #1133 | gate | 2026-09-23T13:28:23-04:00 | 2026-09-23T13:28:53-04:00 | 0.5 | collected |
| 1086 | #1135 | gate | 2026-09-23T13:30:28-04:00 | 2026-09-23T13:31:15-04:00 | 0.8 | collected |
| 1086 | #1135 | second | 2026-09-23T13:32:28-04:00 | 2026-09-23T13:33:22-04:00 | 0.9 | collected |
| 1084 | #1136 | gate | 2026-09-23T13:37:12-04:00 | 2026-09-23T13:38:31-04:00 | 1.3 | collected |
| 1093 | #1138 | gate | 2026-09-23T13:39:25-04:00 | 2026-09-23T13:40:30-04:00 | 1.1 | collected |
| 1052 | #1140 | gate | 2026-09-23T13:48:22-04:00 | 2026-09-23T13:49:23-04:00 | 1.0 | collected |
| 1139 | #1141 | gate | 2026-09-23T13:52:00-04:00 | 2026-09-23T13:52:46-04:00 | 0.8 | collected |
