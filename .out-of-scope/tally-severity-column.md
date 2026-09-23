# A severity column in `tally_review_axes.py --sidecars`

The sidecar tally reports raised, fixed, disputed, filed and undisposed findings per repo and axis. It does not split them by severity (`hard` versus `judgement`).

## Why this is out of scope

The tally exists to answer one question: whether each review axis earns its cost. Severity does not change that answer. The ticket asking for the column (#864) was a reviewer's suggestion, and no one has asked the tally a severity question since. Anyone who needs it once can run a `jq` pass over the sidecar files, which carry the field.

## Prior requests

- #864 — "tally_review_axes.py --sidecars: surface severity (hard vs judgement) in the per-axis table"
