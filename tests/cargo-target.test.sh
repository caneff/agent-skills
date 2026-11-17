#!/usr/bin/env bash
# Guards #1950: every suite that compiles the lane crate shares one persistent
# cargo target dir, so dependencies compile once and not on every all.sh run.
# Seams: tests/cargo-target.sh (what it exports) and tests/all.sh (that a suite
# it runs sees that export).
set -uo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES CARGO_TARGET_DIR
root=$(git rev-parse --show-toplevel) || exit 1
shadow=$(mktemp -d) || { echo "FAIL: mktemp -d"; exit 1; }
trap 'rm -rf "$shadow"' EXIT
fail=0
home="$shadow/home"; mkdir -p "$home"

# 1. The default lives under the cache dir, outside every checkout.
got=$(env -u XDG_CACHE_HOME HOME="$home" bash -c '. "$1"; printf %s "$CARGO_TARGET_DIR"' _ "$root/tests/cargo-target.sh")
[ "$got" = "$home/.cache/agent-skills/cargo-target" ] || { echo "FAIL: default target dir was '$got'"; fail=1; }

# 2. A caller's own CARGO_TARGET_DIR wins (a mutation worktree sets its own).
got=$(HOME="$home" CARGO_TARGET_DIR="$shadow/mine" bash -c '. "$1"; printf %s "$CARGO_TARGET_DIR"' _ "$root/tests/cargo-target.sh")
[ "$got" = "$shadow/mine" ] || { echo "FAIL: caller's CARGO_TARGET_DIR was overridden: '$got'"; fail=1; }

# 3. all.sh hands a suite that value.
repo="$shadow/repo"
mkdir -p "$repo/tests" "$repo/s"
cp "$root/tests/all.sh" "$root/tests/suite-edges.py" "$root/tests/cargo-target.sh" "$repo/tests/"
printf 'printf "%%s" "${CARGO_TARGET_DIR:-unset}" >"%s/seen"\n' "$shadow" >"$repo/s/one.test.sh"
git -C "$repo" init -q
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/fixture-identity.sh"
fixture_identity "$repo" "$shadow" || exit 2
git -C "$repo" add -A; git -C "$repo" commit -qm base
(cd "$repo" && env -u XDG_CACHE_HOME HOME="$home" bash tests/all.sh) >"$shadow/run.out" 2>&1 || { echo "FAIL: fixture run failed"; cat "$shadow/run.out"; fail=1; }
seen=$(cat "$shadow/seen" 2>/dev/null)
[ "$seen" = "$home/.cache/agent-skills/cargo-target" ] || { echo "FAIL: suite saw CARGO_TARGET_DIR='$seen'"; fail=1; }

[ "$fail" = 0 ] || exit 1
echo ok
