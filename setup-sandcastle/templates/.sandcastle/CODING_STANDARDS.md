# Sandcastle coding standards

Standards for the **dev-only** orchestrator under `.sandcastle/` — the `.mts`
sources and prompt-drawer `.md` files. This tooling _builds_ the project; it has
no runtime relationship with the shipped code and never ships. The project has
its own standards in the root `CODING_STANDARDS.md`.

Deliberately short. Strict `tsc --noEmit` and vitest already enforce the
mechanical rules — restating them here would be noise. These are only the
project-specific rules those gates **can't** catch.

## Rules

1. **`main.mts` is the entrypoint, not a module — never import from it.**
   `tsc` will happily let you `import { … } from "./main.mts"`; the design says
   don't. Shared logic belongs in its own module that both `main.mts` and the tests
   import.

2. **Parse external input with zod at the boundary.** `gh` API responses and
   on-disk JSON state (e.g. `review-attempts.json`) are untrusted — validate them
   with a zod schema where they enter the program. No trust-casts (`as`) on data
   that came from outside the process.

3. **Host-coupled sentinel strings are a contract — don't reword them.** The host
   greps reviewer/agent output verbatim: the `SANDCASTLE_SPEC: PASS` /
   `SANDCASTLE_SPEC: FAIL — …` prefix and the `<promise>COMPLETE</promise>` line
   (see `parseSpecVerdict` in `main.mts`). Likewise, don't reuse reserved sandcastle
   promptArgs such as `TARGET_BRANCH`. Changing a string breaks the orchestrator
   silently — no mechanical gate catches it.

4. **Prompt `.md` expansion is live, not literal.** Inside the prompt-drawer files,
   `{{VAR}}` (promptArgs templating), `` !`bash` `` (command execution), and
   `@path` (file include) are expanded by the Claude Code agent at run time.
   Preserve them when editing a prompt — they are not display text.

5. **Diverging from the template needs a `sandcastle:local` marker.** Everything
   in this repo's `.sandcastle/` is rendered from the Sandcastle template. If you
   edit a rendered file, or add a new file here, say why in a comment — in that
   file's own comment syntax — carrying the token `sandcastle:local` and a reason:

   ```
   // sandcastle:local — Playwright needs its Chromium binary in the agent's cache
   ```

   The reason must name a fact about **this repo**. "This repo is TypeScript" does
   not qualify: that is true of every Node adopter, so the change belongs in the
   template, not here. A branch that edits or adds a file in this repo's
   `.sandcastle/` without a marker fails this axis. Unmarked divergence drops the repo behind
   template improvements silently, and no mechanical gate catches it.

6. **How these files are formatted belongs to the template — exclude
   `.sandcastle/` from this repo's formatters and linters.** A formatter that
   reflows a rendered file is doing what rule 5 forbids, by tool rather than by
   hand: divergence with no reason attached. It costs twice — the divergence
   report flags every reflowed file as unmarked drift, and the next template
   update lands as a merge conflict on each one. Nothing checks this at install
   time; a repo's formatter config is its own, so the report is the enforcement.
