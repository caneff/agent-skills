---
name: multi-axis-code-review
description: Review the changes since a fixed point (commit, branch, tag, or merge-base) along three axes — Standards (does the code follow this repo's documented coding standards, the Fowler smell baseline, and the over-engineering lens?), Spec (does the code match what the originating issue/spec asked for?) and Correctness (how does it fail in the field, and does every new test actually witness its claim?). Runs the three reviews in parallel sub-agents, waits for all of them, and reports every finding side by side. It replaces the built-in `/code-review` in the implement lane. Use when the user wants a branch, PR, or work-in-progress diff checked against its spec, the repo's standards, and runtime failure.
---

Review of the diff between `HEAD` and a fixed point the user supplies, along
three axes (it was two until #732; callers still saying "two-axis" mean this):

- **Standards** — does the code conform to this repo's documented coding standards?
- **Spec** — does the code faithfully implement the originating issue / spec?
- **Correctness** — how does it fail in the field, and does each new test witness what it claims?

The axes run as **parallel sub-agents** so they don't pollute each other's context, then this skill aggregates their findings.

The issue tracker should have been provided to you — run `/setup-matt-pocock-skills` if `docs/agents/issue-tracker.md` is missing.

## Process

### 1. Pin the fixed point

Whatever the user said is the fixed point — a commit SHA, branch name, tag, `HEAD~5`, etc. If they gave one, use it as-is and skip straight to capturing the diff command below.

If they didn't specify one, don't default to the local default branch — in a long-lived worktree it can sit far behind the remote, and a diff against it pulls in commits that were already squash-merged upstream, producing findings on code that isn't part of this change. Instead, resolve the fixed point fresh:

1. `git fetch origin` — if this fails (no network, no remote, auth error), say so explicitly to the user before continuing: "fetch failed, falling back to the local default branch — findings may include already-merged commits." Then use the local default branch as the fixed point and skip to capturing the diff command.
2. On a successful fetch, discover the remote's default branch — don't hard-code `main`: `git remote show origin | sed -n 's/.*HEAD branch: //p'` (or `git symbolic-ref refs/remotes/origin/HEAD` if already set).
3. Use `origin/<default>` (e.g. `origin/main`) as the fixed point.

Command sequence for the no-argument case:

```
git fetch origin
default=$(git remote show origin | sed -n 's/.*HEAD branch: //p')
fixed_point="origin/$default"
```

Capture the diff command once: `git diff <fixed-point>...HEAD` (three-dot, so the comparison is against the merge-base). Also note the list of commits via `git log <fixed-point>..HEAD --oneline`.

The diff *itself* is captured to a file in step 4, where the report directory and the issue number are both known; the command keeps its place in every prompt as the provenance record and the fallback.

Before going further, confirm the fixed point resolves (`git rev-parse <fixed-point>`) and the diff is non-empty. A bad ref or empty diff should fail here — not inside three parallel sub-agents.

### 2. Identify the spec source

Look for the originating spec, in this order:

1. Issue references in the commit messages (`#123`, `Closes #45`, GitLab `!67`, etc.) — fetch via the workflow in `docs/agents/issue-tracker.md`.
2. A path the user passed as an argument.
3. A spec file under `docs/`, `specs/`, or `.scratch/` matching the branch name or feature.
4. If nothing is found, ask the user where the spec is. If they say there isn't one, the **Spec** sub-agent will skip and report "no spec available".

### 3. Identify the standards sources

Anything in the repo that documents how code should be written, such as `CODING_STANDARDS.md` or `CONTRIBUTING.md`.

On top of whatever the repo documents, the Standards axis always carries the **smell baseline** below — a fixed set of Fowler code smells (_Refactoring_, ch.3) that applies even when a repo documents nothing. Two rules bind it:

- **The repo overrides.** A documented repo standard always wins; where it endorses something the baseline would flag, suppress the smell.
- **Always a judgement call.** Each smell is a labelled heuristic ("possible Feature Envy"), never a hard violation — and, like any standard here, skip anything tooling already enforces.

Each smell reads *what it is* → *how to fix*; match it against the diff:

- **Mysterious Name** — a function, variable, or type whose name doesn't reveal what it does or holds. → rename it; if no honest name comes, the design's murky.
- **Duplicated Code** — the same logic shape appears in more than one hunk or file in the change. → extract the shared shape, call it from both.
- **Feature Envy** — a method that reaches into another object's data more than its own. → move the method onto the data it envies.
- **Data Clumps** — the same few fields or params keep travelling together (a type wanting to be born). → bundle them into one type, pass that.
- **Primitive Obsession** — a primitive or string standing in for a domain concept that deserves its own type. → give the concept its own small type.
- **Repeated Switches** — the same `switch`/`if`-cascade on the same type recurs across the change. → replace with polymorphism, or one map both sites share.
- **Shotgun Surgery** — one logical change forces scattered edits across many files in the diff. → gather what changes together into one module.
- **Divergent Change** — one file or module is edited for several unrelated reasons. → split so each module changes for one reason.
- **Speculative Generality** — abstraction, parameters, or hooks added for needs the spec doesn't have. → delete it; inline back until a real need shows.
- **Message Chains** — long `a.b().c().d()` navigation the caller shouldn't depend on. → hide the walk behind one method on the first object.
- **Middle Man** — a class or function that mostly just delegates onward. → cut it, call the real target direct.
- **Refused Bequest** — a subclass or implementer that ignores or overrides most of what it inherits. → drop the inheritance, use composition.

**The over-engineering lens.** On top of the smells, the Standards axis runs an over-engineering review — the sharpest depth on "is this well-built?". It hunts what to **delete**, not what to rename. Five tags, one line each — location, what to cut, what replaces it:

- `delete:` dead code, unused flexibility, speculative feature. → replacement: nothing.
- `stdlib:` a hand-rolled thing the standard library ships. → name the function.
- `native:` a dependency or code doing what the platform already does. → name the feature.
- `yagni:` an abstraction with one implementation, config nobody sets, a layer with one caller. → inline it until a second caller exists.
- `shrink:` same logic, fewer lines. → show the shorter form.

This lens **owns** the three smells above that are really over-engineering — Speculative Generality, Middle Man, Refused Bequest. Report each such cut **once**, under the over-engineering subsection (step 4), never twice. A single smoke test or `assert`-based self-check is the minimum, not bloat — never flag it as a cut.

### 4. Spawn the three sub-agents in parallel

Spawn all three with the plain `Agent` tool, `subagent_type: diff-reviewer`, fire-and-return: no `name`, not background, no teammate messaging. This is what makes the result reach *you* as the agent's completion notification — even when you yourself are a subagent of some other caller. A named background teammate parks its report for `SendMessage`/`ListAgents` instead, and when you're a subagent nothing is polling for that: the report idles or lands nowhere.

Pass `model: opus` to all three. Review is Opus-tier and the user reads every line before merge, so a miss is caught downstream — do not let them inherit the session model.

The `diff-reviewer` agent definition (`flow/claude/agents/diff-reviewer.md`, installed at `~/.claude/agents/diff-reviewer.md` by `flow/install.sh`) carries the standing brief and points back at this file's § 3, so a prompt passes only what is specific to this diff. If `diff-reviewer` is not among the available agent types, run `bash flow/install.sh` and it will be; failing that, spawn without `subagent_type` and paste § 3 and the axis brief in full — the reviews still run, at the cost of the paste.

**Settled decisions.** This is the one home for the rule; every caller passes the list and points here rather than rewording it. Every prompt carries a settled-decisions list: what the owner already ruled on — at a grill, in the issue's `**Settled:**` comments, or in an earlier round — one line each. With nothing settled, say so — "settled decisions: none" — rather than dropping the line, so the reviewer knows the list is empty and not forgotten. A reviewer that re-raises a settled decision costs a round the fixer spends re-arguing it, and a reviewer with the issue in reach reads those comments itself before writing a finding.

**A finding names the file and the intent, not the edit.** This is the one home for the rule; callers point here rather than reword it. Say where the problem is and what outcome is wrong; the fixer owns the file and picks the change. The observable: a finding never contains a command to run. A finding written as a patch to apply verbatim ("exactly these, nothing else", or a `git checkout <sha> -- <path>` the fixer is told to paste) turns one round into four — the fixer stops reading for the problem and starts applying the script, so a wrong script lands four times instead of being caught once.

Every prompt carries only the **diff, the commit list, the spec/standards sources, and the settled decisions** — never this session's plan, reasoning, or messages. When this session authored the change, leaked rationale makes the reviewer read your *intent* instead of the code, recreating the same-context blindness the parallel sub-agents exist to remove. Feed the artifacts, not the thinking behind them.

Belt and braces: append to **every** prompt — "Also write your full report to `<dir>/review-<axis>-<n>.md`", `<axis>` being `standards`, `spec` or `correctness`, `<n>` the issue number from step 2 (or the branch name if there is none). `/tmp` is wiped at every boot here and herdr workers never set `$CLAUDE_JOB_DIR`, so these reports — the only record of what each reviewer said — need a home that survives: `~/.cache/agent-reviews/<repo>/`. Never point the report at `./.scratch/` or anywhere under the repo — an untracked file there blocks `git worktree remove` (and so `ship`).

**Alongside the prose, each reviewer also writes a sidecar** so counting a
finding stops needing an LLM pass over prose (#855, #854): "Also write
`<dir>/findings-<axis>-<n>.jsonl`, one JSON object per line, one line per
finding: `{"id": "<letter+ordinal>", "axis": "<axis>", "severity": "hard"
or "judgement", "file": "<path>", "title": "<short title>"}`. Assign each
finding a stable id — the axis's first letter (`S` standards, `P` spec, `C`
correctness) plus a per-report ordinal, e.g. `S1`, `P2`, `C3` — the
convention `~/.cache/agent-reviews/skills/verify-790-dispositions.md`
already reaches for by hand; formalize it, don't invent a new one. Cite the
same id in the prose report next to each finding, so a reader can join the
two. A partial write costs one line, not the file — readers of this
sidecar must tolerate and skip a malformed line rather than fail the whole
file on it. No cost tracking: never add tokens or wall-clock to this line,
in the sidecar or the prose."

**Expand `<dir>` yourself before writing the prompt**, and prune anything
untouched for 14 days, the same folder style and retention `job-run` gives
`~/.cache/agent-jobs` — this sidecar lives in the same directory as the
prose report, so the same expansion and pruning cover it with no extra
step. `<repo>` must be the repo's own name, not the worktree's — reviews
always run from a task worktree, and `git rev-parse --show-toplevel` there
returns the worktree path, so key on the common `.git` instead:

```
top=$(git rev-parse --path-format=absolute --git-common-dir) || exit 1
dir="$HOME/.cache/agent-reviews/$(basename "$(dirname "$top")")"
mkdir -p "$dir"
find "$dir" -maxdepth 1 -type f -mtime +13 -delete  # +13, not +14: find's -mtime +N means "older than N+1 days"
n=<issue number from step 2, or the branch name>
worktree=<the worktree under review>
fixed_point=<the fixed point from step 1>
git -C "$worktree" diff "$fixed_point"...HEAD >"$dir/diff-$n.patch" || exit 1
[ -s "$dir/diff-$n.patch" ] || exit 1   # a failed or empty write fails here, not inside three sub-agents
wc -l "$dir/diff-$n.patch"              # the count goes in every prompt beside the path
```

**Capture the diff once, by the caller** (#937). Those lines derive the diff
one time into `<dir>/diff-<n>.patch` and print its length; every axis prompt
carries that path, that count, and the command that produced it, so three
reviewers read one capture instead of each re-running the same `git diff`.
The axes run in parallel, so the duplication sat on the critical path of all
three. Keep the block runnable shell — `<n>` left unexpanded inside those
quotes is a literal the write and the guard agree on, so the capture lands
under a name no prompt points at and every axis silently falls back. `git -C
"$worktree"` rather than a bare `git diff` because the caller's HEAD is not
always the branch under review.

**Re-capture at the start of every round.** The file is keyed on `<n>` alone,
so a verification round that reuses the prompts without re-running the block
leaves round 1's diff in place — present and non-empty, so nothing below
notices. The command stays in the prompt as the provenance record and as the
fallback: an axis whose diff file is missing or empty re-derives with it and
says so in its report, rather than reviewing nothing.

If the completion notification comes back missing or empty, read that file before treating the report as absent.

**Standards sub-agent prompt** — include:

- The captured diff at `<dir>/diff-<n>.patch` and its line count, the diff command that produced it, and the commit list.
- The list of standards-source files you found in step 3, and the settled decisions. The smell baseline and the over-engineering lens are the agent definition's to read from § 3; paste them only in the no-definition fallback above.
- The brief: "Report — per file/hunk where relevant — (a) every place the diff violates a documented standard: cite the standard (file + the rule); and (b) any baseline smell you spot: name it and quote the hunk. Distinguish hard violations from judgement calls — documented-standard breaches can be hard, but baseline smells are always judgement calls, and a documented repo standard overrides the baseline. Skip anything tooling enforces. For any test in the diff that claims to prove a behaviour, check the verdict depends on it — strip the constraint under test and see whether the assertion still passes; one that survives is a hollow witness, flag it. Then end with a required **### Over-engineering** subsection (a `###` so it nests under the Standards heading): run the over-engineering lens over the diff and list what to cut, one line each in `location: <tag> <what>. <replacement>.` form using the five tags. This subsection owns Speculative Generality / Middle Man / Refused Bequest — report those cuts here, not above. Write `Lean already.` if there is nothing to cut — the subsection is required even when empty. Under 550 words."

**Spec sub-agent prompt** — include:

- The captured diff at `<dir>/diff-<n>.patch` and its line count, the diff command that produced it, and the commit list.
- The path or fetched contents of the spec, and the settled decisions.
- The brief: "Report: (a) requirements the spec asked for that are missing or partial; (b) behaviour in the diff that wasn't asked for (scope creep); (c) requirements that look implemented but where the implementation looks wrong. When the diff knowingly deviates from an acceptance criterion's literal wording, rule on whether it preserves the spec's intent, not the letter — look for a competing, higher AC the deviation exists to satisfy — but flag the deviation, never pass it silently. Quote the spec line for each finding. Under 400 words."

**Correctness sub-agent prompt** — include:

- The captured diff at `<dir>/diff-<n>.patch` and its line count, the diff command that produced it, and the commit list.
- The path or fetched contents of the spec if there is one (so "behaviour the ticket did not ask for" has a referent), the test command the repo uses, and the settled decisions.
- The brief: "Report: (a) bugs — for each, the concrete failure scenario: the input, environment or sequence that makes the diff misbehave, and what a user sees; think about the run nobody is watching (piped output, closed stdin, missing tool, empty result, a name with an odd character, a second run over the same state); (b) behaviour the ticket did not ask for; (c) every new or changed test checked as a witness: strip the constraint under test and see whether the assertion still passes — one that survives is a hollow witness, flag it (do it on a scratch copy of the tree outside the checkout, made with Bash; the checkout is left exactly as found). Rate each bug PLAUSIBLE or CONFIRMED and say which. Under 450 words."

If the spec is missing, skip the Spec sub-agent and note this in the final report. The Correctness sub-agent still runs; replace its part (b) with "(b) say 'no spec available'".

**Wait for every axis.** Each reviewer ends with a completion notification; do nothing with the round until every one you spawned has arrived. Never send a reviewer a "report now" or "wrap up" message — a reviewer hurried mid-pass returns what it has and its unread work is the round's biggest cost (agent-skills #732: eight finder reports, none read). Only when an axis's notification has arrived empty *and* its fallback file is absent do you report that axis in step 5 as `## Standards — NO REPORT RECEIVED` (or `## Spec — …`, `## Correctness — …`); a reviewer that is merely slow is waited on, not replaced.

### 5. Aggregate

Present the reports under `## Standards`, `## Spec` and `## Correctness` headings, verbatim or lightly cleaned. Every finding every axis returned is in the aggregate — none is dropped as minor, duplicate, or already known; the caller disposes of findings, this skill only collects them. Do **not** merge or rerank findings — the axes are deliberately separate (see _Why separate axes_).

Each finding carries the stable id its sidecar gave it (`S1`, `P2`, `C3`).
A downstream pass — the verification pass's disposition, the PR body's
Decisions made section — cites that id rather than restating the finding
in its own prose; that's what makes the disposition sidecar joinable
without a reading pass (#855).

End with a one-line summary: total findings per axis, and the worst issue _within each axis_ (if any). Don't pick a single winner across axes — that's the reranking the separation exists to prevent.

## Why separate axes

A change can pass one axis and fail another:

- Code that follows every standard but implements the wrong thing → **Standards pass, Spec fail.**
- Code that does exactly what the issue asked but breaks the project's conventions → **Spec pass, Standards fail.**
- Code that matches the ticket and the conventions and deletes the wrong branch when stdin is a pipe → **Standards and Spec pass, Correctness fail.**

Reporting them separately stops one axis from masking another. On agent-skills #731 the standards and spec axes found the rule and ticket findings, and every runtime finding (the prompt lost under a pipe, the ahead count that was noise, the unrecorded `branch -D`) came from failure-scenario reading.

This is also the one home for why the built-in `/code-review` is not in the implement lane (#732, measured on that 250-line diff): at medium effort it forked eight finder agents for 80k output and 9.2M cached tokens and returned before reading them; one opus standards axis cost 9.4k output and 0.68M cached. `/code-review low` (3.4k / 70k, one finding) stays available when the owner asks for it.
