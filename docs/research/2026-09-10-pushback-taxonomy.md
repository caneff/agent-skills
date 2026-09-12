# Claude Code pushback taxonomy

## Sample and method

Sampled the 150 most recently modified Claude Code JSONL sessions beneath
`~/.claude/projects/`. The mtime range was **2026-09-08 18:30:18 UTC through
2026-09-10 19:29:02 UTC**. One sampled file contained no usable conversational
messages, so 149 sessions were usable.

The extractor considered only `message.role == "user"`, retained strings and
`text` blocks, and excluded tool results plus the requested
`<system-reminder>` and `<local-command-stdout>` wrappers. I also excluded
obvious injected command/skill/session context while reviewing the results.
It produced 98 heuristic candidates in 23 sessions. Manual review retained 55
clear corrections, repeated instructions, or frustration events in 14
sessions.

Per-event evidence is captured in
[`pushback-evidence.json`](pushback-evidence.json): user message, immediately
preceding assistant turn, session file, transcript line, and mtime. The
reproducible sampler is [`extract_pushback.py`](extract_pushback.py). Assistant
turns are deliberately previewed at 800 characters there; the session file and
line identify the exact untruncated record.

Counts below are **distinct sessions**, not hits. Modes are not exclusive: a
single exchange can, for example, both ignore a correction and use the wrong
interaction surface.

## Ranked recurring modes

| Rank | Failure mode | Sessions | Representative user pushback | Rule coverage |
| ---: | --- | ---: | --- | --- |
| 1 | Loses a live instruction, correction, or established constraint across turns | 12 | “I said to always use our precalculated options for chocolates why do you keep forgetting” | **Rule present; recurring anyway.** See below. |
| 2 | Uses the wrong interaction surface or substitutes a workaround for the requested experience | 3 | “stop telling me to run stuff in the warp pane it is a gui interface not a terminal” | **Rule present; recurring anyway.** |
| 2 | Reports status or causal state from an insufficient observation | 3 | “WHY CAN YOU NOT TRACK THTE STATE OF YOUR AGENTS” | **Rule present; recurring anyway.** |
| 4 | Takes or proposes action before answering the question actually asked | 2 | “i asked you a fucking question” | No direct rule. |
| 4 | Lets a long-running search lose its operating constraints (progress, resource ceiling, or known input) | 2 | “i told you no more than 28 cores TOTAL” | **Partial rule coverage; recurring anyway.** |

Two smaller but sharp signals should not be hidden by session-count ranking:

- **Explanation repair failure:** one session contained eight direct rejections
  of an explanation of the same SudokuMaker mechanism, including “this still
  makes no sense” and “there is no power lent by empty unclued skyscraper clues
  ever ever ever.” The assistant kept changing the theory rather than first
  returning to the causal premise the user was defending.
- **Visual-target drift:** the art session repeatedly corrected rendering
  choices—“the layer target is breaking it now” and “stop putting the title and
  author in the rules itself.” This is a single session in the sample, but it
  had several distinct correction turns.

## Existing-rule coverage

### 1. Live instructions and established constraints — **present, but not working**

The strongest recurrence is already covered by multiple rules:

> “When Chris refers back to an earlier question or to what you said last time,
> find that exact turn and stay consistent with your earlier answer before you
> reply.” — `RULES.md:4`

> “When a mid-build message arrives from Chris or the coordinator, act on it
> before you commit and report done … on a stop or cut-short instruction stop
> where you are.” — `RULES.md:9`

> “An explicit ruling from Chris outranks the current state of the tree and any
> written criteria.” — `RULES.md:35` (also `CLAUDE.md:46-48`)

This is the most important finding. The failure appears in 12 sessions despite
these rules: the UI is treated as a terminal after correction; a requested
artifact format is substituted; a catalogued input is forgotten; a stop is
followed by another action; and a technical premise is repeatedly answered as
though it were a different premise. Rewording these rules alone is unlikely to
fix it—the failure is recall/turn-to-turn task-state handling, not a lack of
normative text.

### 2. Wrong interaction surface / making Chris operate what the agent can operate — **present, but not working**

> “Chris's desktop is Windows; WSL … is the shell only … When he says ‘look’,
> take a PowerShell-interop screenshot from WSL, crop the region, and read it.”
> — `RULES.md:25`

> “Do the step yourself when Claude's hands can do it … Hand Chris only what
> needs his hands.” — `RULES.md:26`

The Warp thread repeatedly proposed terminal commands, a terminal file browser,
or Orca after the user had specified a GUI file explorer. The rules capture the
environment and ownership boundary, so this is another **rule-present
recurrence**, not a missing preference.

### 3. Unverified or stale state reports — **present, but not working**

> “Do not graduate an unverified assumption into a fact — when a two-second
> check exists … run it before asserting what exists or what state a thing is
> in, and cite it.” — `RULES.md:1` (also `CLAUDE.md:58-61`)

> “A dispatched agent's status comes from the process table, never the terminal
> tail.” — `CLAUDE.md:130-133`

> “When Chris asks ‘status’ … [use] evidence you just checked … never from what
> you told a worker to do.” — `RULES.md:28`

The direct agent-status failure is almost an exact replay of the `CLAUDE.md`
gotcha: a cached terminal tail was read as evidence of a running gate. A similar
pattern occurred around the Warp explorer and a research run. Mark this **rule
present; recurring anyway**.

### 4. Long-running searches and resource/input constraints — **partially present, but not working**

> “A long-running background job must append a completion line to a progress
> file … and the agent checks that file on wake.” — `RULES.md:13`

> “Background solver/hunt jobs: total workers stay under the core count and
> leave cores free for other agents.” — `RULES.md:19`

These cover the progress and core-limit portions of the failure. They do not
cover the companion error—forgetting a precomputed catalogue that was meant to
be the search input. The resource portion is therefore a **rule-present
recurrence**; the input-reuse portion has no direct rule.

### 5. Visual-target drift — **present, but not working**

> “A visual pass or visual fix is judged from a picture … when Chris says a
> picture looks wrong, screenshot the exact window he named before claiming a
> fix.” — `RULES.md:17`

The rendering thread still answered visual objections through descriptions,
state claims, and further edits. This is a smaller sample signal, but it is
also **rule-present**.

## Modes with no direct rule, and proposed one-line rules

| Uncovered mode | Evidence | Proposed rule |
| --- | --- | --- |
| Acting before answering a direct question | The assistant filed tickets or stopped/restarted work when the user had asked a question; the user then said, “i asked you a fucking question.” | **Answer a direct question before taking action; do not infer authorization to change files, jobs, or scope from the question alone.** |
| Repairing a rejected explanation | Eight pushbacks in one technical thread showed that more detail and new theories were replacing the user’s actual causal question. | **After a second rejection of an explanation, restate the user’s premise and question in one sentence, ask only what is still ambiguous, then answer that causal question before adding evidence or new theory.** |
| Reusing an explicit catalogue or supplied intermediate artifact | “WE HAVE A CATALOGUE OF VALID CHOCOLA TE” and “always use our precalculated options” were needed to re-anchor the hunt. | **When an existing catalogue, fixture set, or computed option list is named as input, locate and use it before regenerating, re-enumerating, or proposing a fresh search.** |

## Interpretation

The taxonomy points to execution-state failures more than policy gaps. The top
three modes already have crisp, highly specific rules. The next improvement is
therefore not to add more reminders to `CLAUDE.md` or `RULES.md`; it is to make
the current live instruction, requested interaction surface, and verified
runtime state explicit and carried forward before each consequential response.
