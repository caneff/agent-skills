# Prompt audit 2026-09-27 — cluster `audits`

Skills: `all-audits`, `audit-instructions`, `burndown`, `crap-audit`, `duplication`, `improve-codebase-architecture`, `mutation-audit`, `ponytail-audit`, `test-audit`, `thermo-nuclear-code-quality-review`. 21 findings.
Hunks are proposals written against `main` at 9a1c304; re-read the current line before applying. Where a finding has no hunk, write the edit from its action and ruling.
Target model for every judgment: Claude Opus 5.5. Method: the bundled `claude-api` skill's `shared/prompt-audit.md`.

## `batch-4:18` — all-audits/harness/AUDIT-RUN.md:43

- **Confidence:** Low
- **Pattern:** G2 history narratives
- **Evidence:** "## The manifest (#559)"
- **Why:** The issue ID in a heading is archaeology. But the anchor `#the-manifest-559` is linked from HTML-REPORT.md:45, findings-schema.md:88 and crap-audit/SKILL.md:236 (outside batch), so a rename touches four files for little gain.
- **Action:** flag
- **Ruling:** Chris ruled: **strip** dated incident notes, and edit any test that pins the removed wording in the same change.

_No hunk — write the edit._

## `batch-4:7` — all-audits/harness/HTML-REPORT.md:34

- **Confidence:** High
- **Pattern:** G2 volatile specifics
- **Evidence:** "The report is a single self-contained HTML file in the OS temp directory."
- **Why:** `pagelib.page()` (pagelib.py:36-40) links `assets/base/base.css`, `callout.css` and `base.js`, and lines 17-20 of the same doc say `copy_assets` must write them beside the page. The report is a page plus a folder, not a single file.
- **Action:** rewrite (hunk below)
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/all-audits/harness/HTML-REPORT.md
+++ b/all-audits/harness/HTML-REPORT.md
@@ -34,2 +34,3 @@
-The report is a single self-contained HTML file in the OS temp directory. It
-opens offline, carries a working light/dark mode, and loads no external host.
+The report is an HTML page plus the `assets/` folder `copy_assets` writes
+beside it, in the OS temp directory. It opens offline, carries a working
+light/dark mode, and loads no external host.
```

## `batch-4:16` — audit-instructions/SKILL.md:55-56

- **Confidence:** Medium
- **Pattern:** G1f numeric output ceilings
- **Evidence:** "keep answers short, cap document length,"
- **Why:** The audit skill proposes adding length caps as "missing steering". Current guidance removes numeric caps in favor of audience framing, so this seeds the pattern the audit should remove.
- **Action:** rewrite: "cap document length" -> "say what length the reader needs"
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/audit-instructions/SKILL.md
+++ b/audit-instructions/SKILL.md
@@ -55,2 +55,2 @@
-Current models often want steering older files lack — keep answers short, cap document
-length, say how to update me while you work, hold the task scope, limit the helpers you
+Current models often want steering older files lack — keep answers short, say what
+length the reader needs, say how to update me while you work, hold the task scope, limit the helpers you
```

## `batch-2:M9` — burndown/SKILL.md:346-347

- **Confidence:** Medium
- **Pattern:** 1d migration-relative; G2 duplicate
- **Evidence:** "The retired per-repo `~/.cache/burndown/<repo>.progress` file is gone; nothing reads or writes one."
- **Why:** references/run-file.md:207-212 carries the retirement on purpose, and run-file-retirement.test.sh Rule 3 guards it there. The test does not assert the SKILL.md copy (Rule 2 checks only runfile.py/run-id path/herdr name/re-announce/reference link). The SKILL copy names a phantom alternative on every load.
- **Action:** remove from SKILL.md; keep the reference
- **Ruling:** Chris ruled: **strip** dated incident notes, and edit any test that pins the removed wording in the same change.

```diff
--- a/burndown/SKILL.md
+++ b/burndown/SKILL.md
@@ -344,6 +344,5 @@
 A worker is addressed by its **herdr agent name** throughout, because a WSL
 restart renames every Claude session and every brief hard-codes
-`--controller "<name>"`. The retired per-repo `~/.cache/burndown/<repo>.progress`
-file is gone; nothing reads or writes one. The contract, the JSON shape and the
+`--controller "<name>"`. The contract, the JSON shape and the
 resume procedure: [`references/run-file.md`](references/run-file.md).
 
```

## `batch-2:L3` — burndown/SKILL.md:396-398

- **Confidence:** Low
- **Pattern:** G2 history narrative
- **Evidence:** "#1095's worker committed, ran the gate and ended its turn with a summary to no one … (#1148)"
- **Why:** This is a narrative in the policy file. But liveness.test.sh:75 asserts `#1095` in SKILL.md § Liveness, so the repo enforces incident IDs inline on purpose. Removing it would mean changing that test.
- **Action:** flag
- **Ruling:** Chris ruled: **strip** dated incident notes, and edit any test that pins the removed wording in the same change.

_No hunk — write the edit._

## `batch-2:M10` — burndown/SKILL.md:459-461

- **Confidence:** Medium
- **Pattern:** G2 history narrative / duplicate
- **Evidence:** "On #781 that was three clue counts, one browser, no givens; it came back in minutes…"
- **Why:** SKILL.md:356-358 and :465-466 make the references the evidence home. parking.md:82-89 already tells this story. parking.test.sh:74-75 asserts only "bounded probe" and "before it escalates", and both survive the rewrite.
- **Action:** rewrite: pointer to `references/parking.md` § The bounded probe (heading exists)
- **Ruling:** Chris ruled: **strip** dated incident notes, and edit any test that pins the removed wording in the same change.

```diff
--- a/burndown/SKILL.md
+++ b/burndown/SKILL.md
@@ -457,7 +457,6 @@
 probe** from a worker before it escalates — a named, small, time-boxed
 measurement whose shape it states, so an abstract question reaches Chris as a
-table instead of three options in the dark. On #781 that was three clue
-counts, one browser, no givens; it came back in minutes and turned a spec
-question into a one-message ruling.
+table instead of three options in the dark
+([`references/parking.md`](references/parking.md) § The bounded probe).
 
 ## Before a controller rules
```

## `batch-2:M7` — crap-audit/SKILL.md:125

- **Confidence:** Medium
- **Pattern:** 1d migration-relative ("now")
- **Evidence:** "`normalize` now raises loudly"
- **Why:** Implies an earlier behaviour. audit.py:90/110 raise unconditionally.
- **Action:** rewrite: "raises"
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/crap-audit/SKILL.md
+++ b/crap-audit/SKILL.md
@@ -123,5 +123,5 @@
    relative path to both; an absolute `<scope>` here (e.g. from
    `$ARGUMENTS`) makes every radon key miss every coverage key, and
-   `normalize` now raises loudly on that rather than silently scoring
+   `normalize` raises loudly on that rather than silently scoring
    everything 0%/0%. That guard catches a *total* mismatch only — if some
    keys join and some don't (radon's scope is wider than coverage.py's
```

## `batch-2:M8` — crap-audit/SKILL.md:252

- **Confidence:** Medium
- **Pattern:** G2 history narrative
- **Evidence:** "`score()` — ticket 1's, unmodified —"
- **Why:** "ticket 1" is build-plan archaeology with no referent for a reader.
- **Action:** rewrite (diff)
- **Ruling:** Chris ruled: **strip** dated incident notes, and edit any test that pins the removed wording in the same change.

```diff
--- a/crap-audit/SKILL.md
+++ b/crap-audit/SKILL.md
@@ -249,6 +249,6 @@
 already-combined `cov`/`covKind` per method (which axis was lower), never
 both raw percentages — `normalize_ts` (`~/.agents/skills/crap-audit/audit.py`) fills the
-non-dominant axis with `100.0` (can't be the minimum), so `score()` —
-ticket 1's, unmodified — still reproduces the package's own `crap` value
+non-dominant axis with `100.0` (can't be the minimum), so the unmodified `score()`
+still reproduces the package's own `crap` value
 exactly. See `~/.agents/skills/crap-audit/fixtures/ts_sample_project/answer-key.md` for the
 full worked verification, including both `covKind: "N/A"` cases (missing
```

## `batch-3:2` — duplication/fixtures/answer-key.md:37

- **Confidence:** High
- **Pattern:** G2 Volatile specifics
- **Evidence:** `` `sample_a.py:13` `user_age_years` / `sample_b.py:19` `user_age_in_years` ``
- **Why:** The fixture defines `user_age_years` at `sample_a.py:19` and `user_age_in_years` at `sample_b.py:21`. A run checked against this key gets marked wrong on line numbers.
- **Action:** rewrite: `sample_a.py:19` / `sample_b.py:21`
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/duplication/fixtures/answer-key.md
+++ b/duplication/fixtures/answer-key.md
@@ -37 +37 @@
-| 2 | `sample_a.py:13` `user_age_years` / `sample_b.py:19` `user_age_in_years` | semantic-duplicate (pass two, not jscpd) | **consolidate** | Same fact (a user's age in years) decoded from the same stored data (`user["birth_date"]`) two different ways — one via plain year subtraction, one via `dateutil.relativedelta` on a parsed date. Token-different, so jscpd's clone matcher does not flag this pair; it's the semantic pass's job in `duplication/SKILL.md` to surface it as `category: semantic-duplicate`. |
+| 2 | `sample_a.py:19` `user_age_years` / `sample_b.py:21` `user_age_in_years` | semantic-duplicate (pass two, not jscpd) | **consolidate** | Same fact (a user's age in years) decoded from the same stored data (`user["birth_date"]`) two different ways — one via plain year subtraction, one via `dateutil.relativedelta` on a parsed date. Token-different, so jscpd's clone matcher does not flag this pair; it's the semantic pass's job in `duplication/SKILL.md` to surface it as `category: semantic-duplicate`. |
```

## `batch-2:H2` — improve-codebase-architecture/SKILL.md:61

- **Confidence:** High · **vendored:** mattpocock/skills
- **Pattern:** G2 contradiction / volatile specifics
- **Evidence:** "write to `<tmpdir>/architecture-review-<timestamp>.html` … falling back to `/tmp` (or `%TEMP%` on Windows)"
- **Why:** all-audits/harness/HTML-REPORT.md:36-38 (2026-09-07, newer than :61's 2026-09-03) says a skill writes `<tmpdir>/<skill>-<timestamp>/report.html` and needs no fallback note. :63 of the same skill then runs `copy_assets` "next to it", which lands `assets/` in the tmpdir root.
- **Action:** rewrite (diff). vendored: mattpocock/skills
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/improve-codebase-architecture/SKILL.md
+++ b/improve-codebase-architecture/SKILL.md
@@ -59,5 +59,5 @@
 ### 2. Present candidates as an HTML report
 
-Write a self-contained HTML file to the OS temp directory so nothing lands in the repo. Resolve the temp dir from `$TMPDIR`, falling back to `/tmp` (or `%TEMP%` on Windows), and write to `<tmpdir>/architecture-review-<timestamp>.html` so each run gets a fresh file. Open it for the user — `xdg-open <path>` on Linux, `open <path>` on macOS, `start <path>` on Windows — and tell them the absolute path.
+Write a self-contained HTML file to `<tmpdir>/improve-codebase-architecture-<timestamp>/report.html` so nothing lands in the repo and each run gets a fresh folder for the page and its copied assets. Tmpdir resolution, opening the report and handing off its path follow the harness HTML-REPORT.md.
 
 The report is styled with the **visual-teach** design system — the same vendored `vt-*` components and `--vt-*` theme tokens the teaching lessons use — so it opens offline, carries a working light/dark mode, and loads no external host. At render time, copy the assets the report uses next to it with `pagelib.copy_assets` (see the harness HTML-REPORT.md) and link them relatively. Use **Mermaid** (vendored, via the `mermaid.js` bridge) for graph-shaped structure — call graphs, dependencies, sequences — and hand-built `vt-diagram` divs/SVG for the editorial visuals (mass diagrams, cross-sections). Each candidate gets a **before/after visualisation**. Be visual — the diagrams carry the weight.
```

## `batch-5:H3` — mutation-audit/SKILL.md:62-67

- **Confidence:** High
- **Pattern:** G2 volatile specifics; G1c wrong degrees of freedom
- **Evidence:** "Walk the current directory (`os.walk`, skipping `.git`, `node_modules`, … and any dotdir) collecting `.py` paths, then: … `audit.py --suggest <scope>`"
- **Why:** `audit.py` main (line 448-450) takes a root and calls `auditlib.walk_source(root)`. That function prunes `EXCLUDED_DIRS` and dot-dirs itself, so the hand walk does nothing and its skip list can drift from `EXCLUDED_DIRS`.
- **Action:** rewrite (hunk)
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/mutation-audit/SKILL.md
+++ b/mutation-audit/SKILL.md
@@ -61,10 +61,9 @@
 
-   **No target — suggest, don't sweep.** Walk the current directory
-   (`os.walk`, skipping `.git`, `node_modules`, `dist`, `build`, `.venv`,
-   `venv`, `vendor`, `worktrees`, `mutants`, and any dotdir) collecting
-   `.py` paths, then:
+   **No target — suggest, don't sweep.** Pass the repo root; the script walks
+   it itself (`auditlib.walk_source`, which prunes `EXCLUDED_DIRS` and
+   dot-dirs):
```

## `batch-2:M1` — ponytail-audit/HTML-REPORT.md:19-28, 58-60

- **Confidence:** Medium
- **Pattern:** G2 volatile specifics (stale)
- **Evidence:** "Every card carries exactly one tag `vt-pill`, colored by kind" — the list has no `bloat:`
- **Why:** SKILL.md:25-28 added `bloat:` in 4480484 (2026-08-16, #379). The palette and token roles were never updated, so a bloat card has no defined badge.
- **Action:** add (diff, 2 hunks)
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/ponytail-audit/HTML-REPORT.md
+++ b/ponytail-audit/HTML-REPORT.md
@@ -27,4 +27,6 @@
   nobody sets, layer with one caller.
 - `shrink:` — `vt-pill neutral` (slate). Same logic, fewer lines.
+- `bloat:` — `vt-pill warn` (amber). A function or class ruff's `PLR` rules
+  flag as oversized; name the rule code. Split it along its actual seams.
 
 Put the monospaced file list after the badges (e.g. `verdict.py:51`).
```

```diff
--- a/ponytail-audit/HTML-REPORT.md
+++ b/ponytail-audit/HTML-REPORT.md
@@ -57,5 +57,5 @@
 
 Token roles for this card: `--vt-bad` for the before / the deleted, `--vt-good`
-for the after / the replacement, `--vt-warn` for `yagni`, `--vt-accent` for
+for the after / the replacement, `--vt-warn` for `yagni` and `bloat`, `--vt-accent` for
 `stdlib`/`native`. Widen the content column for the side-by-side before/after —
 set `main { --vt-measure: 1080px; }`, never `max-width`, in a local `<style>`.
```

## `batch-2:M2` — ponytail-audit/SKILL.md:78

- **Confidence:** Medium
- **Pattern:** 1d migration-relative phrasing
- **Evidence:** "Ranking is unchanged: **biggest cut first.**"
- **Why:** "Unchanged" refers to a pre-HTML version the model never saw. The rule is already stated at :13.
- **Action:** rewrite: "Rank **biggest cut first.**"
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/ponytail-audit/SKILL.md
+++ b/ponytail-audit/SKILL.md
@@ -76,5 +76,5 @@
 the deliberate redundancy.
 
-Ranking is unchanged: **biggest cut first.** The header carries the only metric
+Rank **biggest cut first.** The header carries the only metric
 that matters — `net: -<N> lines, -<M> deps possible` — and each card its own
 line count. Nothing to cut: a one-card report whose verdict is `Lean already.
```

## `batch-1:T3` — test-audit/SKILL.md:51, 65

- **Confidence:** Low
- **Pattern:** 2 / History narratives
- **Evidence:** "(#685)"
- **Why:** Incident IDs beside rules that already state their reason.
- **Action:** flag
- **Ruling:** Chris ruled: **strip** dated incident notes, and edit any test that pins the removed wording in the same change.

_No hunk — write the edit._

## `batch-1:T1` — test-audit/SKILL.md:258-262

- **Confidence:** High
- **Pattern:** 2 / Volatile specifics
- **Evidence:** "`answer-key.md` has the expected pass-one candidate list and the pass-two bucket for each test"
- **Why:** answer-key.md has no pass-one list and covers only 3 of the 5 fixture files (`test_pytest_smells.py`, `vitest_smells.test.js` are absent from it); no file in the repo writes the pass-one expectation down. A model told to "reproduce that table" will hunt for a list that does not exist.
- **Action:** rewrite (hunk)
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/test-audit/SKILL.md
+++ b/test-audit/SKILL.md
@@ -256,7 +256,9 @@
 ## Verify against the fixture
 
-`~/.agents/skills/test-audit/fixtures/` carries five files spanning the Cut/
-Rewrite/Keep buckets and the mechanical smells above (pytest and vitest).
-`~/.agents/skills/test-audit/fixtures/answer-key.md` has the expected pass-one
-candidate list and the pass-two bucket for each test. Running this skill over
-`~/.agents/skills/test-audit/fixtures/` should reproduce that table.
+`~/.agents/skills/test-audit/fixtures/` carries five files.
+`test_pricing.py`, `test_checkout_e2e.py` and `test_user_service.py` span the
+Cut/Rewrite/Keep buckets; `~/.agents/skills/test-audit/fixtures/answer-key.md`
+has the pass-two bucket for each of their tests, and a run over them should
+reproduce that table. `test_pytest_smells.py` and `vitest_smells.test.js`
+exist for pass one's scanners to flag; the answer key does not cover them.
```

## `batch-1:T2` — test-audit/fixtures/answer-key.md:21

- **Confidence:** High
- **Pattern:** 2 / Volatile specifics
- **Evidence:** "Tally: 2 Keep, 2 Cut, 6 Rewrite."
- **Why:** The table above it has 3 Cut (#2, #4, #9) and 5 Rewrite (#5, #6, #7, #8, #10). The key says the run "must reproduce this table exactly", so a correct run disagrees with the tally.
- **Action:** rewrite: `Tally: 2 Keep, 3 Cut, 5 Rewrite.`
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/test-audit/fixtures/answer-key.md
+++ b/test-audit/fixtures/answer-key.md
@@ -21 +21 @@
-Tally: 2 Keep, 2 Cut, 6 Rewrite.
+Tally: 2 Keep, 3 Cut, 5 Rewrite.
```

## `batch-2:M3` — thermo-nuclear-code-quality-review/HTML-REPORT.md:40

- **Confidence:** Medium · **vendored:** cursor/plugins
- **Pattern:** G2 contradiction (same skill)
- **Evidence:** category tag list includes `` `spaghetti` ``
- **Why:** :109 of the same file says "Do not put this skill's metaphors — … "spaghetti" … — into the card text". The category pill is card text.
- **Action:** rewrite: `spaghetti` → `branching`. vendored: cursor/plugins (local file)
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/thermo-nuclear-code-quality-review/HTML-REPORT.md
+++ b/thermo-nuclear-code-quality-review/HTML-REPORT.md
@@ -38,5 +38,5 @@
 - **Nit** — `vt-pill neutral` (grey). Cosmetic; listed only if it rides along cheaply.
 
-A second **category tag** — `vt-pill neutral outline sm` (`duplication`, `spaghetti`, `boundary`, `file-size`, `dead-abstraction`, `reliability`, `simplification`) — sits next to the badge so the reader can scan by kind. Put the file list after the badges in a monospaced span.
+A second **category tag** — `vt-pill neutral outline sm` (`duplication`, `branching`, `boundary`, `file-size`, `dead-abstraction`, `reliability`, `simplification`) — sits next to the badge so the reader can scan by kind. Put the file list after the badges in a monospaced span.
 
 ## Headline card
```

## `batch-2:M4` — thermo-nuclear-code-quality-review/HTML-REPORT.md:107

- **Confidence:** Medium
- **Pattern:** 1d migration-relative phrasing
- **Evidence:** "the same standard as the terminal review, not softened because it is now in a browser"
- **Why:** Diffs against an older terminal-only output. The rest of the sentence carries the rule.
- **Action:** rewrite (diff)
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/thermo-nuclear-code-quality-review/HTML-REPORT.md
+++ b/thermo-nuclear-code-quality-review/HTML-REPORT.md
@@ -105,5 +105,5 @@
 ## Tone
 
-Direct, serious, and demanding about quality — the same standard as the terminal review, not softened because it is now in a browser. Name the problem plainly. Do not hedge it into a mild suggestion. Rank without mercy: the headline and the Blockers come first; the Nits ride along at the bottom or not at all.
+Direct, serious, and demanding about quality. Name the problem plainly. Do not hedge it into a mild suggestion. Rank without mercy: the headline and the Blockers come first; the Nits ride along at the bottom or not at all.
 
 **Write the prose in Simplified Technical English** (see the SKILL.md "Write the review in plain language" section). Short sentences. One idea per sentence. Active voice, present tense. Use the **target repo's own domain terms** — its `CONTEXT.md` names them if it has one — instead of inventing new ones. Keep real technical terms (module, regex, atomic write). **Do not put this skill's metaphors — "code judo", "spaghetti", "seam leak" — into the card text.** A card that needs the dialect to be understood has failed; rewrite it.
```

## `batch-2:M5` — thermo-nuclear-code-quality-review/SKILL.md:21

- **Confidence:** Medium · **vendored:** cursor/plugins
- **Pattern:** 1a "Be thorough" row
- **Evidence:** "> Be extremely thorough and rigorous."
- **Why:** Opus 5.5 is thorough by default. Next to five other "be ambitious/push hard" lines, this booster over-applies and can inflate cosmetic findings, against :189-190.
- **Action:** remove (keep "Measure twice, cut once."). vendored: cursor/plugins
- **Ruling:** Chris ruled: **take** the tone edit in this vendored skill. `skills-safe-update` already carries it across upstream pulls (lockfile `skillFolderHash`, or `.extra-skills.json` `treeSha` for prompt-master).

```diff
--- a/thermo-nuclear-code-quality-review/SKILL.md
+++ b/thermo-nuclear-code-quality-review/SKILL.md
@@ -19,5 +19,5 @@
 > Work to improve abstractions, modularity, reduce Spaghetti code, improve succinctness and legibility.
 > Be ambitious, if there is a clear path to improving the implementation that involves restructuring some of the codebase, go for it.
-> Be extremely thorough and rigorous. Measure twice, cut once.
+> Measure twice, cut once.
 
 ## Non-Negotiable Additional Standards
```

## `batch-2:M6` — thermo-nuclear-code-quality-review/SKILL.md:112-132

- **Confidence:** Medium · **vendored:** cursor/plugins
- **Pattern:** 1c repetition as reinforcement; 1a pressure
- **Evidence:** "## What to Flag Aggressively … Escalate findings when you see:" (17 bullets)
- **Why:** Each bullet restates rule 0-7 (:27-69). The 1000-line rule appears five times (:34, :104, :118, :167, :248). The model reconciles near-duplicate wordings instead of applying one rule. Only two bullets are unique (:125 copy-paste, :128 "temporary" branching); they fold into rules 6 and 2.
- **Action:** rewrite (diff, 3 hunks). vendored: cursor/plugins
- **Ruling:** Chris ruled: **take** the tone edit in this vendored skill. `skills-safe-update` already carries it across upstream pulls (lockfile `skillFolderHash`, or `.extra-skills.json` `treeSha` for prompt-master).

```diff
--- a/thermo-nuclear-code-quality-review/SKILL.md
+++ b/thermo-nuclear-code-quality-review/SKILL.md
@@ -109,26 +109,4 @@
 - Is this logic living in the canonical layer, or did the diff leak details across a boundary?
 - Is this orchestration more sequential or less atomic than it needs to be?
-
-## What to Flag Aggressively
-
-Escalate findings when you see:
-
-- A complicated implementation where a cleaner reframing could delete whole categories of complexity.
-- Refactors that move code around but fail to reduce the number of concepts a reader must hold in their head.
-- A file crossing 1000 lines due to the PR, especially if the new code could be split out.
-- New conditionals bolted onto unrelated code paths.
-- One-off booleans, nullable modes, or flags that complicate existing control flow.
-- Feature-specific logic leaking into general-purpose modules.
-- Generic "magic" handling that hides simple structure and makes the code harder to reason about.
-- Thin wrappers or identity abstractions that add indirection without simplifying anything.
-- Unnecessary casts, `any`, `unknown`, or optional params that muddy the real contract.
-- Copy-pasted logic instead of extracted helpers.
-- Narrow edge-case handling implemented in the middle of an already busy function.
-- Refactors that technically pass tests but make the code less modular or less readable.
-- "Temporary" branching that is likely to become permanent debt.
-- Bespoke helpers where the codebase already has a canonical utility for the job.
-- Logic added in the wrong layer/package when it should live somewhere more central.
-- Sequential async flow where obviously independent work could stay simpler and clearer with parallel execution.
-- Partial-update logic that leaves state less atomic than necessary.
 
 ## Preferred Remedies
```

```diff
--- a/thermo-nuclear-code-quality-review/SKILL.md
+++ b/thermo-nuclear-code-quality-review/SKILL.md
@@ -61,5 +61,5 @@
 6. **Keep logic in the canonical layer and reuse existing helpers.**
    - Call out feature logic leaking into shared paths or implementation details leaking through APIs.
-   - Prefer existing canonical utilities/helpers over bespoke one-offs.
+   - Prefer existing canonical utilities/helpers over bespoke one-offs, and an extracted helper over copy-pasted logic.
    - Push code toward the right package, service, or module instead of normalizing architectural drift.
 
```

```diff
--- a/thermo-nuclear-code-quality-review/SKILL.md
+++ b/thermo-nuclear-code-quality-review/SKILL.md
@@ -43,4 +43,5 @@
    - Prefer pushing the logic into a dedicated abstraction, helper, state machine, policy object, or separate module instead of tangling an existing path.
    - Call out changes that make the surrounding code harder to reason about, even if they technically work.
+   - Treat "temporary" branching as permanent debt unless its removal is scheduled.
 
 3. **Bias toward cleaning the design, not just accepting working code.**
```

## `batch-2:H1` — thermo-nuclear-code-quality-review/SKILL.md:165-175

- **Confidence:** High · **vendored:** cursor/plugins
- **Pattern:** 1c example over-indexing; G2 contradiction
- **Evidence:** "Good phrases: … `more spaghetti` … `feature logic leaking into a shared path` … `a code-judo move here`"
- **Why:** Examples are the strongest signal, and Opus 5.5 matches their register. These lines (upstream, 2026-06-22) model the dialect that :218 and :226-227 (local, 2026-08-05, newer) ban from the review. The before/after at :224-227 already pins the wanted voice.
- **Action:** remove. vendored: cursor/plugins
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/thermo-nuclear-code-quality-review/SKILL.md
+++ b/thermo-nuclear-code-quality-review/SKILL.md
@@ -163,16 +163,4 @@
 If the implementation missed an opportunity for a dramatic simplification, say that clearly too.
 
-Good phrases:
-
-- `this pushes the file past 1k lines. can we decompose this first?`
-- `this adds another special-case branch into an already busy flow. can we move this behind its own abstraction?`
-- `this works, but it makes the surrounding code more spaghetti. let's keep the behavior and restructure the implementation.`
-- `this feels like feature logic leaking into a shared path. can we isolate it?`
-- `this abstraction seems unnecessary. can we just keep the direct flow?`
-- `why does this need a cast / optional here? can we make the boundary more explicit instead?`
-- `this looks like a bespoke helper for something we already have elsewhere. can we reuse the canonical one?`
-- `i think there's a code-judo move here that makes this much simpler. can we reframe this so these branches disappear?`
-- `this refactor moves complexity around, but doesn't really delete it. is there a way to make the model itself simpler?`
-
 ## Output Expectations
 
```
