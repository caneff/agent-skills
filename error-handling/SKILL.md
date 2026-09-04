---
name: error-handling
description: "Find swallowed errors — bare excepts, `except Exception: pass`, silent drops — and sort a justified silence from an unjustified one, enforcing the repo's fail-loud rule where a plain linter stops short."
disable-model-invocation: true
argument-hint: "[path]"
---

Run ruff + bandit over the target, then judge every hit: is this silence
deliberate and correct, or is an error going missing with nobody the wiser?
A plain linter flags `except Exception: pass` the same way whether it's a
documented, narrow, best-effort suppression or a lazy catch-all hiding a real
bug — the judgment pass here is what tells them apart.

**Two passes.** `audit.py` in this skill's directory is pass one —
mechanical: run ruff and bandit, parse their JSON output into findings rows.
It never judges justified vs unjustified; every row it emits starts `bucket:
fix` (a caught-and-dropped exception is a real smell by construction — same
reasoning `duplication`'s parser uses for a token clone). The judgment pass
below reads those rows and reassigns the real bucket.

## Buckets & categories

- **`fix`** — the silence is unjustified: no re-raise, no log, no comment
  explaining why swallowing is correct here. Make it fail loud — log it,
  re-raise it, or narrow the caught type.
- **`justified`** — the silence is deliberate and correct: a documented
  reason (a comment naming why this failure is expected and safe to ignore),
  a genuinely-optional cleanup, or `contextlib.suppress` with a narrow named
  exception and a comment. Leave it.
- **`unsure`** — flagged, and it isn't a clean fit for either bucket above:
  no comment, but the surrounding code makes the intent ambiguous rather than
  clearly careless.

`category` is the tool code slugged into a small closed set: `bare-except`
(ruff `BLE001`), `try-except-pass` (ruff `SIM105` / bandit `B110`),
`try-except-continue` (bandit `B112`), `raise-without-from` (ruff `B904`),
`try-consider` (any ruff `TRY0xx`). When more than one code fires on the same
line, `bare-except` > `raise-without-from` > `try-except-continue` >
`try-except-pass` > `try-consider` picks the row's category; `extra.codes`
lists every code that fired, so pass two sees the full mechanical picture.

## Run

1. **Scope tight.** Audit `$ARGUMENTS` if given, else the current working
   directory. Skip vendored, generated, and dependency trees (`node_modules`,
   `dist`, `.venv`, `vendor`, build output, lockfiles) and any `.git/` or
   `worktrees/` tree.

2. **Pass one — run ruff and bandit over the SAME absolute scope, parse
   them.**
   ```sh
   scope="$(realpath "${ARGUMENTS:-.}")"
   uvx ruff check --select BLE,TRY,B904,SIM105 --output-format json "$scope" > /tmp/ruff-out.json
   uvx bandit -r "$scope" -f json -t B110,B112 -q \
     --exclude "$scope/node_modules,$scope/.venv,$scope/dist,$scope/vendor,$scope/.git,$scope/build,$scope/worktrees" \
     > /tmp/bandit-out.json
   python3 error-handling/audit.py /tmp/ruff-out.json /tmp/bandit-out.json
   ```
   Using the same absolute path for both tools matters: ruff's JSON always
   reports absolute `filename`s; bandit's mirrors whatever scope you gave it.
   Different scope forms mean different filename strings, and same-line hits
   from the two tools won't merge into one row.

   `audit.py`'s `parse_findings(ruff_json, bandit_json) -> list[dict]` is the
   tested seam (`error-handling/fixtures/` + `answer-key.md` back it,
   mirroring `dead-code/fixtures/`) — pure, no subprocess inside it, fed both
   tools' captured JSON text. `main()` wraps it: reads the two file paths as
   argv, prints one JSON row per merged hit. This is a candidate list, not a
   verdict — every row still needs the judgment pass.

3. **Pass two — judge every row.** For each row, read the except in context:
   is there a comment explaining why the silence is safe? Is the exception
   type narrow and named, or a blind catch-all? Is the failure re-raised,
   logged, or otherwise surfaced anywhere nearby? Reassign `bucket` per the
   rules above, and rewrite `summary` / `failure` to say *why* — "documented
   as an optional best-effort notification at line N" for a `justified`, "no
   comment, no re-raise, no log — a real error goes missing" for a `fix`.
   Two rows can point at the same except block (ruff sometimes reports the
   `try`'s line and the `except`'s line separately for one silence) — judge
   them together and give them the same verdict.

4. **Write the findings log and render the summary — the default
   deliverable.** Write every judged row to `findings.jsonl`, then draw a
   grouped summary `report.html` from it, following
   `~/.agents/skills/all-audits/harness/findings-schema.md` for both — the
   JSONL schema and the summary's grouped-overview shape.
   Resolve `<tmpdir>` from `$TMPDIR`, fall back to `/tmp`. Write both to
   `<tmpdir>/error-handling-<timestamp>/`, then open the summary and hand off
   its path as `~/.agents/skills/all-audits/harness/HTML-REPORT.md`'s
   asset-delivery section describes. This audit touches no code — fixing a
   swallowed error is a separate, opt-in step the user asks for by name.

   - **Log** — one JSONL line per merged hit. `bucket` is `fix` / `justified`
     / `unsure`. `category` is the tool-code slug (see above). `extra.codes`
     carries every ruff/bandit code that fired on that line.
   - **Summary** — the verdict, the `N flagged · F fix · J justified · U
     unsure` metabar, findings grouped by bucket then category with counts.
     No per-hit cards. Call out the `justified` finds in a `vt-callout` — the
     ones a naive tool-only read would have wrongly told the user to fix.

## Verify against the fixture

`error-handling/fixtures/sample.py` carries one unjustified swallow
(`load_config`, catches `Exception` and drops it with no comment) and one
justified one (`notify_best_effort`, catches `Exception` too but a comment
documents that best-effort notification failures must never break the
caller). `error-handling/fixtures/answer-key.md` has the captured ruff +
bandit output and the expected bucket for each. Running this skill over
`error-handling/fixtures/` should reproduce that table: the parser flags
both the same way (`bucket: fix`, both `bare-except`/`try-except-pass`), and
pass two is what tells them apart.
