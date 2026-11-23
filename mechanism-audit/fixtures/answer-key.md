# Answer key — `fixtures/sample/`

Three rules in `AGENTS.md`, one verdict each (`fixtures/findings.jsonl`):

| line | rule | verdict | why |
|---|---|---|---|
| 3 | every run must record its duration | `gap` / `no-mechanism` | `ledger.append` takes an opaque row; nothing measures time |
| 5 | an absent `--blocked-by` falls back to the ticket body | `gap` / `never-reached` | `blocked_by_from_body` exists, `dispatch` never calls it |
| 7 | the push guard refuses a foreign push | `carried` / `has-mechanism` | `hooks.json` wires `push_guard.py`, which exits 1 on a foreign owner |

Every row lists the places searched. A row without that list is invalid.
