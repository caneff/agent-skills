#!/usr/bin/env bash
# Installs whichever of the lane's named binaries (implement-dispatch, resolve-controller,
# merge-cleanup) the crate at flow/lane currently defines, into ~/.local/bin.
# Never installs the test-only fake (lane-fake) — it is never named here.
#
# Shared by install.sh and merge-cleanup's rebuild step, so a failed build is
# reported the same way from both: this script's stderr carries the
# compiler's error, and cargo install only replaces a binary once its build
# succeeds, so a failure here always leaves the previously installed binary
# in place.
#
# #834 (Codex re-run): records the sha it installed from at
# ~/.local/state/lane/build-sha on every successful install, run by hand or
# by merge-cleanup's own rebuild step — so merge-cleanup always has a trusted
# record to compare the tip against, even after a plain `bash
# flow/lane-install.sh` it never saw.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
crate="$here/lane"

names=()
for n in implement-dispatch merge-cleanup resolve-controller controller-restore; do
  grep -qx "name = \"$n\"" "$crate/Cargo.toml" && names+=(--bin "$n")
done
[ "${#names[@]}" -gt 0 ] || { echo "flow/lane-install.sh: no lane binaries found in $crate/Cargo.toml" >&2; exit 1; }

cargo install --path "$crate" --root "$HOME/.local" --force "${names[@]}"

# The record is bookkeeping, not part of the install: the binaries are already
# in place by here, so nothing below may fail the whole install (#883) — not an
# unresolvable HEAD (a checkout with no commits), and not an unwritable
# ~/.local/state. `git rev-parse HEAD` also echoes the literal "HEAD" on stdout
# when it fails, so the sha is taken into a variable and the directory made only
# once git succeeded — a redirect straight to the file records that "HEAD" as
# the baseline. With no record merge-cleanup rebuilds rather than trusting a
# stale one, so dropping it is the safe miss.
state_dir="$HOME/.local/state/lane"
record_build_sha() {
  local build_sha
  build_sha=$(git -C "$here/.." rev-parse HEAD 2>/dev/null) || return 1
  mkdir -p "$state_dir" || return 1
  printf '%s\n' "$build_sha" > "$state_dir/build-sha"
}
if ! record_build_sha; then
  rm -f "$state_dir/build-sha" 2>/dev/null || :
  echo "flow/lane-install.sh: no build sha recorded; merge-cleanup will rebuild" >&2
fi
