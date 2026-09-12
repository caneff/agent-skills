# Skill trigger audit

## Scope and method

I read the YAML frontmatter of all 83 `SKILL.md` files. I then processed the
top-level JSONL files in `~/.claude/projects/-home-caneff--agents-skills/`:
there were 136 available, so the requested 150-session sample resolves to all
136. The scan used only `message.role == "user"` text, skipped records wrapped
in `<system-reminder>` or `<local-command-stdout>` (and Claude's local-command
caveats), ignored `/clear` and other non-tasks, and found 132 task starts, 62
of which were natural-language requests.

For each task start, I traced assistant records up to the next substantive user
message for an explicit `skill` invocation. An explicit slash command counts as
an invocation, not a failed automatic trigger. The judgments below are against
frontmatter descriptions only, not the bodies of the skills.

## Confirmed false negatives

### `diagnosing-bugs`

No invocation followed any of these task openings:

- `9d41ed63…`: “burndown is spawning explore agents **weirdly** … and
  **hanging** while waiting for them …”
- `3ed5cd75…`: “we seem to keep getting issues with **waiters** in different
  orchestration tasks **whats going on**”
- `becadbda…`: “why do reviewers keep getting **cut off**”

The current description recognizes only a “hard bug,” a performance regression,
or the words `diagnose`, `debug this`, `broken`, `throwing`, `failing`, and
`slow`. It does not anticipate the user's operational vocabulary: *hanging*,
*weirdly*, *waiters*, and *cut off*.

Proposed description:

> Diagnose hard bugs, hangs, and performance regressions. Use when the user
> says “diagnose” or “debug this”, or reports something broken, failing,
> hanging, getting cut off, behaving weirdly, or stuck waiting.

### `research`

No invocation followed these explicit research requests:

- `6acaa467…`: “**do your research** are there other skills like prompt-master
  that are more powerful or **up to date**”
- `829dac82…`: “**do some research** … what options do we have” for a
  single steering agent.
- `e9ee53c0…`: “**do some research about** what makes for good tests vs crap
  ones.”

“A topic researched” and “reading legwork” are descriptions of the result, not
the phrases the user uses to request it. The description also omits comparison
and options research.

Proposed description:

> Research a question from high-trust primary sources and capture the findings
> as Markdown in the repo. Use when the user says “do some research”, “research
> about”, “look into”, or asks for options, comparisons, current capabilities,
> or evidence about a tool, workflow, or practice.

### `extract-coding-standards`

No invocation followed `d0dae26e…`:

> “I would like to make a skill that goes over the last N submissions in a repo
> … and **extracts any coding standards** … encoded into `CODING_STANDARDS` …”

This is nearly the capability sentence verbatim, but the description offers no
`Use when…` language and does not anticipate *last N submissions*, *extract
coding standards*, or *encode into CODING_STANDARDS*.

Proposed description:

> Extract the coding standards a repo actually enforces from recent PRs,
> reviews, commits, and current code, and write them into `CODING_STANDARDS.md`.
> Use when the user says “extract coding standards”, “mine recent commits or
> PRs for standards”, “last N submissions”, or “write CODING_STANDARDS”.

### `find-skills`

No invocation followed either request:

- `6acaa467…`: “other **skills like prompt-master** that are more powerful or
  up to date”
- `48b3967c…`: “Which of the **skills** here might be good to **adopt** …”
  with an external skills-repository link.

“Discover and install” misses the selection language the user actually uses:
*skills like X*, *adopt*, *more powerful*, and a linked skill collection.

Proposed description:

> Discover, evaluate, and install agent skills from the open skills ecosystem.
> Use when the user asks “what other skills”, “skills like X”, “which skills
> should we adopt”, “find a skill for”, or shares a skills repository to assess.

### `orca-cli`

No invocation followed `351ce6db…`:

> “how many **abandoned dead worktrees** do we have **across repos**”

The description names an “Orca worktree” but not inventory or cleanup language.
The user does not normally prefix this kind of request with the product name.

Proposed description:

> Inspect and operate Orca-managed worktrees, folder contexts, terminals,
> repositories, automations, artifacts, skill sharing, worktree comments, and
> Orca's embedded browser through the `orca` CLI. Use when the user mentions an
> Orca worktree or asks to list, inspect, find, clean up, or report on stale,
> abandoned, child, or cross-repo worktrees; also use it for Orca terminals,
> handoffs, artifacts, or embedded-browser work.

### `writing-for-agents`

No invocation followed:

- `00ee9cb8…` and `d2345add…`: “Want to update my **global claude stuff** …
  tell me what … to add and to which file”
- `d0dae26e…`: “I would like to **make a skill** …”

The description uses the repository filenames (`AGENTS.md`, `CLAUDE.md`) but
not the user's language for those files: *global Claude stuff* and *make a
skill*. The latter prompt is also an `extract-coding-standards` request; both
skills should be allowed to load, with the extraction skill owning the work.

Proposed description:

> Write and revise instructions for coding agents, including skills and
> `AGENTS.md` or `CLAUDE.md`. Use when the user says “make a skill”, “edit a
> SKILL.md”, “global Claude setup”, “global Claude stuff”, or asks what to add
> to an agent-instruction file.

## Overlapping descriptions / merge or boundary candidates

| Skills | Why they compete | Recommendation |
| --- | --- | --- |
| `auto-paper-demo`, `implement-paper-auto` | Both promise a fully automatic research-paper Marimo notebook. The only distinction is “demo” versus “implement,” which is not a reliable user trigger. | Merge, or make one a clearly named mode of the other. |
| `grill-me`, `grill-with-docs`, `grilling` | All begin with the same “relentless interview to sharpen a plan or design” trigger. The generic `grilling` also owns explicit “grill” phrases. | Make `grilling` the single trigger/dispatcher, with the other two explicit modes; otherwise remove their model invocation. |
| `wait-what`, `ww` | These are the same capability; `ww` says it is an alias. | Keep `ww` as slash-only alias and remove it from model triggering, or merge the aliases at the command layer. |
| `find-skills`, `ask-matt` | “Which skills should I use/adopt?” can mean routing among installed skills or finding an external skill. The audit's linked-repository prompt sits exactly on that boundary. | Keep both only with a hard split: `ask-matt` = choose a current-repo flow; `find-skills` = discover/evaluate external skills. |
| `research`, `read-the-damn-docs` | `research` claims “docs or API facts”; the other claims official current docs for version-sensitive packages, SDKs, auth, billing, and API drift. | Do not necessarily merge, but remove version-sensitive docs/API work from `research`'s trigger clause and route it explicitly to `read-the-damn-docs`. |
| `implement`, `implement-spec` | “Implement a spec or tickets” is covered by `implement`; `implement-spec` starts with “Drive a sliced spec.” | Preserve the scale distinction in both descriptions (one ticket vs. multi-worker sliced spec), or make `implement` dispatch to `implement-spec`. |
| `writing-beats`, `writing-fragments`, `writing-shape` | All start with terse “Writing” language and do not expose a user-facing outcome. A request to draft/rewrite prose has no clear way to select one. | Consider one writing skill with explicit explore/structure/shape modes, or rewrite every description around its input and output. |

## Retire candidates: no plausible trigger in this sample

These had no invocation and no natural-language task opening whose requested
outcome plausibly matched the description. This is a corpus signal, not a
recommendation to delete a useful but niche capability.

- Notebook, puzzle, or app-specific: `add-molab-badge`, `anywidget-generator`,
  `auto-paper-demo`, `create-lmd-page`, `implement-paper`,
  `implement-paper-auto`, `jupyter-to-marimo`, `marimo-batch`,
  `marimo-notebook`, `marimo-pair`, `sm-link`, `streamlit-to-marimo`,
  `wasm-compatibility`.
- Specialized audits: `audit-instructions`, `crap-audit`, `dead-code`,
  `docstring-coverage`, `domain-drift`, `duplication`, `error-handling`,
  `mutation-audit`, `type-tightness`.
- Setup, migration, or scaffolding: `migrate-to-shoehorn`,
  `scaffold-exercises`, `setup-matt-pocock-skills`, `setup-peacock-color`,
  `setup-pre-commit`, `setup-python-repo`, `setup-ts-deep-modules`.
- Writing, teaching, and presentation: `humanizer`, `teach`,
  `to-questionnaire`, `visual-plan`, `visual-recap`, `visual-teach`,
  `writing-beats`, `writing-fragments`, `writing-shape`.
- Other narrow workflows: `grill-with-docs`, `loop-me`, `prototype`.

I deliberately did **not** put `domain-modeling`, `implement-spec`,
`orchestration`, or `python-testing-patterns` on the retirement list. They had
no clean single-skill task start, but several prompts were adjacent to their
purpose; their absence is insufficient evidence that their descriptions have no
future trigger.

## Near misses not counted as false negatives

`skill-audit` was adjacent to “What other things could I strip from Claude's
default context window?”, but that asks about all context sources, not
specifically stale model-invocable skills. Similarly, “I would still like a
command that says ‘burn down the ticket queue’” asks to design/change a command,
not to run `burndown`. Counting either as a trigger failure would overstate the
evidence.
