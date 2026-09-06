# Findings Log + Summary Format

For an audit that finds many things, do **not**
render every finding as its own HTML card. A hundred cards is slow to build, and
a later grill has to parse the findings back out of HTML to act on them. Write
two artifacts instead:

- **`findings.jsonl`** — the full record, one finding per line, machine-read. The
  grill reads this, not the HTML.
- **`report.html`** — a grouped summary for a human to eyeball: the verdict, the
  counts, the findings grouped by kind, and the few standouts. No per-finding
  cards.

Both land in the skill's output folder side by side
(`<tmpdir>/<skill>-<timestamp>/`).

## The log — `findings.jsonl`

One JSON object per line (JSONL), one line per finding, in scan order. One home
for the facts: the summary is drawn from this file, never the reverse. Fields:

- `bucket` (required) — the skill's verdict bucket, a small closed set the
  skill names (e.g. `cut` / `rewrite` / `keep`, or `cut` / `keep` /
  `load-bearing`).
- `file` (required) — repo-relative path.
- `line` (required) — integer line number the finding sits on.
- `category` (required) — the smell/reason slug from the skill's own vocabulary
  (e.g. `duplicate-coverage`, `name-mismatch`, `tautology`, `restatement`,
  `banner`, `citation`, `interaction-only`). This is the axis the summary groups
  on, so keep it a small closed set the skill names.
- `summary` (required) — one line: what the finding is.
- `failure` (required for `cut`/`rewrite`, and for a `keep`) — the **concrete**
  failure the finding names: "cannot fail when X breaks" for a cut, or the
  concrete mistake a reader makes once a keeper is gone. Never a bare label.
- `before` / `after` — a `rewrite`'s test as it stands and its corrected form; a
  comment cut's text and its replacement (`"— gone —"` for a whole delete, the
  tightened clause for a salvage). Omit for a plain keep.
- `owner` (optional) — for a duplicate-coverage cut, the `file:line` of the
  stronger test that already owns the behavior.
- `extra` (optional) — a flat object for signal specific to the auditing
  skill, beyond the six fields every audit shares. Only the six above
  (`bucket`, `file`, `line`, `category`, `summary`, `failure`) are fixed
  across all audits; `extra` is where a skill puts its own axis without
  bending the shared schema to fit it. Examples: a tool-confidence percentage
  carried through unmodified (`{"confidence": 60}`), a suggested replacement
  value (`{"suggested_type": "Sequence[int]", "severity": "blanket"}`), a
  ground-truth citation (`{"should_be": "Order", "source": "CONTEXT.md"}`), a
  clone-size metric (`{"clone_tokens": 42}`), or a mutation-test outcome
  (`{"mutant": "flip <", "killed": false, "survived": true}`). Omit entirely
  when a skill has nothing extra to say.

```jsonl
{"bucket":"cut","file":"layers/group_sum_test.py","line":111,"category":"duplicate-coverage","summary":"count=3 example subsumed by the arity hypothesis test","failure":"cannot fail for any reason line 261 doesn't already catch faster","owner":"layers/group_sum_test.py:261"}
{"bucket":"rewrite","file":"cell_geometry_test.py","line":96,"category":"tautology","summary":"membership-not-bounds test recomputes step on a solid board","failure":"a membership != bounds regression passes","before":"geo over a full size-9 grid","after":"geo = _holed_geometry(); assert step returns None into the hole"}
{"bucket":"keep","file":"verdict_test.py","line":33,"category":"differential-helper","summary":"assert_layer_newly_breaks proves smaller != broke AND full == broke","failure":"~15 layer tests could pass by breaking for an unrelated reason"}
```

## The summary — `report.html`

A single self-contained visual-teach page. Use `HTML-REPORT.md` (in this
repo's `all-audits/harness/`) for the scaffold and asset delivery — same
`vt-*` spine, same copy-assets-alongside step. The body differs: grouped
overview, not cards.

- **Header** — `vt-kicker` skill label, `<h1>` repo, `vt-lede` one-line verdict,
  then a `vt-metabar` with the count (`N judged · C cut · R rewrite · K kept`).
- **Grouped overview** — for each bucket, a compact per-`category` count with a
  one-line gloss, and, when the audit is large, a per-file roll-up (top files by
  finding count). Tables or lists, not cards. This is where a reader sees the
  shape — "80 restatement, 21 banner, 11 citation" — without scrolling a hundred
  cards.
- **Standouts** — a short `vt-callout` naming the few highest-value finds by
  `file:line`, not every keep — the ones that would mislead a naive read of
  the tool output alone. A handful.
- **Full record** — one line pointing at `findings.jsonl` beside the page for the
  complete list.

Do not list every finding here. The log is the list; the summary is the map.

## The fan-out return struct

Every audit subagent `all-audits` spawns returns the same shape — this is
what the orchestrator collects into the index, regardless of which audit ran:

- `audit` — the skill name.
- `headline` — the one-line verdict from the report.
- `count` — how many findings.
- `report_path` — absolute path to the report's `.html` file. For an audit
  that writes `findings.jsonl`, this is the grouped summary page above, not a
  card-per-finding report. Inside a sweep, this whole struct — `report_path`,
  `count`, `headline` — is what you write to the manifest path `driver.py`'s
  prompt names (see [`AUDIT-RUN.md`](AUDIT-RUN.md#the-manifest-559)); the
  driver reads that file, it does not scan your process's stdout.
- `log_path` — absolute path to `findings.jsonl`, for any audit that writes
  one. Omit for an audit that renders a full card-per-finding HTML report
  instead.
- `findings` — a short list, one entry per finding: `{ target, note }`, where
  `target` is the repo-relative file path the finding is about and `note` is
  a one-line summary.

See `all-audits/SKILL.md` for how the orchestrator collects these into
`index.html`.
