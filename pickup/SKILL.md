---
name: pickup
description: Pick up work from the most recent handoff document left in the OS temp dir. Use after a /clear or in a fresh session to resume where a /handoff left off.
argument-hint: "Optional: a word to match if several handoffs exist"
disable-model-invocation: true
---

Resume work from the most recent handoff document.

1. Find it — newest handoff doc in the temp dir:

   ```bash
   ls -t /tmp/*handoff*.md 2>/dev/null | head -1
   ```

   If the user passed an argument, treat it as a filename filter: `ls -t /tmp/*<arg>*handoff*.md /tmp/*handoff*<arg>*.md 2>/dev/null | head -1`.

2. If nothing matches, say so and stop — do not grab an unrelated file from `/tmp`.

3. State which file you found and its modification time so the user can confirm it's the right one, then read it.

4. Follow it: continue the work it describes, invoking any skills its "suggested skills" section names. Reference the artifacts (specs, diffs, issues) it points at rather than re-deriving them.
