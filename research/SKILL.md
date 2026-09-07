---
name: research
description: Investigate a question against high-trust primary sources and capture the findings as a Markdown file in the repo. Use when the user wants a topic researched, docs or API facts gathered, or reading legwork delegated to a background agent.
---

Spin up a **background agent** to do the research, so you keep working while it reads.

Its job:

1. Investigate the question against **primary sources** (official docs, source code, specs, first-party APIs), not a secondary write-up of them. Follow every claim back to the source that owns it. Skip retail and aggregator pages (Amazon, Google Books, blog summaries) — go to the source they're summarizing instead. When a claim quotes a primary `.gov`/`.mil` text verbatim, one citation to that text is enough; don't collect a second source for the same quote.
2. Read every source once per run and reuse that copy for every claim it supports — don't re-fetch a source you've already read this run.
3. Never spin up your own sub-agents. A sub-agent's completion reports to the top-level session, not to you, so its work never reaches your findings file — you'd redo the reading anyway. If the question is too large for one agent to cover, say so and stop; don't fan out to cover it.
4. Write the findings to a single Markdown file, citing each claim's source.
5. Save it where the repo already keeps such notes; match the existing convention, and if there is none, put it somewhere sensible and say where.
