# BUILDABLE (the only issues you may select)

The host has already applied the deterministic frontier filter: every open `ready-for-agent` issue whose native `blockedBy` edges have **all closed, or built successfully earlier in this same run**. Issues with any still-open, not-yet-built blocker have been removed before you ever see them. **Only ids in this set may appear in your plan** — never resurrect an issue absent from it. BUILDABLE is authoritative for declared dependencies: if an issue is here, the host has already cleared its native `blockedBy` edges (including any a parent satisfied by building this run). Your only remaining job is to prune **implicit** same-file conflicts.

<buildable>

{{BUILDABLE}}

</buildable>

# ISSUE DETAILS (reference — read for reasoning, not for selection)

Full content for the open issues, so you can reason about implicit conflicts (two buildable issues that would collide on the same files). Selection is still governed by the BUILDABLE list above; this JSON is only the detail behind it.

<issues-json>

!`gh issue list --state open --label ready-for-agent --limit 100 --json number,title,body,labels,comments,parent,blockedBy,issueType --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body], parent: .parent.number, blockedBy: [.blockedBy.nodes[].number], issueType: .issueType.name}]'`

</issues-json>

# ALREADY IN FLIGHT (context only — never select these)

These issues are already implemented but not yet merged into `main` (in review, or awaiting re-review). They are upcoming changes to `main` — and some may be **parents built earlier in this very run** that a BUILDABLE child now stacks on top of. **Do NOT put any of them in your plan** — they are not selectable. Two rules keep declared and implicit dependencies apart:

- **Declared edge → trust BUILDABLE.** Never exclude a BUILDABLE issue because it has a native `blockedBy`/`parent` edge to one of these. The host already resolved declared edges: a BUILDABLE child of an in-flight parent is one the host is deliberately stacking on that parent this run.
- **Undeclared same-file collision → defer.** If a BUILDABLE issue would edit the **same files** as an in-flight issue with **no declared edge** between them, that is a real merge-conflict risk the host could not see — leave it out this run.

<in-flight-json>

!`gh issue list --search "label:in-review state:open" --limit 100 --json number,title,body,labels,parent,blockedBy --jq '[.[] | {number, title, body, labels: [.labels[].name], parent: .parent.number, blockedBy: [.blockedBy.nodes[].number]}]'`

</in-flight-json>

# TASK

The host already owns every **declared** edge: it excluded each issue whose native `blockedBy` blocker is still open and unbuilt, and it deliberately kept a child whose parent built this run (see BUILDABLE). So do **not** re-apply native `blockedBy` / `parent` edges as blockers — honoring them here would wrongly drop a child the host is stacking on its just-built parent. Your remaining job is narrower: for each **buildable** issue, determine whether it is **implicitly** blocked — a dependency the declared edges never recorded — on any other open issue, whether `ready-for-agent` or already **in flight** (the list above).

An issue B is **implicitly blocked by** issue A if:

- B requires code or infrastructure that A introduces, with no declared edge between them
- B and A modify overlapping files or modules, making concurrent work likely to produce merge conflicts
- B's requirements depend on a decision or API shape that A will establish

Infer these from the issue prose and file overlap. An issue is **buildable** if it carries no such implicit block on any other open issue, ready-for-agent or in-flight.

For each unblocked issue, assign a branch name using the exact format `sandcastle/issue-{id}` (no slug or other suffix). This must be deterministic so that re-planning the same issue always produces the same branch name and accumulated progress is preserved.

## `parents` and `group` — emit them, but keep them simple

Every issue that passes review opens its **own** pull request — one issue, one PR. The host resolves each issue's build base from its native `blockedBy` edges (stacking a child on its parent's branch when the parent built this run), so you do **not** compute or emit real parents.

So for every issue you select:

- Emit `"parents": []`. The host derives the build base from the native edges, not from this field.
- Emit a short lowercase `group` slug naming the issue's theme (e.g. `"auth"`, `"perf"`). It no longer combines PRs — it is carried through for logging only — but the field is still required.

# OUTPUT

Output your plan as a JSON object wrapped in `<plan>` tags. Every issue MUST include a `parents` array (always `[]`) and a `group` slug:

<plan>
{"issues": [{"id": "42", "title": "Fix auth bug", "branch": "sandcastle/issue-42", "parents": [], "group": "auth"}, {"id": "43", "title": "Add dark mode", "branch": "sandcastle/issue-43", "parents": [], "group": "ui"}]}
</plan>

Include only issues from the BUILDABLE set that survive your implicit-conflict pruning. If every buildable issue would conflict on files with another buildable one, include the single highest-priority candidate (the one with the fewest or weakest such conflicts). But if the remaining issues are blocked by **in-flight** work, do NOT force-pick them — leave them out and emit an empty plan; they unblock once that work merges.

Always emit the `<plan>` tags, even when there is nothing to do. If there are no issues to work on at all, output `<plan>{"issues": []}</plan>` so the run can exit cleanly.
