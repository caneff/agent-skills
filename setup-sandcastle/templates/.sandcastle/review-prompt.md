# TASK

Review the code changes on branch `{{BRANCH}}` and improve code clarity, consistency, and maintainability while preserving exact functionality.

# CONTEXT

## Branch diff

!`git --no-pager diff {{REVIEW_BASE}}...{{BRANCH}}`

## Commits on this branch

!`git --no-pager log {{REVIEW_BASE}}..{{BRANCH}} --oneline`

## Originating issue (the spec)

The change must satisfy this issue — its acceptance criteria are the contract.
You are given ONLY the issue, the commits, and the diff: form your own judgment,
independent of however the change was built.

<issue-spec>
{{ISSUE_SPEC}}
</issue-spec>

# REVIEW PROCESS

1. **Understand the change**: Read the diff and commits above to understand the intent.

2. **Analyze for improvements**: Look for opportunities to:
   - Reduce unnecessary complexity and nesting
   - Eliminate redundant code and abstractions
   - Improve readability through clear variable and function names
   - Consolidate related logic
   - Remove unnecessary comments that describe obvious code
   - Avoid nested ternary operators - prefer switch statements or if/else chains
   - Choose clarity over brevity - explicit code is often better than overly compact code

3. **Check correctness**:
   - Does the implementation match the intent? Are edge cases handled?
   - Are new/changed behaviours covered by tests?
   - Test quality (not just presence): do new tests verify observable behavior
     through the public interface, or just source shape (a file exists, a string
     is present, a signature matches)? Shape-assertions that would pass when
     behavior breaks and fail on a pure refactor are the "crap tests" `/tdd`
     warns against — flag them, and flag a single test file added wholesale
     (horizontal slicing) rather than grown slice-by-slice. (Note: a
     no-new-behavior issue — deletion / refactor / docs / config — legitimately
     has only end-state assertions or no new tests; that is correct, not a crap
     test. The fault is manufacturing shape-tests to fake a TDD rhythm where
     real behavior existed to drive out.)
   - Are there unsafe casts, `any` types, or unchecked assumptions?
   - Does the change introduce injection vulnerabilities, credential leaks, or other security issues?

4. **Maintain balance**: Avoid over-simplification that could:
   - Reduce code clarity or maintainability
   - Create overly clever solutions that are hard to understand
   - Combine too many concerns into single functions or components
   - Remove helpful abstractions that improve code organization
   - Make the code harder to debug or extend

5. **Preserve functionality**: Never change what the code does - only how it does it. All original features, outputs, and behaviors must remain intact.

6. **Apply project standards** (these override the generic guidance above on any conflict). Loaded conditionally on what this branch's diff touches — only the standards relevant to the change appear below (a docs-only diff loads neither):

   - Project standards (when the diff touches application code under `src/`, tests included — they're interleaved there):

     !`git diff --name-only {{REVIEW_BASE}}...{{BRANCH}} | grep -qE '^src/' && cat CODING_STANDARDS.md || true`

   - Sandcastle standards (when the diff touches the `.sandcastle/` orchestrator itself):

     !`git diff --name-only {{REVIEW_BASE}}...{{BRANCH}} | grep -qE '^\.sandcastle/' && cat .sandcastle/CODING_STANDARDS.md || true`

# GATES

Lint, type checks, and tests are enforced mechanically by CI on the PR
(`.github/workflows/`), so they are not your job to babysit. You still run
`just check` after any refactor _you_ commit (see EXECUTION), but the
authoritative green gate is CI.

# EXECUTION

If you find improvements to make:

1. Make the changes directly on this branch
2. Run `just check` to ensure nothing is broken
3. Commit describing the refinements

If the code is already clean and well-structured, make no refactor commit — but
the GATES above still run regardless.

# SPEC CONFORMANCE (required — emit the verdict last)

Independently decide whether the diff actually satisfies the originating issue
above. Check each acceptance criterion and classify any failure as one of:

- **missing / partial** — an AC not implemented, or only half done
- **scope creep** — behavior in the diff the issue never asked for
- **implemented-but-wrong** — an AC the code appears to address but does so incorrectly
- **crap tests** — new tests that assert source shape instead of observable
  behavior (would pass when behavior breaks, fail on a pure refactor), or a
  test file added wholesale rather than grown slice-by-slice. An AC backed only
  by shape-assertions is NOT satisfied — the behavior is unverified. Does not
  apply to no-new-behavior issues (see the test-quality note above).

Quote the specific acceptance-criterion line for each finding. This is SEPARATE
from code quality — clean, well-refactored code that does not meet the spec still
FAILS. A FAIL on any category above — including **crap tests** — is a spec FAIL.

Do NOT try to implement missing requirements yourself; that is a re-implement,
which the orchestrator routes back to a fresh implementer. Judge and report only.

Emit your verdict as the FINAL line of your output, exactly one of (the prefix
must match verbatim — the host greps for it):

- `SANDCASTLE_SPEC: PASS`
- `SANDCASTLE_SPEC: FAIL — <one-line reason>`

Then, on the next line, output <promise>COMPLETE</promise>.
