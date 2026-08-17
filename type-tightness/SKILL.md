---
name: type-tightness
description: Audit loose typing the type-checker still accepts — Any where a real type is knowable, ignore-comments with no reason, and fake "boundary" excuses. Slash-only.
disable-model-invocation: true
argument-hint: "[path]"
---

Sweep the code in scope for typing the checker lets through but shouldn't have
to: an `Any` standing in for a type you can actually name, a suppression
comment with no reason, an `Any` excused as "it's a boundary" when the value's
shape is known. Gradual typing rots exactly here — everything the linter
already fails on is someone else's job; this audit's job is what's left after
that.

The default deliverable is a **report**, not applied edits. The sweep writes
a machine-readable findings log and a grouped HTML summary; it touches no
code.

## The one test

**A finding fires only when a precise replacement type can be named, or a
suppression is missing its reason.** Default is NO FINDING: the burden of
proof is on the finding. "This `Any` feels loose" with no nameable type
behind it is not a finding, no matter how untyped it looks — you must be able
to write the type you'd replace it with. "This ignore feels lazy" with a
reason comment already on it is not a finding either — a present reason is a
present reason, whether or not you'd have picked different words.

This is not a strictness pass. A repo choosing gradual typing on purpose is
not this audit's business — only the two provable failures above are.

## Gate-red is not this audit's business — subtract it first

Anything ruff `ANN` or the project's type-checker already flags red is
**excluded**, unconditionally. Re-reporting a gate failure as "noise" this
audit found teaches the reader to distrust both tools. Before triage, run the
gate over the same scope and drop every line a hit already covers:

```sh
uvx ruff check --select ANN --output-format json <scope>
```

and whichever checker the repo actually uses. Check for its config first —
`[tool.ty]`/`[tool.mypy]` in `pyproject.toml`, a `mypy.ini`, or
`pyrightconfig.json`/`[tool.pyright]` — and run that one. No config found
anywhere: fall through `ty` → `mypy` → `pyright` and run the first that's
installed.

```sh
uvx ty check <scope>            # ty
uvx mypy <scope>                # mypy
uvx pyright <scope>             # pyright
```

Parse each tool's file:line hits into a set and drop any grep candidate that
lands on one of those lines before triage starts. A repo with no type-checker
configured just means the gate output is empty — subtract nothing, triage
everything the grep found.

## Grep candidates

Grep does not judge — it only narrows where to look. Two patterns:

- **`Any` usages** — `\bAny\b` in annotations, `TypeVar` bounds, `cast(Any,
  ...)`, `dict[str, Any]`, etc. Import sites (`from typing import Any`) are
  not usages; skip them.
- **Ignore comments**, every dialect: `# type: ignore` / `# type:
  ignore[code]` (mypy/ty), `# pyright: ignore` / `# pyright: ignore[code]`,
  `# mypy: ignore`, `# ty: ignore` / `# ty: ignore[code]`, and the
  file-level `# mypy: ignore-errors`.

## Triage into buckets & categories

For everything left after the gate subtraction, read the code around each
hit — not just the grep line, since knowability depends on how the value is
built and used — and sort into:

- **`tighten`** / `loose-any` — the value's real shape is knowable from how
  it's constructed or consumed (a function always returns a `dict` with
  fixed keys typed `Any`; a param only ever receives `str | int`). Name the
  precise type in both `failure` and `extra.suggested_type`. If you cannot
  name one, this is not a finding — move on.
- **`tighten`** / `fake-boundary` — an `Any` defended as "external boundary,
  can't type it" (in a comment or by context — JSON parse result, API
  response, env var) when the boundary's actual shape is already known and
  typeable (the API's response schema is documented or used consistently
  elsewhere in the file). Name the precise type same as `loose-any`. A
  genuine boundary — truly dynamic, shape unknown at write time — is not a
  finding; that's the rare `keep`.
- **`justify`** / `unexplained-ignore` — a suppression with no reason. A bare
  `# type: ignore` or `# pyright: ignore[reportGeneralTypeIssues]` with
  nothing after it is unexplained; `# type: ignore  # upstream stub is wrong
  until v2` is not, regardless of how thin the reason reads. `failure` says
  what's missing; `extra.severity` carries `blanket` (bare `# type: ignore`,
  no error code) or `narrowed` (`# type: ignore[assignment]` — scoped to one
  or more specific error codes). A blanket ignore is worse: it swallows every
  future error on that line, not just the one it was written for.
- **`keep`** — surfaced as context only, never a finding driver: a genuine
  boundary `Any` or a suppression that already carries a reason. Do not add
  `keep` rows to `findings.jsonl` — they're not findings. Mention the count
  in the summary's metabar only.

## The audit, worked

```python
def parse_config(raw: Any) -> Any:          # (1)
    data = json.loads(raw)
    return data["settings"]                  # (2)

result = risky_call()  # type: ignore        # (3)

value = external_api.fetch()  # type: ignore[no-any-return]  # boundary — SDK is untyped  # (4)
```

1. `raw: Any` / return `Any` on `parse_config` — the param is only ever
   called with `str`, and the return is always the `"settings"` sub-dict, a
   `dict[str, str]` per every call site. **loose-any**, `tighten`,
   `suggested_type: "dict[str, str]"`.
2. Not a separate finding — same function, already covered by (1)'s fix.
3. `# type: ignore` with nothing after it — **unexplained-ignore**,
   `justify`, `severity: "blanket"` (no error code either).
4. Has a reason ("boundary — SDK is untyped") and a scoped code — check
   whether the boundary claim actually holds. If `external_api`'s SDK ships
   no stubs and its response shape genuinely varies, this is a real
   boundary: `keep`. If the SDK's return is documented and used the same way
   at every call site in the file, the boundary excuse is fake: **fake-
   boundary**, `tighten`, `suggested_type` named from the documented shape.

## Run

1. **Scope tight.** Audit `$ARGUMENTS` if given; with no argument, default to
   the current branch's diff against its base (`git diff --name-only
   main...HEAD`), not the whole tree — a repo-wide sweep is an explicit
   opt-in the user asks for by name. Either way, skip vendored, generated,
   and dependency trees (`node_modules`, `dist`, `.venv`, build output,
   lockfiles) and any `worktrees/` tree. Python only — this audit has
   nothing to say about a non-Python file.

2. **Run the gate and subtract.** `uvx ruff check --select ANN
   --output-format json <scope>` plus the repo's type-checker (`ty`/mypy/
   pyright — use whichever the repo already has configured; fall back
   through the list above if none is declared). Collect every `file:line`
   either tool flags. Any grep candidate on one of those lines is dropped
   before triage — it is the gate's finding, not this audit's.

3. **Grep candidates**, both patterns above, over the surviving scope.

4. **Triage every remaining candidate** — not a sample — into loose-any /
   unexplained-ignore / fake-boundary / keep, reading the surrounding code
   each time. Apply the one test before recording anything: named type or
   missing reason, or it doesn't go in the log.

5. **Write the findings log and render the summary — the default
   deliverable.** Write every `tighten`/`justify` finding to
   `findings.jsonl` (`keep` rows are counted, not logged), then draw a
   grouped summary `report.html` from it, following
   `~/.agents/skills/all-audits/harness/findings-schema.md` for both — the
   JSONL schema and the summary's grouped-overview shape.
   Resolve `<tmpdir>` from `$TMPDIR`, fall back to `/tmp`. Write both to
   `<tmpdir>/type-tightness-<timestamp>/`, then open the summary and hand
   off its path as `~/.agents/skills/all-audits/harness/HTML-REPORT.md`'s
   asset-delivery section describes. Print the one-line verdict and the
   summary's absolute path, nothing else.

## Write the log and render the summary

- **Log** — one JSONL line per `tighten`/`justify` finding, the six required
  fields plus `extra`: `file`/`line` of the `Any` or ignore comment,
  `summary` (one line, what's loose), `bucket` (`tighten` / `justify`),
  `category` (`loose-any` / `unexplained-ignore` / `fake-boundary`), and
  `failure` naming the concrete cost ("caller passes a `list[int]` here and
  gets no error until it hits the missing `.items()` three functions away").
  `extra.suggested_type` on `tighten` findings from `loose-any`/`fake-
  boundary`; `extra.severity` (`blanket`/`narrowed`) on `justify` findings.
- **Summary** — the verdict, the `N findings · T tighten · J justify · K
  kept` metabar (`kept` from the count only, no rows), findings grouped by
  bucket then category with counts, and a `vt-callout` naming the highest-
  value finds by `file:line`. No per-finding cards. Note the gate command run
  and how many candidates it removed, so a reader can see the subtraction
  happened.
