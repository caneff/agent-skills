---
name: docstring-coverage
description: Find public functions and classes with no docstring on a typed (py.typed) library, so consumers get docs on the surface they build against. Slash-only.
disable-model-invocation: true
argument-hint: "[path]"
---

Run interrogate + ruff `D` over the target's public surface, then judge every
hit: is this a real public symbol a consumer types against, or something
trivial a docstring wouldn't help (a dunder, an obvious one-line property, an
overload stub)? A plain linter flags every missing docstring the same way —
the judgment pass here is what tells a load-bearing gap from noise.

**Two passes.** `audit.py` in this skill's directory is pass one —
mechanical: run ruff D1xx and interrogate, parse both into findings rows. It
never judges document vs skip; every row it emits starts `bucket: document`
(a ruff D1xx hit is a real missing-docstring candidate by construction, same
reasoning error-handling's parser uses for a caught-and-dropped exception).
The judgment pass below reads those rows and reassigns the real bucket.

## Buckets & categories

- **`document`** — a real gap: public API a consumer builds against, with
  nothing trivial about it. Write the docstring.
- **`skip`** — flagged, but a docstring genuinely adds nothing: a trivial
  dunder (`__repr__`, `__eq__`), an obvious one-line `@property`, an
  `@overload` stub whose implementation carries the real docstring.
- **`unsure`** — flagged, and it isn't a clean fit for either bucket above:
  a symbol whose purpose isn't obvious from its name/shape alone, but nothing
  concrete marks it trivial either.

`category` is the ruff D code's target, slugged into a small closed set:
`missing-module-docstring` (D100), `missing-package-docstring` (D104),
`missing-class-docstring` (D101/D106), `missing-method-docstring` (D102),
`missing-function-docstring` (D103), `missing-init-docstring` (D107),
`missing-magic-method-docstring` (D105). `extra.coverage` carries
interrogate's overall coverage percentage for the whole scanned scope —
the same number on every row, not per-symbol.

## Run

1. **Scope tight.** Audit `$ARGUMENTS` if given, else the current working
   directory. Target the package's public modules — skip tests,
   vendored/generated/dependency trees (`node_modules`, `dist`, `.venv`,
   `vendor`, build output, lockfiles), and any `.git/` or `worktrees/` tree.

2. **Pass one — run ruff D1xx and interrogate over the SAME scope, parse
   them.**
   ```sh
   scope="$(realpath "${ARGUMENTS:-.}")"
   uvx ruff check --select D100,D101,D102,D103,D104,D105,D106,D107 --output-format json "$scope" > /tmp/ruff-out.json
   uvx interrogate -v "$scope" \
     -e "$scope/node_modules" -e "$scope/.venv" -e "$scope/dist" -e "$scope/vendor" \
     -e "$scope/.git" -e "$scope/build" -e "$scope/worktrees" \
     > /tmp/interrogate-out.txt
   python3 docstring-coverage/audit.py /tmp/ruff-out.json /tmp/interrogate-out.txt
   ```
   Only the D1xx "missing docstring" codes are selected — not the D2xx/D4xx
   style-convention codes (blank-line placement, summary formatting). Those
   are ruff's own job to enforce as a lint gate, not this audit's; several of
   them (D203/D211) actively conflict with each other, which is why they stay
   out of scope here.

   `audit.py`'s `parse_coverage(ruff_json, interrogate_text) -> list[dict]`
   is the tested seam (`docstring-coverage/fixtures/` + `answer-key.md` back
   it, mirroring `dead-code/fixtures/`) — pure, no subprocess inside it, fed
   ruff's captured JSON and interrogate's captured text. `main()` wraps it:
   reads the two file paths as argv, prints one JSON row per ruff D1xx hit.
   This is a candidate list, not a verdict — every row still needs the
   judgment pass. Private symbols (leading `_`) and already-documented
   symbols never appear — ruff's own D1xx rule semantics exclude them, so
   there's nothing to hand-filter.

3. **Pass two — judge every row.** For each row, read the flagged symbol in
   context: is it public API a consumer types against, or something trivial
   a docstring wouldn't help? Reassign `bucket` per the rules above, and
   rewrite `summary` / `failure` to say *why* — "public function taking two
   args and returning a computed value, no docstring at all" for a
   `document`, "trivial `__repr__` override, name and body are
   self-explanatory" for a `skip`.

4. **Write the findings log and render the summary — the default
   deliverable.** Write every judged row to `findings.jsonl`, then draw a
   grouped summary `report.html` from it, following
   `~/.agents/skills/all-audits/harness/findings-schema.md` for both — the
   JSONL schema and the summary's grouped-overview shape.
   Resolve `<tmpdir>` from `$TMPDIR`, fall back to `/tmp`. Write both to
   `<tmpdir>/docstring-coverage-<timestamp>/`, then open the summary and hand
   off its path as `~/.agents/skills/all-audits/harness/HTML-REPORT.md`'s
   asset-delivery section describes. This audit touches no code — writing the
   docstrings is a separate, opt-in step the user asks for by name.

   - **Log** — one JSONL line per ruff D1xx hit. `bucket` is `document` /
     `skip` / `unsure`. `category` is the D-code slug (see above).
     `extra.coverage` carries interrogate's overall coverage percentage.
   - **Summary** — the verdict, a `N flagged · D document · S skip · U
     unsure · coverage NN.N%` metabar, findings grouped by bucket then
     category with counts. No per-hit cards. Call out the `skip` finds in a
     `vt-callout` — the ones a naive tool-only read would have wrongly told
     the user to document.

## Verify against the fixture

`docstring-coverage/fixtures/sample.py` carries one undocumented public
function (`undocumented_public`, no docstring — ruff D103 flags it), one
documented public function (`documented_public` — not flagged), and one
private function (`_helper`, no docstring but not public — not flagged by
D1xx). `docstring-coverage/fixtures/answer-key.md` has the captured ruff +
interrogate output and the expected finding. Running this skill over
`docstring-coverage/fixtures/` should reproduce that table: one row,
`undocumented_public` at line 9, `bucket: document`, `extra.coverage: 50.0`.
