# Codex review yield by PR shape (2026-10-03)

Question: among the heavy-tier PRs that ran the Codex adversarial pass, what
separates the ones where Codex found something the three Claude axes missed
from the ones where it found nothing? Needed to decide which PRs keep the
pass once Codex quota is rationed (weekly window, plan `plus`, 66 % used
with six days left on 2026-10-03).

Source: every row of `2026-09-14-codex-review-trial.md` (187 data rows),
joined to `gh pr view <PR> --json additions,deletions,changedFiles,files,title`
for each PR. All 187 fetched. Finding kinds classified by hand from the
free-text column, so the (a)/(d) boundary is approximate.

## Counts

| codex-only confirmed | rows | share |
|---|---|---|
| 0 | 90 | 48 % |
| 1 | 43 | 23 % |
| 2+ | 54 | 29 % |

Four rows carry a count ≥ 1 but read "approve, no material findings"; the
number and the prose disagree.

## Finding kinds, 2+ group (54 rows, 149 findings)

| kind | count | share |
|---|---|---|
| (a) enforcing code: hook, gate, guard, check, merge rule | 48 | 32 % |
| (b) test does not witness its claim | 8 | 5 % |
| (c) doc/prose inconsistency | 6 | 4 % |
| (d) ordinary-code edge case / data handling | 84 | 56 % |
| (e) style/nit | 0 | 0 % |
| (f) other | 3 | 2 % |

(a) is 47 of 107 agent-skills findings and 1 of 42 in sudokumaker/twitch
rows; those repos yield almost entirely (d). Typical (a) failure: a guard
that silently passes, or a refusal that was never applied.

## Shape by group

| measure | zero (n=90) | 1 (n=43) | 2+ (n=54) |
|---|---|---|---|
| median additions+deletions | 108 | 162 | 403 |
| median changedFiles | 3 | 4 | 5.5 |
| median non-test, non-md churn | 19 | 30 | 170 |
| touches any code/hook/settings path | 93 % | 100 % | 100 % |
| only `.md` | 7 % | 0 % | 0 % |
| path contains hook/guard/gate | 8 % | 7 % | 17 % |
| title/ticket matches hook\|gate\|guard\|check\|merge\|review | 33 % | 30 % | 31 % |

## Yield by total churn

| additions+deletions | rows | ≥1 finding | 2+ findings |
|---|---|---|---|
| < 100 | 58 | 26 % | 5 % |
| 100–299 | 69 | 52 % | 20 % |
| 300–699 | 39 | 67 % | 56 % |
| ≥ 700 | 21 | 95 % | 71 % |

The size effect holds within time quartiles: in the last quartile (47 rows,
mostly small PRs) 4 of 32 PRs under 200 lines had a finding against 5 of 14
at 200 or more.

## What predicts a codex-only finding

1. **PR size.** Strongest by far; see the churn table. Non-test, non-md
   churn separates best (median 19 vs 170).
2. **Touches executable code at all.** 0 of 6 md-only PRs had a finding;
   54 % of the 181 code-touching PRs did.
3. **Not predictive:** keyword match on title/ticket (50 % vs 53 %), path
   containing hook/guard/gate (weak), tier (constant — every row is heavy).

## What the data cannot tell

- No baseline of skipped PRs: rows exist only for PRs that ran the pass.
- "Claude missed it" is as recorded by the controller that launched the run.
- Churn is confounded with run count: large PRs got 2–4 Codex runs, so more
  chances to find something. A pre-launch rule cannot see run count.
- `gh pr view --json files` may cap the file list; path shares are lower
  bounds.

## Rebuild

Parser used for the row split (the join and classification were done
interactively in the same session and are not scripted):

```python
import re, json, collections
L = [l for l in open('docs/research/2026-09-14-codex-review-trial.md') if l.startswith('|')]
rows = []
for l in L[2:]:
    c = [x.strip() for x in l.strip().strip('|').split(' | ')]
    if len(c) < 6:
        c = [x.strip() for x in re.split(r'(?<!\\)\|', l.strip().strip('|'))]
    rows.append(c)
def n(r):
    try: return int(r[2])
    except Exception: return None
print(collections.Counter(n(r) for r in rows))
```

Per-PR shape: `gh pr view <PR> --repo caneff/<repo> --json additions,deletions,changedFiles,files,title`,
repo taken from the Ticket column (`agent-skills` when bare).
