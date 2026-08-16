# Answer key

`npx --yes jscpd --reporters json --output /tmp/jscpd-out --min-tokens 20
duplication/fixtures` reports one clone pair between `sample_a.py`'s
`validate_order` and `sample_b.py`'s `validate_shipment` — a copy-pasted
validation block. This is the mechanical, pass-one hit; `parse_jscpd` must
turn it into exactly one findings row, `bucket: consolidate`.

Captured raw jscpd output (this repo, jscpd via `npx`, relevant fields):

```json
{
  "duplicates": [
    {
      "firstFile": { "name": "sample_a.py", "start": 4, "end": 19 },
      "secondFile": { "name": "sample_b.py", "start": 6, "end": 21 },
      "format": "python",
      "lines": 16,
      "tokens": 92
    }
  ]
}
```

Running `python3 duplication/audit.py` over the full captured JSON
(`jscpd-report.json`) produces:

```json
{"bucket": "consolidate", "file": "sample_a.py", "line": 4, "category": "token-clone", "summary": "sample_a.py:4 duplicates sample_b.py:6 (92 tokens)", "failure": "two copies drift; a fix to one at sample_a.py:4 silently skips the other at sample_b.py:6", "extra": {"clone_tokens": 92}, "owner": "sample_b.py:6"}
```

## Expected findings table

| # | Source | Kind | Bucket | Reason |
|---|--------|------|--------|--------|
| 1 | `sample_a.py:4` `validate_order` / `sample_b.py:6` `validate_shipment` | token-clone (jscpd) | **consolidate** | Byte-for-byte identical validation logic pasted into a second function name. A fix to one (e.g. tightening the price check) silently skips the other. Pass-two judgment should keep this `consolidate` — nothing about it looks intentional. |
| 2 | `sample_a.py:13` `user_age_years` / `sample_b.py:19` `user_age_in_years` | semantic-duplicate (pass two, not jscpd) | **consolidate** | Same fact (a user's age in years) decoded from the same stored data (`user["birth_date"]`) two different ways — one via plain year subtraction, one via `dateutil.relativedelta` on a parsed date. Token-different, so jscpd's clone matcher does not flag this pair; it's the semantic pass's job in `duplication/SKILL.md` to surface it as `category: semantic-duplicate`. |

Tally: 1 token-clone (jscpd, pass one), 1 semantic-duplicate (pass two, not
mechanically detectable — confirmed jscpd's JSON above contains only the
`validate_order`/`validate_shipment` pair, nothing for the age functions).
