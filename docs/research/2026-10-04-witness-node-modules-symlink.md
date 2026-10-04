# Does a symlinked `node_modules` work in a witness worktree?

Date: 2026-10-04. Ticket: #1219, which left the question unverified.

`multi-axis-code-review/witness-check.sh` links the reviewed tree's top-level
`node_modules` into each throwaway witness worktree that has none. Some tools
resolve modules through the realpath or refuse symlinks, so the link was
probed on a real repo before shipping.

## Probe

Repo: `~/src/research-queue` (`"test": "vitest run"`), at `96fbd44`.
`witness-check.sh --worktree ~/src/research-queue --no-ledger -- probe`, with a
`mutate` that made no edit, wrote the marker, ran `npx vitest run` and then
exited 1 so its output was shown.

Result: inside the witness, `node_modules -> /home/caneff/src/research-queue/node_modules`;
vitest reported `Test Files 1 passed (1)`, `Tests 36 passed (36)` and exited 0.
After the run, `git worktree list` in that repo showed only the main checkout.

## What this does not cover

One repo and one runner. `twitch-rules-scroller` (`node --test`),
`visual-teach` and `ai-coding-crash-course` (vitest) and
`sudokumaker-custom-constraints` (`just test`) were not run. A tool that
refuses a symlinked `node_modules` would show up as a red whose message names
module resolution, which the reviewer is told to read for (defect class 3).
