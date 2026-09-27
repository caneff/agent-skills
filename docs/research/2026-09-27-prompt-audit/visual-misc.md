# Prompt audit 2026-09-27 — cluster `visual-misc`

Skills: `create-lmd-page`, `setup-python-repo`, `skills-safe-update`, `sm-link`, `visual-plan`, `visual-recap`, `visual-teach`. 13 findings.
Hunks are proposals written against `main` at 9a1c304; re-read the current line before applying. Where a finding has no hunk, write the edit from its action and ruling.
Target model for every judgment: Claude Opus 5.5. Method: the bundled `claude-api` skill's `shared/prompt-audit.md`.

## `batch-3:3` — create-lmd-page/SKILL.md:67

- **Confidence:** High
- **Pattern:** G2 Volatile specifics
- **Evidence:** `Headings at font-size: 120% match LMD's in-box H2 sizing; the caption's #888 matches LMD metadata lines`
- **Why:** `reference/template.md` has no 120% heading. Its caption is `#557` bold "Play Now!" (template.md:34). Git history shows that the `80%`/`#888` caption span was removed and this line was left behind. It describes styles the model is not supposed to emit.
- **Action:** remove
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/create-lmd-page/SKILL.md
+++ b/create-lmd-page/SKILL.md
@@ -66,3 +66,2 @@
 - Background `#eef` and border `#ddf` match LMD's sidebar boxes and image borders; `border-radius: 5px` matches LMD's `.box`.
-- Headings at `font-size: 120%` match LMD's in-box `H2` sizing; the caption's `#888` matches LMD metadata lines (e.g. "eingestellt von...").
 - Use `%`/`px` units like the site does, not `rem` (site font-size is 90%, so rem values don't line up).
```

## `batch-3:1` — setup-python-repo/SKILL.md:29

- **Confidence:** High
- **Pattern:** G2 Volatile specifics
- **Evidence:** `uv init --lib --name <pkg>      # src layout + hatchling + py.typed`
- **Why:** The same file contradicts it: line 43 says `uv init --lib` "uses the `uv_build` backend". `templates/pyproject-snippet.toml:55` configures `[tool.uv.build-backend]` and calls hatchling "a different backend".
- **Action:** rewrite: `# src layout + uv_build + py.typed`
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/setup-python-repo/SKILL.md
+++ b/setup-python-repo/SKILL.md
@@ -28,3 +28,3 @@
```

## `batch-3:7` — setup-python-repo/SKILL.md:158-160

- **Confidence:** Medium
- **Pattern:** G2 Volatile specifics
- **Evidence:** `my answers are always the same: this repo's own AGENTS.md (root) states them`
- **Why:** At step 10 the skill runs in the target repo. That repo's root AGENTS.md was just copied from `templates/AGENTS.md`, which states none of the three answers. The answers live in the skills repo's `AGENTS.md` (Issue tracker / Triage labels / Domain docs). Commit c10e3b29 replaced the inline answers with this pointer.
- **Action:** rewrite: point at `~/.agents/skills/AGENTS.md` by path (diff below)
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/setup-python-repo/SKILL.md
+++ b/setup-python-repo/SKILL.md
@@ -158,3 +158,4 @@
-**Don't ask its three questions — my answers are always the same: this
-repo's own `AGENTS.md` (root) states them. Pass those and proceed
-non-interactively.**
+**Don't ask its three questions — my answers are always the same, and the
+skills repo's root `AGENTS.md` (`~/.agents/skills/AGENTS.md`: Issue tracker,
+Triage labels, Domain docs) states them. Pass those and proceed
+non-interactively.**
```

## `batch-3:15` — skills-safe-update/SKILL.md:76-77

- **Confidence:** Low
- **Pattern:** none (edit leftover)
- **Evidence:** an empty ```` ``` ```` / ```` ``` ```` pair
- **Why:** This is an empty code fence left by commit 234dafd's rewrite of the block above it. It is harmless, but no pattern row covers it.
- **Action:** flag (delete when next touching the file)
- **Ruling:** audit recommendation (fix), accepted by Chris. Delete an empty code fence; zero risk.

_No hunk — write the edit._

## `batch-5:M26` — sm-link/SKILL.md:102-103

- **Confidence:** Medium
- **Pattern:** G2 history narrative
- **Evidence:** "Do not hand-roll this (it was written three times: #287, #289, #290 in **sudokumaker-custom-constraints**)."
- **Why:** The existence of the two checks, listed right below, is the reason. The count of past incidents adds nothing.
- **Action:** rewrite (hunk)
- **Ruling:** Chris ruled: **strip** dated incident notes, and edit any test that pins the removed wording in the same change.

```diff
--- a/sm-link/SKILL.md
+++ b/sm-link/SKILL.md
@@ -102,2 +102,2 @@
-Do not hand-roll this (it was written three times: #287, #289, #290 in
-**sudokumaker-custom-constraints**). Two checks already exist there:
+Do not hand-roll this. Two checks already exist in
+**sudokumaker-custom-constraints**:
```

## `batch-4:8` — visual-plan/SKILL.md:112,123-129

- **Confidence:** Medium · **vendored:** BuilderIO/agent-native
- **Pattern:** G1a pressure language
- **Evidence:** "ALWAYS a structured Agent-Native Plan", "NEVER hand it over", "STOP and give", "READ `references/connection.md`"
- **Why:** The never-inline rule is a real product constraint and carries its reason, so keep it. The caps are extra, and connection.md restates the same rule in full. Opus 5.5 follows a plainly stated constraint, and caps make it over-apply. vendored: BuilderIO/agent-native
- **Action:** rewrite (hunk below)
- **Ruling:** Chris ruled: **take** the tone edit in this vendored skill. `skills-safe-update` already carries it across upstream pulls (lockfile `skillFolderHash`, or `.extra-skills.json` `treeSha` for prompt-master).

```diff
--- a/visual-plan/SKILL.md
+++ b/visual-plan/SKILL.md
@@ -112 +112 @@
-The deliverable is ALWAYS a structured Agent-Native Plan, not a chat-only plan.
+The deliverable is a structured Agent-Native Plan, not a chat-only plan.
@@ -123,7 +123,7 @@
-By default, create the plan via the Plan MCP connector and NEVER hand it over as
+By default, create the plan via the Plan MCP connector and do not hand it over as
 inline chat content — no Markdown prose, ASCII sketch, table, or fenced
 wireframe. If the `plan` (or legacy `agent-native-plans`) tools are not visible,
 discover them through the host's `tool_search` first; if they are still missing,
-STOP and give the user the client-specific reconnect step rather than improvising
+stop and give the user the client-specific reconnect step rather than improvising
 an inline plan. Before publishing, or whenever a connector or auth error appears,
-READ `references/connection.md` in this skill directory — it is the single source
+read `references/connection.md` in this skill directory — it is the single source
```

## `batch-4:10` — visual-plan/SKILL.md:327-330 (same shape at 338-340, 353-355, 359-361, 439-440; visual-recap:204-207, 228)

- **Confidence:** Medium · **vendored:** BuilderIO/agent-native
- **Pattern:** G1a pressure + G1c repetition as reinforcement
- **Evidence:** "Before authoring ANY wireframe ... READ `references/wireframe.md` ... Do not author wireframes from memory."
- **Why:** Every reference pointer is in caps, and each also says "Do not author ... from memory", which the referenced file repeats in its own header. A plain "read X before authoring Y" is enough on Opus 5.5. vendored: BuilderIO/agent-native
- **Action:** rewrite: lower-case "any"/"read", drop the trailing "Do not author ... from memory" sentence (hunk shows the first site)
- **Ruling:** Chris ruled: **take** the tone edit in this vendored skill. `skills-safe-update` already carries it across upstream pulls (lockfile `skillFolderHash`, or `.extra-skills.json` `treeSha` for prompt-master).

```diff
--- a/visual-plan/SKILL.md
+++ b/visual-plan/SKILL.md
@@ -327,4 +327,4 @@
-tags. Before authoring ANY wireframe / `<Screen>` / `WireframeBlock`, READ
+tags. Before authoring any wireframe / `<Screen>` / `WireframeBlock`, read
 `references/wireframe.md` in this skill directory — it is the single source of
 truth for HTML wireframe quality, shared word for word with `/visual-plan`
-and `/visual-recap`. Do not author wireframes from memory.
+and `/visual-recap`.
```

## `batch-4:11` — visual-plan/SKILL.md:419

- **Confidence:** Medium · **vendored:** BuilderIO/agent-native
- **Pattern:** G1a "if in doubt, use [tool]"
- **Evidence:** "`get-plan-feedback`: read unconsumed human feedback. Use it frequently;"
- **Why:** Core Workflow step 5 already says when to call it. "Use it frequently" is a triggering booster that makes the model over-call. vendored: BuilderIO/agent-native
- **Action:** rewrite (hunk below)
- **Ruling:** Chris ruled: **take** the tone edit in this vendored skill. `skills-safe-update` already carries it across upstream pulls (lockfile `skillFolderHash`, or `.extra-skills.json` `treeSha` for prompt-master).

```diff
--- a/visual-plan/SKILL.md
+++ b/visual-plan/SKILL.md
@@ -419 +419 @@
-- `get-plan-feedback`: read unconsumed human feedback. Use it frequently; it
+- `get-plan-feedback`: read unconsumed human feedback (Core Workflow step 5 says when); it
```

## `batch-4:9` — visual-recap/SKILL.md:24-33

- **Confidence:** Medium · **vendored:** BuilderIO/agent-native
- **Pattern:** G1a pressure language
- **Evidence:** "ALWAYS a published Agent-Native Plan", "NEVER inline chat content", "STOP", "READ"
- **Why:** Same as #8. vendored: BuilderIO/agent-native
- **Action:** rewrite (hunk below)
- **Ruling:** Chris ruled: **take** the tone edit in this vendored skill. `skills-safe-update` already carries it across upstream pulls (lockfile `skillFolderHash`, or `.extra-skills.json` `treeSha` for prompt-master).

```diff
--- a/visual-recap/SKILL.md
+++ b/visual-recap/SKILL.md
@@ -24,10 +24,10 @@
-The deliverable is ALWAYS a published Agent-Native Plan, created with
-`create-visual-recap` on the Plan MCP connector — NEVER inline chat content (not
+The deliverable is a published Agent-Native Plan, created with
+`create-visual-recap` on the Plan MCP connector — not inline chat content (not
 Markdown prose, an ASCII sketch, a table, a fenced "wireframe", or a "here's the
 recap" summary). A recap's entire value is the hosted, interactive, annotatable
 plan; an inline summary is not a degraded recap, it is the thing a recap
 replaces. If the `plan` (or legacy `agent-native-plans`) tools are not visible,
 discover them through the host's `tool_search` first; if they are still missing,
-STOP and give the user the client-specific reconnect step rather than improvising
+stop and give the user the client-specific reconnect step rather than improvising
 an inline recap. Before publishing, or whenever a connector or auth error
-appears, READ `references/connection.md` in this skill directory — it is the
+appears, read `references/connection.md` in this skill directory — it is the
```

## `batch-4:12` — visual-recap/SKILL.md:128-138

- **Confidence:** Medium · **vendored:** BuilderIO/agent-native
- **Pattern:** G1f numeric output ceilings + G1d Opus-5 over-verification line
- **Evidence:** "3-8 key-change tabs ... under ~150 lines per tab ... do not exceed them in the name of thoroughness, and do not re-read the full diff"
- **Why:** These are numeric clamps plus a no-re-read rule, the shape the guide removes as a set. The goal (a reviewable summary) survives as outcome framing. The title length stays because it is a display format. vendored: BuilderIO/agent-native
- **Action:** rewrite (hunk below)
- **Ruling:** Chris ruled: **remove** the numeric word caps.

```diff
--- a/visual-recap/SKILL.md
+++ b/visual-recap/SKILL.md
@@ -128,11 +128,8 @@
-Budgets that keep the recap reviewable:
+Keep the recap reviewable:
 
-- 3-8 key-change tabs. Fewer than 3 on a large change under-serves the
-  reviewer; more than 8 stops being a summary.
-- Keep each diff/annotated-code excerpt focused — prefer under ~150 lines per
-  tab; summarize or link the rest of a long file instead of dumping it.
+- One key-change tab per load-bearing file: enough that a large change is not
+  under-served, few enough that the section still reads as a summary.
+- Keep each diff/annotated-code excerpt focused; summarize or link the rest of
+  a long file instead of dumping it.
 - Title at most ~70 characters; brief 1-3 sentences.
-
-These budgets are also the cost ceiling: do not exceed them in the name of
-thoroughness, and do not re-read the full diff after the initial sequential
-pass — work from the notes taken during that pass.
```

## `batch-4:13` — visual-recap/SKILL.md:536-539

- **Confidence:** Medium · **vendored:** BuilderIO/agent-native
- **Pattern:** G1d migration-relative phrasing / G2 time-sensitive
- **Evidence:** "The one thing not yet automatic ... that auto-re-run is the remaining fast-follow."
- **Why:** This is roadmap text written as a diff against a future state. Only the current fact matters to the agent: the Action does not re-run on feedback. vendored: BuilderIO/agent-native
- **Action:** rewrite (hunk below)
- **Ruling:** Chris ruled: **take** the tone edit in this vendored skill. `skills-safe-update` already carries it across upstream pulls (lockfile `skillFolderHash`, or `.extra-skills.json` `treeSha` for prompt-master).

```diff
--- a/visual-recap/SKILL.md
+++ b/visual-recap/SKILL.md
@@ -536,4 +536,3 @@
-for `<plan-dir>`. The one thing not yet automatic is PR-comment-triggered
-re-runs: the GitHub Action creates an initial recap per PR, but it does not yet
-re-run automatically when new review feedback is posted in GitHub — that
-auto-re-run is the remaining fast-follow.
+for `<plan-dir>`. The GitHub Action creates one recap per PR and does not
+re-run when review feedback is posted in GitHub; re-run the recap by hand
+after addressing that feedback.
```

## `batch-4:2` — visual-recap/SKILL.md:550-552

- **Confidence:** High · **vendored:** BuilderIO/agent-native
- **Pattern:** G2 volatile specifics
- **Evidence:** "- **security** — data scoping, secret handling..." / "- **sharing** — org/login-gated visibility..."
- **Why:** No `security` or `sharing` skill exists in this repo (checked with `ls`); they are upstream agent-native skills. vendored: BuilderIO/agent-native
- **Action:** remove
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/visual-recap/SKILL.md
+++ b/visual-recap/SKILL.md
@@ -547,6 +547,3 @@
   plans; see "Interpreting comment anchors" in the visual-plan skill for
   coordinate frames, wireframe node ids, text-quote resolution, detached
   threads, routing via `resolutionTarget`, and two-axis consumed/resolved state.
-- **security** — data scoping, secret handling, and the hardcoded-secret rule the
-  recap's redaction and visibility gating mirror.
-- **sharing** — org/login-gated visibility for the plan that holds the recap.
```

## `batch-5:M27` — visual-teach/assets/visual-teach.md:5-6

- **Confidence:** Medium · **vendored:** caneff/visual-teach
- **Pattern:** G2 volatile specifics
- **Evidence:** "See `demo/showcase.html` for all components on one page."
- **Why:** Neither `visual-teach/demo/` nor `assets/demo/` exists in the installed tree, which holds only `components/*/demo.html` and `base/demo.html`. The file may exist upstream.
- **Action:** rewrite (hunk) · vendored: caneff/visual-teach
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/visual-teach/assets/visual-teach.md
+++ b/visual-teach/assets/visual-teach.md
@@ -3,4 +3,3 @@
 `visual-teach` ships as a **base + standalone components**. Each component is
 self-contained: its CSS file, optional JS, and a co-located `demo.html` that is
-both the usage doc and the rendering proof. See `demo/showcase.html` for all
-components on one page.
+both the usage doc and the rendering proof.
```
