# Prompt audit 2026-09-27 — cluster `review`

Skills: `flow`, `multi-axis-code-review`. 11 findings.
Hunks are proposals written against `main` at 9a1c304; re-read the current line before applying. Where a finding has no hunk, write the edit from its action and ruling.
Target model for every judgment: Claude Opus 5.5. Method: the bundled `claude-api` skill's `shared/prompt-audit.md`.

## `batch-5:M29` — flow/claude/agents/diff-reviewer.md:46-47

- **Confidence:** Medium
- **Pattern:** G1f numeric output ceiling
- **Evidence:** "return a summary under 60 lines, verdict first"
- **Why:** The same numeric-clamp pattern as M17. "verdict first, names that path" carries the operational need. **Affects all projects.**
- **Action:** rewrite (hunk)
- **Ruling:** Chris ruled: **remove** the numeric word caps.

```diff
--- a/flow/claude/agents/diff-reviewer.md
+++ b/flow/claude/agents/diff-reviewer.md
@@ -46,2 +46,2 @@
 **Write your full report to a file** at the path the caller names, then return
-a summary under 60 lines, verdict first, that names that path. `Write` is for
+a short summary, verdict first, that names that path. `Write` is for
```

## `batch-5:M30` — flow/claude/agents/diff-reviewer.md:60

- **Confidence:** Medium
- **Pattern:** follows M17
- **Evidence:** "Read your axis's brief and its word cap from § 4"
- **Why:** The reference goes dead if M17 is taken. **Affects all projects.**
- **Action:** rewrite (hunk; take together with M17)
- **Ruling:** Chris ruled: **remove** the numeric word caps.

```diff
--- a/flow/claude/agents/diff-reviewer.md
+++ b/flow/claude/agents/diff-reviewer.md
@@ -60 +60 @@
-Read your axis's brief and its word cap from § 4 of that file:
+Read your axis's brief from § 4 of that file:
```

## `batch-5:M19` — multi-axis-code-review/SKILL.md:94

- **Confidence:** Medium
- **Pattern:** G1d migration-relative
- **Evidence:** "the rest of this skill is unchanged"
- **Why:** This compares against a version of the skill the model never saw.
- **Action:** rewrite (hunk)
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/multi-axis-code-review/SKILL.md
+++ b/multi-axis-code-review/SKILL.md
@@ -94,3 +94,3 @@
-The capture block is in § 4; the rest of this skill is unchanged — step 2 reads
-the spec off the named commits' messages, and steps 3 to 5 do not know which
-mode produced the patch.
+The capture block is in § 4. Step 2 reads the spec off the named commits'
+messages, and steps 3 to 5 do not know which mode produced the patch.
```

## `batch-5:M20` — multi-axis-code-review/SKILL.md:168-170

- **Confidence:** Medium
- **Pattern:** G2 history narrative; authoring note leaked into a reviewer prompt
- **Evidence:** "the convention `~/.cache/agent-reviews/skills/verify-790-dispositions.md` already reaches for by hand; formalize it, don't invent a new one"
- **Why:** This sits inside the quoted text the reviewer receives. It is an instruction to the skill's author, not the reviewer. It also names a file in a directory the same skill prunes after 14 days.
- **Action:** rewrite (hunk)
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/multi-axis-code-review/SKILL.md
+++ b/multi-axis-code-review/SKILL.md
@@ -167,5 +167,3 @@
 finding a stable id — the axis's first letter (`S` standards, `P` spec, `C`
-correctness) plus a per-report ordinal, e.g. `S1`, `P2`, `C3` — the
-convention `~/.cache/agent-reviews/skills/verify-790-dispositions.md`
-already reaches for by hand; formalize it, don't invent a new one. Cite the
+correctness) plus a per-report ordinal, e.g. `S1`, `P2`, `C3`. Cite the
 same id in the prose report next to each finding, so a reader can join the
```

## `batch-5:M17` — multi-axis-code-review/SKILL.md:301, 307, 313, 590

- **Confidence:** Medium
- **Pattern:** G1b/G1f numeric output ceilings
- **Evidence:** "Under 550 words." / "Under 400 words." / "Under 450 words." / "Under 400 words."
- **Why:** Word caps starve reasoning on hard reviews. The correctness brief asks for five sub-reports, (a) to (e), inside 450 words. The full report goes to a file anyway.
- **Action:** rewrite (hunks; the line-313 edit is shown as a fragment)
- **Ruling:** Chris ruled: **remove** the numeric word caps.

```diff
--- a/multi-axis-code-review/SKILL.md
+++ b/multi-axis-code-review/SKILL.md
@@ -301 +301 @@
-… Write `Lean already.` if there is nothing to cut — the subsection is required even when empty. Under 550 words."
+… Write `Lean already.` if there is nothing to cut — the subsection is required even when empty. Findings and their evidence only, no preamble."
@@ -307 +307 @@
-… Quote the spec line for each finding. Check `docs/agents/defect-classes.md` by name. Under 400 words."
+… Quote the spec line for each finding. Check `docs/agents/defect-classes.md` by name. Findings and their evidence only, no preamble."
@@ -313 +313 @@  (fragment)
-Rate each bug PLAUSIBLE or CONFIRMED and say which. Under 450 words."
+Rate each bug PLAUSIBLE or CONFIRMED and say which. Findings and their evidence only, no preamble."
@@ -589,2 +589,2 @@
 reachable finding unchecked. Report every breach beside the finding it
-belongs to. Under 400 words."
+belongs to."
```

## `batch-5:M18` — multi-axis-code-review/SKILL.md:313

- **Confidence:** Medium
- **Pattern:** G2 history narrative inside a reviewer brief
- **Evidence:** "(2026-09-21: a mutation ran a toast installer for real and left a registry key pointing at a deleted `/tmp` worktree)"
- **Why:** Every correctness reviewer reads the incident. The rule before it ("stub that seam or skip … report it `unknown`") is complete without it.
- **Action:** remove (fragment)
- **Ruling:** Chris ruled: **strip** dated incident notes, and edit any test that pins the removed wording in the same change.

```diff
-stub that seam or skip the mutation and report it `unknown` (2026-09-21: a mutation ran a toast installer for real and left a registry key pointing at a deleted `/tmp` worktree). Rate each bug
+stub that seam or skip the mutation and report it `unknown`. Rate each bug
```

## `batch-5:L7` — multi-axis-code-review/SKILL.md:315-318, 363-364

- **Confidence:** Low
- **Pattern:** G1d migration-relative; G2 history
- **Evidence:** "(#939) … in #893, the zero-cores default in #894 …" / "The serial loop restored implicitly"
- **Why:** This is the same class as M21 and M22. It is lower value to fix.
- **Action:** flag
- **Ruling:** Chris ruled: **strip** dated incident notes, and edit any test that pins the removed wording in the same change.

_No hunk — write the edit._

## `batch-5:M21` — multi-axis-code-review/SKILL.md:325-328

- **Confidence:** Medium
- **Pattern:** G1d migration-relative; G2 history
- **Evidence:** "On 2026-09-20 a worker followed the wording this replaces, copied its tree with `cp -a`, …"
- **Why:** Keep the mechanism: a `git rm --cached` in the copy stages in the real index. Drop the incident.
- **Action:** rewrite (hunk)
- **Ruling:** Chris ruled: **strip** dated incident notes, and edit any test that pins the removed wording in the same change.

```diff
--- a/multi-axis-code-review/SKILL.md
+++ b/multi-axis-code-review/SKILL.md
@@ -324,6 +324,4 @@
 Reviews in this lane always run on a linked worktree, so the copy is not weaker
-isolation — it is none. On 2026-09-20 a worker followed the wording this
-replaces, copied its tree with `cp -a`, and two `git rm --cached` runs inside
-the "isolated" copy staged deletions in the real checkout's index; it noticed
-only because those two mutations happened to be staged ones. A worktree has its
+isolation — it is none: a `git rm --cached` inside the copy stages a deletion
+in the real checkout's index. A worktree has its
 own index and HEAD, so the same command cannot reach the checkout, and `git
```

## `batch-5:H5` — multi-axis-code-review/SKILL.md:331

- **Confidence:** High
- **Pattern:** G2 volatile specifics
- **Evidence:** "costs no copy of the 419 MB / 529 tracked files this repo carries"
- **Why:** `git ls-files \| wc -l` = 673, and `.git` = 21M.
- **Action:** rewrite (hunk)
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/multi-axis-code-review/SKILL.md
+++ b/multi-axis-code-review/SKILL.md
@@ -330,2 +330,2 @@
 clone --no-hardlinks` is the other safe answer. Sharing the object store also
-costs no copy of the 419 MB / 529 tracked files this repo carries. `HEAD` is
+costs no copy of the tracked tree. `HEAD` is
```

## `batch-5:M22` — multi-axis-code-review/SKILL.md:338-344

- **Confidence:** Medium
- **Pattern:** G1d migration-relative; G2 history
- **Evidence:** "The serial reading was an artefact of the brief being written as a list of steps … that correctness pass took 22 minutes."
- **Why:** The paragraph argues against a previous version of the rule. The first sentence (338) already states the rule.
- **Action:** remove (hunk)
- **Ruling:** Chris ruled: **strip** dated incident notes, and edit any test that pins the removed wording in the same change.

```diff
--- a/multi-axis-code-review/SKILL.md
+++ b/multi-axis-code-review/SKILL.md
@@ -337,8 +337,1 @@
 costs one covering-suite run of wall clock instead of one per mutated test.
-The serial reading was an artefact of the brief being written as a list of
-steps; nobody established it as a constraint. Measured on
-`caneff/sudokupad-art` on 2026-09-20: `test_retro_waves.py` is 31.96s of a
-33.9s suite (378 of 602 tests, everything else 0.91s), and the recent work is
-in that file, so the covering suite is the slow one. A diff adding ten tests
-paid five minutes before the reviewer read anything, and that correctness pass
-took 22 minutes.
```

## `batch-5:H6` — multi-axis-code-review/SKILL.md:539-540

- **Confidence:** High
- **Pattern:** G2 volatile specifics
- **Evidence:** "`bash tests/all.sh` is 2m51s wall over 62 suites here"
- **Why:** `bash tests/all.sh --list` prints 94 suites today. The wall time is unverified and goes stale the same way.
- **Action:** rewrite (hunk)
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/multi-axis-code-review/SKILL.md
+++ b/multi-axis-code-review/SKILL.md
@@ -537,5 +537,5 @@
 *Scope.* Re-run the suite that covers the mutated test — the file it lives in,
 run the way `tests/all.sh` would run it (`bash <name>.test.sh`, `python3
-<name>_test.py`) — not the whole gate. `bash tests/all.sh` is 2m51s wall over
-62 suites here, so a diff adding five tests would pay it five times inside one
+<name>_test.py`) — not the whole gate. `bash tests/all.sh` runs every suite in
+the repo, so a diff adding five tests would pay it five times inside one
 axis, while the covering suite finishes in seconds. The whole gate belongs to
```
