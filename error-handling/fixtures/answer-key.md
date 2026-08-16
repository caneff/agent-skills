# Answer key

Both tools run over `error-handling/fixtures/sample.py` with the **same
absolute scope path** so their `filename` fields align:

```sh
scope="$(realpath error-handling/fixtures/sample.py)"
uvx ruff check --select BLE,TRY,B904,SIM105 --output-format json "$scope"
uvx bandit -r "$scope" -f json -t B110,B112
```

Captured raw output (this repo, both tools via `uvx`; relevant fields, path
shortened to `sample.py` for readability):

```json
// ruff
[
  {"filename": "sample.py", "location": {"row": 14}, "code": "BLE001",
   "message": "Do not catch blind exception: `Exception`"},
  {"filename": "sample.py", "location": {"row": 23}, "code": "SIM105",
   "message": "Use `contextlib.suppress(Exception)` instead of `try`-`except`-`pass`"},
  {"filename": "sample.py", "location": {"row": 25}, "code": "BLE001",
   "message": "Do not catch blind exception: `Exception`"}
]
```

```json
// bandit .results[]
[
  {"filename": "sample.py", "line_number": 14, "test_id": "B110",
   "issue_text": "Try, Except, Pass detected."},
  {"filename": "sample.py", "line_number": 25, "test_id": "B110",
   "issue_text": "Try, Except, Pass detected."}
]
```

`sample.py:23` is ruff's `SIM105` reporting at the `try`'s row, not the
`except`'s — bandit's `B110` and ruff's `BLE001` both report at the
`except`'s row (14, 25) for the same block. `parse_findings` merges same-line
hits into one row (14 and 25) and leaves 23 as its own row — three rows
total for two except blocks, which is correct: 23 and 25 are the *same*
silence (`notify_best_effort`'s except), just reported by ruff at two
different lines of that block.

Running `python3 error-handling/audit.py` over the captured JSON produces:

```json
{"bucket": "fix", "file": "sample.py", "line": 14, "category": "bare-except", "summary": "bare except at sample.py:14 (B110, BLE001)", "failure": "exception silenced with no visible re-raise or log: Do not catch blind exception: `Exception`; Try, Except, Pass detected.", "extra": {"codes": ["B110", "BLE001"]}}
{"bucket": "fix", "file": "sample.py", "line": 23, "category": "try-except-pass", "summary": "try except pass at sample.py:23 (SIM105)", "failure": "exception silenced with no visible re-raise or log: Use `contextlib.suppress(Exception)` instead of `try`-`except`-`pass`", "extra": {"codes": ["SIM105"]}}
{"bucket": "fix", "file": "sample.py", "line": 25, "category": "bare-except", "summary": "bare except at sample.py:25 (B110, BLE001)", "failure": "exception silenced with no visible re-raise or log: Do not catch blind exception: `Exception`; Try, Except, Pass detected.", "extra": {"codes": ["B110", "BLE001"]}}
```

## Expected findings table

| # | Function | Line(s) | Codes | Parser bucket | Pass-two bucket | Reason |
|---|----------|---------|-------|----------------|------------------|--------|
| 1 | `load_config` | 14 | BLE001, B110 | `fix` | **`fix`** | Catches `Exception` broadly and drops it with no re-raise, no log, no comment explaining why. Nothing in context justifies the silence. |
| 2 | `notify_best_effort` | 23, 25 | SIM105 / BLE001, B110 | `fix` (both rows) | **`justified`** (both rows) | Same tool signature as #1 — broad except, silent pass — but the comment at line 26-27 documents a deliberate reason: notification failures are expected and must never break the caller's primary operation. Pass two must read the comment and reassign both of this function's rows to `justified`, distinguishing them from `load_config`'s identical-looking but unjustified swallow. |

Tally: 3 mechanical rows (parser, all `bucket: fix` by default), pass-two
verdict: 1 `fix` (row 1), 2 `justified` (rows 2-3, same silence).
