# Subagent dispatch — tiers and gotchas

Read this before fanning out any subagent work: which mode to launch it in, and
which model tier to pick.

## Fire-and-return vs. named-background

- **Fire-and-return work** (the common case): no `name`, `run_in_background:
  false`. The agent runs, reports, and the slot is freed.
- **Named + background** creates a persistent teammate that parks idle between
  turns. Only use this when you actually intend to check back in on a
  long-running agent later — not as the default for a quick fan-out task.
- If you're not sure which you need, test one subagent before fanning out a
  batch — a misconfigured batch of persistent idle agents is expensive to
  notice and clean up.

## Model tier rubric

The interactive session runs on Fable. A subagent with no `model` inherits
that — so **always pass `model`**, never inherit. Fable is for the live
conversation; every handoff that makes sense on Opus goes to Opus.

Pick the tier by how much the agent must *do*, not by the topic:

- **`haiku`** — single-step, self-verifying, no navigation. Classify or
  extract against a rubric, reformat one given file, a lookup where you hand
  the agent the file directly.
  - Example: "Given this file's contents, extract every TODO into a list."
- **`sonnet`** (default for fan-out) — multi-step mechanical work that
  navigates but needs no judgment. Grep sweeps, surveys, locating code,
  specified codemods, doc-reading research passes.
  - Example: "Find every call site of `parseConfig` across the repo and list
    the files." The agent must search and navigate, but there's no judgment
    call in what counts as a match.
- **`sonnet` is also the implementation tier** — ticket-sized, spec'd coding
  with tests. The code lane's downstream nets (TDD red-green, the three axes
  of `/two-axis-code-review`, the after-the-fact log read) are exactly the tie-breaker's "a check would
  catch a miss", so builds default down, not up. Escalate a build to Opus
  only when the ticket itself is a judgment call: design still fuzzy, gnarly
  concurrency, or no test can express the requirement.
- **`opus`** — the agent's own reasoning *is* the deliverable. Adversarial
  review, diagnosis, security review, spec/ticket decomposition, deliverable
  prose.
  - Example: "Review this migration for concurrency safety" — the value is in
    the judgment call, not in finding the file.
- **`fable`** — the rung above Opus. Not a subagent tier by default: the
  session already runs on it. Pass it to a subagent only when Opus has
  visibly fallen short on that exact task and nothing downstream would catch
  a wrong answer. Costs about double Opus and a single turn can run many
  minutes.

The Sonnet/Haiku split is about navigation, not reasoning depth: an Explore
task that must navigate the repo is Sonnet-tier even when the judgment it
exercises along the way is nil (pure pattern matching).

**Fable 5.1 at low effort is not a subagent tier here**, despite Anthropic's
cost-per-task claims: Fable draws from a separate quota, so routing subagent
work to it spends the budget reserved for the live session.

**Tie-breaker:** when unsure between two tiers, drop to the cheaper one only if
a downstream check — a test, a build, or your own review — would catch a
miss. If nothing downstream would catch a wrong answer, go up a tier.
