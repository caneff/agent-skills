# Answer key

Both tools run over `docstring-coverage/fixtures/sample.py`:

```sh
scope="$(realpath docstring-coverage/fixtures/sample.py)"
uvx ruff check --select D100,D101,D102,D103,D104,D105,D106,D107 --output-format json "$scope"
uvx interrogate -v "$scope"
```

Captured raw output (this repo, both tools via `uvx`; path shortened to
`sample.py` for readability):

```json
// ruff
[
  {"filename": "sample.py", "location": {"row": 9}, "code": "D103",
   "message": "Missing docstring in public function"}
]
```

```
= Coverage for docstring-coverage/fixtures/ =
----------------------------------- Summary ------------------------------------
| Name             |        Total |        Miss |        Cover |        Cover% |
|------------------|--------------|-------------|--------------|---------------|
| sample.py        |            4 |           2 |            2 |           50% |
|------------------|--------------|-------------|--------------|---------------|
| TOTAL            |            4 |           2 |            2 |         50.0% |
---------------- RESULT: FAILED (minimum: 80.0%, actual: 50.0%) ----------------
```

`documented_public` and `_helper` never appear in ruff's output — a
documented public function satisfies D103 by rule semantics, and a private
name (leading `_`) isn't a "public function" ruff's D1xx rules apply to. No
hand-filtering needed in `parse_coverage`; ruff's own rule scope does the
work.

Running `python3 docstring-coverage/audit.py` over the captured output
produces:

```json
{"bucket": "document", "file": "sample.py", "line": 9, "category": "missing-function-docstring", "summary": "Missing docstring in public function", "failure": "Missing docstring in public function (D103) at sample.py:9", "extra": {"coverage": 50.0}}
```

## Expected findings table

| # | Symbol | Line | Parser bucket | Pass-two bucket | Reason |
|---|--------|------|----------------|------------------|--------|
| 1 | `undocumented_public` | 9 | `document` | **`document`** | Public function, no docstring, nothing trivial about it (takes an arg, returns a computed value) — a consumer typing against this module gets no explanation. Pass two keeps it `document`. |
| — | `documented_public` | 13 | *(absent)* | *(absent)* | Has a docstring — ruff D103 doesn't fire. Never appears in the parser's output. |
| — | `_helper` | 18 | *(absent)* | *(absent)* | Leading underscore — not part of the public surface D1xx checks. Never appears in the parser's output. |

Tally: 1 mechanical row (parser, `bucket: document`), coverage 50.0% attached
to it. Pass two reads `undocumented_public` in context — it's a real public
symbol, not a trivial dunder or obvious one-liner — and keeps it `document`.
