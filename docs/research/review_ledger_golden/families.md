| type | rows | findings | value | unique share | leftover rate | dispute rate | unknown outcomes | unweighted | unknown-findings rows | unknown-cost rows | refused | skipped | clean passes | audited PRs | usage % | unknown usage | tokens | wall clock | dollars | value per dollar | red rate | unknown mutations |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| standards | 3 | 12 | 20.00 | 100.0% | 0.0% | 0.0% | 0 | 0 | 0 | 1 | 0 | n/a | n/a | n/a | n/a | n/a | 715,836 | 148s | n/a | n/a | n/a | n/a |
| correctness | 1 | 4 | 4.00 | 100.0% | 0.0% | 0.0% | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | n/a | n/a | 1,240,159 | 521s | n/a | n/a | n/a | n/a |
| over-engineering | 1 | 1 | 1.00 | 100.0% | 0.0% | 0.0% | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | n/a | n/a | inside standards | inside standards | inside standards | n/a | n/a | n/a |
| witness-mutation | 3 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0 | 0 | 0 | n/a | n/a | n/a | n/a | n/a | n/a | 3s | n/a | n/a | 50.0% | 1 |
| call-site-mutation | 3 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0 | 0 | 0 | n/a | n/a | n/a | n/a | n/a | n/a | 5s | n/a | n/a | 50.0% | 1 |
| codex-gate | 6 | 4 | 12.00 | 100.0% | 0.0% | 0.0% | 0 | 0 | 0 | 0 | 1 | 2 | 1 | n/a | 7 | 0 | n/a | 370s | n/a | n/a | n/a | n/a |
| codex-second | 1 | 1 | 0.00 | 100.0% | n/a | n/a | 1 | 0 | 0 | 0 | 0 | 0 | 0 | n/a | 2 | 0 | n/a | 65s | n/a | n/a | n/a | n/a |
| codex-audit | 1 | 1 | 3.00 | 100.0% | 0.0% | 0.0% | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 3 | 0 | n/a | 131s | n/a | n/a | n/a | n/a |
| worker-mutation | 3 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0 | 0 | 0 | n/a | n/a | n/a | n/a | n/a | n/a | 6s | n/a | n/a | 50.0% | 1 |

Reviews before #1270 carry no mutation data: a review run earlier has no mutation rows, so a mutation type's counts start at that change and a type with no rows is left out, not shown as zero.
No price table: dollars and value per dollar are n/a, not zero (pass --prices).
