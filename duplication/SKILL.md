---
name: duplication
description: Find the same logic written twice — exact copy-paste and "same data decoded two ways" semantic duplicates — so a second home for one behavior gets caught before it drifts.
disable-model-invocation: true
argument-hint: "[path]"
---

Run jscpd over the target, then judge every clone, and separately sweep the
target for semantic duplicates jscpd's token matching can't see: the same
data walked, decoded, or validated two different ways under two different
names. Two copies of one behavior are a bug waiting for a fix that only
lands in one of them.

**Two passes.** `audit.py` in this skill's directory is pass one —
mechanical: run jscpd, parse its JSON output into findings rows. It never
judges consolidate vs keep; every row it emits starts `bucket: consolidate`
(a token clone is a real clone by construction — jscpd already matched the
tokens). The judgment pass below reads those rows, may downgrade a row to
`keep`, and does a second sweep for semantic duplicates jscpd's tool can't
find at all.

## Buckets & categories

- **`consolidate`** — two homes for one behavior; merge them (extract a
  shared function, call one from the other, or delete the redundant copy).
- **`keep`** — duplication that's intentional or acceptable: two independent
  tests happening to assert the same shape, generated/vendored code, or a
  coincidentally short clone (boilerplate like a standard `__init__` or
  argument-parsing block) where consolidating would cost more coupling than
  it saves.
- **`unsure`** — a clone or a suspected semantic pair where neither verdict
  is clean — genuinely ambiguous whether the two homes are meant to diverge.

`category` is `token-clone` (from jscpd, pass one) or `semantic-duplicate`
(from the pass-two sweep, never mechanically detected). `extra.clone_tokens`
carries jscpd's token count for a `token-clone` row; omit `extra` for
`semantic-duplicate` rows since there's no token count to report.

## Run

1. **Scope tight.** Audit `$ARGUMENTS` if given, else the current working
   directory. Skip vendored, generated, and dependency trees (`node_modules`,
   `dist`, `.venv`, `vendor`, build output, lockfiles) and any `.git/` or
   `worktrees/` tree.

2. **Pass one — run jscpd, parse it.**
   ```sh
   npx --yes jscpd --reporters json --output /tmp/jscpd-out --min-tokens 20 -s \
     --ignore "**/node_modules/**,**/.venv/**,**/dist/**,**/vendor/**,**/.git/**,**/build/**,**/worktrees/**" \
     <scope>
   python3 ~/.agents/skills/duplication/audit.py /tmp/jscpd-out/jscpd-report.json
   ```
   `-s` silences jscpd's progress/promo footer so it doesn't share stdout
   with the JSON report. `--min-tokens 20` lowers jscpd's default floor
   (50) so it catches fixture-sized clones — tune it up for a large repo
   if 20 is too noisy.

   **No node/npx.** jscpd needs `npx`. When it isn't on `PATH`, skip this
   pass instead of failing the whole audit: report pass one as `NOT-RUN` in
   the summary's verdict line and fall straight to pass two's semantic
   sweep — a token-clone miss is better than no report at all.

   `audit.py`'s `parse_jscpd(json_str) -> list[dict]` is the tested seam
   (`duplication/fixtures/` + `answer-key.md` back it, mirroring
   `dead-code/fixtures/`) — pure, no subprocess inside it, fed jscpd's
   captured JSON text. `main()` wraps it: reads a file argument or stdin,
   prints one JSON row per duplicate pair. This is a candidate list, not a
   verdict — every row still needs the judgment pass.

3. **Pass two — judge every token-clone row, then sweep for semantic
   duplicates.**
   - For each `token-clone` row, read both homes in context. Reassign
     `bucket` per the rules above when the clone is boilerplate or
     intentionally-parallel test code. Then write `summary` / `failure`
     from what THESE two cited sites actually share (or differ on) — quote
     the shared line or name the concrete shape you just read (the function
     both define, the field both decode), never a per-category template. A
     rationale you could paste onto every `keep` without reading the code
     isn't evidence; if you can't cite the real shared shape, you haven't
     read the pair.
   - Separately, read through the scope for pairs jscpd's token matcher
     structurally cannot catch: the same source data (same field, same
     external shape) decoded, validated, or walked by differently-shaped
     code in two places — different variable names, different control flow,
     maybe a different library, same underlying fact produced. For each
     pair found, emit a new row: `bucket: consolidate` (or `unsure` if
     genuinely ambiguous), `category: semantic-duplicate`, `file`/`line` at
     the first home, `summary` and `failure` naming both homes by
     `file:line` and the shared fact they both compute — read from the two
     sites, never a per-category template — no `extra`.

4. **Write the findings log and render the summary — the default
   deliverable.** Write every judged row (both passes) to `findings.jsonl`,
   then draw a grouped summary `report.html` from it, following
   `~/.agents/skills/all-audits/harness/findings-schema.md` for both — the
   JSONL schema and the summary's grouped-overview shape.
   Write both to `<tmpdir>/duplication-<timestamp>/` and deliver the summary
   per `~/.agents/skills/all-audits/harness/HTML-REPORT.md` — tmpdir
   resolution, opening, and handing off the path all live there. This audit
   touches no code — consolidating a duplicate is a separate, opt-in step the
   user asks for by name.

   - **Log** — one JSONL line per clone pair or semantic-duplicate pair.
     `bucket` is `consolidate` / `keep` / `unsure`. `category` is
     `token-clone` or `semantic-duplicate`. `extra.clone_tokens` carries
     jscpd's token count for `token-clone` rows.
   - **Summary** — the verdict, the `N flagged · C consolidate · K keep · U
     unsure` metabar, findings grouped by bucket then category with counts.
     No per-hit cards. Call out the `semantic-duplicate` finds in a
     `vt-callout` — the pairs a naive jscpd-only read would have missed
     entirely.

## Verify against the fixture

`duplication/fixtures/sample_a.py` and `sample_b.py` carry one copy-pasted
validation block (`validate_order` / `validate_shipment`, byte-identical)
and one semantic duplicate (`user_age_years` / `user_age_in_years` — same
`birth_date` field decoded into an age two different ways: plain year
subtraction vs. `dateutil.relativedelta`). `duplication/fixtures/answer-key.md`
has the captured jscpd JSON and the expected row for each. Running this
skill over `duplication/fixtures/` should reproduce that table: pass one
catches the validation clone as `token-clone`, pass two's semantic sweep
catches the age-decode pair as `semantic-duplicate`.
