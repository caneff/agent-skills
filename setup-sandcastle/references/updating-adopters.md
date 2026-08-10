# Updating adopters

Operator runbook for the maintainer sweeping template changes across every repo
that already has Sandcastle installed. The reasoning behind the skill's shape
lives in [`design-decisions.md`](design-decisions.md); this file is the
instructions.

Once a repo is installed, later `sandcastle-template/vN` tags reach it through
the [`sandcastle-propagate`](../sandcastle-propagate) maintainer script. It
discovers every adopter under `~/src` by its root `.copier-answers.yml`
breadcrumb (no hardcoded list), lets `copier update` re-assert each repo's own
recorded answers, then commits `.sandcastle` and pushes. Always dry-run first:

```bash
sandcastle-propagate --dry-run     # show what each repo would receive
sandcastle-propagate               # copier update, commit, push (skips dirty repos)
sandcastle-propagate --divergence  # report local drift only — changes nothing
```

Pass a ref to pin (`sandcastle-propagate sandcastle-template/v4`); the default
is the newest `sandcastle-template/v*` tag.

Both the sweep and `--divergence` report how far each repo has drifted from the
template it recorded — one line per hunk, unmarked first:

```
visual-teach   .sandcastle/Dockerfile:12    +6 -2   local: Playwright needs a browser binary
visual-teach   .sandcastle/main.mts:479     +1 -1   UNMARKED
```

The report is computed, never maintained: the script re-renders each repo's own
`_commit` with that repo's own answers and diffs the live tree against it. An
`UNMARKED` line is drift nobody explained — either mark it with a
`sandcastle:local` reason (rule 5 of the standards doc) or lift it into the
template. Exit status is 0 whatever the report finds.

**Install it as a symlink, never a copy**
(`ln -sf "$PWD/setup-sandcastle/sandcastle-propagate" ~/.local/bin/`). A copy goes
stale, and a stale copy fails *silently*: the pre-#93 version searched
`*/.sandcastle/.copier-answers.yml`, so once adopters moved their breadcrumb to
the repo root it reported `updated=0 skipped=0` — indistinguishable from "every
repo is already current" while it swept past all of them.

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
  root breadcrumb before pushing, so every merged change is in that commit's
  diff.
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
