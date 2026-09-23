---
name: multi-axis-code-review
description: Review the changes since a fixed point (commit, branch, tag, or merge-base) — or the union of a list of landed shas — along three axes — Standards (does the code follow this repo's documented coding standards, the Fowler smell baseline, and the over-engineering lens?), Spec (does the code match what the originating issue/spec asked for?) and Correctness (how does it fail in the field, and does every new test actually witness its claim?). Runs the three reviews in parallel sub-agents, waits for all of them, and reports every finding side by side. It replaces the built-in `/code-review` in the implement lane. Use when the user wants a branch, PR, or work-in-progress diff checked against its spec, the repo's standards, and runtime failure.
---

Review of the diff between `HEAD` and a fixed point the user supplies — or of
the union of a list of landed shas (§ Sha-list mode) — along
three axes (it was two until #732; callers still saying "two-axis" mean this):

- **Standards** — does the code conform to this repo's documented coding standards?
- **Spec** — does the code faithfully implement the originating issue / spec?
- **Correctness** — how does it fail in the field, and does each new test witness what it claims?

The axes run as **parallel sub-agents** so they don't pollute each other's context, then this skill aggregates their findings.

The issue tracker should have been provided to you — run `/setup-matt-pocock-skills` if `docs/agents/issue-tracker.md` is missing.

## Process

### 1. Pin the fixed point, or take the sha list

**Which input is this?** Decide before anything else. A list of commits *to
review* — one sha or twenty — is sha-list mode (below), never a fixed point.
Take that branch first, because a single named commit reads as both and the two
answers differ: as a fixed point it means everything that landed *after* that
commit, as a one-element list it means that commit's own first-parent diff. A
list means the second, whatever its length, and a list of one is the shape a
caller reaches for first — after a single squash-merge.

Otherwise, whatever the user said is the fixed point — a commit SHA, branch name, tag, `HEAD~5`, etc. If they gave one, use it as-is and skip straight to capturing the diff command below.

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

#### Sha-list mode

When the caller names **commits** rather than a fixed point — N landed shas,
not necessarily contiguous — this is **sha-list mode**, and there is no fixed
point to pin. Take it whenever the request is a list of commits; never pick one
of them as a fixed point and build a range around it. That invention is the
failure the mode exists to prevent (#932): #897's closing ticket hands the
spec-level review a sha list precisely so a review on a shared `main` cannot
sweep in other people's merged work.

**What the three-dot semantics become.** Three-dot exists to compare against
the merge-base, so commits that landed on the base after the fork point stay
out of the diff. With no single fixed point there is no merge-base to take, so
the list does that job instead, and more narrowly: each named commit is read
against **its own first parent**, and the capture is those per-commit diffs
concatenated, oldest first. A commit nobody named cannot appear, however it is
interleaved — which is a tighter guarantee than three-dot gives, since
three-dot still carries everything on the branch side of the fork point. The
two-dot form is what the mode is a defence against: in the #888 Codex trial one
two-dot comparison read 18 files and 1080 deletions of other people's merged
work, against 2 files and 37 insertions three-dot.

The axes read the union as **one change**. A file two named commits both touch
appears twice in the capture; that is the same file edited in sequence, not two
conflicting versions of it, and the oldest-first order is what makes it read
that way.

The union is a **set of changes, not a final-state diff**. The last hunk set
for a file is that commit's change to it, not the file as it now stands, and
nothing in the capture shows the final state of a file two named commits
touched. An axis that reads the last hunk set as "the change to this file"
reviews an intermediate — the same shape of misread as #937's
replaced-but-non-empty patch: readable, plausible, and not what the reader
thinks it is. Say so in the prompt alongside the capture path.

**Every malformed list refuses by name.** An empty list, a sha that does not
resolve here, a merge commit (no single parent diff to take — name the commits
it merged instead), and a named commit that changes no files each stop the
review with a message saying which. None of them may reach the axes as "no
changes found": a review that silently found nothing is indistinguishable from
a clean one.

The capture block is in § 4; the rest of this skill is unchanged — step 2 reads
the spec off the named commits' messages, and steps 3 to 5 do not know which
mode produced the patch.

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

Which rating counts as high is `implement/SKILL.md` § Review's severity mapping,
stated there once; no brief here restates it, and a reviewer rates in its
own axis's words. A finding whose failure cannot occur here is disputed
under `implement/SKILL.md` § Review's reachability bar, whatever its rating.

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
# The publish protocol, stated once for both capture modes below. Each mode sets
# its own `patch` stem, takes a temp path from new_capture, writes into it, then
# hands both to publish_capture, which appends the temp path's random suffix.
new_capture() { mktemp "$dir/.diff-$n.XXXXXX"; }   # unique per invocation; prints the path
publish_capture() { # <tmp> <stem>: fail on an empty write here, not inside three sub-agents
  [ -s "$1" ] || { rm -f "$1"; echo "capture for $2 is empty" >&2; return 1; }
  # The suffix is mktemp's, unique per invocation; a shell pid is only per shell,
  # and two captures at one revision in one shell would share it.
  mv "$1" "$2-${1##*.}.patch" &&        # atomic publish: no axis ever reads a half-written patch
    wc -l "$2-${1##*.}.patch"           # this exact path and this count go in every prompt
}
```

Then, for a fixed point, the range capture — in the same shell as the preamble,
since the functions it defines do not survive into a separate shell call:

```
type publish_capture >/dev/null 2>&1 ||
  { echo "range review: run the report-directory preamble above first, in this same shell" >&2; exit 1; }
fixed_point=<the fixed point from step 1>
head=$(git -C "$worktree" rev-parse --short HEAD) || exit 1
patch="$dir/diff-$n-$head"               # revision; the protocol adds the per-invocation suffix
tmp=$(new_capture) || exit 1
git -C "$worktree" diff "$fixed_point"...HEAD >"$tmp" || { rm -f "$tmp"; exit 1; }
publish_capture "$tmp" "$patch" || exit 1
```

**Capture the diff once, by the caller** (#937). Those blocks derive the diff
one time into `<dir>/diff-<n>.patch` and print its length; every axis prompt
carries that path, that count, and the command that produced it, so three
reviewers read one capture instead of each re-running the same `git diff`.
The axes run in parallel, so the duplication sat on the critical path of all
three. Keep the block runnable shell — `<n>` left unexpanded inside those
quotes is a literal the write and the guard agree on, so the capture lands
under a name no prompt points at and every axis silently falls back. `git -C
"$worktree"` rather than a bare `git diff` because the caller's HEAD is not
always the branch under review.

**Every invocation gets its own capture, and re-captures at the start of every
round.** The name carries the revision and a per-invocation nonce, and the
block publishes by `mv` onto it, so a retry, a verification round begun while
a lagging axis is still reading, and another worktree on the same issue cannot
overwrite each other — and no axis reads a half-written patch. Keying on `<n>`
alone made the hazard *wrongness* while the fallback below tests only for
*absence*: a replaced-but-non-empty patch reads as valid, and three axes
review the wrong tree while still holding the previous round's commit list and
spec context, with no error anywhere (PR #943). Hand every axis of one
invocation the exact path the block printed, never a pattern. More files, not
more lifetime — the 14-day sweep above collects them under this key the same
way.

**Sha-list mode captures the union** (§ 1). Run the `$dir` preamble above
first, in the same shell — same directory, same 14-day sweep — then this block instead of the
`git diff` one. § 1 has the semantics; what is specific to the block is the
key — a digest of the resolved list rather than a single `HEAD`, since there is
no single revision under review:

```
: "${dir:?sha-list review: run the report-directory preamble above first}"
type publish_capture >/dev/null 2>&1 ||
  { echo "sha-list review: run the report-directory preamble above first, in this same shell" >&2; exit 1; }
set -- <the commits the caller named, space-separated>
[ "$#" -gt 0 ] || { echo "sha-list review: the commit list is empty" >&2; exit 1; }
resolved=""
for s in "$@"; do
  full=$(git -C "$worktree" rev-parse --verify --quiet "$s^{commit}") || {
    echo "sha-list review: '$s' does not resolve to a commit here" >&2; exit 1; }
  if git -C "$worktree" rev-parse --verify --quiet "$full^2" >/dev/null; then
    echo "sha-list review: $full is a merge commit — name the commits it merged" >&2; exit 1
  fi
  resolved="$resolved $full"
done
# Oldest first, by ancestor count: an ancestor always reaches strictly fewer
# commits than its descendant, so a file two named commits both touch reads in
# apply order. Not commit date — two commits landed in the same second sort
# arbitrarily by it, and a test repo builds them all in one. Unrelated commits
# with equal counts tie-break on the sha, so the order is at least stable. The
# awk dedupes, so a sha named twice contributes one diff.
ordered=$(for s in $resolved; do
    printf '%s %s\n' "$(git -C "$worktree" rev-list --count "$s")" "$s"
  done | sort -n -k1,1 -k2,2 | awk '!seen[$2]++ {print $2}')
key=$(printf '%s\n' "$ordered" | git -C "$worktree" hash-object --stdin | cut -c1-12)
patch="$dir/diff-$n-list$key"             # list digest; the protocol adds the suffix
tmp=$(new_capture) || exit 1
for s in $ordered; do
  one=$(git -C "$worktree" show --format='commit %H%n%n    %s%n' --patch "$s") || {
    rm -f "$tmp"; echo "sha-list review: could not read $s" >&2; exit 1; }
  printf '%s\n' "$one" | grep -q '^diff --git ' || {
    rm -f "$tmp"; echo "sha-list review: $s changes no files" >&2; exit 1; }
  printf '%s\n' "$one" >>"$tmp"
done
publish_capture "$tmp" "$patch" || exit 1
```

In this mode the provenance every axis prompt carries is **this per-commit
`git show` loop and the resolved list**, not a `git diff` range — a range is
the thing the mode refuses to invent, and an axis handed one would re-derive
the contaminated diff the moment its file went missing.

The command stays in the prompt as the provenance record and as the fallback:
an axis whose diff file is missing or empty re-derives with it and says so in
its report, rather than reviewing nothing.

If the completion notification comes back missing or empty, read that file before treating the report as absent.

**Standards sub-agent prompt** — include:

- The captured diff — the exact path the block printed, not a pattern — and its line count, the diff command that produced it, and the commit list.
- The list of standards-source files you found in step 3, and the settled decisions. The smell baseline and the over-engineering lens are the agent definition's to read from § 3; paste them only in the no-definition fallback above.
- The brief: "Report — per file/hunk where relevant — (a) every place the diff violates a documented standard: cite the standard (file + the rule); and (b) any baseline smell you spot: name it and quote the hunk. Distinguish hard violations from judgement calls — documented-standard breaches can be hard, but baseline smells are always judgement calls, and a documented repo standard overrides the baseline. Check `docs/agents/defect-classes.md` by name — the three shapes this repo keeps shipping, with every instance. Skip anything tooling enforces, and skip the hollow-witness check — the correctness axis owns it (#938), and two opus agents mutating the same tests over the same diff cost two dispositions for one finding. Then end with a required **### Over-engineering** subsection (a `###` so it nests under the Standards heading): run the over-engineering lens over the diff and list what to cut, one line each in `location: <tag> <what>. <replacement>.` form using the five tags. This subsection owns Speculative Generality / Middle Man / Refused Bequest — report those cuts here, not above. Write `Lean already.` if there is nothing to cut — the subsection is required even when empty. Under 550 words."

**Spec sub-agent prompt** — include:

- The captured diff — the exact path the block printed, not a pattern — and its line count, the diff command that produced it, and the commit list.
- The path or fetched contents of the spec, and the settled decisions.
- The brief: "Report: (a) requirements the spec asked for that are missing or partial; (b) behaviour in the diff that wasn't asked for (scope creep), except a change an adjacent disposition names (`fixed (adjacent)`), which implement's adjacent-fix rule sanctions; (c) requirements that look implemented but where the implementation looks wrong. When the diff knowingly deviates from an acceptance criterion's literal wording, rule on whether it preserves the spec's intent, not the letter — look for a competing, higher AC the deviation exists to satisfy — but flag the deviation, never pass it silently. Quote the spec line for each finding. Check `docs/agents/defect-classes.md` by name. Under 400 words."

**Correctness sub-agent prompt** — include:

- The captured diff — the exact path the block printed, not a pattern — and its line count, the diff command that produced it, and the commit list.
- The path or fetched contents of the spec if there is one (so "behaviour the ticket did not ask for" has a referent), the test command the repo uses, and the settled decisions.
- The brief: "Report: (a) bugs — for each, the concrete failure scenario: the input, environment or sequence that makes the diff misbehave, and what a user sees; think about the run nobody is watching (piped output, closed stdin, missing tool, empty result, a name with an odd character, a second run over the same state); (b) behaviour the ticket did not ask for; (c) `docs/agents/defect-classes.md` checked by name, class 1 (an absent or malformed answer read as a benign one) and class 3 (a test that passes for a reason other than the one it claims) especially, since you own the witness check; (d) every new or changed test checked as a witness: strip the constraint under test and see whether the assertion still passes — one that survives is a hollow witness, flag it — and when a mutation goes red, read the message and confirm the failure is your assertion and not a missing file or a denied path, which is class 3 again. (e) every safety guard the diff adds — a check that refuses, validates or fails closed — gets a second, separate mutation: mutate its call site. For every entry point the guard exists to protect, delete or neutralize the call to the guard there, run the suite that covers that entry point, and confirm it goes red at that entry point — not only in the unit test that calls the guard directly; mutating the guard's own body (d) reddens that unit test and says nothing about whether anything still calls the guard. A call-site mutation that stays green is an unprotected entry point: report it as a finding naming the entry point, since the guard can be bypassed at the only place it matters. Read the failure message as in (d), so a red from a missing file is not taken for a red from the assertion. Isolate each mutation in a throwaway worktree — `git worktree add --detach <a path outside the checkout> HEAD`, removed afterwards with `git worktree remove --force` — and never in a copy of the tree, which on a linked worktree shares the checkout's own index. Re-run only the suite that covers the mutated test (the file it lives in, run the way the repo's gate runs that file), never the whole gate. Prepare every mutation and launch them at once rather than walking them in turn — at most four running together — a third of the headroom under the box's 28-process cap, counted `ps -eo comm= | grep -cx claude` and never `ps aux | grep`, since your axis is one of three — and fewer, down to one at a time again, when the box is already busy or its process table cannot be read: slower, never refused. Each mutation keeps its own worktree and its own captured output, and you collect them by id when they finish; a call-site mutation gets its own id, distinct from the constraint mutation it accompanies, never shared with it, so a failure message is still read against the mutation that produced it. A mutation whose worktree, suite run or output never arrived is `unknown`, reported by that name — never counted as an assertion that held, which is class 1. Nothing is restored between mutations: each worktree is discarded whole, and the checkout is left exactly as found. A file outside the repository (`~/.local/bin`, a dotfile, a registry) is read with one plain command — `cat <path>` or `diff <a> <b>` — never inside a `cd ... && for` compound, which the permission classifier cannot read as the read it is and blocks; and a mutation never reaches a step that writes outside the worktree (an installer, a registry edit, a symlink into `~`): stub that seam or skip the mutation and report it `unknown` (2026-09-21: a mutation ran a toast installer for real and left a registry key pointing at a deleted `/tmp` worktree). Rate each bug PLAUSIBLE or CONFIRMED and say which. Under 450 words."

**What the witness check costs, and what actually isolates it** (#939). The
check itself is the most valuable thing a review does — the `paths()` fail-open
in #893, the zero-cores default in #894 and the suppressed contradictions in
#897 all came out of it in one day. Neither line below runs it less.

*Isolation.* `git worktree add` a throwaway worktree per mutation. **Never
`cp -a`**, or any other byte copy of the reviewed tree: a linked worktree's
`.git` is a *file holding a gitdir pointer*, not a directory, so a copy of one
still points at the original's gitdir and shares its index, HEAD and refs.
Reviews in this lane always run on a linked worktree, so the copy is not weaker
isolation — it is none. On 2026-09-20 a worker followed the wording this
replaces, copied its tree with `cp -a`, and two `git rm --cached` runs inside
the "isolated" copy staged deletions in the real checkout's index; it noticed
only because those two mutations happened to be staged ones. A worktree has its
own index and HEAD, so the same command cannot reach the checkout, and `git
clone --no-hardlinks` is the other safe answer. Sharing the object store also
costs no copy of the 419 MB / 529 tracked files this repo carries. `HEAD` is
the revision the captured diff ends at, so the mutation lands on exactly the
code under review.

*Concurrency* (#957). The mutations share nothing — each has its own worktree,
its own index and its own output file — so they run together, and the check
costs one covering-suite run of wall clock instead of one per mutated test.
The serial reading was an artefact of the brief being written as a list of
steps; nobody established it as a constraint. Measured on
`caneff/sudokupad-art` on 2026-09-20: `test_retro_waves.py` is 31.96s of a
33.9s suite (378 of 602 tests, everything else 0.91s), and the recent work is
in that file, so the covering suite is the slow one. A diff adding ten tests
paid five minutes before the reviewer read anything, and that correctness pass
took 22 minutes.

A call-site mutation (correctness brief, (e)) is one more kind of mutation for
this machinery to run, one per protected entry point, enumerated beside the
constraint mutation it accompanies. Each gets its own id, its own worktree and
its own output file — allocated the same way a constraint mutation's are — and
its `unknown` is reported the same way. No two mutations, call-site or
constraint, ever share an id.

Two things the concurrency must not cost. **The message stays paired with its
mutation**: reading the message rather than the exit status is what catches
defect class 3, and N reds collected into one stream is how that pairing is
lost — hence one output file per id, and a collection loop that prints each
message under the id that produced it. **An unreached mutation is `unknown`,
not a pass**: a worktree that failed to create, a suite that never started, an
output file that is empty. Reported by name, never folded in with the
assertions that genuinely held — that is defect class 1, and it is the failure
this whole block is most exposed to.

There is **nothing to restore**. The serial loop restored implicitly, by moving
on to the next test; with the mutations concurrent nothing is shared to restore
and each worktree is discarded whole. No step here reaches back into the
checkout to undo anything, and reintroducing one would be the `cp -a` defect by
another route.

*The bound.* The box cap is 28 claude processes machine-wide, counted
`ps -eo comm= | grep -cx claude` — by command name, never `ps aux | grep`,
which matches any process whose arguments merely contain a claude path and
overcounted by more than double on 2026-09-20. This axis is one of three
running in parallel and does not own the box, so it takes a third of the
headroom under that cap, capped at four: past that a CPU-bound covering suite
stops overlapping and starts contending. A busy box drives the bound to 1 —
the sequential check this replaces, slower but still run. So does a box whose
process table cannot be read at all: an unreadable count is treated as a full
machine, never as an idle one, which is class 1 applied to the bound itself.
It never refuses: a witness check that declines because the machine is loaded
is worse than a slow one.

```
worktree=<the worktree under review>
ids=<space-separated mutation ids, one per new or changed test — the names you report by>
mutate() { :; }   # <$1 the id, $2 the witness worktree, $3 a marker path: strip that test's constraint in $2, create the marker with `: >"$3"` on the line IMMEDIATELY before the covering suite's command, and run only that suite>

# Job control, so each background mutation is its own process group and an
# interrupt can reach a covering suite's whole process tree rather than only
# the wrapper shell around it. An interrupted run may print a job notice.
set -m
top=$(git -C "$worktree" rev-parse --show-toplevel) || exit 1
# Split into an array with pathname expansion OFF, and use that array from here
# on. An unquoted `$ids` expands before any validation can see it, so `ids='*'`
# becomes the checkout's filenames - each of which passes the character check
# below - and the run mutates a set nobody asked for while omitting the id that
# was actually requested.
set -f
mutations=( $ids )
set +f
# An empty list is a failed enumeration upstream, not a clean check: every loop
# below would run zero times, cleanup would succeed, and the run would report
# success having witnessed nothing. Refused before anything is created.
if [ "${#mutations[@]}" -eq 0 ]; then
  echo "witness check: no mutations supplied - nothing was checked" >&2; exit 2
fi
# An id names a directory and an output file, so it is checked before anything
# exists: a pytest nodeid (`tests/a.py::t1[x]`) would put a mutation's output
# file inside its own worktree and break the per-id prefixing below. Refused by
# name — map the test to a short id and report the mapping — never mangled.
seen=" "
for id in "${mutations[@]}"; do
  case "$id" in ''|*[!A-Za-z0-9._-]*)
    echo "witness check: '$id' is not usable as a mutation id (letters, digits, . - _)" >&2; exit 2;;
  esac
  case "$seen" in *" $id "*)
    echo "witness check: id '$id' is named twice - one mutation would overwrite the other's output" >&2; exit 2;;
  esac
  seen="$seen$id "
done
root=$(mktemp -d)
# Checked, not assumed: a TMPDIR under the reviewed tree would put the
# throwaway worktrees inside the checkout, and those untracked directories then
# block `git worktree remove` and `ship` long after the review reported green.
case "$root" in "$top"/*)
  echo "witness check: TMPDIR is inside the checkout ($root)" >&2; exit 1;;
esac
# Worktrees, outputs and statuses get disjoint directories: with all three in
# one, the ids `x` and `x.out` are both legal and collide - the parent creates
# worktree `x.out` while mutation `x` is opening its output file at that same
# path, so `x`'s redirection fails against a directory and `x` is reported red
# without its suite ever having run.
mkdir -p "$root/worktrees" "$root/output" "$root/status" "$root/ran" || exit 1
# Cleanup that reports rather than covers: an `rm -rf` over a worktree git
# failed to deregister - a full disk is the plausible way - leaves exactly the
# stale entry this recipe's own prose says never to create, and the run would
# exit 0 having created it. A failed removal keeps its directory, keeps the
# root, and says so.
cleanup() {
  cleanup_failed=0
  for w in "$root"/worktrees/*/; do
    [ -d "$w" ] || continue
    git -C "$worktree" worktree remove --force "${w%/}" && continue
    cleanup_failed=$(( cleanup_failed + 1 ))
    echo "witness check: could not remove worktree ${w%/} - it is still registered" >&2
  done
  if [ "$cleanup_failed" -gt 0 ]; then
    echo "witness check: $cleanup_failed worktree(s) left registered; keeping $root - list them with git worktree list and remove them by hand" >&2
    return 1
  fi
  rm -rf "$root" 2>/dev/null
}
# Armed before the first `worktree add` and sweeping every mutation, because a
# witness check that WORKS makes the covering suite fail — that failure is the
# whole point, and it is the ordinary outcome, not the exceptional one. INT and
# TERM as well: this run is minutes long, so a reviewer's ctrl-C is an ordinary
# way for it to end, and it would otherwise leave N registered worktrees behind
# to stall the next `worktree remove` and any later `merge-cleanup`.
# Signalling this shell does not reach its background children, so without this
# the covering suites keep running after their worktrees are force-removed,
# holding the box and writing into deleted paths. Stop them, reap them, and only
# then clean up.
stop_children() {
  pids=$(jobs -pr)
  [ -n "$pids" ] || return 0
  for pid in $pids; do kill -TERM "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null; done
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    [ -n "$(jobs -pr)" ] || break
    sleep 0.5
  done
  for pid in $(jobs -pr); do kill -KILL "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null; done
  wait 2>/dev/null
}
trap cleanup EXIT
trap 'stop_children; cleanup; exit 130' INT TERM
# The bound and its reason are *The bound* above. What the code adds is the
# refusal to guess: no readable process table means a full box, not an idle one.
if procs=$(ps -eo comm= 2>/dev/null) && [ -n "$procs" ]; then
  busy=$(printf '%s\n' "$procs" | { grep -cx claude || true; })
else
  busy=28
fi
slots=$(( (28 - busy) / 3 )); [ "$slots" -gt 4 ] && slots=4; [ "$slots" -lt 1 ] && slots=1
# A mutation's own output, head AND tail, every line tagged with the id that
# produced it: pytest puts the assertion text at the end, so the head alone cuts
# out exactly what you are reading for.
show() {
  n=$(wc -l <"$root/output/$1" 2>/dev/null || echo 0)
  if [ "$n" -le 50 ]; then cat "$root/output/$1"
  else head -25 "$root/output/$1"
       printf '... %s lines omitted from the middle ...\n' "$(( n - 50 ))"
       tail -25 "$root/output/$1"
  fi 2>/dev/null | awk -v p="  $1| " '{print p $0}'
}
for id in "${mutations[@]}"; do
  while [ "$(jobs -pr | wc -l)" -ge "$slots" ]; do wait -n; done
  witness="$root/worktrees/$id"
  if ! git -C "$worktree" worktree add --detach -q "$witness" HEAD; then
    printf 'unknown\n' >"$root/status/$id"   # class 1: an unreached mutation is not a pass
    continue
  fi
  # `mutate` in its own subshell: a mutation body ends in a failing suite and
  # is naturally written with `exit`, which would otherwise kill this job
  # before its status is recorded and read back below as `unknown`.
  { ( mutate "$id" "$witness" "$root/ran/$id" ) >"$root/output/$id" 2>&1
    printf '%s\n' "$?" >"$root/status/$id"; } &
done
wait
for id in "${mutations[@]}"; do
  # The marker says the wrapper reached the line before the covering suite - a
  # wrapper that dies earlier (a missing test path, a denied command) exits
  # nonzero and writes an error, and without this that reads as an assertion
  # witnessed.
  if [ ! -e "$root/ran/$id" ]; then
    printf '%s: unknown — it never reached its covering suite, whatever it exited with\n' "$id"
    continue
  fi
  # 126 and 127 are the kernel answering directly: the command was not
  # executable, or was not found, so it never started. The marker cannot know
  # that - it is written on the line before - and every proxy for "the suite
  # ran" is a proxy. Where a real answer exists, take it instead of inferring.
  case "$(cat "$root/status/$id" 2>/dev/null)" in
    126|127) printf '%s: unknown — its covering suite command never executed (not found, or not executable)\n' "$id" ;;
    0) printf '%s: HOLLOW — the assertion still passed with its constraint stripped\n' "$id" ;;
    [1-9]*) printf '%s: red — its own message follows; confirm it is your assertion, not a missing file or a denied path\n' "$id"
            show "$id" ;;
    *) printf '%s: unknown — the mutation never ran to completion; report it by name, never as a pass\n' "$id" ;;
  esac
done
cleanup || exit 3
trap - EXIT INT TERM
```

`git worktree remove`, never `rm -rf`: a directory deleted out from under the
registration leaves a stale entry that stalls the next `worktree remove` and
any later `merge-cleanup` on this repo.

*Scope.* Re-run the suite that covers the mutated test — the file it lives in,
run the way `tests/all.sh` would run it (`bash <name>.test.sh`, `python3
<name>_test.py`) — not the whole gate. `bash tests/all.sh` is 2m51s wall over
62 suites here, so a diff adding five tests would pay it five times inside one
axis, while the covering suite finishes in seconds. The whole gate belongs to
the worker's own pre-report gate, where it already runs once.

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

### 6. The verification pass

A caller that follows round 1 with one verification pass (implement's review
step 2) spawns one `diff-reviewer`, `model: opus`, fire-and-return as in § 4.
Its prompt carries the round-1 findings sidecars, a fresh capture of the fix
commits, the worker's claimed dispositions — each a claim to check, never
settled, and never with an outcome pre-assigned — and the settled decisions.
It writes `dispositions-<n>.jsonl` in the grammar of `implement/SKILL.md` § Review,
and its report to `<dir>/review-verify-<n>.md`.

The brief: "Check each round-1 finding id against its fix or its claimed
disposition. Fail the pass, naming the finding id, on any of four things:
(a) a round-1 finding with no disposition — `leftover` counts as one, as
do the other four outcomes; (b) a `leftover` whose finding
is high under implement's severity mapping, since a high finding is filed —
read a correctness finding's `CONFIRMED` or `PLAUSIBLE` from its prose
report, since its sidecar line carries only `hard` or `judgement`;
(c) an adjacent fix that breaks `implement/SKILL.md` § Review's adjacent-fix
rule. For (c), write the sidecar
first, then run `python3 ~/.agents/skills/multi-axis-code-review/check_adjacent.py --repo <worktree> --base <fixed point> <dir>/dispositions-<n>.jsonl`:
it measures every sidecar line with `"scope": "adjacent"` for one file, a
file already in the diff and under 20 changed lines, and prints `BREACH <id>`
for each that breaks them, or for any line it cannot read. Judge the other
two parts — one function and no public seam — by reading the fix commit, and
fail by id on those the same way. (d) a `disputed: unreachable — <why>`
disposition whose why does not name how the environment in
`implement/SKILL.md` § Review's reachability bar (this box, our repos,
bodies people here write) rules the failure out; a bare "unlikely" or
"cannot happen" fails by id, since the bar would otherwise suppress a
reachable finding unchecked. Report every breach beside the finding it
belongs to. Under 400 words."

## Why separate axes

A change can pass one axis and fail another:

- Code that follows every standard but implements the wrong thing → **Standards pass, Spec fail.**
- Code that does exactly what the issue asked but breaks the project's conventions → **Spec pass, Standards fail.**
- Code that matches the ticket and the conventions and deletes the wrong branch when stdin is a pipe → **Standards and Spec pass, Correctness fail.**

Reporting them separately stops one axis from masking another. On agent-skills #731 the standards and spec axes found the rule and ticket findings, and every runtime finding (the prompt lost under a pipe, the ahead count that was noise, the unrecorded `branch -D`) came from failure-scenario reading.

This is also the one home for why the built-in `/code-review` is not in the implement lane (#732, measured on that 250-line diff): at medium effort it forked eight finder agents for 80k output and 9.2M cached tokens and returned before reading them; one opus standards axis cost 9.4k output and 0.68M cached. `/code-review low` (3.4k / 70k, one finding) stays available when the owner asks for it.
