# Prompt audit, 2026-09-27

An audit of every skill and always-loaded instruction file for prompting patterns that no longer fit Claude Opus 5.5, stale facts the repo contradicts, and instruction files that contradict each other. It ran `/doctor prompt-audit` (bundled `claude-api` skill, `shared/prompt-audit.md`) over 79 skills and 6 always-loaded files: 149 findings.

## Rulings (Chris, 2026-09-27)

1. **grilling vs CLAUDE.md** — CLAUDE.md wins: a grilling round asks a few numbered questions.
2. **Box size** — RULES.md corrected to 39 GB; the ~24 GB `ulimit -v` budget stays. Shipped in second-brain-v2 0177d70.
3. **28-session cap** — idle and done sessions don't count; burndown's counter is the reference. Shipped in second-brain-v2 0177d70.
4. **Dated incident notes in skills** — strip them, with the matching test edits.
5. **Numeric word caps on reviewer briefs** — remove them.
6. **Tone edits in vendored skills** — take all 24. Every edited vendored skill is covered by `skills-safe-update`'s edit protection: 23 via the lockfile's `skillFolderHash`, prompt-master via `.extra-skills.json` `treeSha` (checked 2026-09-27).

Every other finding took the audit's recommendation: 57 diffs taken, 3 fixes to write, 30 left as they are. `AGENTS.md` (08735f0) and `Memory/RULES.md` shipped directly as non-code.

## Clusters

Each cluster owns its files; no two clusters touch the same file, so they can run in parallel.

| Cluster | Findings | Skills |
|---|---|---|
| [`implement-lane`](implement-lane.md) | 16 | implement, implement-spec |
| [`review`](review.md) | 11 | flow, multi-axis-code-review |
| [`audits`](audits.md) | 21 | all-audits, audit-instructions, burndown, crap-audit, duplication, improve-codebase-architecture, mutation-audit, ponytail-audit, test-audit, thermo-nuclear-code-quality-review |
| [`marimo`](marimo.md) | 23 | anywidget-generator, auto-paper-demo, implement-paper, implement-paper-auto, marimo-batch, marimo-notebook, marimo-pair, streamlit-to-marimo |
| [`testing`](testing.md) | 9 | python-testing-patterns |
| [`writing-workflow`](writing-workflow.md) | 18 | ask-matt, codebase-design, diagnosing-bugs, file-ticket, find-skills, grilling, handoff, prompt-master, research, resolving-merge-conflicts, teach, to-spec, writing-for-agents |
| [`visual-misc`](visual-misc.md) | 13 | create-lmd-page, setup-python-repo, skills-safe-update, sm-link, visual-plan, visual-recap, visual-teach |
