# BUILDABLE (the only issues you may select)

The host has already applied the deterministic frontier filter: every open issue whose native `blockedBy` edges have **all closed**, restricted to `ready-for-agent`. Issues with any still-open blocker have been removed before you ever see them. **Only ids in this set may appear in your plan** — never resurrect an issue absent from it.

<buildable>

{{BUILDABLE}}

</buildable>

# ISSUE DETAILS (reference — read for reasoning, not for selection)

Full content for the open issues, so you can reason about implicit conflicts (two buildable issues that would collide on the same files). Selection is still governed by the BUILDABLE list above; this JSON is only the detail behind it.

<issues-json>

!`gh issue list --state open --label ready-for-agent --limit 100 --json number,title,body,labels,comments,parent,blockedBy,issueType --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body], parent: .parent.number, blockedBy: [.blockedBy.nodes[].number], issueType: .issueType.name}]'`

</issues-json>

# ALREADY IN FLIGHT (context only — never select these)

These issues are already implemented but not yet merged into `main` (in review, or awaiting re-review). They are upcoming changes to `main`. **Do NOT put any of them in your plan** — they are not selectable. But you MUST treat each as a potential **blocker**: if a `ready-for-agent` issue depends on one of these (needs its code, or edits the same files), it is blocked this run and must be excluded until the in-flight issue merges.

<in-flight-json>

!`gh issue list --search "label:in-review state:open" --limit 100 --json number,title,body,labels,parent,blockedBy --jq '[.[] | {number, title, body, labels: [.labels[].name], parent: .parent.number, blockedBy: [.blockedBy.nodes[].number]}]'`

</in-flight-json>

# TASK

The host has already excluded every issue with an open native `blockedBy` blocker (see BUILDABLE). Your remaining job: for each **buildable** issue, determine whether it is **implicitly** blocked by any other open issue the declared edges missed — whether that other issue is `ready-for-agent` or already **in flight** (the list above).

An issue B is **blocked by** issue A if:

- A is listed in B's native `blockedBy` field, or B is listed as a sub-issue of A via B's `parent` field (these GitHub-native relationships are **authoritative** — always honor them)
- B requires code or infrastructure that A introduces
- B and A modify overlapping files or modules, making concurrent work likely to produce merge conflicts
- B's requirements depend on a decision or API shape that A will establish

The native `blockedBy` / `parent` fields are recorded by whoever authored the issues (e.g. the `/to-issues` skill) and are the ground truth for declared dependencies. Treat them as hard edges, then **infer additional** blockers from the prose/file-overlap heuristics above on top. When these fields are empty (a tracker without dependency support, or an issue authored before they were set), fall back entirely to inference from the issue text.

An issue is **unblocked** if it has zero blocking dependencies on any other open issue, ready-for-agent or in-flight.

For each unblocked issue, assign a branch name using the exact format `sandcastle/issue-{id}` (no slug or other suffix). This must be deterministic so that re-planning the same issue always produces the same branch name and accumulated progress is preserved.

## `parents` and `group` — emit them, but keep them simple

Each issue's branch is cut from `main`, and every issue that passes review opens its **own** pull request — one issue, one PR. A run is a single planning pass, and a child issue is only ever selected once its parents' issues have **closed** (their PRs merged to `main`), so within one run there is nothing left to build on top of.

So for every issue you select:

- Emit `"parents": []`. There is no in-run stacking anymore; a dependency you would once have listed here has already merged to `main` by the time the child is buildable.
- Emit a short lowercase `group` slug naming the issue's theme (e.g. `"auth"`, `"perf"`). It no longer combines PRs — it is carried through for logging only — but the field is still required.

# OUTPUT

Output your plan as a JSON object wrapped in `<plan>` tags. Every issue MUST include a `parents` array (always `[]`) and a `group` slug:

<plan>
{"issues": [{"id": "42", "title": "Fix auth bug", "branch": "sandcastle/issue-42", "parents": [], "group": "auth"}, {"id": "43", "title": "Add dark mode", "branch": "sandcastle/issue-43", "parents": [], "group": "ui"}]}
</plan>

Include only issues from the BUILDABLE set that survive your implicit-conflict pruning. If every buildable issue would conflict on files with another buildable one, include the single highest-priority candidate (the one with the fewest or weakest such conflicts). But if the remaining issues are blocked by **in-flight** work, do NOT force-pick them — leave them out and emit an empty plan; they unblock once that work merges.

Always emit the `<plan>` tags, even when there is nothing to do. If there are no issues to work on at all, output `<plan>{"issues": []}</plan>` so the run can exit cleanly.
