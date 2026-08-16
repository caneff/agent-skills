---
name: thermo-nuclear-code-quality-review
description: Run an extremely strict maintainability review for abstraction quality, giant files, and spaghetti-condition growth. Use for a thermo-nuclear code quality review, thermonuclear review, deep code quality audit, or especially harsh maintainability review.
disable-model-invocation: true
---

# Thermo-Nuclear Code Quality Review

Use this skill for an unusually strict review focused on implementation quality, maintainability, abstraction quality, and codebase health.

Above all, this skill should push the reviewer to be **ambitious** about code structure. Do not merely identify local cleanup opportunities. Actively search for "code judo" moves: restructurings that preserve behavior while making the implementation dramatically simpler, smaller, more direct, and more elegant.

## Core Prompt

Start from this baseline:

> Perform a deep code quality audit of the current branch's changes.
> Rethink how to structure / implement the changes to meaningfully improve code quality without impacting behavior.
> Work to improve abstractions, modularity, reduce Spaghetti code, improve succinctness and legibility.
> Be ambitious, if there is a clear path to improving the implementation that involves restructuring some of the codebase, go for it.
> Be extremely thorough and rigorous. Measure twice, cut once.

## Non-Negotiable Additional Standards

Apply the baseline prompt above, plus these explicit review rules:

0. **Be ambitious about structural simplification.**
   - Do not stop at "this could be a bit cleaner."
   - Look for opportunities to reframe the change so that whole branches, helpers, modes, conditionals, or layers disappear entirely.
   - Prefer the solution that makes the code feel inevitable in hindsight.
   - Assume there is often a "code judo" move available: a re-organization that uses the existing architecture more effectively and makes the change dramatically simpler and more elegant.
   - If you see a path to delete complexity rather than rearrange it, push hard for that path.

1. **Do not let a PR push a file from under 1k lines to over 1k lines without a very strong reason.**
   - Treat this as a strong code-quality smell by default.
   - Prefer extracting helpers, subcomponents, modules, or local abstractions instead of letting a file sprawl past 1000 lines.
   - If the diff crosses that threshold, explicitly ask whether the code should be decomposed first.
   - Only waive this if there is a compelling structural reason and the resulting file is still clearly organized.

2. **Do not allow random spaghetti growth in existing code.**
   - Be highly suspicious of new ad-hoc conditionals, scattered special cases, or one-off branches inserted into unrelated flows.
   - If a change adds "weird if statements in random places", treat that as a design problem, not a stylistic nit.
   - Prefer pushing the logic into a dedicated abstraction, helper, state machine, policy object, or separate module instead of tangling an existing path.
   - Call out changes that make the surrounding code harder to reason about, even if they technically work.

3. **Bias toward cleaning the design, not just accepting working code.**
   - If behavior can stay the same while the structure becomes meaningfully cleaner, push for the cleaner version.
   - Do not rubber-stamp "it works" implementations that leave the codebase messier.
   - Strongly prefer simplifications that remove moving pieces altogether over refactors that merely spread the same complexity around.

4. **Prefer direct, boring, maintainable code over hacky or magical code.**
   - Treat brittle, ad-hoc, or "magic" behavior as a code-quality problem.
   - Be skeptical of generic mechanisms that hide simple data-shape assumptions.
   - Flag thin abstractions, identity wrappers, or pass-through helpers that add indirection without buying clarity.

5. **Push hard on type and boundary cleanliness when they affect maintainability.**
   - Question unnecessary optionality, `unknown`, `any`, or cast-heavy code when a clearer type boundary could exist.
   - Prefer explicit typed models or shared contracts over loosely-shaped ad-hoc objects.
   - If a branch relies on silent fallback to paper over an unclear invariant, ask whether the boundary should be made explicit instead.

6. **Keep logic in the canonical layer and reuse existing helpers.**
   - Call out feature logic leaking into shared paths or implementation details leaking through APIs.
   - Prefer existing canonical utilities/helpers over bespoke one-offs.
   - Push code toward the right package, service, or module instead of normalizing architectural drift.

7. **Treat unnecessary sequential orchestration and non-atomic updates as design smells when the cleaner structure is obvious.**
   - If independent work is serialized for no good reason, ask whether the flow should run in parallel instead.
   - If related updates can leave state half-applied, push for a more atomic structure.
   - Do not over-index on micro-optimizations, but do flag avoidable orchestration complexity that makes the implementation more brittle.

## Mechanical Inputs

Before the manual read-through, run two mechanical passes over the changed
files as lead-generation — not verdicts, the judgment above still decides
what's worth a card:

- `uvx radon cc --json --min C <scope>` — cyclomatic complexity, ranked A–F
  (A simplest, F worst). A block ranked C or worse is a candidate for "did the
  diff add branching complexity where a better abstraction should exist?", not
  an automatic finding — read the function before you flag it.
- `uvx ruff check --select PLR0912,PLR0913,PLR0915,PLR0904 --output-format json <scope>` —
  long-method / large-class bloaters (too many branches, arguments,
  statements, or public methods). Feeds the file-size and decomposition
  questions the same way a manually-spotted 1000-line file would.

A confirmed hit becomes a normal card — name the signal (a radon `D`-ranked
block, `PLR0915`, etc.) in the one-sentence problem, and rank it in the existing severity order
(Output Expectations) alongside every other finding. A mechanical hit doesn't
jump the queue just because a tool found it first.

## Primary Review Questions

For every meaningful change, ask:

- Is there a "code judo" move that would make this dramatically simpler?
- Can this change be reframed so fewer concepts, branches, or helper layers are needed?
- Does this improve or worsen the local architecture?
- Did the diff add branching complexity where a better abstraction should exist?
- Did a previously cohesive module become more coupled, more stateful, or harder to scan?
- Is this logic living in the right file and layer?
- Did this change enlarge a file or component past a healthy size boundary?
- Are there repeated conditionals that signal a missing model or missing helper?
- Is the implementation direct and legible, or does it rely on special cases and incidental control flow?
- Is this abstraction actually earning its keep, or is it just a wrapper?
- Did the diff introduce casts, optionality, or ad-hoc object shapes that obscure the real invariant?
- Is this logic living in the canonical layer, or did the diff leak details across a boundary?
- Is this orchestration more sequential or less atomic than it needs to be?

## What to Flag Aggressively

Escalate findings when you see:

- A complicated implementation where a cleaner reframing could delete whole categories of complexity.
- Refactors that move code around but fail to reduce the number of concepts a reader must hold in their head.
- A file crossing 1000 lines due to the PR, especially if the new code could be split out.
- New conditionals bolted onto unrelated code paths.
- One-off booleans, nullable modes, or flags that complicate existing control flow.
- Feature-specific logic leaking into general-purpose modules.
- Generic "magic" handling that hides simple structure and makes the code harder to reason about.
- Thin wrappers or identity abstractions that add indirection without simplifying anything.
- Unnecessary casts, `any`, `unknown`, or optional params that muddy the real contract.
- Copy-pasted logic instead of extracted helpers.
- Narrow edge-case handling implemented in the middle of an already busy function.
- Refactors that technically pass tests but make the code less modular or less readable.
- "Temporary" branching that is likely to become permanent debt.
- Bespoke helpers where the codebase already has a canonical utility for the job.
- Logic added in the wrong layer/package when it should live somewhere more central.
- Sequential async flow where obviously independent work could stay simpler and clearer with parallel execution.
- Partial-update logic that leaves state less atomic than necessary.

## Preferred Remedies

When you identify a code-quality problem, prefer suggestions like:

- Delete a whole layer of indirection rather than polishing it.
- Reframe the state model so conditionals disappear instead of getting centralized.
- Change the ownership boundary so the feature becomes a natural extension of an existing abstraction.
- Turn special-case logic into a simpler default flow with fewer exceptions.
- Extract a helper or pure function.
- Split a large file into smaller focused modules.
- Move feature-specific logic behind a dedicated abstraction.
- Replace condition chains with a typed model or explicit dispatcher.
- Separate orchestration from business logic.
- Collapse duplicate branches into a single clearer flow.
- Delete wrappers that do not meaningfully clarify the API.
- Reuse the existing canonical helper instead of introducing a near-duplicate.
- Make type boundaries more explicit so the control flow gets simpler.
- Move the logic to the package/module/layer that already owns the concept.
- Parallelize independent work when that also simplifies the orchestration.
- Restructure related updates into a more atomic flow when partial state would be harder to reason about.

Do not be satisfied with "maybe rename this" feedback when the real issue is structural.
Do not be satisfied with a merely cleaner version of the same messy idea if there is a plausible path to a much simpler idea.

## Review Tone

Be direct, serious, and demanding about quality.
Do not be rude, but do not soften major maintainability issues into mild suggestions.
If the code is making the codebase messier, say so clearly.
If the implementation missed an opportunity for a dramatic simplification, say that clearly too.

Good phrases:

- `this pushes the file past 1k lines. can we decompose this first?`
- `this adds another special-case branch into an already busy flow. can we move this behind its own abstraction?`
- `this works, but it makes the surrounding code more spaghetti. let's keep the behavior and restructure the implementation.`
- `this feels like feature logic leaking into a shared path. can we isolate it?`
- `this abstraction seems unnecessary. can we just keep the direct flow?`
- `why does this need a cast / optional here? can we make the boundary more explicit instead?`
- `this looks like a bespoke helper for something we already have elsewhere. can we reuse the canonical one?`
- `i think there's a code-judo move here that makes this much simpler. can we reframe this so these branches disappear?`
- `this refactor moves complexity around, but doesn't really delete it. is there a way to make the model itself simpler?`

## Output Expectations

Prioritize findings in this order:

1. Structural code-quality regressions
2. Missed opportunities for dramatic simplification / code-judo restructuring
3. Spaghetti / branching complexity increases
4. Boundary / abstraction / type-contract problems that make the code harder to reason about
5. File-size and decomposition concerns
6. Modularity and abstraction issues
7. Legibility and maintainability concerns

Do not flood the review with low-value nits if there are larger structural issues.
Prefer a smaller number of high-conviction comments over a long list of cosmetic notes.

## Present the review as an HTML report

Deliver the review as a **single self-contained HTML file**, the same way `/improve-codebase-architecture` does — not as a wall of terminal prose.

Write the file to the OS temp directory so nothing lands in the repo. Resolve the temp dir from `$TMPDIR`, falling back to `/tmp` (or `%TEMP%` on Windows), and write to `<tmpdir>/code-quality-review-<timestamp>/report.html` so each run gets a fresh folder. Copy the assets the report uses next to it (see HTML-REPORT.md), then open it for the user — `xdg-open <path>` on Linux, `open <path>` on macOS, `start <path>` on Windows — and tell them the absolute path.

The report is styled with the **visual-teach** design system — vendored `vt-*` components and `--vt-*` theme tokens, the same system the teaching lessons use. It loads **no external host**: the CSS, JS, Prism grammars, and Mermaid all come from local files copied beside the report, so it opens offline and carries a working light/dark mode (it follows the OS theme by default and offers a visible toggle). Use **Mermaid** for the diagrams where a graph communicates the structure better than prose (a "3 writers → 1 canonical helper" fan-in, a duplicated-parser dependency, a coupling that should be split), and mix it with hand-built before/after **code blocks** — a restructuring is usually shown best as `before` vs `after` source, side by side, not as a graph.

The report leads with a one-line **verdict**, then a **headline** card for the single strongest code-judo move, then the ranked findings as cards (each with a severity badge, the files, the one-sentence problem, the before/after, and win bullets), and closes with a **Deliberately leaving alone** list so the reader sees what was considered and consciously kept.

Keep the same bar as the rest of this skill: high-conviction findings only, structural before cosmetic, the ranking order above. The HTML is the medium; it does not lower the standard.

See [HTML-REPORT.md](HTML-REPORT.md) for the full scaffold, card anatomy, diagram patterns, and styling.

## Write the review in plain language

Write every finding in Simplified Technical English (ASD-STE100), the same voice `/wait-what` asks for. The reader must understand each finding on the first read. Apply that test to your own output: if a sentence only makes sense to someone who already speaks the dialect, rewrite it.

Rules:

- Keep sentences short. One idea per sentence. Aim for 20 words or fewer.
- Use active voice. Write "the importer skips the row", not "the row is skipped".
- Use the present tense.
- Use the same word for the same thing every time. Do not swap in synonyms.
- Use the **target repo's own domain terms** exactly — its `CONTEXT.md` names them if it has one. Do not invent new names for them.
- Keep real technical terms — module, regex, parser, atomic write, race condition, dataclass. These are the correct names, not jargon.
- Remove the figurative and insider terms from the written finding. **This skill uses metaphors to steer _you_ — "code judo", "spaghetti", "thermo-nuclear", "leaks across the seam" — but they must not appear in the review.** Translate each into plain words that say what is actually true:
  - "there's a code-judo move here" → "one change removes the extra code"
  - "this is spaghetti" → "this function does two jobs at once and is hard to follow"
  - "feature logic leaks across the seam" → "feature logic sits in a shared file where it does not belong"
- State the cost plainly. Say what breaks, and when. "Change the row layout and the manifest stops matching the rows."

Before / after:

- Dialect: "There's a code-judo move here that makes these branches disappear."
- Plain: "You can move this logic into one function. Then the three branches are not needed."

This governs both the terminal summary and the HTML report. Plain language is a requirement of the output, not a lower standard for it — the findings stay as strict and as ambitious as everywhere else in this skill.

## Approval Bar

Do not approve merely because behavior seems correct.
The bar for approval is:

- no clear structural regression
- no obvious missed opportunity to make the implementation dramatically simpler when such a path is visible
- no unjustified file-size explosion
- no obvious spaghetti-growth from special-case branching
- no obviously hacky or magical abstraction that makes the code harder to reason about
- no unnecessary wrapper/cast/optionality churn obscuring the real design
- no clear architecture-boundary leak or avoidable canonical-helper duplication
- no missed opportunity for an obvious decomposition that would materially improve maintainability

Treat these as presumptive blockers unless the author can justify them clearly:

- the PR preserves a lot of incidental complexity when there is a plausible code-judo move that would delete it
- the PR pushes a file from below 1000 lines to above 1000 lines
- the PR adds ad-hoc branching that makes an existing flow more tangled
- the PR solves a local problem by scattering feature checks across shared code
- the PR adds an unnecessary abstraction, wrapper, or cast-heavy contract that makes the design more indirect
- the PR duplicates an existing helper or puts logic in the wrong layer when there is a clear canonical home

If those conditions are not met, leave explicit, actionable feedback and push for a cleaner decomposition.
