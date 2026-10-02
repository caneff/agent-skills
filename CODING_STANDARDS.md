# Coding standards

The rules a change must satisfy that no gate checks. A reviewer loads this
file to judge a diff; `bash tests/all.sh` enforces the mechanical parts.
Each rule here was drawn from review corrections the repo accepted; the
evidence is in `docs/research/2026-10-02-coding-standards-evidence.md`.

1. **Make every error, refusal and report message state the cause the code
   actually found, and name only actions that exist.** The message is all
   the reader of a failed run sees. One that names a cause the code never
   checked, or advertises a flag nothing accepts, sends the next agent to
   fix the wrong thing, and no test fails because the text is not asserted.

2. **A test sets every path and environment variable it depends on itself,
   inside a temp directory; it never reads or writes the machine's live
   state.** A test that inherits the real HOME or an exported variable
   passes or fails by what the shell happens to hold, and one that writes
   there changes the machine on every gate run.

3. **Wrap a comment, docstring or prose line you add or edit to the width
   of the paragraph around it.** Most files wrap near 78 columns and no
   tool checks it, so one 120-column line in a wrapped block is what the
   next reviewer flags. Contested: several SKILL.md files still hold long
   lines, and a reflow of lines you did not otherwise touch is cosmetic —
   hold new and edited lines to the width, and leave the rest alone.

4. **State a rule in one place and point to it from everywhere else.** A
   rule restated in full drifts: one copy takes the next edit and the
   others keep teaching the old rule. Contested: a copy stays where the
   reader cannot follow a pointer — a brief pasted into another agent, or
   twin skills whose tests pin each clause — and there the copies stay
   word-for-word identical.
