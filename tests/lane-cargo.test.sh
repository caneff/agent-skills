#!/usr/bin/env bash
# Guards #1950: suites that compile the lane crate share one persistent cargo
# target dir through tests/lane-cargo.sh, without one checkout's lane build
# ever serving another's run. Seams: lane-cargo.sh (what a command sees) and
# all.sh (that a discovered cargo suite goes through it).
set -uo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES CARGO_TARGET_DIR LANE_CARGO_WAIT
root=$(git rev-parse --show-toplevel) || exit 1
w="$root/tests/lane-cargo.sh"
shadow=$(mktemp -d) || { echo "FAIL: mktemp -d"; exit 1; }
trap 'rm -rf "$shadow"' EXIT
fail=0
no() { echo "FAIL: $*"; fail=1; }
xdg="$shadow/xdg"; shared="$xdg/agent-skills/cargo-target"
export XDG_CACHE_HOME="$xdg" CARGO_HOME="${CARGO_HOME:-$HOME/.cargo}" RUSTUP_HOME="${RUSTUP_HOME:-$HOME/.rustup}"

mkcrate() { # <dir> <printed word>: a crate named lane that prints the word
  mkdir -p "$1/src"
  printf '[package]\nname = "lane"\nversion = "0.1.0"\nedition = "2021"\n' >"$1/Cargo.toml"
  printf 'fn main() { println!("%s"); }\n' "$2" >"$1/src/main.rs"
}

# 1. The default is the shared dir under the cache dir, and XDG_CACHE_HOME moves it.
mkcrate "$shadow/a" A
got=$(bash "$w" "$shadow/a/Cargo.toml" -- bash -c 'printf %s "$CARGO_TARGET_DIR"')
[ "$got" = "$shared" ] || no "default target dir was '$got', wanted '$shared'"

# 2. A caller's own CARGO_TARGET_DIR wins, with no lock taken (a mutation worktree's).
got=$(CARGO_TARGET_DIR="$shadow/mine" bash "$w" "$shadow/a/Cargo.toml" -- bash -c 'printf %s "$CARGO_TARGET_DIR"')
[ "$got" = "$shadow/mine" ] || no "caller's CARGO_TARGET_DIR overridden: '$got'"

# 3. One checkout's build never serves another's run (the stale-Fresh half of
# C1). B's source is older than A's build and cargo would call it fresh.
mkcrate "$shadow/b" B
touch -d '2001-01-01' "$shadow/b/src/main.rs" "$shadow/b/Cargo.toml"
a_out=$(bash "$w" "$shadow/a/Cargo.toml" -- cargo run -q --manifest-path "$shadow/a/Cargo.toml" 2>&1)
b_out=$(bash "$w" "$shadow/b/Cargo.toml" -- cargo run -q --manifest-path "$shadow/b/Cargo.toml" 2>&1)
[ "$a_out" = A ] || no "checkout A ran '$a_out'"
[ "$b_out" = B ] || no "checkout B ran '$b_out' (another checkout's build)"

# 4. A busy shared dir is waited on for LANE_CARGO_WAIT seconds, then the
# command runs in a private dir that is removed after; its status is kept.
mkdir -p "$xdg/agent-skills"
( exec 8>"$xdg/agent-skills/cargo-target.lock"; flock 8; sleep 20 ) & holder=$!
sleep 0.5
got=$(LANE_CARGO_WAIT=1 bash "$w" "$shadow/a/Cargo.toml" -- bash -c 'printf %s "$CARGO_TARGET_DIR"; exit 7' 2>/dev/null); rc=$?
kill "$holder" 2>/dev/null; wait "$holder" 2>/dev/null
case "$got" in "$xdg/agent-skills/cargo-target-private."*) ;; *) no "busy lock did not fall back to a private dir: '$got'" ;; esac
[ "$rc" = 7 ] || no "the command's exit status was lost (rc=$rc)"
[ ! -e "$got" ] || no "the private dir $got was left behind"

# 4b. A manifest that yields no package stops the run before the command runs
# (an empty clean would read as a clean tree).
mkdir -p "$shadow/bad"; printf 'not toml' >"$shadow/bad/Cargo.toml"
out=$(bash "$w" "$shadow/bad/Cargo.toml" -- bash -c 'echo RAN' 2>/dev/null); rc=$?
{ [ "$rc" != 0 ] && [ "$out" != RAN ]; } || no "a manifest cargo cannot read still ran the command (rc=$rc)"

# 5. A command's exit status passes through the locked path too.
bash "$w" "$shadow/a/Cargo.toml" -- bash -c 'exit 3'; [ $? = 3 ] || no "locked path lost the exit status"

# 6. all.sh sends a discovered Cargo.toml suite through the wrapper.
repo="$shadow/repo"; mkdir -p "$repo/tests" "$repo/c/src"
cp "$root/tests/all.sh" "$root/tests/suite-edges.py" "$w" "$repo/tests/"
printf '[package]\nname = "c"\nversion = "0.1.0"\nedition = "2021"\n' >"$repo/c/Cargo.toml"
printf '#[test]\nfn t() { assert!(std::env::var("CARGO_TARGET_DIR").unwrap().ends_with("agent-skills/cargo-target")); }\n' >"$repo/c/src/lib.rs"
git -C "$repo" init -q
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/fixture-identity.sh"
fixture_identity "$repo" "$shadow" || exit 2
git -C "$repo" add -A; git -C "$repo" commit -qm base
(cd "$repo" && bash tests/all.sh) >"$shadow/run.out" 2>&1 || { no "fixture cargo suite failed"; cat "$shadow/run.out"; }

# 7. The install suite re-runs itself inside the wrapper; running it is
# minutes of cargo, so this reads the call site rather than executing it.
grep -q 'exec bash "\$root/tests/lane-cargo.sh"' "$root/flow/install.test.sh" || no "flow/install.test.sh does not go through tests/lane-cargo.sh"

[ "$fail" = 0 ] || exit 1
echo ok
