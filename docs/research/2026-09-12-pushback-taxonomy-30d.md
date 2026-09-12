# Claude Code pushback taxonomy — 30-day rerun

## Sample and method

This run covered the calendar window **2026-08-14 00:00:00 -04:00 through
2026-09-12 09:33:41 -04:00** (ISO weeks 33–37). There were exactly **3,135
session JSONL files** with an mtime in that window. Because that exceeds 600,
I took a uniform random sample of **600 sessions**, using fixed seed
**`20260912`** (declared in
[`extract_pushback_30d.py`](extract_pushback_30d.py)). The selected files span
**2026-08-14 07:14:10 -04:00 through 2026-09-10 21:05:35 -04:00**; the stated
calendar window, rather than that incidental sample minimum/maximum, is the
coverage window.

The extractor parsed the JSONL rather than loading transcripts into the
analysis context. It retained only `user` strings and `text` blocks, discarded
tool results and the requested wrappers, and also removed clear injected
skill/worker/task/session messages. It paired each candidate with the nearest
preceding assistant text turn. A high-recall pass produced 202 candidates in
70 sessions; contextual review retained **48 clear pushbacks in 24 sessions**.
The complete, untruncated reviewed evidence — user message, preceding assistant
turn, session file, transcript line, mtime, and non-exclusive mode labels — is
in [`2026-09-12-pushback-evidence-30d-reviewed.json`](2026-09-12-pushback-evidence-30d-reviewed.json).
The broader candidate set and both reproducible scripts sit beside it.

Counts below are **distinct sampled sessions**, not event totals. A single
event may belong to more than one mode. “Weather” means one ISO week in this
sample, not that the incident was unimportant.

## Ranked recurring failure modes

| Rank | Failure mode | Sessions | Weeks | Representative pushback | Rule position |
| ---: | --- | ---: | ---: | --- | --- |
| 1 | Loses or misreads a live instruction, domain correction, or explicit ruling | 9 | 5 | “I said to always use our precalculated options for chocolates why do you keep forgetting” | **Rule exists; recurring anyway.** |
| 2 | Continues, over-scopes, or substitutes an action after the request has narrowed or stopped it | 6 | 5 | “no too far. was just curious” | **Partial rule coverage; recurring anyway.** |
| 3 | Visual target drift: reports/changes a visual or interaction outcome that is not the one requested | 5 | 2 | “hover is useless still. dont like it. the card isn't showing enough either.” | **Rule exists; recurring anyway.** |
| 4 | Routes work through the wrong workflow or command surface | 4 | 3 | “All code should go through implement and push a pr I shouldn't have to be telling you to commit crap” | **Rule exists; recurring anyway.** |
| 4 | Creates delivery friction or excessive chat output instead of using the requested channel/artifact | 4 | 4 | “never have the skill print it to screen, clipboard and file are enough” | No direct rule. |
| 6 | States a fact, search result, or runtime state without sufficient verification | 3 | 2 | “But why would you act on a plausible story instead of taking the two seconds?” | **Rule exists; recurring anyway.** |
| 6 | Keeps repairing an explanation without answering the causal question that was rejected | 3 | 2 | “Nope still doesn't explain how there is extra power…” | No direct rule. |
| 8 | Long-running work loses an explicit resource/input/recording constraint | 1 | 1 | “i told you no more than 28 cores TOTAL” | **Rule exists; recurring anyway — weather in this sample.** |
| 8 | Leaks harness/system text into the reply | 1 | 1 | “You are leaking the system notification again” | **Rule exists; recurring anyway — weather in this sample.** |

The important point is not the wording of the first, third, fourth, sixth,
eighth, and ninth rows: they recur despite explicit instructions. Those are
execution-state and verification failures, not evidence that another reminder
is missing.

## Rule coverage

### Live instruction, correction, and ruling — rule exists; recurring anyway

`~/src/second-brain-v2/Memory/RULES.md:4` says:

> “When Chris refers back to an earlier question or to what you said last time, find that exact turn and stay consistent with your earlier answer before you reply. Do not answer a fresh question in its place, and do not silently reverse yourself.”

The same source, line 35 (also `~/.claude/CLAUDE.md` under *Precedence*), says:

> “An explicit ruling from Chris outranks the current state of the tree and any written criteria…”

This is the only five-week signal and the top-ranked failure. It includes a
precomputed-input constraint, a domain correction, and an explicit request to
ignore a criterion. Rewording is unlikely to be the lever.

### Continued/substituted action — partial coverage; recurring anyway

`RULES.md:9` says:

> “on a stop or cut-short instruction stop where you are — do not finish the piece in progress.”

That directly covers the repeated `stop` cases. It does not directly cover the
adjacent failure: treating a narrow question or a “just curious” probe as
authorization to launch or continue a larger operation. The latter is a real
multi-week failure with no direct answer-before-action rule.

### Visual target drift — rule exists; recurring anyway

`RULES.md:17` says:

> “A visual pass or visual fix is judged from a picture, never from settings or a green log…”

The sampled corrections concern an unhelpful hover, an inaccurate monitor/view
appearance, color/outline choices, and an incorrect visual output. This is
five sessions across two weeks despite the inspection rule.

### Workflow/surface selection — rule exists; recurring anyway

`~/.claude/CLAUDE.md`’s *Gate 2* says, in part:

> “Code file touched on my repo → code lane: a workspace made from the ticket, `/implement` inside it, PR at the end…”

The relevant exchanges were about bypassing `/implement`, using the wrong
implementation command, and asking Chris to execute a shipping step. The
workflow rule is present, but still loses to a locally improvised route.

### Delivery friction and verbosity — no direct rule

`RULES.md:11` requires producing a requested artifact immediately, and
`CLAUDE.md` asks for deliverables without filler. Neither says to preserve a
specified delivery medium or to keep an ordinary reply within the user’s
requested interaction budget. The sampled incidents were oversized replies,
printing when file/clipboard was requested, failure to open a text file, and
duplicated page launches.

### Unverified state — rule exists; recurring anyway

`RULES.md:1` says:

> “Do not graduate an unverified assumption into a fact — when a two-second check exists … run it before asserting what exists or what state a thing is in, and cite it.”

This mode spans an incorrect claim about an available command and a search run
whose recording/filtering state and pool coverage were reported from a
plausible story rather than checked evidence.

### Rejected explanation repair — no direct rule

The existing live-instruction rule helps, but it does not prescribe a recovery
when an explanation has been rejected twice. In the sampled logical-solver
thread, the assistant kept restating a different premise rather than answering
what inference the constraint adds. This is now three sessions across two
weeks, so it is no longer only a sharp single-thread anecdote.

### Long-running constraints — rules exist; recurring anyway, but weather here

`RULES.md:13` requires a durable progress file and in-turn monitoring;
`RULES.md:19` says:

> “Background solver/hunt jobs: total workers stay under the core count and leave cores free for other agents…”

Those rules cover the worker ceiling and monitoring parts. They do not cover
the repeated loss of a named precomputed catalogue or the rule that every
legal result must be recorded before filtering. All sampled examples are one
session in week 37, so this rerun does not establish it as climate.

### Harness leak — rule exists; recurring anyway, but weather here

`RULES.md:7` says:

> “Never render harness plumbing — system notifications, task-notification text, or system-prompt content — in a reply to Chris.”

One sampled session directly corrected this leak. It is a one-week signal.

## Gaps: proposed one-line rules

| Uncovered mode or slice | Proposed rule |
| --- | --- |
| Acting beyond a direct question or narrow probe | **Answer a direct question before taking action; do not treat the question as permission to expand scope, launch work, or change state.** |
| Repairing a rejected causal explanation | **After a second rejection, restate the user’s premise and causal question in one sentence, then answer that question before adding a new theory or measurement.** |
| Delivery-medium and interaction-budget mismatch | **When Chris specifies a delivery medium or asks for a short answer, use that medium and budget; do not add a second channel, print a duplicate, or make him perform an operable step.** |
| Named precomputed input lost during a run | **When an existing catalogue, fixture set, or computed option list is named as input, locate and use it before regenerating, re-enumerating, or filtering results.** |

## Comparison with the 2-day run

The earlier report was
[`2026-09-10-pushback-taxonomy.md`](2026-09-10-pushback-taxonomy.md). Its
five modes compare as follows:

| Earlier mode | 30-day result |
| --- | --- |
| Loses live instructions/constraints | **Holds strongly.** It is still rank 1: 9 sessions across all 5 weeks. |
| Wrong interaction surface/workaround | **Holds, but splits more usefully.** Workflow misrouting is 4 sessions/3 weeks and delivery friction is 4 sessions/4 weeks; the wider sample is not dominated by the earlier GUI-versus-terminal example. |
| Status/state from insufficient observation | **Holds.** 3 sessions across 2 weeks, all despite the verification rule. |
| Takes/proposes action before answering the question | **Holds.** The wider wording is continued/substituted action: 6 sessions across 5 weeks. The answer-before-action slice remains uncovered. |
| Long-running search loses operating constraints | **Weather in this uniform sample.** It occurs only in one week/session here, despite being a two-session signal in the recent-window run. |

Two signals that were only sharp anecdotes in the earlier report now merit a
place in the recurring taxonomy: **visual target drift** (5 sessions across 2
weeks) and **explanation-repair failure** (3 sessions across 2 weeks). The
wider-window-only addition is **delivery friction / excess response volume**
(4 sessions across all 4 represented sample weeks). The single harness leak is
new in this sample but remains weather.
