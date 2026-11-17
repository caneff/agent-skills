#!/usr/bin/env bash
# Runs a command that compiles the lane crate against one persistent cargo
# target dir, so the registry dependencies compile once and not on every run
# (#1950).
#   usage: tests/lane-cargo.sh <Cargo.toml of the crate under test> -- <command...>
#
# One dir is shared by every checkout of this repo, and cargo cannot tell two
# checkouts' copies of the lane crate apart: a copy older than another's build
# is judged fresh and never compiled, and a build by one checkout replaces the
# binary another's running tests spawn (reproduced with cargo 1.97, review of
# #1950). So the shared dir is used under an exclusive lock held for the whole
# command, tests included, and the crate's own artifacts are cleaned first;
# only the dependencies are reused.
#
# The lock wait is bounded: after LANE_CARGO_WAIT seconds (default 240, inside
# the 590 s worker cap with room for the run itself) the command builds into a
# private dir, cold, and removes it after, rather than queue behind other
# checkouts. A waiting process is blocked, not computing, so the wait costs no
# CPU and cannot push a suite over its `cpu_budget`.
#
# A caller's own CARGO_TARGET_DIR wins and skips the lock and the clean: a
# mutation worktree sets its own (implement/SKILL.md § Build). The wrapper
# exports the dir it picked, so a nested call passes straight through.
#
# The shared dir lives under the user's cache, outside every checkout: a test
# that writes it is the same deliberate exception to CODING_STANDARDS rule 2 as
# CARGO_HOME, a build cache the suite is meant to keep warm.
set -euo pipefail
manifest=${1:?usage: lane-cargo.sh <Cargo.toml> -- <command...>}
[ "${2:-}" = -- ] || { echo "usage: lane-cargo.sh <Cargo.toml> -- <command...>" >&2; exit 2; }
shift 2
[ "$#" -gt 0 ] || { echo "lane-cargo.sh: no command given" >&2; exit 2; }

if [ -n "${CARGO_TARGET_DIR:-}" ]; then exec "$@"; fi

cache=${XDG_CACHE_HOME:-$HOME/.cache}/agent-skills
mkdir -p "$cache"
exec 9>"$cache/cargo-target.lock"
if flock -w "${LANE_CARGO_WAIT:-240}" 9; then
  export CARGO_TARGET_DIR=$cache/cargo-target
  # The crate's own artifacts only; the dependencies stay. Both profiles: the
  # tests build debug, `cargo install` builds release.
  # Assigned first so a failing cargo or jq stops the run: inside `for ... in $(...)`
  # it would leave an empty loop and skip the clean, which reads as a clean tree.
  pkgs=$(cargo metadata --no-deps --format-version 1 --manifest-path "$manifest" | jq -r '.packages[].name')
  [ -n "$pkgs" ] || { echo "lane-cargo.sh: no package found in $manifest" >&2; exit 1; }
  for pkg in $pkgs; do
    cargo clean -q --manifest-path "$manifest" -p "$pkg"
    cargo clean -q --manifest-path "$manifest" -p "$pkg" --release
  done
else
  echo "lane-cargo.sh: shared target dir busy for ${LANE_CARGO_WAIT:-240}s; building in a private dir" >&2
  CARGO_TARGET_DIR=$(mktemp -d "$cache/cargo-target-private.XXXXXX")
  export CARGO_TARGET_DIR
  trap 'rm -rf "$CARGO_TARGET_DIR"' EXIT
fi
"$@"
