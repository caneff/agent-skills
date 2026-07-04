# Sandcastle coding standards

Standards for the **dev-only** orchestrator under `.sandcastle/` — the `.mts`
sources and prompt-drawer `.md` files. This tooling _builds_ the project; it has
no runtime relationship with the shipped code and never ships. The project has
its own standards in the root `CODING_STANDARDS.md`.

Deliberately short. Strict `tsc --noEmit` and vitest already enforce the
mechanical rules — restating them here would be noise. These are only the
project-specific rules those gates **can't** catch.

## Rules

1. **`main.mts` is the entrypoint, not a module — never import from it** (ADR-0002).
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
