#!/usr/bin/env bash
# Contract test for verification-check.sh (#1188): given a ticket number, run
# from any checkout of the repo, it exits 0 when the verification pass left
# dispositions-<n>.jsonl OR round 1 provably found nothing, and 1 when the pass
# is missing. Run: bash implement/verification-check.test.sh
set -uo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
check="$here/verification-check.sh"
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
repo="$tmp/skills-repo"
git init -q -b main "$repo"
git -C "$repo" config user.email t@example.com; git -C "$repo" config user.name t
echo x >"$repo/a"; git -C "$repo" add -A; git -C "$repo" commit -qm x
git -C "$repo" worktree add -q -b implement-5 "$tmp/wt" main
export HOME="$tmp/home"
rev="$HOME/.cache/agent-reviews/skills-repo"; mkdir -p "$rev"
fails=0
# t <name> <want-exit> <needle> [cwd]
t() {
  local out rc
  out=$(cd "${4:-$tmp/wt}" && bash "$check" 5 2>&1); rc=$?
  if [ "$rc" != "$2" ] || [[ "$out" != *"$3"* ]]; then
    echo "FAIL: $1 — want exit $2 + '$3', got $rc: $out"; fails=1
  else echo "PASS: $1"; fi
}
axes() { for a in standards spec correctness; do printf '%s' "$1" >"$rev/findings-$a-5.jsonl"; done; }
clear_rev() { rm -f "$rev"/*-5.jsonl; }

t "nothing in the cache: the pass never ran" 1 "verification pass"
axes '{"id": "S1"}
'
t "round-1 findings but no dispositions: pass skipped" 1 "verification pass"
printf '{"id": "S1", "outcome": "fixed", "sha": "abc"}\n' >"$rev/dispositions-5.jsonl"
t "a non-empty dispositions sidecar passes" 0 "dispositions-5.jsonl present"
: >"$rev/dispositions-5.jsonl"
t "empty dispositions beside real findings is refused" 1 "empty"
# A sweep PR's worker writes `<file> <id>` leftover lines itself (#1259); those
# are not the verification pass having run.
printf '{"id": "a/one.md P9", "outcome": "leftover", "file": "a/one.md", "title": "t", "severity": "hard", "text": "x"}\n' >"$rev/dispositions-5.jsonl"
t "a sidecar holding only worker-written sweep lines is not a verification pass" 1 "verification pass"
printf '{"id": "S1", "outcome": "fixed", "sha": "abc"}\n' >>"$rev/dispositions-5.jsonl"
t "a verification line beside the sweep lines passes" 0 "present"
: >"$rev/dispositions-5.jsonl"
clear_rev; axes ''
t "all three findings sidecars empty: round 1 found nothing, passes" 0 "round 1 found nothing"
: >"$rev/dispositions-5.jsonl"
t "an empty dispositions file beside an empty round passes" 0 "round 1 found nothing"
rm "$rev/dispositions-5.jsonl"
rm "$rev/findings-spec-5.jsonl"
t "one findings sidecar absent is not an empty round" 1 "verification pass"
printf '\n  \n' >"$rev/findings-spec-5.jsonl"
t "a blank-only findings sidecar counts as empty" 0 "round 1 found nothing"
printf '{"id": "P1"' >"$rev/findings-spec-5.jsonl"
t "a malformed findings line counts as a finding" 1 "verification pass"
printf '\377\376\n' >"$rev/findings-spec-5.jsonl"
t "an undecodable findings sidecar is not an empty round (#1336)" 1 "verification pass"
clear_rev; printf '{"id": "S1", "outcome": "fixed", "sha": "abc"}\n' >"$rev/dispositions-5.jsonl"
t "the cache keys on the shared .git from the primary checkout too" 0 "present" "$repo"
out=$(cd "$repo" && bash "$check" 2>&1); rc=$?
[ "$rc" = 2 ] && [[ "$out" == *usage* ]] && echo "PASS: no ticket number is a usage error" || { echo "FAIL: usage — got $rc: $out"; fails=1; }
[ "$fails" = 0 ] && echo "ALL PASS" || { echo FAILURES; exit 1; }
