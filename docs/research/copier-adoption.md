# Copier adoption research — driving `copier update` on repos copier never generated

Ticket: #66
Question: Can copier adopt repos it did NOT generate (scaffolded by `cp -r`, no
`.copier-answers.yml`, since drifted with hand-edits) and drive `copier update`
(3-way merge) without clobbering truly-local additions?

Sources are copier's official docs (copier.readthedocs.io, `stable`) and the
copier GitHub repo. Every load-bearing claim is quoted below.

## Bottom line

Yes — adoption is feasible and is an explicitly supported use case, but there is
**no `copier adopt` command yet** (it is only a proposed feature). The supported
path is: run `copier copy` from the template into the existing tree so copier
writes a real `.copier-answers.yml` breadcrumb, resolve the one-time collision
between template output and your drifted files, commit that, and from then on
`copier update` does exactly the 3-way merge you want. Details and the exact
procedure at the end.

---

## 1. Seeding `.copier-answers.yml` on a repo copier never generated

### Copier explicitly supports applying a template over a pre-existing project

Copier's FAQ answers this directly.

> **Q: Can Copier be applied over a preexisting project?**
> A: "Yes, of course. Copier understands this use case out of the box." … it
> "powers features such as updating or the ability of applying multiple
> templates to the same subproject", with the example:
> `copier copy https://github.com/me/my-template.git ./my-preexisting-git-project`

(FAQ, https://copier.readthedocs.io/en/stable/faq/)

So you do **not** have to hand-author the answers file. You run `copier copy`
into the existing directory and copier itself writes the breadcrumb — *provided
the template contains an answers-file template*, see below.

### The breadcrumb is produced by a file in the TEMPLATE, not written by hand

The answers file only appears in generated projects because the template ships a
Jinja file that renders it. From the template-authoring docs:

> The `.copier-answers.yml` file is created in the template using
> `{{_copier_conf.answers_file}}.jinja`, and should contain:
> `# Changes here will be overwritten by Copier\n{{ _copier_answers|to_nice_yaml -}}`

(Creating a template, https://copier.readthedocs.io/en/stable/creating/)

And from the configuring docs, the file **must** be named exactly this in the
template root:

> "The file **must be called exactly `{{ _copier_conf.answers_file }}.jinja`**
> (or ended with your chosen suffix) in your template's root folder"

(Configuring, https://copier.readthedocs.io/en/stable/configuring/)

Implication for our 5 repos: the *central template* must itself contain a
`{{ _copier_conf.answers_file }}.jinja` file. If it does, `copier copy` into each
existing repo will drop a correct `.copier-answers.yml`. If the template does not
yet have that file, add it first — that is the single prerequisite.

### Which ref/commit gets recorded, and how `copier update` finds its base

The breadcrumb records two special keys that are the entire basis for future
updates:

> These metadata fields track template updates:
> `_commit: 0.1.0`
> `_src_path: gh:your_account/your_template`
> The `_copier_answers` variable … "includes the special `_commit` and
> `_src_path` keys", which indicate "how the last template update was done."

(Creating a template, https://copier.readthedocs.io/en/stable/creating/)

`_commit` is the git ref/tag of the template version the project currently
corresponds to; `_src_path` is where the template lives. `copier update` reads
these to regenerate the *old* baseline (see §2). Requirement, quoted:

> "The destination folder includes a valid `.copier-answers.yml` file" (a
> necessary condition), alongside "The template is versioned with Git (with
> tags)" and "The destination folder is versioned with Git."

(Updating, https://copier.readthedocs.io/en/stable/updating/)

**Do not hand-edit the answers file after the fact.** Both the configuring and
updating docs warn against it:

> "Did you notice that `NEVER EDIT MANUALLY` part? It is important" … the system
> automatically regenerates this file. (Configuring)
> "**Never** update `.copier-answers.yml` manually. This will trick Copier,
> making it believe that those modified answers produced the current subproject."
> (Updating)

So the supported seeding move is *let `copier copy` write it* rather than author
it by hand. Whatever `_commit` you copy at becomes the base; pin it with
`--vcs-ref` to a real tag so the first `copier update` has a valid, checkout-able
baseline to diff from.

### Is there a first-class "adopt" command? Not yet.

There is an open feature request, **Issue #2486 "Feature: `copier adopt` —
first-class workflow for adopting a template in an existing project"** (opened
2026-02-04). Status, quoted from the issue:

> `copier adopt` is proposed, not implemented.
> "The current documented workaround (from #955 / PR #981) is to
> `copier copy --overwrite` and then use `git difftool` to manually cherry-pick
> changes back." … characterized as "tedious, error-prone, and doesn't scale
> when adopting a template across many existing repositories."

(https://github.com/copier-org/copier/issues/2486)

So the officially-documented adoption path today is `copier copy` (optionally
`--overwrite`) into the tree + git to reconcile — exactly what the FAQ endorses.
No hand-authoring of the answers file is required or recommended.

---

## 2. What the FIRST `copier update` does on an adopted, already-drifted repo

### The update algorithm (verbatim)

> "It regenerates a fresh project from the current template version. Then, it
> compares both version to get the diff from 'fresh project' to 'current
> project'. Now, it applies pre-migrations to your project, and updates the
> current project with the latest template changes (asking for confirmation).
> Finally, it re-applies the previously obtained diff and then runs the
> post-migrations."

(Updating, https://copier.readthedocs.io/en/stable/updating/)

Mechanically (confirmed by the requirement that `_commit` be recorded and the
template be tag-versioned): copier checks out the template at the **old**
`_commit`, regenerates a pristine "what the template would have produced" tree
using your recorded answers, treats your current working tree as the other side,
computes your local diff against that pristine baseline, generates the **new**
template version, and re-applies your local diff on top via a git 3-way merge.
Conflicts surface the same way a `git merge` conflict does (see §3 quote).

### (a) A file the repo locally modified that IS in the template

This is the case 3-way merge is built for. Copier's baseline is the *old*
template's version of that file; your working copy is the modified side; the new
template is the incoming side. Your hand-edits are preserved where they don't
collide, and where the template also changed the same lines you get a normal
merge conflict to resolve:

> "`--conflict inline` (default): Updates the file with conflict markers. This is
> quite similar to the conflict markers created when a `git merge` command
> encounters a conflict." (Updating)

**Important caveat for our 5 repos:** because they were `cp -r`'d and have since
drifted, the baseline copier regenerates at `_commit` will NOT match the drifted
files. Every place your repo diverged from that template version is a local diff
copier will try to carry forward — which is what you want — but where the *new*
template touches those same regions you will get conflict markers. So the first
update is the noisy one; expect conflicts proportional to how far each repo
drifted. That is inherent to adoption, not a bug.

### (b) A pure local addition NOT in the template

Safe. A file that exists in your project but in neither the old nor new template
output is simply not part of the template diff, so copier never regenerates or
touches it. Corroborating doc statement about the inverse (template files you
deleted also stay out of the way):

> "Template-based files/directories that were deleted in the generated project
> are automatically excluded from updates." (Updating)

Truly-local additions are preserved untouched. This is the core reassurance for
the goal ("preserve truly-local additions").

### Clean merge vs markers vs overwrite — summary

- Local-only files: untouched (no merge, no overwrite).
- Template files you didn't touch but the template changed: updated cleanly.
- Files you edited where the template also changed the same lines: conflict
  markers (`inline`, default) or `.rej` files (`rej`) for you to resolve. Not a
  silent overwrite.

The docs stress manual review:

> Users "should review those manually before committing." (Updating)

---

## 3. Flags / keys that govern this

- **`--conflict inline` (default) vs `--conflict rej`** — on `copier update`:
  > "`--conflict rej`: Creates a separate `.rej` file for each file with
  > conflicts. These files contain the unresolved diffs."
  > "`--conflict inline` (default): Updates the file with conflict markers."
  (Updating). Use `inline` for git-merge-style `<<<<<<<` markers in place.

- **`--defaults`** — reuse recorded answers non-interactively:
  > "`copier update --defaults`" reuses all previous answers. (Updating)

- **`--vcs-ref` / `-r`** — choose which template ref to move to:
  > "`copier update --vcs-ref=HEAD`" updates to the latest commit;
  > "`copier update --vcs-ref=:current:`" updates answers without changing the
  > template. (Updating).
  On the initial `copier copy` for adoption, use `--vcs-ref=<tag>` to pin the
  `_commit` baseline that gets recorded.

- **`--skip` / `-s`** — DOCS UNCERTAIN ON EXACT WORDING. This is a `copier copy`
  option meaning "skip files that already exist" (the counterpart to
  `--overwrite`). I could not retrieve the verbatim one-line description from the
  stable reference page in this session (the CLI reference page redirected), so
  treat the exact semantics as needing a `copier copy --help` confirmation. Its
  role in adoption: on the seeding copy, `--skip` keeps your drifted files
  instead of prompting, at the cost of not laying down template files that
  collide. Verify before relying on it.

- **`--overwrite` / `-w`** — the workaround in Issue #2486 uses
  `copier copy --overwrite` to force the template output down, then `git` to
  cherry-pick your edits back. Default `copier copy` onto an existing tree
  prompts per conflicting file rather than overwriting.

- **`_exclude`** — template key:
  > "Patterns for files/folders that must not be copied." Default excludes
  > `copier.yaml`, `copier.yml`, and version-control dirs. (Configuring). Use it
  so the template never tries to own paths that should remain purely local.

- **`_subdirectory`** — template key:
  > "Subdirectory to use as the template root when generating a project."
  (Configuring). Only the subdirectory's contents are rendered into the project,
  which keeps template metadata out of the generated tree.

- **`.jinja` suffix / `_templates_suffix`** — governs which files are rendered:
  > File contents are "copied to the destination without changes, **unless they
  > end with `.jinja`**" (or a configured suffix); with the suffix "the
  > templating engine will be used to render them." (Creating). Default suffix
  > is `.jinja` (Configuring, `_templates_suffix`).
  Interaction with adopting an existing tree: the template stores a file as
  `foo.py.jinja` but writes it to the project as `foo.py`. So when `copier copy`
  lands on your existing repo, the template's `foo.py.jinja` collides with your
  existing `foo.py` (correct — that's the file to reconcile). The answers-file
  template itself is `{{ _copier_conf.answers_file }}.jinja` and renders to
  `.copier-answers.yml`. No special handling needed beyond knowing the suffix is
  stripped on output.

---

## 4. Copier vs cruft for "adopt an existing, non-generated repo"

**cruft supports this explicitly, via `cruft link`.** From cruft's README/docs:

> "If you have an existing project that you created from a template in the past
> using Cookiecutter directly, you can link it to the template that was used to
> create it using: `cruft link TEMPLATE_REPOSITORY`. You can then specify the
> last commit of the template the project has been updated to be consistent
> with, or accept the default of using the latest commit from the template."

(cruft README, https://github.com/cruft/cruft/blob/main/README.md)

cruft's `link` is the exact "adopt" primitive copier lacks as a named command: it
writes the `.cruft.json` breadcrumb (analogous to `.copier-answers.yml`) with a
chosen base commit, after which `cruft update` / `cruft diff` / `cruft check`
work. Note cruft is Cookiecutter-based, and its own docs acknowledge the same
adoption pain ("linking existing projects to the template project or merge
conflicts when the same line of code is changed in both repositories").

**Verdict for our case:** both tools can do it. cruft has a first-class command
(`cruft link`) for recording the breadcrumb; copier does not (yet) but achieves
the same result through its supported `copier copy` onto an existing project,
which writes the breadcrumb for you. If the central template is (or will be) a
copier template, stay on copier — its 3-way update and `--conflict inline`
markers are exactly what the goal needs, and the only missing piece is the
one-time seeding step, which is a documented use case rather than a gap in
capability.

---

## Recommended procedure to seed the breadcrumb (per repo)

Prereq (once): ensure the central copier template contains a
`{{ _copier_conf.answers_file }}.jinja` file rendering
`{{ _copier_answers|to_nice_yaml -}}`. Without it, no breadcrumb is ever written.

Then, for each of the 5 drifted repos (each must be a clean git working tree):

1. `cd repo && git switch -c copier-adopt` (isolate the noise).
2. `copier copy --vcs-ref=<template-tag> <template-url> .`
   - Pin `--vcs-ref` to the template tag whose output most closely matches what
     these repos were `cp -r`'d from; that becomes the recorded `_commit` base.
   - When copier prompts on files that already exist, keep your drifted versions
     (or use `--skip` after confirming its semantics via `copier copy --help`).
     The goal of this step is only to obtain a correct `.copier-answers.yml`, not
     to overwrite your code.
3. Commit: the tree now has a real `.copier-answers.yml` breadcrumb + your files.
4. `copier update --conflict inline` (optionally `--vcs-ref=HEAD` to jump to the
   latest template). This is the first real 3-way merge:
   - purely-local files: untouched;
   - unmodified template files: updated cleanly;
   - files you edited that the template also changed: `<<<<<<<` conflict markers
     to resolve by hand before committing.
5. Resolve conflicts, run tests, commit, open the PR for review.

Uncertainties stated plainly:
- Exact `--skip` one-line wording not confirmed from the stable CLI reference in
  this session (page redirected); confirm with `copier copy --help`.
- The precise internal ordering of the update's regenerate/diff/merge is
  paraphrased from the docs' prose + the `_commit` requirement; the docs describe
  it narratively ("regenerates a fresh project… compares… re-applies the diff")
  rather than as a numbered algorithm, so the "git 3-way merge" characterization
  is inferred from the `--conflict` behavior being "similar to … `git merge`".
