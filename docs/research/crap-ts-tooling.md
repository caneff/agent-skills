# TypeScript per-function CRAP tooling — pipeline research

Question: what is the best pipeline to compute per-function CRAP scores
(`CRAP = complexity^2 * (1 - coverage)^3 + complexity`, `coverage = min(statement,
branch)`) in a TypeScript repo? Sources are the ESLint docs, the npm registry
(`registry.npmjs.org`), the istanbuljs/istanbul GitHub repos, Vitest/Jest
official docs, and the npm registry entry + GitHub repo for
`@barney-media/crap-typescript-core`.

## Bottom line

- **Complexity:** none of the three candidates is a clean off-the-shelf
  per-function emitter. `eslint`'s `complexity` rule only *reports* a function
  when it exceeds a `max` threshold, but the report message embeds the raw
  computed number (`"{{name}} has a complexity of {{complexity}}. Maximum
  allowed is {{max}}."`), so setting `max: 0` forces every function to report
  and `--format json` gives you a parseable per-function value — no forked
  rule needed. `typhonjs-escomplex` is TS-capable (Babel-parser based) but its
  last publish is December 2018 (v0.1.0), i.e. effectively unmaintained.
  Recommended: **ESLint `complexity` rule with `max: 0` + `--format json`**,
  because it's officially maintained, needs no extra dependency beyond ESLint
  itself, and requires no custom AST walk. Fallback ranking if that's
  unworkable: `cyclomatic-complexity` (npm, actively published Oct 2024, has a
  native `--json` per-function output) → a bespoke ts-morph walk → 
  `typhonjs-escomplex`.
- **Coverage:** run tests through Istanbul-shaped output and read
  `coverage-final.json`'s `fnMap`/`f` for per-function statement-adjacent
  counts and `branchMap`/`b` for per-function branch counts, matching
  statements to functions by comparing `statementMap` locations against each
  function's `loc` range (Istanbul's own schema doc does not give a helper for
  this — it must be done by hand). Exact commands below for both Vitest
  (`provider: 'istanbul'`, which — unlike Vitest's default `v8` provider —
  produces this exact Istanbul JSON shape) and Jest (`coverageProvider:
  "babel"`, Jest's default, also Istanbul-shaped).
- **`@barney-media/crap-typescript-core`:** real, current, and does
  essentially the requested task already — worth evaluating as a
  build-vs-buy option before hand-rolling the pipeline below. See §3.

---

## 1. Per-function cyclomatic complexity

### ESLint's `complexity` rule

The rule is a threshold gate, not a metrics reporter, by design: "This rule is
aimed at reducing code complexity by capping the amount of cyclomatic
complexity allowed in a program. As such, it will warn when the cyclomatic
complexity crosses the configured threshold."
(https://eslint.org/docs/latest/rules/complexity)

But the rule's own source shows it always computes the exact value and only
gates *reporting* on it, and the message template embeds that value:

```
"{{name}} has a complexity of {{complexity}}. Maximum allowed is {{max}}."
```

reported from `onCodePathEnd` whenever `complexity > threshold`
(https://raw.githubusercontent.com/eslint/eslint/main/lib/rules/complexity.js).
So `{"rules": {"complexity": ["warn", 0]}}` forces a report for effectively
every function (complexity is always ≥ 1), and each report's `message` string
contains the real number. Run with the built-in JSON formatter — "The `json`
formatter is useful when you want to programmatically work with the CLI's
linting results," emitting `ruleId`/`severity`/`message`/`line`/`column` per
finding (https://eslint.org/docs/latest/use/formatters/) — then regex the
complexity value out of `message`, or read `messageId`/`data` if you use the
Node API directly instead of the CLI formatter. This is a documented,
officially-maintained path with no forked rule or custom traversal, at the
cost of parsing the number out of a message string rather than getting a
first-class field.

### `typhonjs-escomplex`

Registry metadata: latest version **0.1.0**, last modified **2018-12-21**,
description "Next generation complexity reporting for Javascript & Typescript
based on the Babel parser" (https://registry.npmjs.org/typhonjs-escomplex).
Despite the description name-checking TypeScript, and despite still pulling
non-trivial weekly downloads (34,774 for the week of 2026-08-23 per
https://api.npmjs.org/downloads/point/last-week/typhonjs-escomplex, likely
mostly transitive/CI pulls rather than direct new adoption), a single 2018
publish with no subsequent release is effectively unmaintained. It needs a
Babel parse (not the TS compiler) for TS support, so decorators/newer syntax
support is whatever that pinned Babel config handled seven years ago.

### ts-morph-based custom walk

ts-morph itself is scoped to "Setup, navigation, and manipulation of the
TypeScript AST" via a wrapped compiler API (https://ts-morph.com) — no
built-in complexity metric; a per-function cyclomatic-complexity walk would be
bespoke (count decision points: `if`/`for`/`while`/`case`/`catch`/`&&`/`||`/
`??`/ternary, +1 per function). This pattern is common enough that multiple
small packages already do it instead of you writing it from scratch:

- **`ts-complex`** (https://github.com/anandundavia/ts-complex) — "Calculates
  Halstead Matrices, Cyclomatic Complexity and Maintainability for
  Typescript," explicitly "Inspired from 'typhonjs-escomplex'." Latest
  version **1.0.0**, published **2022-05-22**
  (https://registry.npmjs.org/ts-complex), computing per-function complexity.
  Low weekly downloads (804 for 2026-08-23,
  https://api.npmjs.org/downloads/point/last-week/ts-complex) but more recent
  than typhonjs-escomplex and purpose-built for TS.
- **`cyclomatic-complexity`** (https://github.com/pilotpirxie/cyclomatic-complexity)
  — latest **1.2.5**, published **2024-10-05**
  (https://registry.npmjs.org/cyclomatic-complexity), ships TS type defs and
  a native JSON mode: `npx cyclomatic-complexity './src/**/*.ts'
  --threshold-warnings 10 --threshold-errors 20 --json` returns a
  `functionComplexities` array of `{name, complexity, line}` — a real
  first-class per-function JSON emitter, and the most recently published of
  the complexity options checked here.
- **`complexity-report`** — per npm search results it is "a node.js-based
  command-line wrapper around escomplex," and "since escomplex does not
  directly support TypeScript, you have two options: use a TypeScript-compatible
  alternative, or compile your TypeScript to JavaScript first" — i.e. not a
  direct TS solution.

### Recommendation

Primary: **ESLint `complexity` rule at `max: 0` + `--format json`**, parsing
the number out of each message — zero new runtime dependency if ESLint is
already in the repo, officially maintained, and the "hack" (threshold 0) is a
one-line config change with no forked rule code.

If a first-class numeric field (not string-embedded) is required, or ESLint
isn't already wired into the repo: **`cyclomatic-complexity`** (npm) —
actively published (Oct 2024), TS-aware, and has a native `--json` per-function
array. Fallback ranking: ESLint(`max:0`) → `cyclomatic-complexity` →
`ts-complex` → bespoke ts-morph walk → `typhonjs-escomplex` (last resort,
unmaintained since 2018).

---

## 2. Per-function statement + branch coverage attribution

### Istanbul's coverage-final.json schema

Per Istanbul's own schema doc
(https://github.com/gotwarlost/istanbul/blob/master/coverage.json.md):

- `fnMap` — "Hash of functions where keys are function IDs... and values are
  `{name, line, loc, skip}`," where `loc` is the function *declaration's*
  Location, not its body range.
- `f` — "Hash of function counts, where keys are function IDs" (hit counts
  per function — this is your per-function *execution* signal, i.e. was the
  function called and how many times).
- `branchMap` — keys are branch IDs, values `{line, type, locations}` (an
  array of Location objects per possible outcome — if/else arms, switch
  cases, `&&`/`||` short-circuits, ternary arms).
- `b` — "Hash of branch counts, where keys are branch IDs and values are
  arrays of counts" (one count per branch outcome/arm).
- `statementMap` — keys are statement IDs, values are Location objects per
  statement.
- `s` — "Hash of statement counts, where keys as statement IDs."
- All IDs are "sequential integers, starting at 1." Location objects are
  `{start: {line, column}, end: {line, column}}`, line 1-based, column
  0-based.

**Statements are not directly keyed by function.** The schema doc gives no
documented join field between `statementMap`/`s` entries and `fnMap` entries —
confirmed by direct inspection of the schema doc, which defines the two maps
independently and states nothing about attribution
(https://github.com/gotwarlost/istanbul/blob/master/coverage.json.md). The
only way to compute **per-function statement coverage** is to do the spatial
join yourself: for each function in `fnMap`, take its `loc` range (or, more
robustly, derive the function body's full range separately since `fnMap.loc`
is documented as the *declaration* location, not guaranteed to bound the
whole body — verify against your instrumenter's actual output rather than
assume), then select every `statementMap` entry whose Location falls inside
that range, and average their `s` hit/no-hit counts. **Per-function branch
coverage** is the same join against `branchMap`/`b` instead. So: "is `fnMap`/`f`
plus `branchMap`/`b` sufficient" — no, not for the statement half; `f` alone
only tells you whether/how often the function itself was entered, not
statement-level completeness inside it. You need `statementMap`/`s`
cross-referenced by location, and there is no documented Istanbul-provided
helper that does this join for you.

### Exact commands

**Vitest** (https://vitest.dev/guide/coverage): the provider must be set to
`istanbul` to get this exact `fnMap`/`branchMap`/`statementMap` shape — the
default provider is `v8`.

```ts
// vitest.config.ts
export default defineConfig({
  test: {
    coverage: {
      enabled: true,
      provider: 'istanbul',
      reporter: ['json'], // emits coverage/coverage-final.json
    },
  },
})
```
```
vitest run --coverage
```

**Jest** (https://jestjs.io/docs/configuration#coverageprovider-string): the
default provider, `babel`, is Istanbul-instrumented and produces this schema
directly — "Indicates which provider should be used to instrument code for
coverage. Allowed values are `babel` (default) or `v8`."

```
jest --coverage --coverageReporters=json
```

`coverageReporters` defaults include `json`
(`["clover", "json", "lcov", "text"]`) and "Any istanbul reporter can be
used" (same page), and this writes `coverage/coverage-final.json` in the raw
schema above.

### Known gaps

- **Arrow functions in `fnMap`.** The Istanbul schema doc's `fnMap` entry
  format (`{name, line, loc, skip}`) is generic across function forms and the
  schema text does not carve out arrow functions as a special case
  (https://github.com/gotwarlost/istanbul/blob/master/coverage.json.md); in
  practice Istanbul-family instrumenters register every function-like node —
  declarations, expressions, and arrow functions — as its own `fnMap` entry,
  but this was not independently confirmed from a schema-level primary source
  in this pass; verify against a real `coverage-final.json` from your repo
  before trusting arrow-function attribution, especially for concise-body
  arrows (`() => x`) versus block-body arrows.
- **Source-map remapping when TS is transpiled.** Both Jest's `babel`
  provider and Vitest's `istanbul` provider instrument code before/around the
  TS→JS transform, so line/column numbers in `fnMap`/`statementMap`/
  `branchMap` should already be in original-TS coordinates via the
  instrumenter's own transform step rather than needing a separate remap —
  but this claim rests on the providers' documented instrumentation
  descriptions ("Coverage tracking works by transforming your source code to
  add instrumentation logic," Vitest coverage guide) rather than a schema
  spec that states coordinate space explicitly; treat any mismatch between
  reported line numbers and actual `.ts` source as a signal to check the
  transform pipeline (ts-jest / babel preset ordering) rather than assume
  it's handled.
- **`v8`/`c8` provider vs `istanbul` provider shape.** Vitest's docs describe
  the mechanics but not schema equivalence: v8's provider works via
  "`node:inspector`," has "No pre-transpile step," and "Coverage report
  accuracy is as good as with Istanbul (since Vitest v3.2.0)," while istanbul
  "transform[s] your source code to add instrumentation logic" before running
  (https://vitest.dev/guide/coverage) — the docs fetched in this pass do not
  state whether v8's output, once remapped, is byte-for-byte the same
  `fnMap`/`branchMap` JSON shape as istanbul's, only that accuracy is
  comparable as of v3.2.0. Separately, `c8`
  (https://github.com/bcoe/c8) is explicitly built to make V8's native
  coverage "compatible with Istanbul's reporters," i.e. it's a V8→Istanbul-report
  bridge, not proof the two providers' raw per-function branch counts are
  computed identically — c8's README documents reporter compatibility, not a
  schema equivalence guarantee. **Given this uncertainty, prefer the
  `istanbul` provider explicitly (Vitest) / `babel` provider (Jest, default)
  over `v8` for a CRAP pipeline that reads `coverage-final.json` directly**,
  since those are the two documented to natively emit this schema.

---

## 3. Is `@barney-media/crap-typescript-core` real and reusable?

**Yes, it's real, current, and does close to exactly this task.**

- npm registry confirms the package exists: latest version **0.5.1**,
  published **2026-08-29**
  (https://registry.npmjs.org/@barney-media/crap-typescript-core), with 10
  published versions (0.2.0 → 0.5.1) showing a real release cadence, not a
  one-off publish. Description: "Core CRAP metric analyzer for TypeScript
  projects. Combines cyclomatic complexity with function-level Istanbul
  coverage data." Weekly downloads: 3,081 for the week of 2026-08-23
  (https://api.npmjs.org/downloads/point/last-week/@barney-media/crap-typescript-core).
  License Apache-2.0.
- Its GitHub repo, https://github.com/fabian-barney/crap-typescript, shows
  active maintenance: last push **2026-09-03** (today), 358 commits on main,
  16 stars, 1 fork, 2 open issues, created 2026-04-03
  (https://api.github.com/repos/fabian-barney/crap-typescript). This is a
  young (~5 month old) but currently-active project, not abandoned.
- Per its README (https://raw.githubusercontent.com/fabian-barney/crap-typescript/main/README.md):
  it implements the exact same formula as this ticket,
  `CRAP = CC^2 * (1 - coverage)^3 + CC`, reads `coverage/coverage-final.json`
  from the module root and uses Istanbul's `fnMap` "for validation when
  present," ships a CLI (`npx crap-typescript`) plus dedicated Vitest and Jest
  adapters with test-runner auto-detection, supports `--format` of
  toon/json/text/junit/none, a configurable `--threshold` (default 6.0, with
  warnings if set below 4.0 or above 8.0), a `--changed`-only mode, and
  exclusion filters. It does not document (in the README fetched) which
  library it uses internally to compute cyclomatic complexity.
- Given it's a young single-maintainer package (per the repo, one apparent
  primary author) with only 16 stars, treat it as a plausible **build vs
  buy** candidate rather than an automatic default: evaluate it directly
  against a real repo's `coverage-final.json` before committing, since its
  complexity-computation internals weren't verifiable from the README alone
  in this pass.

**Other npm packages checked:**

- **`crap`** on npm (https://registry.npmjs.org/crap) exists but is
  unrelated: latest version 5.1.0, published 2016-04-05, is "Ⓒontrollers
  Ⓡesources Ⓐnd ⓟroviders framework" — a dependency-injection/module-loading
  framework for Node (repo https://github.com/Tinder/crap), nothing to do
  with the CRAP metric. Not usable for this ticket.
- **`jest-it-up`** or similar CRAP-for-JS naming — no such package surfaced in
  the npm registry lookups or GitHub/npm searches performed in this pass;
  treat as not existing until directly confirmed otherwise.

---

## Known gaps (all in one place)

1. **Arrow-function attribution in `fnMap`** is plausible-but-unverified from
   a schema-level primary source — confirm against a real
   `coverage-final.json` before trusting concise-body arrow coverage
   numbers.
2. **Source-map / line-coordinate space** for `fnMap`/`statementMap`/
   `branchMap` when TS is transpiled is asserted by the instrumentation
   providers' own descriptions, not an explicit schema field — verify
   reported line numbers land on real `.ts` source lines for your specific
   ts-jest/babel pipeline.
3. **`v8`/c8 vs `istanbul` provider schema equivalence** is not proven
   identical by any source fetched here — only "compatible with Istanbul's
   reporters" (c8) and "accuracy is as good as … since Vitest v3.2.0"
   (Vitest docs), neither of which is a byte-for-byte schema guarantee. Use
   the `istanbul`/`babel` providers explicitly for a pipeline that parses
   `coverage-final.json` directly.
4. **No documented Istanbul-native statement→function join.** `statementMap`
   has no function-ID field; per-function statement coverage requires a
   hand-rolled spatial join against `fnMap` location ranges — build and test
   this join carefully, especially around nested functions (a statement
   inside an inner function must not be double-counted against the outer
   function's coverage).
5. **`@barney-media/crap-typescript-core`'s internal complexity engine is
   undocumented** in its README — if adopting it, verify empirically (e.g.
   against a known-complexity fixture function) rather than assuming it
   matches classic McCabe cyclomatic complexity or matches ESLint's
   `complexity` rule's counting rules exactly.
