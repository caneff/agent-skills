#!/usr/bin/env bash
# Guards the discovery rules in tests/all.sh: one fixture per rule in a shadow
# repo, each found (or, for the plugin rule, withheld) by the rule alone, never
# by a name the runner special-cases. Asserts on `all.sh --list` rather than a
# full run — the list IS the seam (#609). Reads no real-tree state: a renamed or
# retired real suite cannot fail it.
set -uo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
root=$(git rev-parse --show-toplevel) || exit 1
shadow=$(mktemp -d) || { echo "FAIL: mktemp -d"; exit 1; }
trap 'rm -rf "$shadow"' EXIT

repo="$shadow/repo"
mkdir -p "$repo/tests" "$repo/s" "$repo/p" "$repo/cargo" "$repo/flow/mods/m" "$repo/skillplug" "$repo/testedplug"
cp "$root/tests/all.sh" "$root/tests/suite-edges.py" "$repo/tests/"
echo 'exit 0' >"$repo/s/one.test.sh"
echo 'def test_x(): pass' >"$repo/p/two_test.py"
printf '[package]\nname = "x"\n' >"$repo/cargo/Cargo.toml"
for plug in flow/mods/m skillplug testedplug; do
  mkdir -p "$repo/$plug/.claude-plugin"; echo '{}' >"$repo/$plug/.claude-plugin/plugin.json"
done
echo 'test' >"$repo/testedplug/x.test.ts"
git -C "$repo" init -q
git -C "$repo" config user.email owner@example.org
git -C "$repo" config user.name owner
git -C "$repo" add -A
git -C "$repo" commit -qm base

listed=$(cd "$repo" && bash tests/all.sh --list) || { echo "FAIL: all.sh --list exited non-zero"; exit 1; }

fail=0
for label in s/one.test.sh p/two_test.py cargo/Cargo.toml flow/mods/m testedplug; do
  grep -qxF "$label" <<<"$listed" || { echo "FAIL: $label not discovered"; fail=1; }
done

# A plugin outside flow/mods runs only once it holds a test: a skill plugin with
# a plugin.json and no test.ts is not a failing suite. The control above
# (testedplug, the same shape plus a test.ts) shows the rule is exercised.
! grep -qxF "skillplug" <<<"$listed" || { echo "FAIL: skillplug (no test.ts) was discovered"; fail=1; }

(cd "$repo" && bash tests/all.sh --bogus) >/dev/null 2>&1; [ $? = 2 ] || { echo "FAIL: unknown flag did not exit 2"; fail=1; }

[ "$fail" = 0 ] || { echo "--- discovered ---"; printf '%s\n' "$listed"; exit 1; }
echo "ok"
