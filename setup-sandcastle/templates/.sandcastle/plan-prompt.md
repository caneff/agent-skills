# ISSUES

Here are the open issues in the repo:

<issues-json>

!`gh issue list --state open --label ready-for-agent --limit 100 --json number,title,body,labels,comments,parent,blockedBy,issueType --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body], parent: .parent.number, blockedBy: [.blockedBy.nodes[].number], issueType: .issueType.name}]'`

</issues-json>

The list above has already been filtered to issues ready for work. **Only these `ready-for-agent` issues may appear in your plan.**

# ALREADY IN FLIGHT (context only — never select these)

These issues are already implemented but not yet merged into `main` (in review, or awaiting re-review). They are upcoming changes to `main`. **Do NOT put any of them in your plan** — they are not selectable. But you MUST treat each as a potential **blocker**: if a `ready-for-agent` issue depends on one of these (needs its code, or edits the same files), it is blocked this run and must be excluded until the in-flight issue merges.

<in-flight-json>

!`gh issue list --search "label:in-review,needs-review state:open" --limit 100 --json number,title,body,labels,parent,blockedBy --jq '[.[] | {number, title, body, labels: [.labels[].name], parent: .parent.number, blockedBy: [.blockedBy.nodes[].number]}]'`

</in-flight-json>

# ALREADY DONE THIS RUN (in your base — satisfied dependencies, NOT blockers)

These issues were completed earlier in this same run. Their code is **already merged into the branch your work will be cut from**, so anything depending on them can build on top right now.

<completed-this-run>

{{COMPLETED_THIS_RUN}}

</completed-this-run>

**Override rule:** if an issue in the "in flight" list above _also_ appears here, it is in your base — treat it as a satisfied dependency, **not** a blocker. An issue whose only blockers are listed here is **UNBLOCKED**: select it and it will be stacked on top of that work.

# TASK

Analyze the issues and build a dependency graph. For each `ready-for-agent` issue, determine whether it **is blocked by** any other open issue — whether that other issue is `ready-for-agent` or already **in flight** (the list above) — **except** issues listed under "ALREADY DONE THIS RUN", which are satisfied dependencies you build on, never blockers.

An issue B is **blocked by** issue A if:

- A is listed in B's native `blockedBy` field, or B is listed as a sub-issue of A via B's `parent` field (these GitHub-native relationships are **authoritative** — always honor them)
- B requires code or infrastructure that A introduces
- B and A modify overlapping files or modules, making concurrent work likely to produce merge conflicts
- B's requirements depend on a decision or API shape that A will establish

The native `blockedBy` / `parent` fields are recorded by whoever authored the issues (e.g. the `/to-issues` skill) and are the ground truth for declared dependencies. Treat them as hard edges, then **infer additional** blockers from the prose/file-overlap heuristics above on top. When these fields are empty (a tracker without dependency support, or an issue authored before they were set), fall back entirely to inference from the issue text.

An issue is **unblocked** if it has zero blocking dependencies on any other open issue, ready-for-agent or in-flight.

For each unblocked issue, assign a branch name using the exact format `sandcastle/issue-{id}` (no slug or other suffix). This must be deterministic so that re-planning the same issue always produces the same branch name and accumulated progress is preserved.

## Parents — what each issue builds on

For each issue you select, also emit `parents`: the ids of the issues it **builds on** — the dependencies whose code it needs sitting underneath it. Each issue's branch will be cut directly from its parent's branch, so this is what wires up the dependency forest.

Draw parents from **both**:

- **Open blockers** that are listed under "ALREADY DONE THIS RUN" (their branches exist right now, so a dependent can stack on them this run).
- Any "ALREADY DONE THIS RUN" issue this one builds on, even if you would not have called it a hard blocker.

Rules:

- A parent must be an issue id from the "ALREADY DONE THIS RUN" list. (An unbuilt blocker — `ready-for-agent` or in-flight — is **not** a parent; if a selectable issue is blocked by such an issue, leave it out of the plan entirely instead of listing it as a parent.)
- **Bias toward declaring a parent when unsure.** A missed parent breaks the dependent's build (its code is cut without the dependency underneath); a falsely-declared parent only over-groups two changes that could have been independent. When in doubt, declare it.
- A root issue that builds on nothing this run gets `"parents": []`.
- Most issues have zero or one parent. Multiple parents are allowed but rare.

## Topic group — which issues belong in the same PR

For each issue you select, also emit a `group`: a short lowercase slug naming the feature or theme it belongs to (e.g. `"auth"`, `"dark-mode"`, `"perf"`). Issues sharing a `group` are combined into **one pull request**, even when no dependency links them — this is how a run produces a few coherent PRs by topic instead of one PR per issue.

Rules:

- **Reuse existing keys.** If an issue belongs to the same theme as one under "ALREADY DONE THIS RUN" (each is shown with its `[group: X]`), reuse that exact key — do not coin a synonym, or the topic splits across two PRs.
- Issues you genuinely cannot group with anything else get their own unique slug.
- `group` is about theme only; it does **not** override dependencies. A parent edge always forces same-PR regardless of group, so you never need a group to encode a dependency — use `parents` for that.
- Keep groups meaningful: don't lump unrelated issues into one catch-all, and don't over-split a single feature.

# OUTPUT

Output your plan as a JSON object wrapped in `<plan>` tags. Every issue MUST include a `parents` array (use `[]` for a root) and a `group` slug:

<plan>
{"issues": [{"id": "42", "title": "Fix auth bug", "branch": "sandcastle/issue-42", "parents": [], "group": "auth"}, {"id": "43", "title": "Add auth UI", "branch": "sandcastle/issue-43", "parents": ["42"], "group": "auth"}]}
</plan>

Include only unblocked `ready-for-agent` issues. If every ready-for-agent issue is blocked **only** by other ready-for-agent issues (not by in-flight work), include the single highest-priority candidate (the one with the fewest or weakest dependencies). But if the remaining issues are blocked by **in-flight** work, do NOT force-pick them — leave them out and emit an empty plan; they unblock once that work merges.

Always emit the `<plan>` tags, even when there is nothing to do. If there are no issues to work on at all, output `<plan>{"issues": []}</plan>` so the run can exit cleanly.
