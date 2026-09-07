---
name: research
description: Investigate a question against high-trust primary sources and capture the findings as a Markdown file in the repo. Use when the user wants a topic researched, docs or API facts gathered, or reading legwork delegated to a background agent.
---

Spin up a **background agent** to do the research, so you keep working while it reads.

Its job:

1. Investigate the question against **primary sources** (official docs, source code, specs, first-party APIs), not retail or aggregator pages (Amazon, Google Books, blog summaries) summarizing them. Follow every claim back to the source that owns it — one citation is enough even when several sources repeat a primary `.gov`/`.mil` text verbatim.
2. Read each source once per run; reuse it for every claim it supports.
3. Do the reading yourself — a sub-agent's completion reports to the top-level session, not to you, so nested delegation loses the work. If the question is too large for one agent, report that and stop.
4. Write the findings to a single Markdown file, citing each claim's source.
5. Save it where the repo already keeps such notes; match the existing convention, and if there is none, put it somewhere sensible and say where.
