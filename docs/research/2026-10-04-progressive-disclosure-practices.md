# Progressive disclosure in agent instruction files: what loads, what gets read (2026-10-04)

Question: how do vendors and practitioners handle progressive disclosure in coding-agent instruction files (Claude Code CLAUDE.md, AGENTS.md, Cursor rules, Codex, Copilot, Agent Skills)? Which mechanisms actually get disclosed material loaded when it is needed? Context: `2026-10-04-claude-md-pointer-reads.md` found the four pointer docs under `flow/claude/` opened in 0-17% of the sessions that performed the action each one covers.

Method: fetched each source's markdown or HTML with curl on 2026-10-04 and read the relevant sections; arXiv abstracts via the export API; Lost in the Middle via its PDF. Claude Code installed here is v2.1.289 (`claude --version`). Sources already read in full by `2026-10-04-agent-workflow-prior-art.md` (IFScale, the ETH AGENTS.md study, OpenAI's Harness post, Beardsley) are reused from that doc, not re-read. I spawned no subagents.

Evidence grades: **doc** (vendor documentation of its own product's behaviour), **observed** (checked on this machine), **measured** (a study with numbers; peer review status noted), **vendor-internal** (a vendor's eval of its own setup, unaudited), **opinion** (advice, vendor or practitioner, without data).

## Synopsis

1. **Only three Claude Code mechanisms load text without the model choosing to:** session-start files (CLAUDE.md, unscoped rules, `@`imports, output style, SessionStart hooks), path-triggered files (nested CLAUDE.md, `paths:` rules, `paths:` skills), and hook output (`additionalContext`, a deny reason, a Stop-hook block). Everything else depends on the model choosing to load it: skill bodies, files a skill references, and any "read X" sentence. Anthropic's memory doc says this directly about a CLAUDE.md that tells Claude in words to read AGENTS.md: "Claude sees `AGENTS.md` only if it decides to open the file."
2. **Path triggers fire on Read, Write and Edit, not Bash.** Most of Chris's pointer-doc triggers are Bash commands (`gh pr merge`, `pkill`, `shot-scraper`, `gh issue create`), so `.claude/rules/` with `paths:` cannot reach them. A PreToolUse/PostToolUse hook with an `if: "Bash(gh pr merge *)"` filter can, and its `additionalContext` (up to 10,000 characters) arrives deterministically.
3. **On-demand loading by model choice measured badly in the one controlled eval I found.** Vercel's Next.js evals (vendor-internal) found the skill was never invoked in 56% of cases, and the pass rate with the skill matched having no docs at all (53%). An explicit instruction raised the trigger rate to 95%+ and the pass rate to 79%. An always-on 8 KB index in AGENTS.md reached 100%. Chris's 0-17% pointer-read rate fits that pattern.
4. **Vendors converge on the same numbers.** Anthropic: under 200 lines per CLAUDE.md; imports "don't reduce its context cost". Cursor: rules under 500 lines. Copilot: instructions "no longer than 2 pages". Codex: 32 KiB cap on combined AGENTS.md. Every vendor says to move things that must happen into hooks, permissions or linters, not prose. All of this is opinion or a product limit, not measurement.
5. **Measured degradation is real, but at higher counts or on different tasks than Chris's setup.** IFScale found near-perfect compliance to about 150-250 simple instructions for reasoning models, then decline. ManyIFEval found all-of-10 success of 44% for Claude 3.5 Sonnet. Lost in the Middle found a U-shape with a drop of more than 20 points. Chris's always-on set is roughly 155 sentence-level statements before the system prompt and the output style. That puts it in the zone IFScale flags, though IFScale measures keyword inclusion, not agent behaviour.
6. **HumanLayer's claim that CLAUDE.md arrives wrapped in "may or may not be relevant" does not hold here.** In transcripts from v2.1.284 and v2.1.289, that disclaimer is attached to the separate userEmail/gitStatus block. CLAUDE.md arrives under "IMPORTANT: These instructions OVERRIDE any default behavior and you MUST follow them exactly as written."
7. **Implication for Chris:** turn the pointer lines into hooks keyed on the commands that need them. Shrink the hard-rule text that existing hooks already enforce to a single line each. Move reply-shape rules (Communication) into the Quill output style. Put each procedure into the skill that runs it. Use `paths:` rules only for file-edit triggers (instruction files, `SKILL.md`, `docs/research/`). Details in Q5.

## Q1. Claude Code mechanisms and their exact semantics

All from "How Claude remembers your project", Anthropic, docs, undated (fetched 2026-10-04), https://code.claude.com/docs/en/memory (**doc**) unless noted.

| Mechanism | When it loads | Deterministic? | Notes |
|---|---|---|---|
| `~/.claude/CLAUDE.md`, ancestor `CLAUDE.md`/`CLAUDE.local.md` | Session start, in full; re-read from disk after `/compact` | Yes | Delivered "as a user message after the system prompt, not as part of the system prompt itself". Target "under 200 lines per CLAUDE.md file. Longer files consume more context and reduce adherence." Files up to 4 MiB load in full. |
| `@path` imports | Session start, "expanded and loaded into context at launch alongside the CLAUDE.md that references them" | Yes (eager) | "Imported files can recursively import other files, with a maximum depth of four hops." Imports "help you organize a long file but don't reduce its context cost". A path in backticks is not imported. So Chris's `@RULES.md` and `@SOUL.md` are eager. |
| Nested `CLAUDE.md` below cwd | "included when Claude reads files in those subdirectories" | Yes, on file read | Lost on compaction until that directory is touched again ("Steering Claude Code", below). |
| `.claude/rules/*.md` without `paths:` | Session start, "same priority as `.claude/CLAUDE.md`" | Yes | Mechanically the same as CLAUDE.md text. |
| `.claude/rules/*.md` with `paths:` | "trigger when Claude uses the Read, Write, or Edit tool on a file matching the pattern, not on every tool use" | Yes, but only on file tools | `paths` is the only frontmatter field read. User-level `~/.claude/rules/` exists and loads before project rules. The doc does not say what a user-level `paths:` glob is matched against (see "Not verified"). A rules symlink pointing outside the working directory loads only after you approve external imports, and then only the files without `paths`. |
| AGENTS.md | Read by default only when no CLAUDE.md/CLAUDE.local.md is in cwd or above (v2.1.277+); setting `claude-md-and-agents-md` reads both | Yes | Chris's repo `CLAUDE.md` is `@AGENTS.md`, which is the documented way to share one file. |
| Skills (model-invocable) | "Description always in context, full skill loads when invoked" | **No**: the model decides | Listing budget is 1% of the context window. Each description plus `when_to_use` is cut at 1,536 characters. When the budget overflows, descriptions are dropped starting with the least-used skills. "Skill not triggering" troubleshooting is about rewording the description. (Skills doc, https://code.claude.com/docs/en/skills) |
| Skills with `disable-model-invocation: true` | "Description not in context, full skill loads when invoked" (by the user typing `/name`) | Yes when typed; the model cannot pick it on its own | 57 of the 79 `SKILL.md` files in `~/.agents/skills/` carry this key (`grep -l`). Detail placed in such a skill reaches a session only when someone types its command. |
| Skills with `paths:` | "Claude loads the skill automatically only when working with files matching the patterns" | Partly: the path match is deterministic, but it gates auto-loading and the doc does not say whether a match injects the body or only makes the skill eligible | Not tested. |
| Files a skill references | Read with Read/Bash when Claude decides | **No** | Anthropic's skill guide warns that nested references get partly read: "Claude might use commands like `head -100` to preview content", so it says to keep references one level deep and give files over 100 lines a table of contents. ("Skill authoring best practices", Anthropic, docs, undated, https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) |
| Skill body after compaction | Re-attached: first 5,000 tokens of each invoked skill, 25,000 tokens in total, most recent first | Yes, within the budget | Skills doc. |
| Hook `additionalContext` | Wrapped in a system reminder at the point the hook fired: SessionStart and SubagentStart before the first prompt; UserPromptSubmit alongside the prompt; **PreToolUse/PostToolUse "next to the tool result"**; Stop at end of turn | Yes, fires on its event | Capped at 10,000 characters. Above that, the text goes to a file and Claude gets the path plus a 2,000-character preview, and "Claude Code doesn't ask it to" read the file. The `if` field takes one permission rule such as `"Bash(gh pr merge *)"`. The doc advises writing the text "as factual statements rather than imperative system instructions", because text framed as system commands "can trigger Claude's prompt-injection defenses". ("Hooks reference", Anthropic, docs, undated, https://code.claude.com/docs/en/hooks) |
| PreToolUse deny | `permissionDecisionReason` (or stderr on exit 2) "shown to Claude" before the call runs | Yes, and it blocks | The only hook output that arrives *before* the action. PreToolUse `additionalContext` arrives after the call runs. |
| Stop hook block / `additionalContext` | End of turn; keeps the conversation going; capped at 8 consecutive continuations | Yes | Hooks doc. |
| InstructionsLoaded hook | Fires on every CLAUDE.md/rules load with `load_reason` (`session_start`, `nested_traversal`, `path_glob_match`, `include`, `compact`) | Observability only | This is how to measure whether path rules fire. Hooks doc. |
| Output style | System prompt, every session; never compacted | Yes | A custom style drops Claude Code's built-in software-engineering instructions unless `keep-coding-instructions: true`. Applies to the main session and forks, not other subagents. ("Output styles", Anthropic, docs, undated, https://code.claude.com/docs/en/output-styles) |
| Subagent definitions | Name and description at session start; body becomes the subagent's own system prompt | Body loads only when spawned | Subagents load CLAUDE.md (except Explore/Plan, or with `omitClaudeMd: true`). `skills:` preloads full skill bodies at startup, but not skills with `disable-model-invocation: true`. ("Create custom subagents", Anthropic, docs, undated, https://code.claude.com/docs/en/sub-agents) |
| Plain-text pointer ("read X") | Whenever the model decides | **No** | Memory doc, "Remove an earlier AGENTS.md workaround": "A `CLAUDE.md` that tells Claude in words to read `AGENTS.md`: Claude sees `AGENTS.md` only if it decides to open the file." |

"Steering Claude Code: when to use CLAUDE.md, skills, hooks, and subagents", Michael Segner (Anthropic), 2026-06-18, https://claude.com/blog/steering-claude-code-skills-hooks-rules-subagents-and-more (**doc/opinion**). It gives the same table plus two authority claims. First, output styles "carry the highest instruction-following weight of any method" because they sit in the system prompt. Second, on "Never do this" in CLAUDE.md: "Claude will follow the instruction most of the time, but when under pressure, in a long session or an ambiguous situation... the model can fail to follow a prompted rule. A real guardrail needs to be deterministic, and the enforcement methods are hooks and permissions." It also says to think of CLAUDE.md "as an index pointing to other files where Claude can find more information as needed". That index advice is opinion, and the pointer-read data here contradicts it for Chris's setup.

**Observed: how CLAUDE.md is framed.** HumanLayer's post (Q4) says Claude Code wraps CLAUDE.md in "IMPORTANT: this context may or may not be relevant to your tasks". I grepped the 60 most recent transcripts under `~/.claude/projects`. In `-home-caneff-src-factorio-crap/bfebb434-….jsonl` (v2.1.284, 2026-09-29), that sentence ends the *userEmail/gitStatus* system reminder. The CLAUDE.md reminder in the same transcript opens: "Codebase and user instructions are shown below. Be sure to adhere to these instructions. IMPORTANT: These instructions OVERRIDE any default behavior and you MUST follow them exactly as written." This session (v2.1.289) shows the same split. So the "ignored because it is told it may be irrelevant" explanation does not apply to current versions. Earlier versions are not checked.

## Q2. What vendors recommend (all opinion or product limits unless marked)

- **Anthropic, "Best practices for Claude Code"**, docs, undated, https://code.claude.com/docs/en/best-practices : "For each line, ask: 'Would removing this cause Claude to make mistakes?' If not, cut it. Bloated CLAUDE.md files cause Claude to ignore your actual instructions!" "If Claude keeps doing something you don't want despite having a rule against it, the file is probably too long and the rule is getting lost." On emphasis: "If you emphasize many lines, none of them stands out." Hooks: "Unlike CLAUDE.md instructions which are advisory, hooks are deterministic." Its fix for the over-specified CLAUDE.md: "If Claude already does something correctly without the instruction, delete it or convert it to a hook."
- **Anthropic, memory doc** (above): add to CLAUDE.md when "Claude makes the same mistake a second time". "If an entry is a multi-step procedure or only matters for one part of the codebase, move it to a skill or a path-scoped rule." Startup warns when a file, or the combined total, is over length.
- **Anthropic, "Extend Claude Code"**, docs, undated, https://code.claude.com/docs/en/features-overview : hook vs skill, "Determinism: Always fires on its event; the trigger is guaranteed" vs "Claude interprets the instructions; outcome can vary".
- **Barry Zhang, Keith Lazuka, Mahesh Murag, "Equipping agents for the real world with Agent Skills"**, Anthropic Engineering, 2025-10-16, https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills : three levels (metadata, then SKILL.md body, then bundled files), and "the amount of context that can be bundled into a skill is effectively unbounded". Levels 2 and 3 load only "If Claude thinks the skill is relevant", with "the skill author… trusting that Claude will read `forms.md` only when filling out a form." Advice: "Monitor how Claude uses your skill in real scenarios… watch for unexpected trajectories."
- **Anthropic, "Skill authoring best practices"** (above): SKILL.md body under 500 lines; references one level deep. Its conditional-pointer pattern names the *situation*: "**For tracked changes**: See REDLINING.md". Chris's pointers name a topic list instead ("Detail — gates, lanes, …: path").
- **agents.md**, Agentic AI Foundation, undated, https://agents.md/ : no required fields; nested files, "the closest one takes precedence"; "explicit user chat prompts override everything". Nothing on length.
- **OpenAI, "Custom instructions with AGENTS.md"**, Codex docs, undated, https://developers.openai.com/codex/guides/agents-md : the chain is built "once per run". Codex walks from the project root *down to cwd* only, with no lazy loading of deeper directories, at most one file per directory, and `AGENTS.override.md` wins. It "stops adding files once the combined size reaches… 32 KiB by default". That is a hard truncation, not advice.
- **Ryan Lopopolo, "Harness engineering"**, OpenAI, 2026-02-11, https://openai.com/index/harness-engineering/ (read in full by the prior-art doc): one big AGENTS.md "failed in predictable ways. Too much guidance becomes non-guidance… It rots instantly." They keep about 100 lines as a map and "promote the rule into code" (custom linters whose errors carry remediation text). **vendor-internal**.
- **Cursor, "Rules"**, docs, undated, https://cursor.com/docs/rules : four types. `Always Apply`; `Apply Intelligently` ("When Agent decides it's relevant based on description"); `Apply to Specific Files` (globs); `Apply Manually` (@-mention). Advice: "Keep rules under 500 lines"; "Reference files instead of copying their contents"; "Copying entire style guides: Use a linter instead"; "Add rules only when you notice Agent making the same mistake repeatedly." Cursor's types map onto Claude Code's: Always = CLAUDE.md, Intelligently = skill description, Specific Files = `paths:` rule, Manually = `/skill`.
- **GitHub, "Adding repository custom instructions for GitHub Copilot"**, docs, undated, https://docs.github.com/en/copilot/how-tos/configure-custom-instructions/add-repository-instructions : repo-wide file plus `*.instructions.md` with `applyTo` globs (both apply when matched); `excludeAgent`; nearest AGENTS.md wins; "Instructions must be no longer than 2 pages."

## Q3. Evidence on instruction count, length and compliance

| Study | Grade | Result | Caveat |
|---|---|---|---|
| Jaroslawicz, Whiting, Shah, Maamari, "How Many Instructions Can LLMs Follow at Once?" (IFScale), arXiv 2507.11538, 2025-07-15, https://arxiv.org/abs/2507.11538 | measured, preprint | Best model 68% at 500 instructions. Reasoning models near-perfect to about 150-250, then decline. Bias toward earlier instructions. Errors shift to omission under load. Claude Opus 4: 44.6% at 500 (from the prior-art doc's full read). | The task is keyword inclusion in a report, not agent behaviour. |
| Harada, Yamazaki, Taniguchi, Kojima, Iwasawa, Matsuo, "Curse of Instructions: Large Language Models Cannot Follow Multiple Instructions at Once" (ManyIFEval), OpenReview, 2024-10-04, https://openreview.net/forum?id=R6q67CDBCH | measured, ICLR 2025 submission; **abstract only** | All-of-n success ≈ (per-instruction success)^n. Ten instructions: GPT-4o 15%, Claude 3.5 Sonnet 44%. Self-refinement raised these to 31% and 58%. | Formatting constraints; older models. |
| Liu, Lin, Hewitt, Paranjape, Bevilacqua, Petroni, Liang, "Lost in the Middle: How Language Models Use Long Contexts", arXiv 2307.03172, 2023-07-06 (v3 2023-11-20), https://arxiv.org/abs/2307.03172 | measured, TACL | U-shaped accuracy by position. In 20- and 30-document QA, GPT-3.5-Turbo with the answer mid-context dropped more than 20 points, below its closed-book 56.1%. | Retrieval QA, 2023 models. Chris's text sits at the *start* of context, but the pointer lines are at the end of each section, mid-file. |
| Kelly Hong, Anton Troynikov, Jeff Huber, "Context Rot: How Increasing Input Tokens Impacts LLM Performance", Chroma technical report, 2025-07-14, https://research.trychroma.com/context-rot | measured, not peer reviewed | 18 models, including Claude 4. "Performance grows increasingly unreliable as input length grows", and distractors hurt non-uniformly. | Read the introduction and section list only. Lengths far above Chris's ~4k tokens of instructions. |
| Gloaguen, Mündler, Müller, Raychev, Vechev, "Evaluating AGENTS.md", arXiv 2602.11988, 2026-02-12 (v2 2026-06-23), https://arxiv.org/abs/2602.11988 | measured, preprint | Context files did not generally raise success and added over 20% to cost. "Instructions in the context files are well followed." Repo overviews were "not helpful". | Instructions *are* followed, which means each one costs work whether it helps or not. |
| Jude Gao, "AGENTS.md outperforms skills in our agent evals", Vercel, 2026-01-27, https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals | vendor-internal | Baseline 53%. Skill as default 53%, never invoked in 56% of cases. Skill plus an explicit AGENTS.md instruction: 79%, trigger rate 95%+, and the wording changed results ("You MUST invoke the skill" anchored on docs and missed project context). An 8 KB docs *index* in AGENTS.md: 100%. Their reasons: "No decision point", "Consistent availability", "No ordering issues". | Suite size and model not stated in the parts I read. The task needed knowledge the model lacked (new Next.js 16 APIs), which is a stronger pull to read than Chris's docs, whose content the model believes it already has. |

Not measured anywhere I opened: whether a *pointer line* in CLAUDE.md gets followed, as a function of how it is worded. The closest are Vercel's wording sensitivity and Chris's own 0-17% count.

## Q4. What practitioners do

- **Kyle (HumanLayer), "Writing a good CLAUDE.md"**, 2025-11-25, https://www.humanlayer.dev/blog/writing-a-good-claude-md (**opinion**). Their root CLAUDE.md is "less than sixty lines", and "< 300 lines is best". Keep task docs in `agent_docs/*.md` and list them with a one-line description, telling Claude "to decide which (if any) are relevant and to read them". "Prefer pointers to copies… include `file:line` references." "Never send an LLM to do a linter's job", with a Stop hook to run formatter and linter. It claims "Claude Code's system prompt contains ~50 individual instructions" (their count, unverified here). Its system-reminder explanation is contradicted by Q1's observation. Its own progressive-disclosure method is the plain-text pointer that Q1 classes as model-chosen.
- **Simon Willison, "Claude Skills are awesome, maybe a bigger deal than MCP"**, 2025-10-16, https://simonwillison.net/2025/Oct/16/claude-skills/ (**opinion**): each skill "only takes up a few dozen extra tokens". He notes the pre-skills pattern of an AGENTS.md line like "Read PDF.md before attempting to create a PDF". That pointer is keyed on an *action*, not a topic.
- **Ryan Lopopolo (OpenAI)**, above: rules promoted to linters with remediation text; a "doc-gardening" agent; CI checks that docs stay fresh and cross-linked.
- **Scott Beardsley, "I built 51 agents. Then I started removing some."**, 2026-02-23, https://scott.beards.ly/blog/built-51-agents (from the prior-art doc; **opinion**): a rule, a hook or a test only after a mistake repeats; "I don't want the harness filled with instructions for hypothetical problems."
- **Jude Gao (Vercel)**, above: "Compress aggressively… An index pointing to retrievable files works just as well". The index carried a one-line instruction to prefer retrieval over training data.

Common patterns across these: pointers rather than copies; keep the always-on file to a map; turn anything that must happen into a hook, linter or test; add a rule on the second occurrence. The two disclosure styles differ in one way that matters. Vercel's index and Willison's example name the *situation or API* that should send the agent to a file. HumanLayer's and Chris's name *topics*.

## Q5. Implications for Chris's setup

**Why the pointers get skipped.** I suggest three reasons, from Q1-Q4 plus the pointer-reads doc; this is inference, not a test.

1. Reading is a model choice. Anthropic documents it, and Vercel measured a 56% non-use rate with nothing wording-sensitive to pull the agent in.
2. Each pointer follows an inline summary of its doc. The agent judges it already has the rule, and nothing tells it that the rule is incomplete. Vercel's agents read because the model *lacked* the API knowledge.
3. The lines name topics ("gates, lanes, issue labels, CI, sweeps…"), not the triggering action. The skill guide's pattern is "**For X**: See FILE".

Rewording would probably help somewhat, but Q3 shows wording effects are fragile. The deterministic route is a hook.

**Hooks (deterministic).** Hooks already exist for several rules: `block-dangerous-git.sh` (push and `gh pr merge` gated on ownership, history destroyers), `require-agent-model.sh` (Agent `model`), `wrap-background-jobs.sh`, and the git `commit-identity-guard*` hooks.
- *Hard rules → Gate 1, merge ownership, Commit identity; Agents and jobs → "Every Agent call passes `model`"*: already enforced. Inline text could drop to one line each (the rule plus "a hook enforces it"). The hook's deny reason already carries the detail at the moment of action. That trims much of the 660-word Hard rules section.
- *Agents and jobs → "A merge … `--repo owner/name`, only after `gh pr view` shows not-draft and CLEAN"*: candidate for a check in `block-dangerous-git.sh`'s `gh pr merge` branch (deny without `--repo`; or run `gh pr view --json isDraft,mergeStateStatus` itself). That turns prose into a check.
- *Gotchas → "A process kill gets its own Bash call"*: PreToolUse `if: "Bash(*kill*)"`, deny when the command contains anything else. The deny reason can carry all 314 words of SHELL-SAFETY's kill section, which fits under 10,000 characters.
- *Workflow → "Before filing any ticket … search open issues"*: a PreToolUse hook on `gh issue create` can run the search itself and return the matching open issues. That is deterministic retrieval, not a reminder.
- *Pointer docs*: replace each "Detail — …" line with a hook keyed on the triggering command that returns the relevant section as `additionalContext`. Examples: `implement-dispatch` and `gh pr merge` → the OPERATIONS § Dispatch / § End section; `shot-scraper` and `zed` → VISUAL-INSPECTION; `gh issue create|edit` → WORKFLOW § Issue state.

Two cautions:
- PreToolUse `additionalContext` arrives *after* the call runs. Key the hook on a precursor command (`gh pr view` before `gh pr merge`) or use a deny.
- A deny-to-teach conflicts with Chris's own hard rule, "When a permission prompt or hook denies a step, report the exact denial and stop". Teaching hooks should use `additionalContext`, not deny, unless that rule gets a carve-out. **Decision for Chris.**

OPERATIONS (3,176 words) is too large for one injection. Above 10,000 characters the agent gets a path it is not asked to read, so split it by section.

**Skills.** Procedures belong in the skill that performs them (memory doc; Steering post). OPERATIONS § Dispatch/Control/Wait/End and WORKFLOW § Gate 2 lane mechanics are procedures. Most of Chris's skills are `disable-model-invocation: true`, so their bodies load only when typed. That is deterministic for user-started workflows (`/implement`, `/landed`). It is invisible to a model deciding on its own. Moving operational detail into the skill that runs the operation ties loading to the run. A skill the model is supposed to find by itself is the weakest option (Vercel).

**Path-scoped rules.** These fire only on Read, Write and Edit, so they suit file-edit triggers:
- `**/CLAUDE.md`, `**/AGENTS.md`, `**/RULES.md`, `**/CODING_STANDARDS.md` → the "Progressive disclosure governs this file" paragraph, now inline in Hard rules.
- `**/SKILL.md` and code extensions → Gate 2's code-lane reminder.
- `docs/research/**` → the research-write conventions.

Whether `paths:` works from user-level `~/.claude/rules/` across repos is undocumented. Test it with an InstructionsLoaded hook logging `load_reason: path_glob_match`.

**Output style.** *Communication* (474 words) is entirely about reply shape. Quill (630 words) already sits in the system prompt, which Anthropic says has the highest instruction-following weight. Moving Communication there removes it from CLAUDE.md with no loss of determinism, because both load every session. Output styles do not reach non-fork subagents, and Communication is about talking to Chris, so that is not a loss.

Separately: Quill's frontmatter has no `keep-coding-instructions: true` (checked with `head`). Per the output-styles doc, that drops Claude Code's built-in instructions on scoping, comments and "running tests before declaring work complete". Some of *Done means verified* may be re-adding what the style removed. I have not tested that.

**Stays inline.** *Precedence*, *Done means verified*, the principle line of each hard rule, and the Workflow ordering (`/grill-me` → `/to-spec` → …). These fire in most sessions, are judgement rather than tool-shaped, and no hook can check them.

**Measure, then cut.** Add an InstructionsLoaded logger and a PostToolUse logger for the new teaching hooks. Rerun the pointer-reads count after two weeks. Anthropic's own test is "observing whether Claude's behavior actually shifts".

## Not verified

- Whether user-level `~/.claude/rules/*.md` with `paths:` match files in every repo, and what the glob is relative to: the memory doc is silent.
- Whether a `paths:` skill injects its body on match or only becomes eligible to load.
- What happens to model behaviour when Quill drops the coding instructions.
- Vercel's suite size and model; ManyIFEval beyond the abstract; Context Rot beyond its introduction.
- HumanLayer's "~50 instructions" in the system prompt.
- Whether the "may or may not be relevant" wrapper was ever on CLAUDE.md in older versions; only v2.1.284 and v2.1.289 transcripts were checked.

Pages opened for this note: the eight code.claude.com pages named above (memory, skills, hooks, hooks-guide, output-styles, sub-agents, best-practices, features-overview); the Steering post; the Agent Skills engineering post; the skill authoring best-practices page; agents.md; the Codex AGENTS.md guide; Cursor Rules; GitHub's Copilot repository-instructions page; the HumanLayer, Willison and Vercel posts; arXiv abstracts 2307.03172, 2507.11538 and 2602.11988; the Lost in the Middle PDF (pages 1-6); the Chroma report; and the ManyIFEval OpenReview abstract via search.

## Addendum: settings hooks vs mods (function hooks)

Sources: "React to events", Anthropic, docs, undated,
https://code.claude.com/docs/en/plugins/mods/events ; "Mods overview",
Anthropic, docs, undated, https://code.claude.com/docs/en/plugins/mods/overview .
Local: `claude --version` = 2.1.289 (mods need 2.1.287+); no mod installed
(no `register.js` under `~/.claude/plugins` or `~/src`).

What a mod adds for disclosure, versus a settings hook:

- **Text before the action.** A `tool.call` hook runs before the tool. It can
  `deny`, rewrite arguments, or answer with `{ result }` so the tool never
  runs. A settings PreToolUse `additionalContext` arrives "alongside the tool
  result", i.e. after.
- **Prompt-time context.** `prompt.submit` can append text only Claude reads
  (`context: [...]`), so a prompt mentioning "merge" can carry the merge
  section. `skill.prompt` and `prompt.section` can rewrite a skill's text or a
  system-prompt section.
- **Shared state.** A mod's hooks share module variables, so "show the
  SHELL-SAFETY section once per session" needs no temp file.
- **Subagents.** `tool.call` fires for subagent tool calls too.

Costs:

- Fails open: a hook that throws or times out is skipped unless it has a
  `.catch` handler.
- Not loaded in a Desktop-app WSL session ("plugins aren't available in WSL
  sessions"); the terminal CLI under WSL does load them.
- Text that changes between requests from `prompt.section`/`skill.prompt`
  invalidates the prompt cache.
- New surface: JavaScript plugin plus marketplace install, versus the
  existing tested shell hooks in `flow/claude/hooks/`.

Anthropic's own guidance (overview, "Compare" table): pick a settings hook
"to block, allow, or log an event with a script you already have"; pick a mod
for a pane, a command, or "to rewrite an event".
