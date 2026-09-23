# Guarding `sessions::in_tree` against an empty root

`in_tree(path, "")` in the lane's sessions module returns true for every absolute path, because it compares `"{path}/"` with the prefix `"/"`. The lane does not add a guard for this.

## Why this is out of scope

No caller can pass an empty root. The one empty-string fallback that reaches it (a workspace path that fails UTF-8 conversion) needs a path that could never have been created by `implement-dispatch`, which builds every workspace path itself. A guard would be code that no test can reach through a real caller, and it would be dead weight at the one place the lane's liveness checks all pass through.

If a new caller ever takes a root from user input or a file, that caller should validate it at its own boundary.

## Prior requests

- #828 — "sessions::in_tree(cwd, \"\") matches every absolute path"
