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
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
crate="$here/lane"

names=()
for n in implement-dispatch merge-cleanup; do
  grep -qx "name = \"$n\"" "$crate/Cargo.toml" && names+=(--bin "$n")
done
[ "${#names[@]}" -gt 0 ] || { echo "flow/lane-install.sh: no lane binaries found in $crate/Cargo.toml" >&2; exit 1; }

cargo install --path "$crate" --root "$HOME/.local" --force "${names[@]}"
