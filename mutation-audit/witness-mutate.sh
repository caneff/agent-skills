# The `mutate` that witness.sh hands to multi-axis-code-review/witness-check.sh:
# apply one patch in the witness worktree, then run one covering test command.
# Both arrive through the environment (WITNESS_PATCH, an absolute path, and
# WITNESS_TEST, a shell command), so neither is ever pasted into code.
mutate() { # <id> <witness worktree> <marker>
  cd "$2" || exit 1
  # A patch that does not apply never reached the suite: no marker, so the
  # check reports it `unknown`, never red.
  git apply "$WITNESS_PATCH" || { echo "single-diff witness: the patch does not apply at HEAD" >&2; exit 1; }
  : >"$3"
  bash -c "$WITNESS_TEST"
}
