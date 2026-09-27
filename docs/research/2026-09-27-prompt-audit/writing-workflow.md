# Prompt audit 2026-09-27 — cluster `writing-workflow`

Skills: `ask-matt`, `codebase-design`, `diagnosing-bugs`, `file-ticket`, `find-skills`, `grilling`, `handoff`, `prompt-master`, `research`, `resolving-merge-conflicts`, `teach`, `to-spec`, `writing-for-agents`. 18 findings.
Hunks are proposals written against `main` at 9a1c304; re-read the current line before applying. Where a finding has no hunk, write the edit from its action and ruling.
Target model for every judgment: Claude Opus 5.5. Method: the bundled `claude-api` skill's `shared/prompt-audit.md`.

## `batch-4:1` — ask-matt/SKILL.md:83

- **Confidence:** High · **vendored:** mattpocock/skills
- **Pattern:** G2 volatile specifics
- **Evidence:** "Model-invoked, so the agent reaches for it the moment it hits a wall only you can pass."
- **Why:** `wizard/SKILL.md:3` carries `disable-model-invocation: true` (set locally in f6bac07, 2026-08-18), so the agent cannot reach for it. The router teaches a trigger that no longer exists. vendored: mattpocock/skills
- **Action:** rewrite: "Slash-only here, so run `/wizard` yourself when the agent hits a wall only you can pass."
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/ask-matt/SKILL.md
+++ b/ask-matt/SKILL.md
@@ -83 +83 @@
-- **`/wizard`** is for the steps only a **human** can take: provisioning infrastructure, setting up credentials or CI secrets, clicking through an unfamiliar third-party dashboard, running a one-off migration or cutover. It generates an interactive bash script that opens each URL, captures each value, and writes it into `.env` and GitHub secrets, so the procedure stops being something you re-explain to an agent every time. Model-invoked, so the agent reaches for it the moment it hits a wall only you can pass. If the agent could just do it itself, it should; this is for where a human is genuinely in the loop.
+- **`/wizard`** is for the steps only a **human** can take: provisioning infrastructure, setting up credentials or CI secrets, clicking through an unfamiliar third-party dashboard, running a one-off migration or cutover. It generates an interactive bash script that opens each URL, captures each value, and writes it into `.env` and GitHub secrets, so the procedure stops being something you re-explain to an agent every time. Slash-only here, so run `/wizard` yourself when the agent hits a wall only you can pass. If the agent could just do it itself, it should; this is for where a human is genuinely in the loop.
```

## `batch-5:M25` — codebase-design/SKILL.md:67-95

- **Confidence:** Medium · **vendored:** mattpocock/skills
- **Pattern:** G2 explaining what the model already knows
- **Evidence:** "Designing for testability … Accept dependencies, don't create them … Return results, don't produce side effects" (two TS examples)
- **Why:** Dependency injection and pure-return testability are general programming knowledge. The glossary and principles around this section are the author-only content.
- **Action:** remove (hunk) · vendored: mattpocock/skills
- **Ruling:** Chris ruled: **take** the tone edit in this vendored skill. `skills-safe-update` already carries it across upstream pulls (lockfile `skillFolderHash`, or `.extra-skills.json` `treeSha` for prompt-master).

```diff
--- a/codebase-design/SKILL.md
+++ b/codebase-design/SKILL.md
@@ -66,31 +66,2 @@
 - **One adapter means a hypothetical seam. Two adapters means a real one.** Don't introduce a seam unless something actually varies across it.
 
-## Designing for testability
-
-Good interfaces make testing natural:
-
-1. **Accept dependencies, don't create them.**
-
-   ```typescript
-   // Testable
-   function processOrder(order, paymentGateway) {}
-
-   // Hard to test
-   function processOrder(order) {
-     const gateway = new StripeGateway();
-   }
-   ```
-
-2. **Return results, don't produce side effects.**
-
-   ```typescript
-   // Testable
-   function calculateDiscount(cart): Discount {}
-
-   // Hard to test
-   function applyDiscount(cart): void {
-     cart.total -= discount;
-   }
-   ```
-
-3. **Small surface area.** Fewer methods = fewer tests needed. Fewer params = simpler test setup.
-
 ## Relationships
```

## `batch-1:D1` — diagnosing-bugs/SKILL.md:23

- **Confidence:** Medium · **vendored:** mattpocock/skills
- **Pattern:** 1a / "Be thorough. Do not be lazy. Do not stop early."
- **Evidence:** "Spend disproportionate effort here. **Be aggressive. Be creative. Refuse to give up.**"
- **Why:** Current models are persistent by default; boosters over-apply. The sentence before it and the completion criterion at line 58-67 already set the bar concretely. vendored: mattpocock/skills
- **Action:** rewrite (hunk)
- **Ruling:** Chris ruled: **take** the tone edit in this vendored skill. `skills-safe-update` already carries it across upstream pulls (lockfile `skillFolderHash`, or `.extra-skills.json` `treeSha` for prompt-master).

```diff
--- a/diagnosing-bugs/SKILL.md
+++ b/diagnosing-bugs/SKILL.md
@@ -23 +23 @@
-Spend disproportionate effort here. **Be aggressive. Be creative. Refuse to give up.**
+Spend disproportionate effort here: try the constructions below until one meets the completion criterion.
```

## `batch-2:M12` — file-ticket/SKILL.md:118-120

- **Confidence:** Medium
- **Pattern:** 1c repetition
- **Evidence:** "Say so in your reply when the edge fails — the section still states the relationship…"
- **Why:** Restates :106-108 ("If that edge fails … name it as such in your reply") twelve lines later.
- **Action:** remove
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/file-ticket/SKILL.md
+++ b/file-ticket/SKILL.md
@@ -116,7 +116,5 @@
 rather than a filing that never happened. (`gh` 2.95.0 has both
 `--add-blocked-by` here and `--blocked-by` on the create; the second
-command is for the machines that do not.) Say so in your reply when the
-edge fails — the section still states the relationship, and nobody has to
-find out from the tracker later.
+command is for the machines that do not.)
 
 Filing more than one target prints one URL per line, in the order the
```

## `batch-5:M23` — find-skills/SKILL.md:11-20

- **Confidence:** Medium · **vendored:** vercel-labs/skills
- **Pattern:** G2 trigger-case enumeration in the body
- **Evidence:** "## When to Use This Skill … Asks "how do I do X" where X might be a common task …"
- **Why:** The body loads only after the skill has triggered, so this list cannot route anything. It is also broader than the frontmatter trigger ("how do I do X", "can you do X").
- **Action:** remove (hunk) · vendored: vercel-labs/skills
- **Ruling:** Chris ruled: **take** the tone edit in this vendored skill. `skills-safe-update` already carries it across upstream pulls (lockfile `skillFolderHash`, or `.extra-skills.json` `treeSha` for prompt-master).

```diff
--- a/find-skills/SKILL.md
+++ b/find-skills/SKILL.md
@@ -9,14 +9,3 @@
 This skill helps you discover and install skills from the open agent skills ecosystem.
 
-## When to Use This Skill
-
-Use this skill when the user:
-
-- Asks "how do I do X" where X might be a common task with an existing skill
-- Says "find a skill for X" or "is there a skill for X"
-- Asks "can you do X" where X is a specialized capability
-- Expresses interest in extending agent capabilities
-- Wants to search for tools, templates, or workflows
-- Mentions they wish they had help with a specific domain (design, testing, deployment, etc.)
-
 ## What is the Skills CLI?
```

## `batch-5:M24` — find-skills/SKILL.md:86-95, 137-143

- **Confidence:** Medium
- **Pattern:** G1c single gold output
- **Evidence:** "I found a skill that might help! …" / "I can still help you with this task directly! Would you like me to proceed?"
- **Why:** A verbatim response template fixes the reply's tone and shape. The register ("!" enthusiasm) also conflicts with the owner's output style. Lines 77-82 already list the content the reply needs.
- **Action:** remove (hunk) · vendored
- **Ruling:** Chris ruled: **take** the tone edit in this vendored skill. `skills-safe-update` already carries it across upstream pulls (lockfile `skillFolderHash`, or `.extra-skills.json` `treeSha` for prompt-master).

```diff
--- a/find-skills/SKILL.md
+++ b/find-skills/SKILL.md
@@ -82,16 +82,3 @@
 4. A link to learn more at skills.sh
 
-Example response:
-
-```
-I found a skill that might help! The "react-best-practices" skill provides
-React and Next.js performance optimization guidelines from Vercel Engineering.
-(185K installs)
-
-To install it:
-npx skills add vercel-labs/agent-skills@react-best-practices
-
-Learn more: https://skills.sh/vercel-labs/agent-skills/react-best-practices
-```
-
 ### Step 6: Offer to Install
@@ -129,15 +116,5 @@
 If no relevant skills exist:
 
 1. Acknowledge that no existing skill was found
 2. Offer to help with the task directly using your general capabilities
 3. Suggest the user could create their own skill with `npx skills init`
-
-Example:
-
-```
-I searched for skills related to "xyz" but didn't find any matches.
-I can still help you with this task directly! Would you like me to proceed?
-
-If this is something you do often, you could create your own skill:
-npx skills init my-xyz-skill
-```
```

## `batch-4:17` — grilling/SKILL.md:8

- **Confidence:** Low · **vendored:** skill
- **Pattern:** G2 instruction files contradict
- **Evidence:** "Ask the whole frontier in one round"
- **Why:** `~/.claude/CLAUDE.md` (Communication) says: "Multi-part questions (grilling, triage, spec review): a few numbered questions per round, not a batch." A wide frontier breaks that rule. The fix would touch user-level config or a local edit to a vendored skill (line from 9f525f8 "restore local edits"). ask-matt:78 describes the same round shape. vendored: mattpocock/skills
- **Action:** flag - Chris rules which one wins
- **Ruling:** Chris ruled: **CLAUDE.md wins**. Rewrite so a round asks a few numbered frontier questions, not the whole frontier. No hunk exists; write it.

_No hunk — write the edit._

## `batch-5:M28` — handoff/SKILL.md:50, 54

- **Confidence:** Medium · **vendored:** mattpocock/skills
- **Pattern:** G2 volatile specifics (tool contract)
- **Evidence:** "**no** `name`, `run_in_background: false`" / "pass a descriptive `name`, `run_in_background: true`"
- **Why:** The Agent tool in this harness has no `run_in_background` parameter; subagents always run in the background. Only `name` separates the two modes.
- **Action:** rewrite (hunk) · vendored: mattpocock/skills
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/handoff/SKILL.md
+++ b/handoff/SKILL.md
@@ -50 +50 @@
-Spawn a fire-and-return subagent with the Agent tool: **no** `name`, `run_in_background: false`, prompt = the seed line above. It does the handed-off work and returns its result into *this* session. Use when you want the work done now and the answer back in the current thread.
+Spawn a fire-and-return subagent with the Agent tool: **no** `name`, prompt = the seed line above. It does the handed-off work and its result returns into *this* session as a completion notification. Use when you want the answer back in the current thread.
@@ -54 +54 @@
-Spawn a persistent side-agent with the Agent tool: pass a descriptive `name`, `run_in_background: true`, prompt = the seed line above. It runs concurrently; you keep working and address it later with SendMessage. Use when the handed-off work should proceed in parallel without blocking you.
+Spawn a persistent side-agent with the Agent tool: pass a descriptive `name`, prompt = the seed line above. The name makes it addressable; you keep working and reach it later with SendMessage. Use when the handed-off work should proceed in parallel without blocking you.
```

## `batch-3:11` — prompt-master/SKILL.md:82, 93-99, 210

- **Confidence:** Medium · **vendored:** nidhinjs/prompt-master
- **Pattern:** G2 History narratives (pinned model names)
- **Evidence:** `start with **Claude Opus 5** (claude-opus-5)`; `Use **Claude Fable 5** (claude-fable-5)`
- **Why:** These routes name Opus 5 and Fable 5 as the current defaults. Claude Opus 5.5 and Fable 5.1 are the current models. The migration guide says Opus 5's prompting patterns "remain a reasonable starting point", so only the names move. vendored: nidhinjs/prompt-master
- **Action:** rewrite names (diff below). The README.md:400 changelog stays as history
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/prompt-master/SKILL.md
+++ b/prompt-master/SKILL.md
@@ -82 +82 @@
-Do not assume one universal Claude default. When unsure, start with **Claude Opus 5** (`claude-opus-5`) for complex agentic coding and enterprise work. Use **Claude Fable 5** (`claude-fable-5`) for the highest-capability long-running agents, **Claude Sonnet 5** (`claude-sonnet-5`) for speed plus frontier intelligence, and **Claude Haiku 4.5** for fast, economical workloads. Ask which model only when the distinction changes the prompt.
+Do not assume one universal Claude default. When unsure, start with **Claude Opus 5.5** (`claude-opus-5-5`) for complex agentic coding and enterprise work. Use **Claude Fable 5.1** (`claude-fable-5-1`) for the highest-capability long-running agents, **Claude Sonnet 5** (`claude-sonnet-5`) for speed plus frontier intelligence, and **Claude Haiku 4.5** for fast, economical workloads. Ask which model only when the distinction changes the prompt.
```

```diff
--- a/prompt-master/SKILL.md
+++ b/prompt-master/SKILL.md
@@ -93,7 +93,7 @@
-*Fable 5:*
-- Fable 5 is optimized for the hardest long-horizon autonomous work. Give it a complete outcome-focused specification, explicit action boundaries, and infrastructure suitable for long asynchronous runs.
+*Fable 5.1:*
+- Fable 5.1 is optimized for the hardest long-horizon autonomous work. Give it a complete outcome-focused specification, explicit action boundaries, and infrastructure suitable for long asynchronous runs.
 - Ground every long-run progress claim in actual tool results. Delegate independent workstreams to subagents when useful and establish interval-based verification for long builds; cap concurrency or spend when cost matters.
 
-*Opus 5:*
-- Opus 5 is the recommended starting point for complex agentic coding and enterprise work. Keep scope tight: "Deliver what was asked. Do not add features, refactors, or abstractions beyond the task."
-- Opus 5 already self-verifies strongly. Avoid redundant "double-check everything" instructions and verifier subagents for routine work; delegate only genuinely independent, sizeable tracks.
+*Opus 5.5:*
+- Opus 5.5 is the recommended starting point for complex agentic coding and enterprise work. Keep scope tight: "Deliver what was asked. Do not add features, refactors, or abstractions beyond the task."
+- Opus 5.5 already self-verifies strongly. Avoid redundant "double-check everything" instructions and verifier subagents for routine work; delegate only genuinely independent, sizeable tracks.
```

```diff
--- a/prompt-master/SKILL.md
+++ b/prompt-master/SKILL.md
@@ -210 +210 @@
-- Do not force a separate verifier on Opus 5 for routine work; request concrete tests and tool-backed evidence instead. For long Fable 5 runs, require progress claims to cite actual tool results.
+- Do not force a separate verifier on Opus 5.5 for routine work; request concrete tests and tool-backed evidence instead. For long Fable 5.1 runs, require progress claims to cite actual tool results.
```

## `batch-3:9` — prompt-master/SKILL.md:415; references/patterns.md:15

- **Confidence:** Medium · **vendored:** nidhinjs/prompt-master
- **Pattern:** G1 1b/1f (numeric output caps)
- **Evidence:** `Implicit length ("write a summary") → add word or sentence count`; `"Write a summary in exactly 3 sentences"`
- **Why:** These tell the skill to put hard word/sentence caps into every prompt it generates. Caps tuned for padding models starve reasoning, and qualitative length guidance works better on current Claude. patterns.md:38 (`each under 20 words`) is the same limb. vendored: nidhinjs/prompt-master
- **Action:** rewrite (diff below)
- **Ruling:** Chris ruled: **take** the tone edit in this vendored skill. `skills-safe-update` already carries it across upstream pulls (lockfile `skillFolderHash`, or `.extra-skills.json` `treeSha` for prompt-master).

```diff
--- a/prompt-master/SKILL.md
+++ b/prompt-master/SKILL.md
@@ -415 +415 @@
-- Implicit length ("write a summary") → add word or sentence count
+- Implicit length ("write a summary") → name the reader and what they need from it; add a hard count only when the output fills a fixed-size slot
```

```diff
--- a/prompt-master/references/patterns.md
+++ b/prompt-master/references/patterns.md
@@ -15 +15 @@
-| 15 | **Implicit length** | "write a summary" | "Write a summary in exactly 3 sentences" |
+| 15 | **Implicit length** | "write a summary" | "Write a summary a busy executive can act on without reading the source" |
```

## `batch-3:10` — prompt-master/SKILL.md:432; references/patterns.md:22, :33; references/templates.md:247

- **Confidence:** Medium · **vendored:** nidhinjs/prompt-master
- **Pattern:** G1 1f / 1d (fixed update cadence)
- **Evidence:** `add "After each step output: ✅ [what was completed]"`
- **Why:** This is a fixed per-step narration cadence written for silent or chatty older agents. It also contradicts the skill's own Template M (templates.md:427): "report progress only when it changes or when a checkpoint is reached". All four limbs go together. vendored: nidhinjs/prompt-master
- **Action:** rewrite to the Template M wording (4 hunks below)
- **Ruling:** Chris ruled: **take** the tone edit in this vendored skill. `skills-safe-update` already carries it across upstream pulls (lockfile `skillFolderHash`, or `.extra-skills.json` `treeSha` for prompt-master).

```diff
--- a/prompt-master/SKILL.md
+++ b/prompt-master/SKILL.md
@@ -432 +432 @@
-- Silent agent → add "After each step output: ✅ [what was completed]"
+- Silent agent → add "Report progress when it changes or a checkpoint is reached; ground each completion claim in a tool result"
```

```diff
--- a/prompt-master/references/patterns.md
+++ b/prompt-master/references/patterns.md
@@ -22 +22 @@
-| 22 | **No stop condition for agents** | "build the whole feature" | Explicit stop conditions + ✅ checkpoint output after each step |
+| 22 | **No stop condition for agents** | "build the whole feature" | Explicit stop conditions + progress reported at checkpoints |
```

```diff
--- a/prompt-master/references/patterns.md
+++ b/prompt-master/references/patterns.md
@@ -33 +33 @@
-| 33 | **Silent agent** | No progress output | "After each step output: ✅ [what was completed]" |
+| 33 | **Silent agent** | No progress output | "Report progress when it changes or a checkpoint is reached; ground each completion claim in a tool result" |
```

```diff
--- a/prompt-master/references/templates.md
+++ b/prompt-master/references/templates.md
@@ -246,3 +246,3 @@
 Checkpoints:
-After each major step, output: ✅ [what was completed]
+Report progress when it changes or a checkpoint is reached; ground each completion claim in a tool result.
 At the end, output a full summary of every file changed.
```

## `batch-3:6` — prompt-master/SKILL.md:481

- **Confidence:** High · **vendored:** nidhinjs/prompt-master
- **Pattern:** G1 1a
- **Evidence:** `Does every instruction use the strongest signal word? MUST over should. NEVER over avoid.`
- **Why:** This final-check line makes every generated prompt shout. On Claude targets that causes over-triggering and rigid output. It also contradicts the skill's own Claude guidance at :88, "Prefer positive instructions... over long lists of prohibitions". vendored: nidhinjs/prompt-master
- **Action:** rewrite: `Is each hard constraint stated plainly, once, with its reason, with no emphasis word standing in for the reason?`
- **Ruling:** Chris ruled: **take** the tone edit in this vendored skill. `skills-safe-update` already carries it across upstream pulls (lockfile `skillFolderHash`, or `.extra-skills.json` `treeSha` for prompt-master).

```diff
--- a/prompt-master/SKILL.md
+++ b/prompt-master/SKILL.md
@@ -481 +481 @@
-3. Does every instruction use the strongest signal word? MUST over should. NEVER over avoid.
+3. Is each hard constraint stated plainly, once, with its reason, with no emphasis word standing in for the reason?
```

## `batch-1:R1` — research/SKILL.md:11

- **Confidence:** Medium · **vendored:** mattpocock/skills
- **Pattern:** 2 / Recency trap
- **Evidence:** "one citation is enough even when several sources repeat a primary `.gov`/`.mil` text verbatim"
- **Why:** A general rule (cite the primary once) patched with one session's domain. Local addition #648. vendored: mattpocock/skills
- **Action:** rewrite (hunk)
- **Ruling:** Chris ruled: **take** the tone edit in this vendored skill. `skills-safe-update` already carries it across upstream pulls (lockfile `skillFolderHash`, or `.extra-skills.json` `treeSha` for prompt-master).

```diff
--- a/research/SKILL.md
+++ b/research/SKILL.md
@@ -11 +11 @@
-1. Investigate the question against **primary sources** (official docs, source code, specs, first-party APIs), not retail or aggregator pages (Amazon, Google Books, blog summaries) summarizing them. Follow every claim back to the source that owns it — one citation is enough even when several sources repeat a primary `.gov`/`.mil` text verbatim.
+1. Investigate the question against **primary sources** (official docs, source code, specs, first-party APIs), not retail or aggregator pages (Amazon, Google Books, blog summaries) summarizing them. Follow every claim back to the source that owns it, and cite that source once even when others repeat its text.
```

## `batch-2:M11` — resolving-merge-conflicts/SKILL.md:14

- **Confidence:** Medium · **vendored:** mattpocock/skills
- **Pattern:** G2 instruction files contradict
- **Evidence:** "Stage everything and commit."
- **Why:** burndown/references/merge-tail.md:144, :157-163 (f3ccd00, 2026-09-20, newer than 6388a2e 2026-09-03) says "**Never `git add -A` here**", because it sweeps untracked scripts, local config or credentials into a pushed commit. That reason holds for any merge that is pushed. The rewrite tightens the rule, so no safety rule gets weaker.
- **Action:** rewrite (diff). vendored: mattpocock/skills
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/resolving-merge-conflicts/SKILL.md
+++ b/resolving-merge-conflicts/SKILL.md
@@ -12,3 +12,3 @@
 4. Discover the project's **automated checks** and run them, typically typecheck, then tests, then format. Fix anything the merge broke.
 
-5. **Finish the merge/rebase.** Stage everything and commit. If rebasing, continue the rebase process until all commits are rebased.
+5. **Finish the merge/rebase.** Stage the paths you resolved by name (never `git add -A`, which also sweeps in untracked scratch files and local config), read `git diff --cached`, and commit. If rebasing, continue the rebase process until all commits are rebased.
```

## `batch-3:13` — teach/LEARNING-RECORD-FORMAT.md:41

- **Confidence:** Medium · **vendored:** mattpocock/skills
- **Pattern:** G2 Volatile specifics
- **Evidence:** `Anything already captured tersely in [[GLOSSARY.md]]`
- **Why:** The workspace layout in SKILL.md:12-20 has no GLOSSARY.md. Glossaries are reference documents under `./reference/*.html` (SKILL.md:15, :130-132), so this link points at a file the skill never creates. vendored: mattpocock/skills
- **Action:** rewrite (diff below)
- **Ruling:** audit recommendation (take), accepted by Chris.

```diff
--- a/teach/LEARNING-RECORD-FORMAT.md
+++ b/teach/LEARNING-RECORD-FORMAT.md
@@ -41 +41 @@
-- Anything already captured tersely in [[GLOSSARY.md]] as a term definition. Don't duplicate.
+- Anything already captured tersely in the glossary reference document under `./reference/` as a term definition. Don't duplicate.
```

## `batch-3:12` — teach/SKILL.md:55

- **Confidence:** Medium · **vendored:** mattpocock/skills
- **Pattern:** G1 1a (hedge on a requirement)
- **Evidence:** `If possible, open the lesson file for the user by running a CLI command.`
- **Why:** "If possible" reads literally as permission to skip. Opening the file is the intended behavior, and the user's global rules require it ("open it for me"). vendored: mattpocock/skills
- **Action:** rewrite: `Open the lesson file for the user with a CLI command.`
- **Ruling:** Chris ruled: **take** the tone edit in this vendored skill. `skills-safe-update` already carries it across upstream pulls (lockfile `skillFolderHash`, or `.extra-skills.json` `treeSha` for prompt-master).

```diff
--- a/teach/SKILL.md
+++ b/teach/SKILL.md
@@ -55 +55 @@
-If possible, open the lesson file for the user by running a CLI command.
+Open the lesson file for the user with a CLI command.
```

## `batch-3:14` — to-spec/SKILL.md:32, :40

- **Confidence:** Medium · **vendored:** mattpocock/skills
- **Pattern:** G1 1a / 1c padding
- **Evidence:** `A LONG, numbered list of user stories`; `should be extremely extensive and cover all aspects`
- **Why:** Caps plus "extremely extensive" is a thoroughness booster. Opus 5.5 follows it literally and pads the spec with near-duplicate stories. Coverage of every actor and behavior is the real bar. vendored: mattpocock/skills
- **Action:** rewrite :32, remove :40
- **Ruling:** Chris ruled: **take** the tone edit in this vendored skill. `skills-safe-update` already carries it across upstream pulls (lockfile `skillFolderHash`, or `.extra-skills.json` `treeSha` for prompt-master).

```diff
--- a/to-spec/SKILL.md
+++ b/to-spec/SKILL.md
@@ -32,10 +32,8 @@
-A LONG, numbered list of user stories. Each user story should be in the format of:
+A numbered list of user stories covering every actor and behaviour the feature touches. Each user story should be in the format of:
 
 1. As an <actor>, I want a <feature>, so that <benefit>
 
 <user-story-example>
 1. As a mobile bank customer, I want to see balance on my accounts, so that I can make better informed decisions about my spending
 </user-story-example>
-
-This list of user stories should be extremely extensive and cover all aspects of the feature.
 
```

## `batch-1:W1` — writing-for-agents/SKILL.md:82

- **Confidence:** Medium · **vendored:** mattpocock/skills
- **Pattern:** 1a / Pressure language (taught as technique)
- **Evidence:** "a word too weak to beat the default (_be thorough_ ...) is a no-op, and the fix is a stronger word (_relentless_)"
- **Why:** The skill that writes every other skill teaches escalating intensity words, the pattern that causes over-triggering on current models. Its own "Demand" section (line 51) is the better fix: a concrete completion criterion. vendored: mattpocock/skills
- **Action:** rewrite (hunk)
- **Ruling:** Chris ruled: **take** the tone edit in this vendored skill. `skills-safe-update` already carries it across upstream pulls (lockfile `skillFolderHash`, or `.extra-skills.json` `treeSha` for prompt-master).

```diff
--- a/writing-for-agents/SKILL.md
+++ b/writing-for-agents/SKILL.md
@@ -82 +82 @@
-- Hunt **no-ops** sentence by sentence: an instruction the model already obeys by default pays load to say nothing. The test (does it change behaviour versus the default?) is model-relative, not reader-relative: two people disagreeing about a no-op disagree about the default, and settle it by running the document, not by debate. When a sentence fails, delete the whole sentence rather than trim words from it. The test also grades leading words: a word too weak to beat the default (_be thorough_ when the agent is already thorough-ish) is a no-op, and the fix is a stronger word (_relentless_), not a different technique.
+- Hunt **no-ops** sentence by sentence: an instruction the model already obeys by default pays load to say nothing. The test (does it change behaviour versus the default?) is model-relative, not reader-relative: two people disagreeing about a no-op disagree about the default, and settle it by running the document, not by debate. When a sentence fails, delete the whole sentence rather than trim words from it. The test also grades leading words: a word too weak to beat the default (_be thorough_ when the agent is already thorough-ish) is a no-op; when the default really falls short, raise the step's **demand** (a checkable, exhaustive completion criterion), not the word's volume.
```
