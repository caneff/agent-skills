---
name: two-axis-code-review
description: Review the changes since a fixed point (commit, branch, tag, or merge-base) along two axes — Standards (does the code follow this repo's documented coding standards, the Fowler smell baseline, and the over-engineering lens?) and Spec (does the code match what the originating issue/spec asked for?). Runs both reviews in parallel sub-agents and reports them side by side. It does NOT hunt runtime correctness bugs — the built-in `/code-review` does that, and the two are meant to run back to back. Use when the user wants a branch, PR, or work-in-progress diff checked against its spec and the repo's standards.
---

Two-axis review of the diff between `HEAD` and a fixed point the user supplies:

- **Standards** — does the code conform to this repo's documented coding standards?
- **Spec** — does the code faithfully implement the originating issue / spec?

Both axes run as **parallel sub-agents** so they don't pollute each other's context, then this skill aggregates their findings.

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

Before going further, confirm the fixed point resolves (`git rev-parse <fixed-point>`) and the diff is non-empty. A bad ref or empty diff should fail here — not inside two parallel sub-agents.

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

### 4. Spawn both sub-agents in parallel

Spawn both with the plain `Agent` tool, `subagent_type: diff-reviewer`, fire-and-return: no `name`, not background, no teammate messaging. This is what makes the result reach *you* as the agent's completion notification — even when you yourself are a subagent of some other caller. A named background teammate parks its report for `SendMessage`/`ListAgents` instead, and when you're a subagent nothing is polling for that: the report idles or lands nowhere.

Pass `model: opus` to both. Review is Opus-tier and the user reads every line before merge, so a miss is caught downstream — do not let them inherit the session model.

The `diff-reviewer` agent definition (`flow/claude/agents/diff-reviewer.md`, installed at `~/.claude/agents/diff-reviewer.md` by `flow/install.sh`) carries the standing brief and points back at this file's § 3, so a prompt passes only what is specific to this diff. If `diff-reviewer` is not among the available agent types, run `bash flow/install.sh` and it will be; failing that, spawn without `subagent_type` and paste § 3 and the axis brief in full — the reviews still run, at the cost of the paste.

**Settled decisions.** This is the one home for the rule; every caller passes the list and points here rather than rewording it. Every prompt carries a settled-decisions list: what the owner already ruled on — at a grill, in the issue's `**Settled:**` comments, or in an earlier round — one line each. With nothing settled, say so — "settled decisions: none" — rather than dropping the line, so the reviewer knows the list is empty and not forgotten. A reviewer that re-raises a settled decision costs a round the fixer spends re-arguing it, and a reviewer with the issue in reach reads those comments itself before writing a finding.

**A finding names the file and the intent, not the edit.** This is the one home for the rule; callers point here rather than reword it. Say where the problem is and what outcome is wrong; the fixer owns the file and picks the change. The observable: a finding never contains a command to run. A finding written as a patch to apply verbatim ("exactly these, nothing else", or a `git checkout <sha> -- <path>` the fixer is told to paste) turns one round into four — the fixer stops reading for the problem and starts applying the script, so a wrong script lands four times instead of being caught once.

Both prompts carry only the **diff, the commit list, the spec/standards sources, and the settled decisions** — never this session's plan, reasoning, or messages. When this session authored the change, leaked rationale makes the reviewer read your *intent* instead of the code, recreating the same-context blindness the parallel sub-agents exist to remove. Feed the artifacts, not the thinking behind them.

Belt and braces: append to **both** prompts — "Also write your full report to `<dir>/review-<axis>-<n>.md`", `<axis>` being `standards` or `spec`, `<n>` the issue number from step 2 (or the branch name if there is none). **Expand `<dir>` yourself before writing the prompt**: `$CLAUDE_JOB_DIR/tmp` if that variable is set in your session, else `/tmp`. Sub-agents do not inherit the variable, and a fallback inside the checkout leaves an untracked file that blocks `git worktree remove` (and so `ship`). Never point the report at `./.scratch/` or anywhere under the repo. If the completion notification comes back missing or empty, read that file before treating the report as absent.

**Standards sub-agent prompt** — include:

- The full diff command and commit list.
- The list of standards-source files you found in step 3, and the settled decisions. The smell baseline and the over-engineering lens are the agent definition's to read from § 3; paste them only in the no-definition fallback above.
- The brief: "Report — per file/hunk where relevant — (a) every place the diff violates a documented standard: cite the standard (file + the rule); and (b) any baseline smell you spot: name it and quote the hunk. Distinguish hard violations from judgement calls — documented-standard breaches can be hard, but baseline smells are always judgement calls, and a documented repo standard overrides the baseline. Skip anything tooling enforces. For any test in the diff that claims to prove a behaviour, check the verdict depends on it — strip the constraint under test and see whether the assertion still passes; one that survives is a hollow witness, flag it. Then end with a required **### Over-engineering** subsection (a `###` so it nests under the Standards heading): run the over-engineering lens over the diff and list what to cut, one line each in `location: <tag> <what>. <replacement>.` form using the five tags. This subsection owns Speculative Generality / Middle Man / Refused Bequest — report those cuts here, not above. Write `Lean already.` if there is nothing to cut — the subsection is required even when empty. Under 550 words."

**Spec sub-agent prompt** — include:

- The diff command and commit list.
- The path or fetched contents of the spec, and the settled decisions.
- The brief: "Report: (a) requirements the spec asked for that are missing or partial; (b) behaviour in the diff that wasn't asked for (scope creep); (c) requirements that look implemented but where the implementation looks wrong. When the diff knowingly deviates from an acceptance criterion's literal wording, rule on whether it preserves the spec's intent, not the letter — look for a competing, higher AC the deviation exists to satisfy — but flag the deviation, never pass it silently. Quote the spec line for each finding. Under 400 words."

If the spec is missing, skip the Spec sub-agent and note this in the final report.

Once both agents finish, if an axis has neither a completion notification nor a fallback file, don't block or self-review in its place — report that axis in step 5 as `## Standards — NO REPORT RECEIVED` (or `## Spec — NO REPORT RECEIVED`) and move on.

### 5. Aggregate

Present the two reports under `## Standards` and `## Spec` headings, verbatim or lightly cleaned. Do **not** merge or rerank findings — the two axes are deliberately separate (see _Why two axes_).

End with a one-line summary: total findings per axis, and the worst issue _within each axis_ (if any). Don't pick a single winner across axes — that's the reranking the separation exists to prevent.

## Why two axes

A change can pass one axis and fail the other:

- Code that follows every standard but implements the wrong thing → **Standards pass, Spec fail.**
- Code that does exactly what the issue asked but breaks the project's conventions → **Spec pass, Standards fail.**

Reporting them separately stops one axis from masking the other.
