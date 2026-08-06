# setup-sandcastle — design decisions

Why the skill is shaped the way it is. Not shipped to targets (the install copies
only `templates/.sandcastle/`). Maintenance reference for future edits.

## Origin

`templates/.sandcastle/` is a heavily-diverged fork of upstream's
`@ai-hero/sandcastle` `parallel-planner-with-review` scaffold (`main.mts` grew
226→968 lines; the single-merge model was replaced by a dependency **forest**
with topic-grouped per-component PRs). Seeded from `~/src/visual-teach/.sandcastle/`
at package version `0.10.0`. Upstream survives only as the **npm library**, never
as inherited scaffold.

## Locked decisions

1. **Targets get runtime-only.** The 10 vitest tests + vitest stay in this skill's
   `templates/` (the canonical home you hack); install copies `.sandcastle/` minus
   `tests/`. Nobody edits the `.mts` in a target, so the tests are dead weight there.
2. **Canonical home = this skill's `templates/`.** No separate repo — that would
   re-create the drift it exists to avoid. You hack here with `npm test` green,
   commit to the skills repo, and the next install carries it. One source of truth.
3. **Upstream drift = exact pin + `tsc` net + CHANGELOG, manual.** Pin
   `@ai-hero/sandcastle` to an exact version. On bump: read the CHANGELOG,
   `npm run typecheck` (the mechanical drift net — the vitest tests don't exercise
   the sandcastle API, only pure functions), fix `main.mts`, `npm test`, commit.
   No auto-folding of upstream's scaffold — the fork diverged too far to merge.
4. **Install-only v1.** No "update an already-installed `.sandcastle/`" path — that's
   a merge against possibly-hacked target code; build it when N targets actually drift.
5. **Isolated Docker sandbox** — not `noSandbox()`. The use case is AFK/parallel
   autonomous agents making commits; running that unsandboxed on the host is the
   3am page. Isolation is load-bearing, not speculative.
6. **Dockerfile: debian-slim + uv, no Node, no system Python.** The sandbox image
   needs only the agent + git + gh + the target's uv toolchain (`main.mts` runs on
   the *host* via tsx; Claude CLI is a standalone binary). uv provides Python;
   `RUN uv python install ${PYTHON_VERSION}` **bakes the interpreter into an image
   layer** so no container re-fetches it. `ARG PYTHON_VERSION` is set from the
   target's `.python-version` at install (step 2). Dropped: node, wrangler,
   Playwright/chromium.
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
11. **Prompts stored pre-retargeted; install = dumb copy.** All templatization
    (`npm run test`→`just check`, Python grep paths in the review standards-loader,
    uv Dockerfile, `.venv` copyToWorktree) is baked into `templates/` at build time.
    Install never seds a prompt. `disable-model-invocation`, user-invoked.
12. **`.env` seed copies by path, never reads.** Secrets never enter the agent's
    context; the copy is verified gitignored before proceeding (SKILL.md step 4).

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
