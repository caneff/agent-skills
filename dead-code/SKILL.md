---
name: dead-code
description: Find code nobody calls — dead functions, classes, unreachable branches, stray imports — and sort real dead code from code that only looks unused.
disable-model-invocation: true
argument-hint: "[path]"
---

Run vulture over the target, then sort each hit into truly-dead vs
reached-by-a-mechanism-vulture-can't-see. Vulture's static analysis only sees
direct calls in the code it reads — it cannot see a `console_scripts`
entrypoint, a pytest fixture injected by parameter name, a plugin registered
by decorator, or any other name-based dynamic dispatch. Reporting every
vulture hit as dead would tell you to delete load-bearing code; the judgment
pass here is what makes the report safe to act on.

**Two passes.** `audit.py` in this skill's directory is pass one — mechanical:
run vulture, parse its stable text-output format into findings rows. It never
judges dead vs dynamic; every row it emits starts `bucket: unsure`. The
judgment pass below reads those rows and reassigns the real bucket.

## Buckets & categories

- **`dead`** — no mechanism reaches it. Delete it.
- **`dynamic`** — vulture flagged it, but something outside static call analysis
  reaches it: an entrypoint (`if __name__ == "__main__"`, a `console_scripts`
  entry point, a CLI command function), a test fixture (`@pytest.fixture`,
  `setUp`/`tearDown`, a fixture referenced only by name in a test's
  parameter list), a dunder/protocol method (`__enter__`, `__eq__`,
  `__getattr__`) invoked implicitly by the language, or a plugin/handler
  registered by decorator or string lookup (`@app.route(...)`,
  `getattr(self, f"handle_{kind}")`).
- **`unsure`** — vulture flagged it, and it isn't a clean fit for either bucket
  above: a low-confidence hit (see below), or a name that *could* be reached
  by something outside the repo (a public library export with unknown
  external callers) but shows no concrete dynamic-dispatch evidence in this
  codebase. Default here when the judgment call isn't clean — false "dead"
  costs more than a false "unsure."

`category` is the mechanical kind vulture reported, slugged:
`unused-function`, `unused-import`, `unused-class`, `unused-method`,
`unused-variable`, `unused-attribute`, `unused-property`. `extra.confidence`
carries vulture's percentage (60% is its default floor; imports report at
90%, unused variables/attributes lower). Confidence is vulture's own signal
about how sure *it* is the name is unused, not the triage bucket — a 60%
`unused function` that turns out to be a `console_scripts` entrypoint is
still `dynamic`, not `unsure`, once the entrypoint evidence is concrete.

## Run

1. **Scope tight.** Audit `$ARGUMENTS` if given; with no argument, scope
   defaults per `~/.agents/skills/all-audits/SKILL.md`'s Scope section. Skip
   vendored, generated, and dependency trees (`node_modules`, `dist`, `.venv`,
   `vendor`, build output, lockfiles) and any `.git/` or `worktrees/` tree.

2. **Pass one — run vulture, parse it.**
   ```sh
   uvx vulture <scope> \
     --exclude "*/node_modules/*,*/.venv/*,*/dist/*,*/vendor/*,*/.git/*,*/build/*,*/worktrees/*" \
     > /tmp/vulture-out.txt
   python3 ~/.agents/skills/dead-code/audit.py /tmp/vulture-out.txt
   ```
   `audit.py`'s `parse_vulture(text) -> list[dict]` is the tested seam
   (`~/.agents/skills/dead-code/fixtures/` + `answer-key.md` back it, mirroring
   `~/.agents/skills/test-audit/fixtures/`) — pure, no subprocess inside it, fed vulture's
   captured text. `main()` wraps it: reads a file argument or stdin, prints
   one JSON row per hit. This is a candidate list, not a verdict — every row
   still needs the judgment pass.

3. **Pass two — judge every row.** For each row, read the flagged symbol
   in context: its definition, its decorators, whether it's named or shaped
   like an entrypoint, whether the module it lives in is a plugin/handler
   registry. Reassign `bucket` per the rules above, and rewrite `summary` /
   `failure` to say *why* — "reached via `@app.route` decorator registration
   at line N" for a `dynamic`, "no caller, no decorator, no entrypoint shape"
   for a `dead`.

4. **Write the findings log and render the summary — the default
   deliverable.** Write every judged row to `findings.jsonl`, then draw a
   grouped summary `report.html` from it, following
   `~/.agents/skills/all-audits/harness/findings-schema.md` for both — the
   JSONL schema and the summary's grouped-overview shape.
   Write both to `<tmpdir>/dead-code-<timestamp>/` and deliver the summary per
   `~/.agents/skills/all-audits/harness/HTML-REPORT.md` — tmpdir resolution,
   opening, and handing off the path all live there. This audit touches no
   code — deleting dead code is a separate, opt-in step the user asks for by
   name.

   - **Log** — one JSONL line per vulture hit. `bucket` is `dead` / `dynamic`
     / `unsure`. `category` is the vulture kind, slugged (see above).
     `extra.confidence` carries vulture's percentage.
   - **Summary** — the verdict, the `N flagged · D dead · Y dynamic · U
     unsure` metabar, findings grouped by bucket then category with counts.
     No per-hit cards. Call out the `dynamic` finds in a `vt-callout` — the
     ones a naive vulture-only read would have wrongly told the user to
     delete.

## Verify against the fixture

`~/.agents/skills/dead-code/fixtures/sample.py` carries four dead symbols (an unused import,
an uncalled function, an uncalled class, and its uncalled method) and two
dynamically-reached ones (a `main()` entrypoint, a `@pytest.fixture`).
`~/.agents/skills/dead-code/fixtures/answer-key.md` has the captured vulture output and the
expected bucket for each. Running this skill over `~/.agents/skills/dead-code/fixtures/`
should reproduce that table.
