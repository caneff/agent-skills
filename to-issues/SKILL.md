---
name: to-issues
description: Break a plan, spec, or PRD into independently-grabbable issues on the project issue tracker using tracer-bullet vertical slices.
disable-model-invocation: true
---

# To Issues

Break a plan into independently-grabbable issues using vertical slices (tracer bullets).

The issue tracker and triage label vocabulary should have been provided to you — run `/setup-matt-pocock-skills` if not.

## Process

### 1. Gather context

Work from whatever is already in the conversation context. If the user passes an issue reference (issue number, URL, or path) as an argument, fetch it from the issue tracker and read its full body and comments.

### 2. Explore the codebase (optional)

If you have not already explored the codebase, do so to understand the current state of the code. Issue titles and descriptions should use the project's domain glossary vocabulary, and respect ADRs in the area you're touching.

Look for opportunities to prefactor the code to make the implementation easier. "Make the change easy, then make the easy change."

### 3. Draft vertical slices

Break the plan into **tracer bullet** issues. Each issue is a thin vertical slice that cuts through ALL integration layers end-to-end, NOT a horizontal slice of one layer.

<vertical-slice-rules>

- Each slice delivers a narrow but COMPLETE path through every layer (schema, API, UI, tests)
- A completed slice is demoable or verifiable on its own
- Any prefactoring should be done first

</vertical-slice-rules>

### 4. Quiz the user

Present the proposed breakdown as a numbered list. For each slice, show:

- **Title**: short descriptive name
- **Blocked by**: which other slices (if any) must complete first
- **User stories covered**: which user stories this addresses (if the source material has them)

Ask the user:

- Does the granularity feel right? (too coarse / too fine)
- Are the dependency relationships correct?
- Should any slices be merged or split further?

Iterate until the user approves the breakdown.

### 5. Publish the issues to the issue tracker

For each approved slice, publish a new issue to the issue tracker. Use the issue body template below. These issues are considered ready for AFK agents, so publish them with the correct triage label unless instructed otherwise.

Publish issues in dependency order (blockers first) so the parent and blocker issues exist with real numbers before anything references them.

**Wire relationships natively, not just as prose.** When the tracker is GitHub, record the parent and dependency edges as first-class GitHub relationships at create time so automation (planners, dependency graphs) can read them from structured fields — `gh issue list --json parent,blockedBy,blocking,issueType` — instead of re-parsing the body:

```
gh issue create --title "..." --body "..." \
  --type <Task|Bug|...> --parent <parent#> --blocked-by <blocker#,blocker#>
```

- `--parent` makes this a sub-issue of the source issue (the `## Parent` section's machine-readable form).
- `--blocked-by` records the dependency edges from step 4 (the `## Blocked by` section's machine-readable form).
- `--type` sets the issue type. Only pass a type name the tracker already defines (draw from the triage/type vocabulary referenced above); omit `--type` when no types are defined, since `gh` errors on an unknown type name.

GitHub now renders sub-issues and dependencies in its UI, so the body's `## Parent` / `## Blocked by` sections become a human-readable mirror of these native fields — keep them as a fallback for trackers that lack native types/dependencies, but the native flags are the source of truth.

<issue-template>
## Parent

A reference to the parent issue on the issue tracker (if the source was an existing issue, otherwise omit this section). On GitHub, also set this natively via `gh issue create --parent <parent#>` — this section mirrors that relationship for readers.

## What to build

A concise description of this vertical slice. Describe the end-to-end behavior, not layer-by-layer implementation.

Avoid specific file paths or code snippets — they go stale fast. Exception: if a prototype produced a snippet that encodes a decision more precisely than prose can (state machine, reducer, schema, type shape), inline it here and note briefly that it came from a prototype. Trim to the decision-rich parts — not a working demo, just the important bits.

## Acceptance criteria

- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Criterion 3

## Blocked by

- A reference to the blocking ticket (if any)

Or "None - can start immediately" if no blockers. On GitHub, also record these natively via `gh issue create --blocked-by <#,#>`; this section mirrors those relationships for readers.

</issue-template>

Do NOT close or modify any parent issue.
