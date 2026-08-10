# Updating adopters

Operator runbook for the maintainer sweeping template changes across every repo
that already has Sandcastle installed. The reasoning behind the skill's shape
lives in [`design-decisions.md`](design-decisions.md); this file is the
instructions.

Once a repo is installed, later `sandcastle-template/vN` tags reach it through
the [`sandcastle-propagate`](../sandcastle-propagate) maintainer script. It
discovers every adopter under `~/src` by its root `.copier-answers.yml`
breadcrumb (no hardcoded list), lets `copier update` re-assert each repo's own
recorded answers, then opens a pull request on each. A linked git worktree holds
a checked-out copy of its repo's breadcrumb, so the walk finds it too — the sweep
passes over it in silence, because sweeping it would open a pull request out of
someone's in-progress branch. Always dry-run first:

```bash
sandcastle-propagate --dry-run     # show what each repo would receive
sandcastle-propagate               # copier update, branch, PR (skips dirty repos)
sandcastle-propagate --divergence  # report local drift only — changes nothing
```

Pass a ref to pin (`sandcastle-propagate sandcastle-template/v4`); the default
is the newest `sandcastle-template/v*` tag.

## What the summary line says, and what the exit status means

A sweep sorts every adopter it claims into one of four classes and prints the
tally on one line:

```
Done. updated=2 current=1 skipped=1 failed=0
```

- **updated** — the ref was carried and a PR is open for it.
- **current** — the repo was already at the target ref, so there was nothing to
  carry. This is the class the old two-counter summary had no word for.
- **skipped** — a legitimate pass. The working tree was dirty, or a sweep PR is
  already open and waiting for review. Someone chose this state; nothing is
  wrong.
- **failed** — a fault. copier could not render, the merge left inline conflict
  markers, the commit or push did not land, `gh` could not answer whether a PR
  was open or could not open one, or a breadcrumb turned out not to sit inside a
  git repo at all.

**The sweep exits non-zero exactly when `failed` is non-zero.** A fault never
stops the sweep — the repos after it are still swept, and the exit code carries
the fault out. A dirty tree deliberately does *not* fail the run: a status that
goes red on the ordinary case is a status people learn to ignore, which is how a
fleet ends up read by summary again.

**Matching no adopter is an error**, whichever way it happens, and the two are
worded apart because they send you to different places: finding no
`.copier-answers.yml` at all names the search root you gave it, while finding
breadcrumbs that none of them name this template says so instead. This is the
case #93 got wrong.

`--dry-run` and `--divergence` carry nothing, so they have no update to count.
They report what they reached — `Done. inspected=2 skipped=0 failed=0` — and
`--divergence` still exits 0 whatever drift it finds. The zero-adopter error
applies to both.

**Nothing reaches an adopter's default branch.** Every update goes up as a PR on
a `sandcastle/update-to-<ref>` branch, whatever its size — a one-line change to
the Dockerfile's base image is the most dangerous diff in the fleet and the
smallest, so diff size is no threshold to gate on. Install requires a CI
workflow, so the PR is where that repo's checks run. The sweep prints each PR
URL and exits: no polling, no auto-merge, and merging is yours.

The branch is named for the target ref, so a re-run at the same ref reuses it
rather than littering the repo with dated branches. That push is forced: the
sweep owns the `sandcastle/update-to-` namespace, and a branch an earlier run
left behind would otherwise reject every later attempt. Nothing under review is
at risk, because **an adopter that already has a sweep PR open is skipped by
name** and counted with the other skips — stacking an update on an unreviewed
one puts the second diff against a base nobody has accepted. If `gh` cannot say
whether a PR is open, that repo is left alone rather than swept on a guess, and
counted as a failure: an unanswered question is not an answer of "none open".

The local checkout never switches branches. The sweep commits on whatever branch
is checked out, pushes that commit under the new name by refspec, then restores
the branch to the SHA it recorded first. That restore is unconditional: a failed
push leaves the repo byte-identical to how the sweep found it, with the work
still on the pushed branch if the push is what succeeded.

`gh` is checked once, up front — missing or unauthenticated aborts the whole
sweep before any repo is touched, rather than stranding a half-swept fleet.
`--dry-run` stops short of `gh` entirely, so it stays usable before you log in.

Both the sweep and `--divergence` report how far each repo has drifted from the
template it recorded — one line per hunk, unmarked first:

```
visual-teach   .sandcastle/Dockerfile:12    +6 -2   local: Playwright needs a browser binary
visual-teach   .sandcastle/main.mts:479     +1 -1   UNMARKED
```

That report is also the PR body, under the refs the repo moved between, so a
reviewer reads what the update carried and what it could not in one place.

The report is computed, never maintained: the script re-renders each repo's own
`_commit` with that repo's own answers and diffs the live tree against it. An
`UNMARKED` line is drift nobody explained — either mark it with a
`sandcastle:local` reason (rule 5 of the standards doc) or lift it into the
template. The report never blocks: it exits 0 whatever drift it finds, and even
when a repo faults under it — only a run that matched nobody fails.

**Put a marker next to what it explains — within about three lines.** The diff
runs at zero context, so it cuts a hunk at every run of changed lines: a marker
comment with even one untouched line beneath it is a hunk of its own, and the
divergence under it is another. The report carries a reason down to the next
hunk when that hunk starts within three lines, which covers a marker sitting
above its paragraph, blank line and all. Further away and nothing travels —
otherwise one reason at the top of a file would excuse everything below it. A
marker that ends up too far reads as `UNMARKED` no matter how good the reason
is; move it, don't reword it.

What the adopter's own git ignores never reaches the report. The orchestrator
writes logs, `.env` and scratch JSON into `.sandcastle/`, and that runtime output
is not drift from the template — it is the tool's exhaust. The filter asks
`git -C <repo> check-ignore`, so it honors every level of ignore the repo has:
its root file, the `.sandcastle/` subtree, and your global one. A file git
tracks is never reported ignored, so an adopter-added file that nothing ignores
still reports as `NEW UNMARKED`.

**Install it as a symlink, never a copy**
(`ln -sf "$PWD/setup-sandcastle/sandcastle-propagate" ~/.local/bin/`). A copy goes
stale, and a stale copy used to fail *silently*: the pre-#93 version searched
`*/.sandcastle/.copier-answers.yml`, so once adopters moved their breadcrumb to
the repo root it reported `updated=0 skipped=0` — indistinguishable from "every
repo is already current" while it swept past all of them. That particular
silence is now impossible: matching nothing is an error, and a fleet that really
is current says `current=N`.

**It is a real 3-way merge, not a re-render.** The script runs `copier update`
(#93): template edits merge in and a file an adopter legitimately edited under
`.sandcastle` is preserved. Update resolves now because the subproject root is
the repo's git root, so copier's update diff runs against a path that exists in
both the temp render and the real tree. A genuine conflict (adopter and template
touched the same lines) lands as inline `<<<<<<<` markers; the script refuses to
commit such a tree and flags the repo for a human, so a half-merged state is
never pushed. Resolve each one by reading it: a conflict whose local side is
empty is a template addition, so take theirs; a conflict with real local content
is a decision, so make it deliberately.

Safety properties:

- **Runtime state is untouched.** `.env`, `logs/`, `worktrees/`, and
  `review-attempts.json` are not template-rendered, so copier never writes or
  deletes them.
- **Uncommitted work is skipped.** The script refuses any repo with a dirty
  tree — commit or stash first. On a clean repo it commits `.sandcastle` and the
  root breadcrumb onto the pushed branch, so every merged change is in that
  commit's diff, and restores the checkout afterwards.
- **A `tests/` directory an adopter carries never updates itself.** copier
  excludes `tests/` from the render, so a sweep cannot refresh one; an adopter
  installed before that exclusion is pinned to whatever API it copied. Copy the
  current suite over by hand if you find one, skipping `copier-template.test.mjs`
  and `propagate.test.mjs`, which test this skill rather than a target.

To confirm before running, `--dry-run` (`copier update --pretend`) shows the
merge each repo would receive without touching it.

## Upstream upgrades

Bumping `@ai-hero/sandcastle` is a maintenance action on this skill's
`templates/`, never on a target. In `templates/`: `npm outdated
@ai-hero/sandcastle` → read its CHANGELOG → bump the pin → `npm run typecheck
&& npm test` → commit. The next install carries it, and the sweep above pushes
it to repos already installed.

## One-time: record `LANGUAGE=node` on a Node adopter

`LANGUAGE` defaults to `python`, so a breadcrumb written before the answer
existed carries no `LANGUAGE` and the first sweep supplies the default. For a
Node adopter that is wrong: the sweep would render the Python image over its
repo. Correct the answer once, by hand, and it persists to every later update
with no flag:

```bash
# vN = the newest sandcastle-template tag, the same ref the sweep would use
cd ~/src/visual-teach && copier update --defaults --trust \
  --vcs-ref sandcastle-template/vN --data LANGUAGE=node
```

**Run it before the first sweep reaches that repo.** A `sandcastle-propagate`
run that gets there first re-asserts `python` and rewrites the image, and
undoing that costs a second migration.
