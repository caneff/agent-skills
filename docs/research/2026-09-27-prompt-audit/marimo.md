# Prompt audit 2026-09-27 — cluster `marimo`

Skills: `anywidget-generator`, `auto-paper-demo`, `implement-paper`, `implement-paper-auto`, `marimo-batch`, `marimo-notebook`, `marimo-pair`, `streamlit-to-marimo`. 23 findings.
Hunks are proposals written against `main` at 9a1c304; re-read the current line before applying. Where a finding has no hunk, write the edit from its action and ruling.
Target model for every judgment: Claude Opus 5.5. Method: the bundled `claude-api` skill's `shared/prompt-audit.md`.

## `batch-4:5` — anywidget-generator/SKILL.md:19

- **Confidence:** High · **vendored:** marimo-team/skills
- **Pattern:** G1c single gold example
- **Evidence:** `document.createElement("b8utton")`
- **Why:** The typo makes a `<b8utton>` element, so the example's own `_css` `button{}` selector never matches. The model copies its one example verbatim. vendored: marimo-team/skills
- **Action:** rewrite: `"button"`
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/anywidget-generator/SKILL.md
+++ b/anywidget-generator/SKILL.md
@@ -19 +19 @@
-      let btn = document.createElement("b8utton");
+      let btn = document.createElement("button");
```

## `batch-5:M6` — auto-paper-demo/SKILL.md:59-61

- **Confidence:** Medium
- **Pattern:** G1a pressure; G1b prose steering thinking depth
- **Evidence:** "I cannot stress enough how important it is … You should really ultra think this. … Feel free to think about this decision"
- **Why:** On Opus 5.5 thinking is always on and `effort` is the only depth control. "ultra think" (with a space) is not the Claude Code keyword. Keep the real instruction, which is to settle story and example before coding.
- **Action:** rewrite (hunk) · vendored
- **Ruling:** Chris ruled: **take** the tone edit in this vendored skill. `skills-safe-update` already carries it across upstream pulls (lockfile `skillFolderHash`, or `.extra-skills.json` `treeSha` for prompt-master).

```diff
--- a/auto-paper-demo/SKILL.md
+++ b/auto-paper-demo/SKILL.md
@@ -59,3 +59,3 @@
-I cannot stress enough how important it is to actually think about the story and the example before you write any code whatsoever. You should really ultra think this. Give the user some interaction but really try to prevent scrolling. A good example tells a story, it doesn't just state some facts. 
+Settle the story and the example before you write any code: they matter more than the implementation. Give the user some interaction but keep scrolling to a minimum. A good example tells a story, it doesn't just state some facts. 
 
-Feel free to think about this decision, but once you've got it clear what idea is best to showcase, immediately proceed to build the marimo notebook. 
+Once it is clear which idea is best to showcase, build the marimo notebook. 
```

## `batch-5:M7` — auto-paper-demo/SKILL.md:63

- **Confidence:** Medium
- **Pattern:** G2 volatile specifics
- **Evidence:** "possibly the anywidget skill"
- **Why:** No skill is named `anywidget`. The repo has `anywidget-generator/SKILL.md`.
- **Action:** rewrite (hunk) · vendored
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/auto-paper-demo/SKILL.md
+++ b/auto-paper-demo/SKILL.md
@@ -63 +63 @@
-Use the marimo-notebook skill for this, and possibly the anywidget skill, but only if a custom widget makes for a better story. If you strongly feel that it makes sense to use a custom anywidget, refer to [references/ANYWIDGET.md](references/ANYWIDGET.md).
+Use the marimo-notebook skill for this, and the anywidget-generator skill only if a custom widget makes for a better story; its essentials are in [references/ANYWIDGET.md](references/ANYWIDGET.md).
```

## `batch-5:H4` — auto-paper-demo/SKILL.md:69-74

- **Confidence:** High · **vendored:** marimo-team/skills
- **Pattern:** G1c single gold example; G2 contradiction
- **Evidence:** "@app.cell\ndef _(hide_code=True):"
- **Why:** marimo takes `hide_code` on the decorator. `marimo-notebook/references/SQL.md:4` and `COLUMNS.md:15` both write `@app.cell(hide_code=True)`. The model will copy this wrong example, because it is the skill's only code.
- **Action:** rewrite (hunk) · vendored: marimo-team/skills
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/auto-paper-demo/SKILL.md
+++ b/auto-paper-demo/SKILL.md
@@ -69,6 +69,6 @@
```

## `batch-1:P3` — implement-paper/SKILL.md:25

- **Confidence:** Medium · **vendored:** marimo-team/skills
- **Pattern:** 1c / Padding
- **Evidence:** "If the user gives you an Arxiv/AlphaXiv link, you will an efficient way to read the paper."
- **Why:** A broken sentence that says nothing line 27 does not say. vendored: marimo-team/skills
- **Action:** remove (hunk)
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/implement-paper/SKILL.md
+++ b/implement-paper/SKILL.md
@@ -23,6 +23,4 @@
 ## Step 2: Fetch the paper
 
-If the user gives you an Arxiv/AlphaXiv link, you will an efficient way to read the paper. 
-
 See [references/fetching-papers.md](references/fetching-papers.md) for how to retrieve paper content via alphaxiv.org. This avoids reading raw PDFs and gives you structured markdown.
```

## `batch-1:P1` — implement-paper/SKILL.md:33

- **Confidence:** High · **vendored:** marimo-team/skills
- **Pattern:** 2 / Volatile specifics
- **Evidence:** "consider the `anywidget` skill"
- **Why:** No `anywidget` skill exists in the repo; the skill is `anywidget-generator/`. vendored: marimo-team/skills
- **Action:** rewrite: `` `anywidget-generator` ``
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/implement-paper/SKILL.md
+++ b/implement-paper/SKILL.md
@@ -33 +33 @@
-**Keep the notebook as small as possible.** Sometimes the idea is best conveyed with just a single interactive widget — if you need a custom one, consider the `anywidget` skill. Other times you need a full training loop — if so, consider using the `marimo-batch` skill for heavy computation. The goal is the minimum amount of code needed to get the idea across.
+**Keep the notebook as small as possible.** Sometimes the idea is best conveyed with just a single interactive widget — if you need a custom one, consider the `anywidget-generator` skill. Other times you need a full training loop — if so, consider using the `marimo-batch` skill for heavy computation. The goal is the minimum amount of code needed to get the idea across.
```

## `batch-1:P2` — implement-paper/references/anywidget.md:18

- **Confidence:** High · **vendored:** marimo-team/skills
- **Pattern:** 1c / Example over-indexing (a broken gold example) + 2 / repo contradicts
- **Evidence:** `document.createElement("b8utton")`
- **Why:** The example's own `_css` targets `button` and the prose calls it a counter button; `b8utton` creates an unknown element, and the model copies the single example verbatim. Same typo in marimo-notebook/references/ANYWIDGET.md, auto-paper-demo/references/ANYWIDGET.md, anywidget-generator/SKILL.md, implement-paper-auto/references/ANYWIDGET.md (other batches). vendored: marimo-team/skills
- **Action:** rewrite: `"button"`
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/implement-paper/references/anywidget.md
+++ b/implement-paper/references/anywidget.md
@@ -18 +18 @@
-      let btn = document.createElement("b8utton");
+      let btn = document.createElement("button");
```

## `batch-4:14` — implement-paper-auto/SKILL.md:59

- **Confidence:** Medium · **vendored:** marimo-team/skills
- **Pattern:** G1a pressure + G1b prose steering thinking depth
- **Evidence:** "I cannot stress enough how important it is ... You should really ultra think this."
- **Why:** On Opus 5.5 thinking is always on, and effort is the depth control. "ultra think" (two words) is prose, not the `ultrathink` keyword. The real rule (settle the story first) survives at normal volume. vendored: marimo-team/skills
- **Action:** rewrite (hunk below)
- **Ruling:** Chris ruled: **take** the tone edit in this vendored skill. `skills-safe-update` already carries it across upstream pulls (lockfile `skillFolderHash`, or `.extra-skills.json` `treeSha` for prompt-master).

```diff
--- a/implement-paper-auto/SKILL.md
+++ b/implement-paper-auto/SKILL.md
@@ -59 +59 @@
-I cannot stress enough how important it is to actually think about the story and the example before you write any code whatsoever. You should really ultra think this. Give the user some interaction but really try to prevent scrolling. A good example tells a story, it doesn't just state some facts. 
+Settle the story and the example before writing any code; the example carries the story. Give the user some interaction but keep scrolling to a minimum. A good example tells a story, it doesn't just state some facts.
```

## `batch-4:15` — implement-paper-auto/SKILL.md:63

- **Confidence:** Medium · **vendored:** marimo-team/skills
- **Pattern:** G2 volatile specifics
- **Evidence:** "possibly the anywidget skill"
- **Why:** No skill named `anywidget` exists; the repo's skill is `anywidget-generator`. vendored: marimo-team/skills
- **Action:** rewrite: "possibly the `anywidget-generator` skill"
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/implement-paper-auto/SKILL.md
+++ b/implement-paper-auto/SKILL.md
@@ -63 +63 @@
-Use the marimo-notebook skill for this, and possibly the anywidget skill, but only if a custom widget makes for a better story. If you strongly feel that it makes sense to use a custom anywidget, refer to [references/ANYWIDGET.md](references/ANYWIDGET.md).
+Use the marimo-notebook skill for this, and possibly the `anywidget-generator` skill, but only if a custom widget makes for a better story. If you strongly feel that it makes sense to use a custom anywidget, refer to [references/ANYWIDGET.md](references/ANYWIDGET.md).
```

## `batch-4:4` — implement-paper-auto/SKILL.md:70-71

- **Confidence:** High · **vendored:** marimo-team/skills
- **Pattern:** G2 volatile specifics + G1c single gold example
- **Evidence:** "@app.cell / def _(hide_code=True):"
- **Why:** `hide_code` is an `@app.cell(...)` argument, as the repo's own `marimo-notebook/references/SQL.md:4` and `COLUMNS.md:15` show. The only example teaches a no-op function parameter, and the model copies it. vendored: marimo-team/skills
- **Action:** rewrite: `@app.cell(hide_code=True)` / `def _():`
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/implement-paper-auto/SKILL.md
+++ b/implement-paper-auto/SKILL.md
@@ -70,2 +70,2 @@
-@app.cell
-def _(hide_code=True):
+@app.cell(hide_code=True)
+def _():
```

## `batch-4:6` — implement-paper-auto/references/ANYWIDGET.md:18

- **Confidence:** High · **vendored:** marimo-team/skills
- **Pattern:** G1c single gold example
- **Evidence:** `document.createElement("b8utton")`
- **Why:** Same broken example; this file is a copy of anywidget-generator/SKILL.md. vendored: marimo-team/skills
- **Action:** rewrite: `"button"`
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/implement-paper-auto/references/ANYWIDGET.md
+++ b/implement-paper-auto/references/ANYWIDGET.md
@@ -18 +18 @@
-      let btn = document.createElement("b8utton");
+      let btn = document.createElement("button");
```

## `batch-1:M1` — marimo-batch/SKILL.md:36-37

- **Confidence:** Medium · **vendored:** marimo-team/skills
- **Pattern:** 1c / Example over-indexing (stale example)
- **Evidence:** `len(cli_args) == 0` / `print("Usage: uv run git_archaeology.py --repo <url> [--samples <n>]")`
- **Why:** `cli_args` is undefined (NameError) and the usage line belongs to an unrelated notebook, contradicting the `ModelParams` above it and the `uv run notebook.py` line below. The model copies it. vendored: marimo-team/skills
- **Action:** rewrite (hunk)
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/marimo-batch/SKILL.md
+++ b/marimo-batch/SKILL.md
@@ -35,3 +35,3 @@
 if mo.app_meta().mode == "script":
-    if "help" in mo.cli_args() or len(cli_args) == 0:
-        print("Usage: uv run git_archaeology.py --repo <url> [--samples <n>]")
+    if "help" in mo.cli_args() or len(mo.cli_args()) == 0:
+        print("Usage: uv run notebook.py [--sample-size <n>] [--learning-rate <x>]")
         print()
```

## `batch-1:M2` — marimo-batch/SKILL.md:64, 91

- **Confidence:** Medium · **vendored:** marimo-team/skills
- **Pattern:** 1a / Pressure language + 1c / repetition
- **Evidence:** "Make sure you keep the columns intact in this notebook!" / "you must keep these columns intact!"
- **Why:** The same rule twice, shouted, no reason; seven "make sure" in the file. Opus 5.5 follows a plain statement. vendored: marimo-team/skills
- **Action:** rewrite (hunk)
- **Ruling:** Chris ruled: **take** the tone edit in this vendored skill. `skills-safe-update` already carries it across upstream pulls (lockfile `skillFolderHash`, or `.extra-skills.json` `treeSha` for prompt-master).

```diff
--- a/marimo-batch/SKILL.md
+++ b/marimo-batch/SKILL.md
@@ -64 +64 @@
-If the user is keen to start a training job for ML, make sure you use [this starting point](references/starting-point.py). Make sure you keep the columns intact in this notebook! 
+If the user is keen to start a training job for ML, use [this starting point](references/starting-point.py); it uses columns (see Columns below).
@@ -91 +91 @@
-It can be common for larger marimo notebooks to use the columns feature to make it easy to navigate. If that is the case, you must keep these columns intact! 
+Larger marimo notebooks often use columns so the user can navigate them. When a notebook does, keep each cell's `column=` argument as it is: the layout is the user's navigation.
```

## `batch-5:M1` — marimo-notebook/SKILL.md:244

- **Confidence:** Medium
- **Pattern:** G1a trait claim + emphasis
- **Evidence:** "**Important**: you have a tendency to over-do variables with an underscore prefix."
- **Why:** Trait claims about "you" were written against older models' habits. State the wanted behaviour and its reason instead.
- **Action:** rewrite (hunk) · vendored
- **Ruling:** Chris ruled: **take** the tone edit in this vendored skill. `skills-safe-update` already carries it across upstream pulls (lockfile `skillFolderHash`, or `.extra-skills.json` `treeSha` for prompt-master).

```diff
--- a/marimo-notebook/SKILL.md
+++ b/marimo-notebook/SKILL.md
@@ -244 +244 @@
-**Important**: you have a tendency to over-do variables with an underscore prefix. You should only apply this to one or two variables at most. Consider creating a new variable instead of prefixing entire cells in marimo. 
+Use an underscore prefix only for the one or two variables that must stay cell-local; otherwise give the variable a new, unique name rather than prefixing a whole cell's variables.
```

## `batch-5:M2` — marimo-notebook/SKILL.md:251

- **Confidence:** Medium
- **Pattern:** G2 volatile specifics (malformed command)
- **Evidence:** "uv --with marimo run python -c …"
- **Why:** `--with` is an option of `uv run`, not a top-level `uv` flag. The repo's own sm-link writes it correctly (`uv run --with lzstring …`). The command as written errors.
- **Action:** rewrite (hunk) · vendored
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/marimo-notebook/SKILL.md
+++ b/marimo-notebook/SKILL.md
@@ -251 +251 @@
-uv --with marimo run python -c "import marimo as mo; help(mo.ui.form)"
+uv run --with marimo python -c "import marimo as mo; help(mo.ui.form)"
```

## `batch-5:H7` — marimo-notebook/SKILL.md:272

- **Confidence:** High · **vendored:** marimo-team/skills
- **Pattern:** G2 volatile specifics
- **Evidence:** "For marimo notebooks that run in width=columns [SQL.md](references/COLUMNS.md)"
- **Why:** The link text names the wrong file; the target is COLUMNS.md.
- **Action:** rewrite (hunk) · vendored: marimo-team/skills
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/marimo-notebook/SKILL.md
+++ b/marimo-notebook/SKILL.md
@@ -272 +272 @@
-- For marimo notebooks that run in width=columns [SQL.md](references/COLUMNS.md)
+- For marimo notebooks that run in width=columns [COLUMNS.md](references/COLUMNS.md)
```

## `batch-5:M4` — marimo-notebook/references/ANYWIDGET.md:18 (same file at auto-paper-demo/references/ANYWIDGET.md:18)

- **Confidence:** Medium
- **Pattern:** G1c gold example with a defect
- **Evidence:** `document.createElement("b8utton")`
- **Why:** The typo creates an unknown element, so the example's own `button{}` CSS never applies. A copied example carries the bug.
- **Action:** rewrite (hunk, apply to both copies) · vendored
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/marimo-notebook/references/ANYWIDGET.md
+++ b/marimo-notebook/references/ANYWIDGET.md
@@ -18 +18 @@
-      let btn = document.createElement("b8utton");
+      let btn = document.createElement("button");
```

## `batch-5:M3` — marimo-notebook/references/UI.md:26

- **Confidence:** Medium
- **Pattern:** same as M2
- **Evidence:** "`uv --with marimo run python -c …`"
- **Why:** Same malformed command, in a second place.
- **Action:** rewrite (hunk) · vendored
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/marimo-notebook/references/UI.md
+++ b/marimo-notebook/references/UI.md
@@ -26 +26 @@
-As always, you can learn more about the available inputs to all these components via `uv --with marimo run python -c "import marimo as mo; help(mo.ui.form)"` 
+As always, you can learn more about the available inputs to all these components via `uv run --with marimo python -c "import marimo as mo; help(mo.ui.form)"` 
```

## `batch-5:M5` — marimo-notebook/references/WATCHING.md:55

- **Confidence:** Medium
- **Pattern:** G2 volatile specifics
- **Evidence:** "`mo.watch.file` and `mo.watch.file` utilities that can cause cells to update when a file/folder updates"
- **Why:** The same name appears twice. The folder half is `mo.watch.directory`.
- **Action:** rewrite (hunk) · vendored
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/marimo-notebook/references/WATCHING.md
+++ b/marimo-notebook/references/WATCHING.md
@@ -55 +55 @@
-marimo has `mo.watch.file` and `mo.watch.file` utilities that can cause cells to update when a file/folder updates. 
+marimo has `mo.watch.file` and `mo.watch.directory` utilities that can cause cells to update when a file/folder updates. 
```

## `batch-3:8` — marimo-pair/SKILL.md:22-24, 120, 125, 128-131, 264, 280

- **Confidence:** Medium · **vendored:** marimo-team/marimo-pair
- **Pattern:** G1 1a (caps density)
- **Evidence:** `WARNING.` / `SHOULD NOT` / `WILL NOT` / `MUST` / `PRIVATE, UNSTABLE` / `DO NOT` (x3)
- **Why:** Nine all-caps markers in one body, where each already carries its reason. On current models the markers stop carrying signal and push rigid behavior. The reasons alone steer correctly. vendored: marimo-team/marimo-pair
- **Action:** rewrite at normal case, keeping every reason. Hunks below cover :22-24 and :128-131; apply the same change to :120 (`WILL NOT`→`is not`), :125 (`you MUST submit`→`submit`), :264 and :280 (`DO NOT`→`Do not`)
- **Ruling:** Chris ruled: **take** the tone edit in this vendored skill. `skills-safe-update` already carries it across upstream pulls (lockfile `skillFolderHash`, or `.extra-skills.json` `treeSha` for prompt-master).

```diff
--- a/marimo-pair/SKILL.md
+++ b/marimo-pair/SKILL.md
@@ -22,3 +22,3 @@
-**WARNING. The active runtime is the source of truth.** During a session, you
-SHOULD NOT modify the associated `.py` file directly. File edits WILL NOT reach
-the active kernel or user, and the kernel may overwrite them on save. Use
+**The active runtime is the source of truth.** During a session, do not
+modify the associated `.py` file directly: file edits do not reach the active
+kernel or user, and the kernel may overwrite them on save. Use
```

```diff
--- a/marimo-pair/SKILL.md
+++ b/marimo-pair/SKILL.md
@@ -128,4 +128,4 @@
-`marimo._code_mode` is a PRIVATE, UNSTABLE agent API (note the leading
+`marimo._code_mode` is a private, unstable agent API (note the leading
 underscore). It exists for tools like this skill to drive a live kernel from
-the scratchpad. DO NOT import it from notebook cells, library code, or
+the scratchpad. Do not import it from notebook cells, library code, or
 anything a user would run — methods can change or disappear across marimo
```

## `batch-3:5` — marimo-pair/SKILL.md:251

- **Confidence:** High · **vendored:** marimo-team/marimo-pair
- **Pattern:** G1 1a (row "Be thorough. Do not be lazy.")
- **Evidence:** `Don't be lazy.`
- **Why:** Current models are proactive by default. The sentence around it already states the real bar (durable edits, no brittle workarounds). vendored: marimo-team/marimo-pair
- **Action:** remove
- **Ruling:** Chris ruled: **take** the tone edit in this vendored skill. `skills-safe-update` already carries it across upstream pulls (lockfile `skillFolderHash`, or `.extra-skills.json` `treeSha` for prompt-master).

```diff
--- a/marimo-pair/SKILL.md
+++ b/marimo-pair/SKILL.md
@@ -250,3 +250,3 @@
 Make durable edits that reuse the notebook's existing names, imports,
-dependencies, and UI model. Don't be lazy. Avoid one-off workarounds that pass
-`cm` validation but leave a brittle notebook.
+dependencies, and UI model. Avoid one-off workarounds that pass `cm`
+validation but leave a brittle notebook.
```

## `batch-3:4` — marimo-pair/reference/execution-context.md:26

- **Confidence:** High · **vendored:** marimo-team/marimo-pair
- **Pattern:** G2 Volatile specifics
- **Evidence:** `` `Authorization: ******` ``
- **Why:** `scripts/execute-code.sh:106` sends `Authorization: Bearer ${token}`. The doc shows a redaction artifact where the header value should be. vendored: marimo-team/marimo-pair
- **Action:** rewrite: `` `Authorization: Bearer <token>` ``
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/marimo-pair/reference/execution-context.md
+++ b/marimo-pair/reference/execution-context.md
@@ -25,2 +25,2 @@
 present, `--token` overrides `MARIMO_TOKEN`. The script sends the token as
-`Authorization: ******` on session discovery and code execution requests.
+`Authorization: Bearer <token>` on session discovery and code execution requests.
```

## `batch-4:3` — streamlit-to-marimo/SKILL.md:55

- **Confidence:** High · **vendored:** marimo-team/skills
- **Pattern:** G2 volatile specifics
- **Evidence:** "marimo uses KaTeX; see `references/latex.md`"
- **Why:** `streamlit-to-marimo/` has no `references/` dir; the file lives at `jupyter-to-marimo/references/latex.md`. vendored: marimo-team/skills
- **Action:** rewrite: "see `../jupyter-to-marimo/references/latex.md`"
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/streamlit-to-marimo/SKILL.md
+++ b/streamlit-to-marimo/SKILL.md
@@ -55 +55 @@
-| `st.latex()` | `mo.md(r"$...$")` | marimo uses KaTeX; see `references/latex.md` |
+| `st.latex()` | `mo.md(r"$...$")` | marimo uses KaTeX; see `../jupyter-to-marimo/references/latex.md` |
```
