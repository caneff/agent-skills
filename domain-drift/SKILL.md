---
name: domain-drift
description: Audit whether code names match the project's own domain vocabulary — a generic name standing in for a defined term, two names for one concept, or a term used for the wrong thing.
disable-model-invocation: true
argument-hint: "[path]"
---

Sweep the code in scope and check it against the project's own ubiquitous
language — the terms `CONTEXT.md` and `docs/adr/` already define. Code that
drifts from those terms makes every reader re-translate between what the docs
call a thing and what the code calls it.

The default deliverable is a **report**, not applied edits. The sweep writes
a machine-readable findings log and a grouped HTML summary; it touches no
code.

## The one test

**A finding fires only when a code name displaces a specific named domain
term.** Default is NO FINDING: the burden of proof is on the finding, not the
name. A name that is merely vague, generic, or not what you'd have chosen —
with no defined term standing behind it — is not this audit's business. If
you cannot point at the term the name displaces and where it's defined, there
is no finding, no matter how bad the name is.

This is not a style pass. `data`, `helper`, `process` in a file with no
glossary are ugly, not drift — nothing has been displaced, because nothing
was ever defined. The moment a term *is* defined and the code disagrees, that
disagreement — and only that — is in scope.

## Extract the term set first — and print it

Before judging anything, read every `CONTEXT.md` in the repo (root and
nested, e.g. `<some-skill>/docs/CONTEXT.md`) and every file under
`docs/adr/`, and build the term set: each defined noun/verb, its definition,
and its source file. Glossary entries (`**Term** — definition`) and ADR
decision titles/bodies that name a concept both count.

Print this term set at the top of the report, verbatim — term, one-line gloss,
source. **A wrong or incomplete extraction must be visible in the report, not
silent** — if the repo has no `CONTEXT.md`/`docs/adr/`, the term set is empty
and the report says so plainly; that is a correct, boring result, not an
error to paper over.

## Buckets & categories

- **`rename`** / `generic-standin` — a code name is generic where the project
  has a specific defined term for exactly that thing (`data` where the domain
  term is `Order`; `process()` where the term is `reconcile`).
- **`consolidate`** / `synonym-sprawl` — two (or more) code names refer to the
  same concept the glossary treats as one term (`job` and `task` both meaning
  what `CONTEXT.md` calls a `Run`).
- **`misuse`** / `term-misuse` — a defined term is used in code for something
  the glossary says it is not (a variable named `parent` holding what the
  glossary defines as a `blocker` — `CONTEXT.md`'s own `_Avoid_` note may name
  the mix-up directly).

`extra` carries `should_be` (the displaced/correct term) and `source` (where
it's defined, e.g. `CONTEXT.md` or `docs/adr/0001-....md`). The displaced term
must be named in both `failure` and `extra.should_be` — a finding that can't
name the term it displaces is not a finding, per the one test above.

## The audit, worked

`CONTEXT.md` defines **Run** — "one orchestrator invocation, loops
plan→execute until the backlog drains." The code has two names fighting over
that concept:

```ts
function startJob(cfg: Config) { ... }      // job.ts
function runTask(id: string) { ... }        // scheduler.ts — same invocation
```

Neither name is *wrong* on its own — `startJob` and `runTask` both read fine
in isolation, which is exactly why a style pass would pass them. Set beside
`CONTEXT.md`'s `Run`, they're two names for the one term the glossary already
settled: a `consolidate` / `synonym-sprawl` finding, `should_be: "Run"`,
`source: "CONTEXT.md"`.

Contrast a name the audit leaves alone: `cfg` in the same file. Generic,
sure — but nothing in `CONTEXT.md` or the ADRs defines a term `cfg` displaces.
No finding.

## Out of scope

Pure style naming — `snake_case` vs `camelCase`, unclear-but-undefined names,
abbreviation style — is a different axis and stays with ruff `N`. This audit
only fires where a *defined* term exists and the code disagrees with it. Do
not flag a name for being bad; flag it only for being wrong against a
specific, sourced term.

## Run

1. **Scope.** Audit `$ARGUMENTS` if given; with no argument, default to the
   whole repo — see `all-audits/SKILL.md`'s Scope section for the shared
   default-scope rule. Skip vendored, generated, and dependency trees
   (`node_modules`, `dist`, `.venv`, build output, lockfiles) and any
   `worktrees/` tree.

2. **Extract and print the term set** as above, before judging any code.

3. **Sweep every name in scope against the term set** — identifiers, class
   names, function names, key variable names, not a sample. For each one,
   check: does a defined term describe exactly what this name refers to, and
   does the code's name disagree with it (generic-standin), collide with
   another name for the same concept (synonym-sprawl), or borrow the term for
   something else (term-misuse)? A name with no term behind it is silently
   fine — do not record it, do not almost-flag it.

   **Then, for each confirmed drifted word, enumerate every site — grep, do
   not eyeball.** A rename executed from this finding must be safe and total,
   so the site list has to be both exhaustive and clean. `grep` the whole
   repo — not just the audit scope; a drifted word's occurrences straddle
   files the diff never touched, and a rename touches all of them — for the
   word in every form it takes: identifiers, string literals, dict keys, CSS
   class names, filenames. Then re-check each hit against the term's meaning
   before you emit it — the same one test as above, applied per site: a hit
   that uses the word in a different, correct sense is not drift (`invalid
   puzzle document` covering broken JSON, when the glossary excludes that from
   `malformed`, is a defensible clear, not a rename target). Emit one finding
   row per real drift site, all sharing the same `should_be` and `source`.
   Miss a real site and the rename half-applies — renaming the dispatch call
   but not the constructor literal it dispatches to breaks the code; sweep in
   a defensible clear and the rename corrupts a correct use. If you cannot
   confirm the list is complete, flag the term `partial coverage` in the
   summary rather than presenting a half-list as the finding.

4. **Write the findings log and render the summary — the default
   deliverable.** Write every finding to `findings.jsonl`, then draw a
   grouped summary `report.html` from it, following
   `~/.agents/skills/all-audits/harness/findings-schema.md` for both — the
   JSONL schema and the summary's grouped-overview shape.
   Resolve `<tmpdir>` from `$TMPDIR`, fall back to `/tmp`. Write both to
   `<tmpdir>/domain-drift-<timestamp>/`, then open the summary and hand off
   its path as `~/.agents/skills/all-audits/harness/HTML-REPORT.md`'s
   asset-delivery section describes. Print the one-line verdict and the
   summary's absolute path, nothing else.

## Write the log and render the summary

- **Log** — one JSONL line per finding, the six required fields plus `extra`:
  `file` and `line` where the drifting name sits, `summary` (one line, what
  drifted), `bucket` (`rename` / `consolidate` / `misuse`), `category`
  (`generic-standin` / `synonym-sprawl` / `term-misuse`), and `failure` naming
  the displaced term and the concrete confusion it causes ("reader sees `data`
  and can't tell this is the `Order` `CONTEXT.md` defines without opening the
  file"). `extra` carries `should_be` and `source`.
- **Summary** — the term set (term, gloss, source) printed in full at the
  top, then the verdict, the `N findings · R rename · C consolidate · M
  misuse` metabar, findings grouped by bucket then category with counts, and
  a `vt-callout` naming the highest-value finds by `file:line`. No
  per-finding cards. Any term whose site list isn't confirmed exhaustive
  carries a `partial coverage` flag here.
