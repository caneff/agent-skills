#!/usr/bin/env bash
# Contract test for pre-report-gate.sh: run inside a throwaway repo, assert
# exit 0 + pass line on a clean tree with an ancestor sha, non-zero + a
# one-line reason on a dirty tree or a sha off the branch.
# Run: bash implement/pre-report-gate.test.sh
set -uo pipefail
# A caller's leaked GIT_DIR/GIT_WORK_TREE/GIT_INDEX_FILE/GIT_COMMON_DIR/
# GIT_OBJECT_DIRECTORY/GIT_ALTERNATE_OBJECT_DIRECTORIES would point the repo
# init below at that caller's repo instead of $tmp (#620) — and this test must
# never touch the real skills checkout.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
gate="$here/pre-report-gate.sh"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# A throwaway repo: two commits on main, one commit on an abandoned branch.
repo="$tmp/repo"
git init -q -b main "$repo"
git -C "$repo" config user.email t@example.com
git -C "$repo" config user.name t
echo one > "$repo/a.txt"; git -C "$repo" add -A; git -C "$repo" commit -qm one
first=$(git -C "$repo" rev-parse HEAD)
echo two >> "$repo/a.txt"; git -C "$repo" commit -qam two
tip=$(git -C "$repo" rev-parse HEAD)
git -C "$repo" checkout -q -b sidetrack "$first"
echo side > "$repo/b.txt"; git -C "$repo" add -A; git -C "$repo" commit -qm side
offbranch=$(git -C "$repo" rev-parse HEAD)
git -C "$repo" checkout -q main

# The gate asks gh whether the ticket is a sweep (#1259); no network here. The
# stub answers from $tmp/ticket-title and $tmp/ticket-body, and fails when
# $tmp/gh-down exists.
mkdir -p "$tmp/bin"
cat >"$tmp/bin/gh" <<STUB
#!/usr/bin/env bash
[ -e "$tmp/gh-down" ] && { echo "gh: no network" >&2; exit 1; }
case "\$*" in
  *--json\ title*) cat "$tmp/ticket-title" ;;
  *--json\ body*) cat "$tmp/ticket-body" ;;
  *) exit 1 ;;
esac
STUB
chmod +x "$tmp/bin/gh"
echo "Ordinary ticket" >"$tmp/ticket-title"
: >"$tmp/ticket-body"
export PATH="$tmp/bin:$PATH"

fails=0
# run <name> <expected-exit> <sha> [<substring the output must contain>]
run() {
  local name=$1 want=$2 sha=$3 needle=${4:-}
  local out rc
  out=$(cd "$repo" && bash "$gate" "$sha" 2>&1)
  rc=$?
  if [ "$rc" != "$want" ]; then
    echo "FAIL: $name — want exit $want, got $rc"; echo "  out: $out"; fails=1; return
  fi
  if [ -n "$needle" ] && [[ "$out" != *"$needle"* ]]; then
    echo "FAIL: $name — output missing '$needle'"; echo "  out: $out"; fails=1; return
  fi
  echo "PASS: $name"
}

run "clean tree, sha on the branch passes" 0 "$tip" "pre-report gate: clean tree"
run "an older commit on the branch is an ancestor" 0 "$first"
run "a sha off the branch fails" 1 "$offbranch" "not an ancestor"
run "a sha git cannot resolve is exit 2" 2 nosuchsha "cannot resolve"

# Dirty tree: an untracked file is as blocking as a modified one.
echo scratch > "$repo/untracked.txt"
run "untracked file fails the gate" 1 "$tip" "uncommitted"
rm "$repo/untracked.txt"
echo three >> "$repo/a.txt"
run "modified file fails the gate" 1 "$tip" "uncommitted"
git -C "$repo" checkout -q -- a.txt

# A leftover .scratch/ is as blocking as a dirty tree, even though it's
# git-ignored and git status stays clean.
mkdir -p "$repo/.scratch"
echo leftover > "$repo/.scratch/leftover.txt"
echo '.scratch/' > "$repo/.gitignore"
git -C "$repo" add .gitignore; git -C "$repo" commit -qm gitignore
tip=$(git -C "$repo" rev-parse HEAD)
run ".scratch/ with content fails the gate" 1 "$tip" ".scratch/"

# The check is repo-wide, not cwd-relative: a worker's shell can sit in a
# subdirectory when it calls the gate by absolute path.
mkdir -p "$repo/sub"
out=$(cd "$repo/sub" && bash "$gate" "$tip" 2>&1); rc=$?
if [ "$rc" = 1 ] && [[ "$out" == *".scratch/"* ]]; then
  echo "PASS: .scratch/ content fails the gate from a subdirectory too"
else
  echo "FAIL: .scratch/ content from a subdirectory — want exit 1 + '.scratch/', got $rc: $out"; fails=1
fi
rmdir "$repo/sub"

# An acknowledged keep: the ticket's escape hatch for content the worker
# cannot commit. The gate warns instead of blocking, and the warning must
# carry the reason so it lands in the PR-up report.
out=$(cd "$repo" && PRE_REPORT_KEEP_SCRATCH="raw probe log, too big for docs/research" bash "$gate" "$tip" 2>&1); rc=$?
if [ "$rc" = 0 ] && [[ "$out" == *"raw probe log, too big for docs/research"* ]]; then
  echo "PASS: PRE_REPORT_KEEP_SCRATCH acknowledges a kept .scratch/ and passes"
else
  echo "FAIL: PRE_REPORT_KEEP_SCRATCH — want exit 0 + the reason quoted, got $rc: $out"; fails=1
fi

# The pass line itself — the one line the worker is told to quote — must not
# claim .scratch/ is clear when it was kept, and stdout alone (what a
# captured invocation keeps) must carry the acknowledgement.
stdout_only=$(cd "$repo" && PRE_REPORT_KEEP_SCRATCH="raw probe log" bash "$gate" "$tip" 2>/dev/null)
if [[ "$stdout_only" != *".scratch/ clear"* ]] && [[ "$stdout_only" == *"kept"* ]]; then
  echo "PASS: the pass line doesn't call a kept .scratch/ clear"
else
  echo "FAIL: pass line on stdout — want no 'clear' claim and a 'kept' mention, got: $stdout_only"; fails=1
fi

# An empty reason isn't an acknowledgement — it's the unset case, so a
# worker that forgets the reason still gets blocked, not silently waved
# through.
out=$(cd "$repo" && PRE_REPORT_KEEP_SCRATCH="" bash "$gate" "$tip" 2>&1); rc=$?
if [ "$rc" = 1 ] && [[ "$out" == *".scratch/"* ]]; then
  echo "PASS: an empty PRE_REPORT_KEEP_SCRATCH still fails the gate"
else
  echo "FAIL: empty PRE_REPORT_KEEP_SCRATCH — want exit 1, got $rc: $out"; fails=1
fi

rm -rf "$repo/.scratch"
mkdir -p "$repo/.scratch"
run "empty .scratch/ dir passes" 0 "$tip"
rmdir "$repo/.scratch"

# An unreadable .scratch/ must fail closed, not read as empty — root
# ignores directory permissions, so this case is skipped under root.
if [ "$(id -u)" != "0" ]; then
  mkdir -p "$repo/.scratch"
  echo hidden > "$repo/.scratch/hidden.txt"
  chmod 000 "$repo/.scratch"
  out=$(cd "$repo" && bash "$gate" "$tip" 2>&1); rc=$?
  chmod 755 "$repo/.scratch"
  if [ "$rc" = 1 ] && [[ "$out" != *"clear"* ]]; then
    echo "PASS: an unreadable .scratch/ fails closed"
  else
    echo "FAIL: unreadable .scratch/ — want exit 1 and no 'clear' claim, got $rc: $out"; fails=1
  fi
  rm -rf "$repo/.scratch"
else
  echo "SKIP: unreadable .scratch/ case (running as root)"
fi

# The dispositions check (#1214): on an implement-<n> branch whose review
# cache holds dispositions-<n>.jsonl, the PR body's Decisions made must agree
# with the sidecar — the same comparison `runfile.py leftover` makes at
# harvest, run here so the worker fixes a stale line, not the controller.
git -C "$repo" checkout -q -b implement-7
cache_home="$tmp/home"
reviews="$cache_home/.cache/agent-reviews/$(basename "$repo")"
mkdir -p "$reviews"
sidecar="$reviews/dispositions-7.jsonl"
body="$reviews/pr-body-7.md"
tip=$(git -C "$repo" rev-parse HEAD)
printf '%s\n' '{"id": "S1", "outcome": "disputed", "reason": "no"}' >"$sidecar"
printf '## Decisions made\n\n- S1: fixed, abc1234.\n' >"$body"
out=$(cd "$repo" && HOME="$cache_home" bash "$gate" "$tip" 2>&1); rc=$?
if [ "$rc" = 1 ] && [[ "$out" == *"S1"* ]] && [[ "$out" == *"fixed"* ]]; then
  echo "PASS: a sidecar line the PR body contradicts fails the gate, naming the id"
else
  echo "FAIL: stale sidecar — want exit 1 naming S1, got $rc: $out"; fails=1
fi

printf '%s\n' '{"id": "S1", "outcome": "fixed", "sha": "abc1234"}' >"$sidecar"
out=$(cd "$repo" && HOME="$cache_home" bash "$gate" "$tip" 2>&1); rc=$?
if [ "$rc" = 0 ] && [[ "$out" == *"dispositions agree"* ]]; then
  echo "PASS: an agreeing sidecar passes and the pass line says it was checked"
else
  echo "FAIL: agreeing sidecar — want exit 0 + 'dispositions agree', got $rc: $out"; fails=1
fi

rm "$body"
out=$(cd "$repo" && HOME="$cache_home" bash "$gate" "$tip" 2>&1); rc=$?
if [ "$rc" = 1 ] && [[ "$out" == *"write the body there first"* ]]; then
  echo "PASS: a sidecar with no PR body file fails closed"
else
  echo "FAIL: sidecar without body — want exit 1 + the gate's own 'write the body there first', got $rc: $out"; fails=1
fi

# A check that could not run (no runfile.py beside the gate) is an environment
# error, exit 2, never a disagreement the worker is told to fix (#1214 C3).
printf '%s\n' '{"id": "S1", "outcome": "fixed", "sha": "abc1234"}' >"$sidecar"
printf '## Decisions made\n\n- S1: fixed, abc1234.\n' >"$body"
mkdir -p "$tmp/lonely/implement"
cp "$gate" "$tmp/lonely/implement/pre-report-gate.sh"
out=$(cd "$repo" && HOME="$cache_home" bash "$tmp/lonely/implement/pre-report-gate.sh" "$tip" 2>&1); rc=$?
if [ "$rc" = 2 ] && [[ "$out" == *"could not run"* ]]; then
  echo "PASS: a check that cannot run is exit 2, not a disagreement"
else
  echo "FAIL: check cannot run — want exit 2 + 'could not run', got $rc: $out"; fails=1
fi

# A heavy PR with no verification pass has no sidecar (#1188): on an
# implement-<n> branch that is a refusal, not a pass that skips the check.
rm "$sidecar"
out=$(cd "$repo" && HOME="$cache_home" bash "$gate" "$tip" 2>&1); rc=$?
if [ "$rc" = 1 ] && [[ "$out" == *"no dispositions sidecar"* ]] && [[ "$out" == *"verification pass"* ]]; then
  echo "PASS: no sidecar on an implement-<n> branch fails the gate, naming the verification pass"
else
  echo "FAIL: no sidecar — want exit 1 + 'no dispositions sidecar' + 'verification pass', got $rc: $out"; fails=1
fi

# Round-1 findings on disk and no dispositions sidecar at all is the same
# skipped pass (#1258): the gate refuses, never "check not run".
printf '%s\n' '{"id": "S1"}' >"$reviews/findings-standards-7.jsonl"
out=$(cd "$repo" && HOME="$cache_home" bash "$gate" "$tip" 2>&1); rc=$?
if [ "$rc" = 1 ] && [[ "$out" == *"no dispositions sidecar"* ]] && [[ "$out" != *"check not run"* ]]; then
  echo "PASS: round-1 findings with no sidecar fail the gate rather than skip the check"
else
  echo "FAIL: findings without sidecar — want exit 1 + 'no dispositions sidecar', got $rc: $out"; fails=1
fi
rm "$reviews/findings-standards-7.jsonl"

# An empty sidecar beside real round-1 findings is a pass that recorded nothing.
printf '%s\n' '{"id": "S1"}' >"$reviews/findings-standards-7.jsonl"
: >"$sidecar"
out=$(cd "$repo" && HOME="$cache_home" bash "$gate" "$tip" 2>&1); rc=$?
if [ "$rc" = 1 ] && [[ "$out" == *"empty"* ]]; then
  echo "PASS: an empty sidecar beside real findings fails the gate"
else
  echo "FAIL: empty sidecar — want exit 1 + 'empty', got $rc: $out"; fails=1
fi
rm "$sidecar" "$reviews/findings-standards-7.jsonl"

# A clean round 1 (all three findings sidecars empty) leaves nothing to verify:
# it passes, and there is no disposition to compare the PR body against.
for a in standards spec correctness; do : >"$reviews/findings-$a-7.jsonl"; done
out=$(cd "$repo" && HOME="$cache_home" bash "$gate" "$tip" 2>&1); rc=$?
if [ "$rc" = 0 ] && [[ "$out" == *"round 1 found nothing"* ]]; then
  echo "PASS: a clean round 1 passes without a sidecar and the pass line says so"
else
  echo "FAIL: clean round 1 — want exit 0 + 'round 1 found nothing', got $rc: $out"; fails=1
fi
rm "$reviews"/findings-*-7.jsonl

# The Codex lane writes no findings sidecars: it waives the check by naming why,
# and the reason lands in the pass line.
out=$(cd "$repo" && HOME="$cache_home" PRE_REPORT_NO_VERIFICATION="codex lane, no Claude axes" bash "$gate" "$tip" 2>&1); rc=$?
if [ "$rc" = 0 ] && [[ "$out" == *"waived"* ]] && [[ "$out" == *"codex lane, no Claude axes"* ]]; then
  echo "PASS: PRE_REPORT_NO_VERIFICATION waives the check and quotes the reason"
else
  echo "FAIL: waiver — want exit 0 + 'waived' + reason, got $rc: $out"; fails=1
fi
out=$(cd "$repo" && HOME="$cache_home" PRE_REPORT_NO_VERIFICATION="" bash "$gate" "$tip" 2>&1); rc=$?
if [ "$rc" = 1 ]; then
  echo "PASS: an empty PRE_REPORT_NO_VERIFICATION is not a waiver"
else
  echo "FAIL: empty waiver — want exit 1, got $rc: $out"; fails=1
fi

# A sweep ticket's PR (#1259): every item of the ticket is a sidecar leftover or
# done in the body. One item in neither is refused, by name.
printf '%s\n' 'Sweep: leftovers from burn r1' >"$tmp/ticket-title"
printf '## a/one.md\n\n- **P9** (hard) t — clump #1, #1, PR #2: x\n- **P14** (low) t — clump #1, #1, PR #2: y\n' >"$tmp/ticket-body"
printf '%s\n' '{"id": "a/one.md P9", "outcome": "leftover", "file": "a/one.md", "title": "t", "severity": "hard", "text": "x"}' '{"id": "r1-S1", "outcome": "fixed", "sha": "abc1234"}' >"$sidecar"
printf '## Decisions made\n\n- **a/one.md P9**: leftover.\n- r1-S1: fixed, abc1234.\n' >"$body"
out=$(cd "$repo" && HOME="$cache_home" bash "$gate" "$tip" 2>&1); rc=$?
if [ "$rc" = 1 ] && [[ "$out" == *"a/one.md P14"* ]] && [[ "$out" != *"a/one.md P9,"* ]]; then
  echo "PASS: a sweep PR missing one item from sidecar and body fails the gate, naming it"
else
  echo "FAIL: sweep item missing — want exit 1 naming 'a/one.md P14', got $rc: $out"; fails=1
fi
printf '## Decisions made\n\n- **a/one.md P9**: leftover.\n- **a/one.md P14**: fixed, abc1234.\n- r1-S1: fixed, abc1234.\n' >"$body"
out=$(cd "$repo" && HOME="$cache_home" bash "$gate" "$tip" 2>&1); rc=$?
if [ "$rc" = 0 ] && [[ "$out" == *"sweep item"* ]]; then
  echo "PASS: a sweep PR accounting for every item passes and says so"
else
  echo "FAIL: sweep accounted — want exit 0 + 'sweep item', got $rc: $out"; fails=1
fi
# An unreadable ticket is not "not a sweep": the gate cannot tell, exit 2.
touch "$tmp/gh-down"
out=$(cd "$repo" && HOME="$cache_home" bash "$gate" "$tip" 2>&1); rc=$?
rm "$tmp/gh-down"
if [ "$rc" = 2 ] && [[ "$out" == *"cannot read ticket"* ]]; then
  echo "PASS: a ticket gh cannot read fails the gate closed, exit 2"
else
  echo "FAIL: gh down — want exit 2 + 'cannot read ticket', got $rc: $out"; fails=1
fi
echo "Ordinary ticket" >"$tmp/ticket-title"
printf '%s\n' '{"id": "S1", "outcome": "fixed", "sha": "abc1234"}' >"$sidecar"
printf '## Decisions made\n\n- S1: fixed, abc1234.\n' >"$body"

# Off an implement-<n> branch there is no ticket to look a sidecar up by: the
# gate still passes and says the sidecar was not looked for.
git -C "$repo" checkout -q main
out=$(cd "$repo" && HOME="$cache_home" bash "$gate" "$(git -C "$repo" rev-parse HEAD)" 2>&1); rc=$?
if [ "$rc" = 0 ] && [[ "$out" == *"not implement-<n>"* ]]; then
  echo "PASS: a non-implement branch passes and says dispositions were not looked for"
else
  echo "FAIL: non-implement branch — want exit 0 + 'not implement-<n>', got $rc: $out"; fails=1
fi
git -C "$repo" checkout -q implement-7
# Real workers run from a linked worktree, whose own directory name is not
# the repo's: the cache folder must key on the shared .git (#1214), or the
# check finds no sidecar and refuses a worker whose pass did run (#1188).
git -C "$repo" worktree add -q -b implement-8 "$tmp/implement-8" main
printf '%s\n' '{"id": "S1", "outcome": "disputed", "reason": "no"}' >"$reviews/dispositions-8.jsonl"
printf '## Decisions made\n\n- S1: fixed, abc1234.\n' >"$reviews/pr-body-8.md"
wt_tip=$(git -C "$tmp/implement-8" rev-parse HEAD)
out=$(cd "$tmp/implement-8" && HOME="$cache_home" bash "$gate" "$wt_tip" 2>&1); rc=$?
if [ "$rc" = 1 ] && [[ "$out" == *"S1"* ]]; then
  echo "PASS: a linked worktree finds the repo's sidecar and refuses a stale one"
else
  echo "FAIL: linked worktree — want exit 1 naming S1, got $rc: $out"; fails=1
fi
git -C "$repo" worktree remove --force "$tmp/implement-8"
git -C "$repo" checkout -q main

# Wrong usage is a usage error, not a pass.
out=$(cd "$repo" && bash "$gate" 2>&1); rc=$?
if [ "$rc" = 2 ] && [[ "$out" == *"usage"* ]]; then
  echo "PASS: no sha argument is a usage error"
else
  echo "FAIL: no sha argument — want exit 2 + usage, got $rc: $out"; fails=1
fi

[ "$fails" = 0 ] && echo "ALL PASS" || { echo "FAILURES"; exit 1; }
