# Prompt audit 2026-09-27 — cluster `implement-lane`

Skills: `implement`, `implement-spec`. 16 findings.
Hunks are proposals written against `main` at 9a1c304; re-read the current line before applying. Where a finding has no hunk, write the edit from its action and ruling.
Target model for every judgment: Claude Opus 5.5. Method: the bundled `claude-api` skill's `shared/prompt-audit.md`.

## `batch-5:L12` — implement/*.test.sh (turn-end, worker-hygiene, codex-pass-schedule)

- **Confidence:** Low
- **Pattern:** G1d patch accretion
- **Evidence:** `check '#1095'`, `check 'PR 908 went up carrying #886'"'"'s body'`
- **Why:** Prose-assertion tests pin incident narratives into the prompt, so no narrative can be removed without its test line. Assert on the rule text, not the incident.
- **Action:** flag
- **Ruling:** Chris ruled: **strip** dated incident notes, and edit any test that pins the removed wording in the same change.

_No hunk — write the edit._

## `batch-5:L1` — implement/SKILL.md:73-74, 114-116, 255-256, 263-264, 366-367, 414-416 and the remaining bare `(#NNN)` citations

- **Confidence:** Low
- **Pattern:** G2 history narrative
- **Evidence:** e.g. "(`caneff/sudokumaker-custom-constraints#522`: two required items sat in a two-day-old comment …)"
- **Why:** This is the same class as M9-M16. Several are test-pinned, and the style is a house convention. Hunks are available on request.
- **Action:** flag
- **Ruling:** Chris ruled: **strip** dated incident notes, and edit any test that pins the removed wording in the same change.

_No hunk — write the edit._

## `batch-5:M16` — implement/SKILL.md:125-128

- **Confidence:** Medium
- **Pattern:** G2 history narrative
- **Evidence:** "Another session overwrote a shared `pr-body.md` … PR 908 went up carrying #886's body …; only luck left #886 open to nobody's harm (#909)."
- **Why:** Restate it as the mechanism, which is why the file name must be ticket-specific.
- **Action:** rewrite (hunk + test hunk)
- **Ruling:** Chris ruled: **strip** dated incident notes, and edit any test that pins the removed wording in the same change.

```diff
--- a/implement/SKILL.md
+++ b/implement/SKILL.md
@@ -124,5 +124,5 @@
   `merge-cleanup` refuse the removal on every heavy landing, and the
-  controller re-ran it with `--discard` by hand (#1052). Another session
-  overwrote a shared `pr-body.md` between its write and `gh pr create`, and
-  PR 908 went up carrying #886's body and a `Closes #886`; only luck left #886
-  open to nobody's harm (#909).
+  controller re-ran it with `--discard` by hand (#1052). The name is
+  ticket-specific because a shared `pr-body.md` can be overwritten by
+  another session between the write and `gh pr create`, and the PR then
+  goes up with another ticket's body and closes that ticket instead.
--- a/implement/worker-hygiene-wording.test.sh
+++ b/implement/worker-hygiene-wording.test.sh
@@ -37 +37 @@
-check 'PR 908 went up carrying #886'"'"'s body'
+check 'can be overwritten by another session between the write and `gh pr create`'
```

## `batch-5:M12` — implement/SKILL.md:153-155

- **Confidence:** Medium
- **Pattern:** G2 history narrative
- **Evidence:** "#1095's worker committed its fix, ran the gate and ended its turn … only because Chris asked (#1148)."
- **Why:** The rule and its mechanism (the stop hook, the `stalled` backstop) stand without the incident.
- **Action:** rewrite (hunk + test hunk)
- **Ruling:** Chris ruled: **strip** dated incident notes, and edit any test that pins the removed wording in the same change.

```diff
--- a/implement/SKILL.md
+++ b/implement/SKILL.md
@@ -151,8 +151,6 @@
 **Your turn ends mid-lane only on a message to the controller**: a question,
 a job declaration, or "PR up". A summary in your own pane reaches no one.
-#1095's worker committed its fix, ran the gate and ended its turn with review,
-verification and the PR undone; herdr showed its pane `done`, and the
-controller found it ten minutes later only because Chris asked (#1148). The
+herdr shows such a pane `done` while review, verification and the PR sit
+undone. The
 stop hook alerts the controller on such a stop, and a burn's sweep reads the
--- a/implement/turn-end-wording.test.sh
+++ b/implement/turn-end-wording.test.sh
@@ -33,3 +33,2 @@
 check 'A summary in your own pane reaches no one'
-check '#1095'
 check '`stalled`'
```

## `batch-5:M15` — implement/SKILL.md:489-491, 500-502

- **Confidence:** Medium
- **Pattern:** G2 history narrative
- **Evidence:** "(#456 reported CLEAN at a sha two pushes stale …)" / "4 of 7 reports in the #781 burn carried a tip past the reviewed sha …"
- **Why:** Both follow a reason that is already stated.
- **Action:** remove (hunk)
- **Ruling:** Chris ruled: **strip** dated incident notes, and edit any test that pins the removed wording in the same change.

```diff
--- a/implement/SKILL.md
+++ b/implement/SKILL.md
@@ -488,4 +488,2 @@
   re-checks and is the only authority; naming the sha makes the staleness
-  explicit instead of a race this report silently loses. (#456 reported
-  CLEAN at a sha two pushes stale; the PR read UNSTABLE seconds later — one
-  controller wake.)
+  explicit instead of a race this report silently loses.
@@ -499,4 +497,2 @@
   check against the PR; a bare list of classes it cannot. That is what lets
-  it rule on another review round without diffing it blind. 4 of 7 reports
-  in the #781 burn carried a tip past the reviewed sha, and the controller
-  diffed each one by hand.
+  it rule on another review round without diffing it blind.
```

## `batch-5:M13` — implement/SKILL.md:508-511

- **Confidence:** Medium
- **Pattern:** G2 history narrative
- **Evidence:** "#351's worker ran a `verify.py` that hard-codes an 8-worker CP-SAT portfolio, at ~793% CPU; box load hit 25.8 …"
- **Why:** The incident can be kept as a one-clause reason. The same numbers already live in `burndown/references/liveness.md`.
- **Action:** rewrite (hunk)
- **Ruling:** Chris ruled: **strip** dated incident notes, and edit any test that pins the removed wording in the same change.

```diff
--- a/implement/SKILL.md
+++ b/implement/SKILL.md
@@ -507,6 +507,5 @@
   that launched nothing and a worker that forgot to say produce the same
-  silence, and the controller charges zero for both. #351's worker ran a
-  `verify.py` that hard-codes an 8-worker CP-SAT portfolio, at ~793% CPU;
-  box load hit 25.8 with **no dispatch pending**, so no box check could
-  have caught it. Declare the job's own core count, not the load you
-  observed.
+  silence, and the controller charges zero for both. A script that
+  hard-codes its own worker pool loads the box with no dispatch pending,
+  so no box check catches it. Declare the job's own core count, not the
+  load you observed.
```

## `batch-5:M14` — implement/SKILL.md:518-522

- **Confidence:** Medium
- **Pattern:** G2 history narrative
- **Evidence:** "on 2026-09-20 three workers each running three review axes … took the box from 12 claude processes to 35 …"
- **Why:** "So `none` means none" already carries the rule.
- **Action:** rewrite (hunk)
- **Ruling:** Chris ruled: **strip** dated incident notes, and edit any test that pins the removed wording in the same change.

```diff
--- a/implement/SKILL.md
+++ b/implement/SKILL.md
@@ -517,6 +517,3 @@
   as any other. So `none` means none, not "none of the kind I had in
-  mind": on 2026-09-20 three workers each running three review axes plus a
-  verification pass took the box from 12 claude processes to 35, and the
-  first report to carry this field declared `none` while four of its own
-  subagents were the overrun.
+  mind": three review axes plus a verification pass are four processes.
```

## `batch-5:M11` — implement/SKILL.md:585-589

- **Confidence:** Medium
- **Pattern:** G2 history narrative
- **Evidence:** "Three of map #776's disputes were exactly that: PR #930's merge-tail pointer was in PR #929, …"
- **Why:** The PR-by-PR list adds nothing that "what it cannot see, it reports as a missing requirement" does not already say.
- **Action:** rewrite (hunk)
- **Ruling:** Chris ruled: **strip** dated incident notes, and edit any test that pins the removed wording in the same change.

```diff
--- a/implement/SKILL.md
+++ b/implement/SKILL.md
@@ -584,6 +584,4 @@
    controller knows that the tree does not say is invisible to it — and
-   what it cannot see, it reports as a missing requirement. Three of map
-   #776's disputes were exactly that: PR #930's merge-tail pointer was in
-   PR #929, PR #940's four-bucket sentence was on `implement-898`, and
-   PR #945's `[high]` "tier tagger is unreachable from the active lane"
-   was the parked skill every ticket in that map lands into. Write both
+   what it cannot see — a split onto a sibling branch, a parked skill a
+   map lands into — it reports as a missing requirement. Write both
    lines with your file-write tool, into the same file, never interpolated
```

## `batch-5:M9` — implement/SKILL.md:666-669

- **Confidence:** Medium
- **Pattern:** G2 history narrative
- **Evidence:** "#1015 retired that early launch: measured on `burn-2026-09-21-0930`, 4 early launches raced … 0 were banked"
- **Why:** The rule's authority is its mechanism, not the measurement. Keep the reason in one clause.
- **Action:** rewrite (hunk + test hunk)
- **Ruling:** Chris ruled: **strip** dated incident notes, and edit any test that pins the removed wording in the same change.

```diff
--- a/implement/SKILL.md
+++ b/implement/SKILL.md
@@ -665,7 +665,6 @@
    **The pass launches once, here, at PR-up** — not earlier, at the
-   worker's round-1 report. #1015 retired that early launch: measured on
-   `burn-2026-09-21-0930`, 4 early launches raced against the worker's own
-   round-1 fix commits and 0 were banked, so every one was refused and
-   rerun here anyway, each costing its wall clock twice. Run the whole
+   worker's round-1 report: an earlier launch races the worker's own
+   round-1 fix commits, is refused as stale, and is rerun here anyway,
+   costing its wall clock twice. Run the whole
    block inline, in the foreground, as part of this step; each launch is
--- a/implement/codex-pass-schedule.test.sh
+++ b/implement/codex-pass-schedule.test.sh
@@ -66 +66 @@
-check_in "$merge_section" '4 early launches raced against the worker'"'"'s own' 'implement/SKILL.md § The merge'
+check_in "$merge_section" 'an earlier launch races the worker'"'"'s own' 'implement/SKILL.md § The merge'
```

## `batch-5:M8` — implement/SKILL.md:704-707

- **Confidence:** Medium
- **Pattern:** G1d migration-relative; G2 history
- **Evidence:** "Everything after that — … — is #888's, #812's and #1028's, unchanged by #1015."
- **Why:** This is a diff against an earlier version of the step. The steps that follow already state the current rule.
- **Action:** remove (hunk + test hunk)
- **Ruling:** Chris ruled: **strip** dated incident notes, and edit any test that pins the removed wording in the same change.

```diff
--- a/implement/SKILL.md
+++ b/implement/SKILL.md
@@ -702,6 +702,3 @@
    `gh pr comment <pr> --repo <owner/name> --body-file "$out_file"`, before
    acting on it. If `gh pr comment` fails, stop before merging — the
-   comment is what makes the verdict readable by anyone but you. Everything
-   after that — the dispositions, #888's conditional second pass (which
-   runs the same block with `phase=second`), the third-run ceiling, the
-   trial row — is #888's, #812's and #1028's, unchanged by #1015.
+   comment is what makes the verdict readable by anyone but you.
--- a/implement/codex-pass-schedule.test.sh
+++ b/implement/codex-pass-schedule.test.sh
@@ -121,3 +121,2 @@
 check_in "$merge_section" 'A collected verdict is this step' 'implement/SKILL.md § The merge'
-check_in "$merge_section" "is #888's, #812's and #1028's, unchanged by #1015" 'implement/SKILL.md § The merge'
 check_absent_in "$whole_file" 'unchanged by where the collected pass was launched' 'implement/SKILL.md (whole file)'
```

## `batch-5:H1` — implement/SKILL.md:719-721

- **Confidence:** High
- **Pattern:** G2 volatile specifics (stale fact)
- **Evidence:** "beside it `sha256sum "$body_file"`, taken before the `rm` above removes that file"
- **Why:** No `rm` exists above it. Commit 6b8b008 deleted `rm "$out_file" "$body_file"`, and line 660-661 now says "nothing here is cleaned up by hand, `rm` or `rmdir`, in any phase". The record written at 646-647 already stores `body_sha256`.
- **Action:** rewrite (hunk)
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/implement/SKILL.md
+++ b/implement/SKILL.md
@@ -718,6 +718,6 @@
    No material findings → go to step 4. Findings → hold the merge: send the
    worker the findings and the comment URL. Note the head sha this pass ran
-   against — step 2's `headRefOid` — and beside it `sha256sum "$body_file"`,
-   taken before the `rm` above removes that file. That sum covers the
+   against — step 2's `headRefOid` — and beside it the record's
+   `body_sha256`. That sum covers the
    appendix as well as the rendered ticket, both being in the one file, so
```

## `batch-5:M10` — implement/SKILL.md:764-770

- **Confidence:** Medium
- **Pattern:** G2 history narrative
- **Evidence:** "(#888: twice in the #781 burn — `sudokumaker-custom-constraints#559` at `203ac7a` … #882, cannot skip on an input that ignores one.)"
- **Why:** This is incident archaeology in the controller's merge step. 745-762 already state the rule and its reason.
- **Action:** remove (hunk)
- **Ruling:** Chris ruled: **strip** dated incident notes, and edit any test that pins the removed wording in the same change.

```diff
--- a/implement/SKILL.md
+++ b/implement/SKILL.md
@@ -762,11 +762,4 @@
    runs the second pass after all.
 
-   (#888: twice in the #781 burn — `sudokumaker-custom-constraints#559` at
-   `203ac7a`, `agent-skills#877` at `b96aa32` — the sha was unmoved and the
-   mandated run would have re-read an unchanged file. The ticket half has
-   its own incident: on 2026-09-20 every controller invocation of this pass
-   built its body file from the ticket body alone, no comments, against a
-   step that names both — a lane that treats a comment as a requirement,
-   #882, cannot skip on an input that ignores one.)
-
    When either moved, run this pass once more on the fixes, with
```

## `batch-5:H2` — implement/codex-lane.md:80-82

- **Confidence:** High
- **Pattern:** G2 volatile specifics (dead cross-reference)
- **Evidence:** "the same injection-safety and `--wait` rationale, as `implement/SKILL.md`'s Review step"
- **Why:** § Review holds no `--wait` or injection rationale. Both are in § The merge step 3 (SKILL.md:575-579 and 623-630).
- **Action:** rewrite (hunk)
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/implement/codex-lane.md
+++ b/implement/codex-lane.md
@@ -78,5 +78,5 @@
    Both carry `disable-model-invocation: true` (#814): the SlashCommand tool
    never reaches either for a dispatched worker. Invoke the plugin's own
    script instead of the slash command, for each — same commands, and the
-   same injection-safety and `--wait` rationale, as `implement/SKILL.md`'s
-   Review step:
+   same injection-safety and `--wait` rationale, as `implement/SKILL.md`
+   § The merge step 3:
```

## `batch-1:I3` — implement-spec/SKILL.md:15

- **Confidence:** Low
- **Pattern:** 2 / History narratives
- **Evidence:** "which is its single home (#779)"
- **Why:** Same.
- **Action:** flag
- **Ruling:** Chris ruled: **strip** dated incident notes, and edit any test that pins the removed wording in the same change.

_No hunk — write the edit._

## `batch-1:I2` — implement-spec/SKILL.md:66-69

- **Confidence:** Medium
- **Pattern:** 2 / History narratives (past tense)
- **Evidence:** "because the two things the closing worker was left to invent last time"
- **Why:** "last time" is a diff against a run the reader never saw; the rule stands on its present-tense reason.
- **Action:** rewrite (hunk)
- **Ruling:** Chris ruled: **strip** dated incident notes, and edit any test that pins the removed wording in the same change.

```diff
--- a/implement-spec/SKILL.md
+++ b/implement-spec/SKILL.md
@@ -66,4 +66,3 @@
 The spec's last slice, blocked by every other one. Its body is generated by
-[`closing_ticket.py`](closing_ticket.py), because the two things the closing
-worker was left to invent last time are exactly the two the generator
-refuses to omit:
+[`closing_ticket.py`](closing_ticket.py), which refuses to omit the two things
+a closing worker left to write it would otherwise invent:
```

## `batch-1:I1` — implement-spec/SKILL.md:91-94

- **Confidence:** Medium
- **Pattern:** 2 / History narratives
- **Evidence:** "the #781 spec run's three squash commits sat in a range with ~17 commits nobody in that spec wrote"
- **Why:** The same incident is the evidence in references/closing-ticket.md:70-73, which the SKILL.md already points to. The policy file only needs the reason.
- **Action:** rewrite (hunk)
- **Ruling:** Chris ruled: **strip** dated incident notes, and edit any test that pins the removed wording in the same change.

```diff
--- a/implement-spec/SKILL.md
+++ b/implement-spec/SKILL.md
@@ -90,5 +90,4 @@
 The closing ticket hands the review the **list of merge shas** — this run's
 landings, read off the run file — and **never a git range**. On a shared
-default branch the obvious range holds every other session's work: the #781
-spec run's three squash commits sat in a range with ~17 commits nobody in
-that spec wrote.
+default branch the obvious range holds every other session's work
+([`references/closing-ticket.md`](references/closing-ticket.md) has the run).
```
