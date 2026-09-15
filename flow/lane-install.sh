#!/usr/bin/env bash
# Installs whichever of the lane's two named binaries (implement-dispatch,
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
for n in implement-dispatch merge-cleanup; do
  grep -qx "name = \"$n\"" "$crate/Cargo.toml" && names+=(--bin "$n")
done
[ "${#names[@]}" -gt 0 ] || { echo "flow/lane-install.sh: no lane binaries found in $crate/Cargo.toml" >&2; exit 1; }

cargo install --path "$crate" --root "$HOME/.local" --force "${names[@]}"

state_dir="$HOME/.local/state/lane"
mkdir -p "$state_dir"
git -C "$here/.." rev-parse HEAD > "$state_dir/build-sha"
