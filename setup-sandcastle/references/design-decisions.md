# setup-sandcastle — design decisions

Why the skill is shaped the way it is. Not shipped to targets (the install renders
only `templates/.sandcastle/`). Maintenance reference for future edits.

## Origin

`templates/.sandcastle/` is a heavily-diverged fork of upstream's
`@ai-hero/sandcastle` `parallel-planner-with-review` scaffold (`main.mts` grew
226→968 lines; the single-merge model was replaced by a dependency **forest**
with topic-grouped per-component PRs). Seeded from `~/src/visual-teach/.sandcastle/`
at package version `0.10.0`. Upstream survives only as the **npm library**, never
as inherited scaffold.

## Locked decisions

1. **Targets get runtime-only.** The dev harness — `package.json`,
   `vitest.config.mjs`, and the `tests/` suite — is the canonical home you hack;
   copier renders the `.sandcastle/` subtree with `tests/` excluded (`copier.yml`
   `_exclude`). The `package.json`/`vitest.config.mjs` sit at `setup-sandcastle/`,
   ABOVE the `_subdirectory` (`setup-sandcastle/templates`), so they are outside the
   render boundary and never ship; the `tests/` live under `templates/.sandcastle/`
   and are dropped by `_exclude`. Nobody edits the `.mts` in a target, so the tests
   are dead weight there.
2. **Canonical home = this skill's `templates/.sandcastle/`.** No separate repo —
   that would re-create the drift it exists to avoid. You hack the `.mts` there, run
   `npm test` from `setup-sandcastle/` green, commit to the skills repo, and the next
   install carries it. One source of truth.
3. **Upstream drift = exact pin + `tsc` net + CHANGELOG, manual.** Pin
   `@ai-hero/sandcastle` to an exact version. On bump: read the CHANGELOG,
   `npm run typecheck` (the mechanical drift net — the vitest tests don't exercise
   the sandcastle API, only pure functions), fix `main.mts`, `npm test`, commit.
   No auto-folding of upstream's scaffold — the fork diverged too far to merge.
4. **The template is copier-managed; `copier update` merges edits into adopters.**
   copier was adopted (map #65, spec #70) precisely so template edits can later be
   merged into already-installed repos via `copier update` — the answers-file
   breadcrumb makes that update a reproducible diff between two tags. `sandcastle-propagate`
   drives it across every adopter (the `setup-sandcastle` skill itself only installs).
   Two placements are load-bearing:
   - **`copier.yml` lives at the repo root**, not in the template folder: copier
     records `_commit` in the breadcrumb only when sourced from the git root, and
     without `_commit` there is no version to diff from — a subfolder source renders
     correct files but silently breaks update.
   - **`_subdirectory` is `setup-sandcastle/templates`, and the subproject root the
     template installs into is the TARGET's git root** — `.sandcastle/` renders as a
     subtree beneath it, with the answers breadcrumb at the root (#93). The earlier
     `_subdirectory: .../templates/.sandcastle` + install-into-`./.sandcastle` layout
     put the breadcrumb in a subdir, so `copier update` run from the target root could
     not find it ("Template not found"), and copier's update diff — scoped to the
     `.sandcastle` subproject path — did not resolve. Moving the subproject root to the
     git root is what makes update a real 3-way merge. The dev-home harness
     (`package.json`, `vitest.config.mjs`, `tests/`) sits ABOVE this subdirectory in
     `setup-sandcastle/`, structurally outside the render, so it never ships to a target
     (decision 1's boundary, one level up from the old `_exclude`-only guard).
5. **Isolated Docker sandbox** — not `noSandbox()`. The use case is AFK/parallel
   autonomous agents making commits; running that unsandboxed on the host is the
   3am page. Isolation is load-bearing, not speculative.
6. **Dockerfile: debian-slim + uv, no Node, no system Python.** Since #134 this
   describes the `LANGUAGE=python` arm; the Node arm renders `node:22-bookworm`
   with no uv, no interpreter and no `just`. The sandbox image
   needs only the agent + git + gh + the target's uv toolchain (`main.mts` runs on
   the *host* via tsx; Claude CLI is a standalone binary). uv provides Python;
   `RUN uv python install ${PYTHON_VERSION}` **bakes the interpreter into an image
   layer** so no container re-fetches it. copier renders `ARG PYTHON_VERSION` from the
   target's `.python-version` (a copier answer) at install (step 1) — the Dockerfile
   ships as `Dockerfile.jinja`. Dropped: node, wrangler, Playwright/chromium.
7. **Hard-require setup-python-repo; drop proof entirely.** The pipeline leans on
   `just check` (implementer gate) + the target's PR CI (authoritative) + the
   reviewer's spec verdict. That IS the proof — a Python repo needs no visual
   proof-protocol. Dropped `proof-protocol.md`, `shot.mjs`, all VISUAL PROOF prompt
   sections, the `## Visual proof` PR section.
8. **`/tdd` not vendored — mounted.** `sandboxConfig` bind-mounts host
   `~/.claude/skills` read-only into every sandbox, so the in-sandbox agent has
   your live global skills (tdd + any other a prompt cites). Prompts reference
   `/tdd` as a normal global skill. Install prereq-checks `~/.claude/skills/tdd/`.
9. **Models:** planner = `claude-opus-4-8` (dependency reasoning); implementer +
   reviewer + pr + address = `claude-sonnet-5`. (Bumped from the stale
   `claude-sonnet-4-6`.) Haiku micro-opt for pr/address deferred.
10. **Bot identity kept as-is.** `sandbox-identity.mts` + `mint-gh-token.mjs` +
    `bot-setup.md` + the `GITHUB_APP_*` `.env` block. Wired into `main.mts`/`address.mts`,
    no-ops when env unset — removing it is net work. `.env.example` only dropped the
    Cloudflare/R2 block.
11. **Prompts stored pre-retargeted; install renders with copier.** All templatization
    (`npm run test`→`just check`, Python grep paths in the review standards-loader,
    uv Dockerfile, `.venv` copyToWorktree) is baked into `templates/` at build time.
    copier's install-time substitutions are the `LANGUAGE` answer and, on the Python
    arm, `PYTHON_VERSION` (into `Dockerfile.jinja`); prompts/config carry no jinja and
    copier copies them verbatim.
    `disable-model-invocation`, user-invoked.
12. **`.env` seed copies by path, never reads.** Secrets never enter the agent's
    context; the copy is verified gitignored before proceeding (SKILL.md step 3).
13. **Never re-render over an adopter — migrate by merging.** `copier copy
    --overwrite` is the obvious shortcut for a layout shift `copier update`
    cannot bridge, and it is wrong: it replaces every file the adopter edited
    with template text, silently, since copier prints `overwrite` for a
    clobbered local edit and a stale template file alike. This was documented
    advice once, on the grounds that `.sandcastle` is "generated and unedited" —
    it isn't. visual-teach carried a hand-edited `Dockerfile`, a TS sandbox
    bootstrap in place of `uv sync`, and its own prompt-drawer wording; the
    re-render took all of it, and none of those files had even changed between
    the two refs. Assume every adopter has edits until you have diffed and
    proved otherwise. Merge instead: base = the old ref's render, ours = the
    repo as it stands, theirs = the new ref's render. Preflight enforces this
    now — a second install over an existing render is refused.
14. **A line merge can be textually clean and semantically broken.** `git
    merge-file` works a region at a time, so on a badly diverged file it happily
    keeps *ours* where the new version added a definition and *theirs* where the
    new version calls it. Migrating visual-teach that way produced a `main.mts`
    calling `parseCheckVerdict` and `retiredByGate` that nothing defined, and a
    `reconcile.mts` missing the very buckets `main.mts` passed it. So split
    files by how far they drifted — a handful of deliberate local edits means
    take the new render whole and re-apply them by hand, each commented with why
    it diverges — and afterwards prove no local line vanished: extract the lines
    the repo had that the old render did not, confirm each survives, then
    classify what that flags as age or as customization. Only the second is a
    loss.
15. **Read the exit code, not the summary.** Run the adopter's whole CI, not
    just `tsc`, and check `$?` explicitly: a wrapper or a summarizing proxy can
    print something that reads like success over a failing command. The
    migration that prompted this rule was pushed on exactly that false green.
    The same failure shape is why `sandcastle-propagate` counts four outcome
    classes — a healthy fleet and a sweep that matched nothing must not print
    the same line.

## Gotchas found in the live rag-bootcamp install

- **`@standard-schema/spec` is an undeclared upstream dep.**
  `@ai-hero/sandcastle/dist/index.d.ts` imports `StandardSchemaV1` from
  `@standard-schema/spec`, but sandcastle's package.json only declares
  `@clack/prompts`. Without `@standard-schema/spec` installed, `Output.object<T>`
  collapses to `any` and `main.mts` throws implicit-any errors. The dev-home only
  typechecked clean *by accident* (vitest pulls the package transitively). Both the
  dev-home package.json and SKILL.md step 3 now declare it explicitly. Re-check on
  every sandcastle bump — if upstream starts declaring it, this can drop.
- **`@types/node` is required in the target.** `tsconfig` sets `types:["node"]`;
  a Python target has no Node types otherwise. In SKILL.md step 3 devDeps.

## Retargeting map (what changed from the visual-teach fork)

- `main.mts` — `copyToWorktree` node_modules→`.venv`; 3 model ids sonnet-4-6→sonnet-5.
- `sandbox-identity.mts` — `npm install`→`uv sync`; added the `~/.claude/skills` ro mount.
- `address.mts` — same `uv sync`/`.venv`/mount; model sonnet-4-6→sonnet-5.
- `implement/review/pr/address` prompts — `just check`; visual-proof sections removed;
  `/tdd` de-vendored; review standards-loader grep → `^src/` + `^\.sandcastle/`.
- `Dockerfile` — full rewrite (see decision 6).
- `.env.example` — dropped Cloudflare/R2. `.gitignore` — dropped `proof/`.
- `CONTEXT.md` / `CODING_STANDARDS.md` — de-visual-teach'd wording; dropped a stale
  eslint/ADR-0007 ref.
- `plan-prompt.md`, the pure `.mts` modules, `mint-gh-token.mjs`, ADRs, `tsconfig.json`,
  `bot-setup.md` — copied verbatim (language-agnostic).
- Dropped: `proof-protocol.md`, `shot.mjs`, `logo.*`, `logs/`, `proof/`,
  `review-attempts.json` (runtime state).
- `tests/review-standards-loading.test.mjs` — retargeted to Python paths; synthesizes
  its own root + Sandcastle `CODING_STANDARDS.md` markers in a temp dir (no tracked
  dev-home fixture).
