# RTK - Rust Token Killer

Token-optimized CLI proxy. A PreToolUse hook rewrites Bash commands to
`rtk <cmd>` automatically — never type `rtk` yourself for ordinary commands.

Meta commands the hook does not rewrite, so call them directly:
`rtk gain` (savings), `rtk gain --history`, `rtk discover`,
`rtk proxy <cmd>` (bypass filtering for debugging).
