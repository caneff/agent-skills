# Review ledger baseline (2026-09-30)

First run of `review_ledger.py` over every past review on this machine (#1271, slice 7 of
#1262). It reports what the data holds. It judges no review type: which to keep or cut is
Chris's call.

## Where the data lives, and how to regenerate it

The 2413-row ledger is **not committed**. Chris ruled (relayed by the burn controller
`skills-burn-ctl`) that raw rows stay out of the repo, because the rows carry finding titles
and file paths from private repos and this repo is public. This replaces the ticket's
"committed snapshot / reproducible from the snapshot" criterion: the note commits the report and
aggregates, and the snapshot is regenerated from the cache.

| What | Where |
|---|---|
| Ledger (harvest rows plus 62 rows `append` had written) | `~/.cache/agent-reviews/ledger-baseline-2026-09-30.jsonl` |
| Review file (label mappings, matches, unjoined dispositions) | `~/.cache/agent-reviews/ledger-baseline-2026-09-30.review.md` |

The live `~/.cache/agent-reviews/ledger.jsonl` was not touched. The harvest ran on a copy of it,
so the 62 live `append` rows are in the baseline and the regenerated copy below reproduces them
only if they are copied in first.

```
cp ~/.cache/agent-reviews/ledger.jsonl /path/to/ledger.jsonl    # carries the 62 append rows
python3 docs/research/review_ledger.py harvest --ledger /path/to/ledger.jsonl --review-file /path/to/ledger.review.md
python3 docs/research/review_ledger.py report  --ledger /path/to/ledger.jsonl
```

A harvest replaces every earlier harvest row, so re-running it gives the same harvest rows as
long as the cache and transcripts are unchanged. They were read 2026-09-30; reviews written
since add rows. Run on the real cache (`~/.cache/agent-reviews`) and transcripts
(`~/.claude/projects`): 5 seconds, one process, `ulimit -v` 4 GB, exit 0. Its summary line:
2413 rows, 2 unmapped values, 62 overlap matches, 20 sidecars not harvested, 27 skipped lines or
duplicates, 104 transcripts not attributed.

## Per-type table (`report`, default weights, `--split 1/k`, no price table)

| type | rows | findings | value | unique share | leftover rate | dispute rate | unknown outcomes | unknown-findings rows | unknown-cost rows | refused | skipped | clean passes | tokens | wall clock | red rate | unknown mutations |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| standards | 523 | 1732 | 1265.00 | 97.7% | 17.0% | 18.4% | 18 | 108 | 8 | 0 | n/a | n/a | 172,575,023 | 52875s | n/a | n/a |
| spec | 522 | 973 | 627.33 | 96.1% | 10.2% | 31.4% | 12 | 139 | 8 | 0 | n/a | n/a | 143,208,114 | 52474s | n/a | n/a |
| correctness | 506 | 1437 | 1413.00 | 97.1% | 7.8% | 12.4% | 22 | 108 | 11 | 0 | n/a | n/a | 341,199,008 | 135033s | n/a | n/a |
| over-engineering | 74 | 146 | 76.00 | 100.0% | 24.8% | 22.8% | 1 | 0 | 0 | 0 | n/a | n/a | inside standards | inside standards | n/a | n/a |
| verification | 492 | 37 | 14.00 | 100.0% | 16.7% | 0.0% | 25 | 472 | 3 | 0 | n/a | n/a | 195,544,518 | 70334s | n/a | n/a |
| witness-mutation | 22 | n/a | n/a | n/a | n/a | n/a | n/a | 0 | 0 | 0 | n/a | n/a | n/a | 31s | 90.9% | 0 |
| call-site-mutation | 6 | n/a | n/a | n/a | n/a | n/a | n/a | 0 | 0 | 0 | n/a | n/a | n/a | 8s | 50.0% | 0 |
| worker-mutation | 11 | n/a | n/a | n/a | n/a | n/a | n/a | 0 | 0 | 0 | n/a | n/a | n/a | 16s | 100.0% | 0 |
| codex-gate | 218 | 137 | 17.00 | 100.0% | 41.7% | 8.3% | 125 | 0 | 0 | 39 | 0 | 77 | n/a | 13889s | n/a | n/a |
| codex-second | 70 | 74 | 3.00 | 100.0% | 42.9% | 42.9% | 67 | 0 | 0 | 0 | 0 | 10 | n/a | 6112s | n/a | n/a |
| codex-third | 8 | 11 | 0.00 | 100.0% | 100.0% | 0.0% | 3 | 0 | 0 | 0 | 0 | 2 | n/a | 782s | n/a | n/a |

Two columns are dropped from the table for width and are `n/a` on every row: `unweighted` is 0
on every reviewer and Codex row, and `usage %`, `dollars` and `value per dollar` are `n/a`
because no `--prices` file was given (`report` prints "No price table: dollars and value per
dollar are n/a, not zero"). Value is the report's severity-weighted sum over findings with a
known severity, not a judgement.

Read the rates with the unknowns beside them: each rate is over findings whose outcome is
known, so a type with many unknown outcomes has a rate over fewer findings (codex-gate: 137
findings, 125 unknown outcomes).

## `unknown` counts by reason

Counted over the baseline ledger; nothing is folded into an average or a rate. Ticket numbers,
repo names and finding ids in the reasons are replaced by `<…>`. The count matches `report`'s
`unknown outcomes` and `unknown-findings rows` columns for each type.

```python
# rows = [json.loads(l) for l in open(ledger)]
for r in rows:
    for f, s in r['cost'].items():                      # tokens, wall_clock, usage_delta
        if isinstance(s, dict) and s.get('status') == 'unknown': key(r['type'], 'cost.' + f, s['reason'])
    fs = r['status']['fields'].get('findings', {})
    if fs.get('status') == 'unknown': key(r['type'], 'findings', fs['reason'])
    for x in r['findings'] or []:
        if x['outcome_status']['status'] == 'unknown': key(r['type'], 'outcome', x['outcome_status']['reason'])
```

| type | field | reason | count |
|---|---|---|---|
| standards | findings | no findings sidecar for this run: nothing found, or nothing written | 106 |
| standards | findings | sidecar is empty: nothing found, or nothing written | 2 |
| standards | outcome | no dispositions file for the ticket | 10 |
| standards | outcome | no disposition line for the finding id | 8 |
| standards | cost.tokens, cost.wall_clock | no transcript attributed to this row | 8 each |
| spec | findings | no findings sidecar for this run | 106 |
| spec | findings | sidecar is empty | 32 |
| spec | findings | 1 unreadable line in the sidecar | 1 |
| spec | outcome | no dispositions file for the ticket | 7 |
| spec | outcome | no disposition line for the finding id | 4 |
| spec | outcome | unmapped outcome `open` | 1 |
| spec | cost.tokens, cost.wall_clock | no transcript attributed to this row | 8 each |
| correctness | findings | no findings sidecar for this run | 89 |
| correctness | findings | sidecar is empty | 19 |
| correctness | outcome | no disposition line for the finding id | 12 |
| correctness | outcome | no dispositions file for the ticket | 9 |
| correctness | outcome | unmapped outcome `contested` | 1 |
| correctness | cost.tokens, cost.wall_clock | no transcript attributed to this row | 8 each |
| correctness | cost.tokens, cost.wall_clock | two sidecar rows share one transcript; it cannot be split | 2 each |
| correctness | cost.tokens, cost.wall_clock | 2 unreadable lines in the transcript | 1 each |
| over-engineering | outcome | no disposition line for the finding id | 1 |
| verification | findings | no findings sidecar for this run | 467 |
| verification | findings | sidecar is empty | 5 |
| verification | outcome | no disposition line for the finding id | 24 |
| verification | outcome | no dispositions file for the ticket | 1 |
| verification | cost.tokens, cost.wall_clock | no transcript attributed to this row | 2 each |
| verification | cost.tokens, cost.wall_clock | 2 unreadable lines in the transcript | 1 each |
| codex-gate | outcome | no dispositions line `codex-gate-<k>` or `-<sev><k>` | 125 |
| codex-gate | cost.usage_delta | before reading missing; after reading missing | 218 |
| codex-second | outcome | no dispositions line `codex-second-<k>` or `-<sev><k>` | 67 |
| codex-second | cost.usage_delta | before reading missing; after reading missing | 70 |
| codex-third | outcome | no dispositions line `codex-third-<k>` or `-<sev><k>` | 3 |
| codex-third | cost.usage_delta | before reading missing; after reading missing | 8 |

"No findings sidecar" and "sidecar is empty" both read "nothing found, or nothing written": the
harvest cannot tell a clean review from one whose sidecar was never written, so those rows are
unknown, not zero-finding. Verification is 467 of 492 rows in that state because verification
rows come from transcripts and its findings sidecar is written only when the pass finds
something.

**Codex outcomes are mostly unknown, and why.** Of 222 Codex findings read, 195 have no known
outcome (125 + 67 + 3). The only joinable source is the dispositions sidecar, where the controller
writes a `codex-<phase>-<label>` line by rule for a `leftover` alone (`implement/SKILL.md` § The
merge step 3). Fixed and disputed Codex findings live in the PR body as prose, which the harvest
does not parse. So the Codex value, leftover-rate and dispute-rate cells are over 27 findings
and skew to leftover; read them as a floor on unknown, not as a rate. Detail:
`2026-09-30-codex-outcome-source.md`. Fixing the harvest for this is not part of this baseline.
Codex usage change is unknown on every one of the 296 Codex rows (table above): backfilled rows
have no before or after reading.

## Label mappings applied (from the review file)

| Mapping | Rows |
|---|---|
| phase `gate-retry` read as `codex-gate` | 30 |
| `verify` in the axis filename read as `verification` | 25 |
| outcome `partial` read as fixed plus partial | 5 |
| `fixed-partial` read as fixed plus partial | 2 |
| `not-fixed` read as leftover | 2 |
| `not_fixed` read as leftover | 1 |
| Codex label `M<k>` read as the k-th finding of that severity | 1 |

Unmapped, so `unknown`: outcome `contested` (1) and `open` (1). Also listed, not harvested: 20
sidecars whose names match no harvested pattern (6 retired `early` Codex records, plus
differently-named round, spec and re-run sidecars); 27 skipped lines or
duplicates, where duplicate ids keep both findings and join them to one disposition; 104
transcripts that could not be attributed to a row.

## Spot-check of the overlap matcher

The match-review file lists the 62 findings the harvest marked `shared` across two reviewers on
one ticket (rule: same file, title word sets overlapping by Jaccard at least 0.5, matches chaining
transitively). I read **all 62** (sample size 62, the whole list), judging by the two titles and
the file; I did not open the review reports behind them.

- **False matches: 0 of 62** (two reviewers naming a different defect under one label).
- **Borderline: 1**, in a private repo, not quoted: the two titles agree on the defect and
  differ in one detail.
- Of the 62, 35 are in public repos and 27 in private ones. Public examples of a true match:
  `implement/SKILL.md` ticket #888 (spec P2 and correctness C2: the skip branch jumps past the
  Codex trial-row paragraph); `burndown/references/run-file.md` ticket #1084, where all three
  axes flagged one stale doc claim and the matcher chained them.

What this does not measure: **false non-matches**, two reviewers raising one defect under titles
the matcher scored below 0.5. At most 4% of findings per type are shared (`unique share` 96 to 100%),
which is low enough that misses are plausible, but no sample here tests it. The `unique share`
column is an upper bound until that is checked.

## What the data cannot yet say

- **Mutations before slice 6 (#1270).** Mutation rows exist only from `append`: 39 rows (22
  witness, 6 call-site, 11 worker). A review run earlier than that change has no mutation row,
  and no type's red rate covers it. `report` leaves a type with no rows out rather than showing
  zero.
- **Codex usage change.** `unknown` on all 296 Codex rows; none of the backfilled passes has a
  before or after reading. Only passes the controller appends from now on carry one.
- **Escapes.** The ledger records a review's findings and their outcomes; it has no record of a
  defect that shipped past a review and was found later, so no type's miss rate can be computed.
- **Dollars.** No price table was supplied, so dollars and value per dollar are `n/a`. Tokens
  and wall clock are the cost figures here.
- **Cost on 30 reviewer rows.** `unknown-cost rows` (8 + 8 + 11 + 3) have no readable
  transcript; they are in neither the token nor the wall-clock sums.
