---
name: research
description: >-
  Research a question from high-trust primary sources and capture the findings as Markdown in the repo. Use when the user says "do some research", "research about", "look into", or asks for options, comparisons, current capabilities, or evidence about a tool, workflow, or practice. Version-sensitive package, SDK, or API docs go to read-the-damn-docs instead.
---

Spin up a **background agent** to do the research, so you keep working while it reads.

Its job:

1. Investigate the question against **primary sources** (official docs, source code, specs, first-party APIs), not retail or aggregator pages (Amazon, Google Books, blog summaries) summarizing them. Follow every claim back to the source that owns it, and cite that source once even when others repeat its text.
2. Read each source once per run; reuse it for every claim it supports.
3. Do the reading yourself — a sub-agent's completion reports to the top-level session, not to you, so nested delegation loses the work. If the question is too large for one agent, report that and stop.
4. Write the findings to a single Markdown file, citing each claim's source.
5. Save it where the repo already keeps such notes; match the existing convention, and if there is none, put it somewhere sensible and say where.
6. Report a search result with the space it actually covered. Never state a ceiling, a floor or an impossibility from a sampled, annealed or time-capped run: say what was enumerated and what was not, and call a bound proven only after an exhaustive pass over a stated space. A solver or hunt report splits its runs into proven infeasible, timed out and found, and labels any count a cap or timeout stopped as capped. The same holds for a catalogue or web search: 'none found' names the pages actually opened and the field that was matched, because a title-only pass misses what a full-page pass finds.
7. Evidence for a claim about the outside world is the specific page — title, author, date, URL — never a site, index or tag link, and never a search phrase standing in for a result.
