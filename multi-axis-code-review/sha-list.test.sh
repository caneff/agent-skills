#!/usr/bin/env bash
# Guards #932: N non-contiguous landed commits reviewed as one change, with
# the axes seeing the union of those commits' own diffs. A review on a shared
# `main` must never sweep in other people's merged work — the two-dot form of
# one #888 comparison read 18 files and 1080 deletions of exactly that.
# Prose assertions over SKILL.md, plus the documented capture block run for
# real against a scratch repo with unrelated commits interleaved.
# BASH_SOURCE rather than `git rev-parse --show-toplevel`, and GIT_* scrubbed:
# a caller's leaked GIT_DIR/GIT_WORK_TREE would point git at the caller's repo
# (#620).
set -euo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"
[ -f "$skill" ] || { echo "FAIL: missing $skill" >&2; exit 1; }

flatten() { tr '\n' ' ' | tr -s ' '; }
skill_text="$(flatten <"$skill")"

fail=0
check_in() {
  local haystack="$1" needle="$2" where="$3"
  case "$haystack" in
    *"$needle"*) ;;
    *) echo "FAIL: $where is missing: $needle" >&2; fail=1 ;;
  esac
}

# The front door: a caller naming commits must land in this mode rather than
# have the fixed point invented for it, which is the failure #897's closing
# ticket was written to prevent.
check_in "$skill_text" 'sha-list mode' multi-axis-code-review/SKILL.md
# What three-dot becomes is the part that decides whether a finding lands on
# this work or on somebody else's, so the doc has to say it, not imply it.
check_in "$skill_text" "its own first parent" multi-axis-code-review/SKILL.md

# The standing brief every axis reads must not let a fallback turn the list
# back into a range — that is the contamination, re-derived.
reviewer="$here/../flow/claude/agents/diff-reviewer.md"
[ -f "$reviewer" ] || { echo "FAIL: missing $reviewer" >&2; exit 1; }
check_in "$(flatten <"$reviewer")" 'never substitute a range for a sha list' flow/claude/agents/diff-reviewer.md

recipe="$(awk '
  /^```$/ { if (inb) { if (buf ~ /sha-list review/) printf "%s", buf; buf = ""; inb = 0 }
            else inb = 1
            next }
  inb { buf = buf $0 "\n" }
' "$skill")"
case "$recipe" in
  *'sha-list review'*) ;;
  *) echo "FAIL: could not extract the sha-list capture block from $skill" >&2; exit 1 ;;
esac

scratch="$(mktemp -d)" || { echo "FAIL: mktemp -d" >&2; exit 1; }
trap 'rm -rf "$scratch"' EXIT

# Three commits to review, with somebody else's work interleaved between each
# pair — the shape of a shared `main`.
(
  cd "$scratch"
  git init -q -b main repo
  cd repo
  git config user.email t@example.com
  git config user.name t
  echo base >base.txt; git add base.txt; git commit -qm base
  echo one >keep-a.txt;  git add keep-a.txt;  git commit -qm "keep A"
  echo x >other-x.txt;   git add other-x.txt; git commit -qm "somebody else X"
  echo two >keep-b.txt;  git add keep-b.txt;  git commit -qm "keep B"
  echo y >other-y.txt;   git add other-y.txt; git commit -qm "somebody else Y"
  echo three >keep-c.txt; git add keep-c.txt; git commit -qm "keep C"
  git commit -q --allow-empty -m "an empty commit"
  git checkout -q -b side main
  echo s >side.txt; git add side.txt; git commit -qm side
  git checkout -q main
  git merge -q --no-ff -m "a merge" side
) || { echo "FAIL: could not build the scratch repo" >&2; exit 1; }
repo="$scratch/repo"
sha() { git -C "$repo" rev-parse "$(git -C "$repo" log --format='%H %s' | grep -F -m1 -- "$1" | cut -d' ' -f1)"; }
a="$(sha 'keep A')"; b="$(sha 'keep B')"; c="$(sha 'keep C')"
empty="$(sha 'an empty commit')"; merge="$(sha 'a merge')"

# `dir` comes from § 4's directory preamble, which diff-capture.test.sh
# already witnesses; this block's own refusal when it is unset is checked
# below.
mkdir -p "$scratch/dir"
run_block() { # <shas...> -> stdout of the block; exit status is the block's
  printf 'dir=%s\n' "$scratch/dir" >"$scratch/block.sh"
  printf '%s\n' "$recipe" |
    sed -e "s|^n=<.*|n=932|" \
        -e "s|^worktree=<.*|worktree=$repo|" \
        -e "s|^set -- <.*|set -- $*|" >>"$scratch/block.sh"
  ( cd "$scratch" && bash "$scratch/block.sh" )
}

out="$(run_block "$a" "$b" "$c")" || { echo "FAIL: the block refused a good three-sha list" >&2; fail=1; }
patch="$(printf '%s\n' "$out" | tail -1 | awk '{print $NF}')"
if [ -z "$patch" ] || [ ! -s "$patch" ]; then
  echo "FAIL: the block published no capture for a three-sha list" >&2
  fail=1
else
  for f in keep-a.txt keep-b.txt keep-c.txt; do
    grep -q "^diff --git a/$f" "$patch" ||
      { echo "FAIL: the capture is missing the named commit touching $f" >&2; fail=1; }
  done
  # The whole point: interleaved commits nobody named are not in the union.
  for f in other-x.txt other-y.txt side.txt; do
    if grep -q "$f" "$patch"; then
      echo "FAIL: the capture swept in $f, which no named commit touches" >&2
      fail=1
    fi
  done
  # Oldest first, so a file two named commits both touch reads in apply order.
  order="$(awk '/^commit /{printf "%s ", $2}' "$patch")"
  case "$order" in
    "$a $b $c "*) ;;
    *) echo "FAIL: the capture orders the commits '$order', not oldest-first '$a $b $c'" >&2; fail=1 ;;
  esac
  # A sha named twice is one commit, not two copies of its diff.
  dupes="$(run_block "$a" "$b" "$a" | tail -1 | awk '{print $NF}')"
  hits="$(grep -c '^diff --git a/keep-a.txt' "$dupes" || true)"
  [ "$hits" -eq 1 ] ||
    { echo "FAIL: a sha named twice put its diff in the capture $hits times" >&2; fail=1; }
fi

# #776's recurring defect: an absent or malformed answer read as a benign one.
# None of these may review as "no changes found" — each refuses by name.
# The diagnosis is part of the refusal, not decoration: a merge commit reported
# as "changes no files" is a true exit status attached to a false reason, and
# the caller retries the wrong thing. Each case names its own cause.
refuses() { # <label> <needle> <shas...>
  local label="$1" needle="$2"; shift 2
  local o
  if o="$(run_block "$@" 2>&1)"; then
    echo "FAIL: the block accepted $label instead of refusing it" >&2
    fail=1
  elif ! printf '%s' "$o" | grep -qF "$needle"; then
    echo "FAIL: the block refused $label without naming why ($needle): $o" >&2
    fail=1
  fi
}
refuses 'an empty sha list' 'sha-list review: the commit list is empty'
refuses 'a sha that does not resolve' 'does not resolve to a commit' \
  "$a" 0000000000000000000000000000000000000000
refuses 'a merge commit' 'is a merge commit' "$a" "$merge"
refuses 'a commit that changes no files' 'changes no files' "$a" "$empty"

# Pasted without § 4's preamble, `dir` is unset: the block must say so rather
# than write its capture to the filesystem root or silently produce nothing.
printf '%s\n' "$recipe" |
  sed -e "s|^n=<.*|n=932|" -e "s|^worktree=<.*|worktree=$repo|" -e "s|^set -- <.*|set -- $a|" \
  >"$scratch/nodir.sh"
if ( cd "$scratch" && unset dir; bash "$scratch/nodir.sh" >/dev/null 2>&1 ); then
  echo "FAIL: the block ran with no report directory set" >&2
  fail=1
fi

# No temp file left behind to be handed to an axis or to stall merge-cleanup.
leftovers="$(find "$scratch/dir" -maxdepth 1 -type f ! -name '*.patch' | wc -l)"
[ "$leftovers" -eq 0 ] ||
  { echo "FAIL: the block left $leftovers non-patch file(s) beside the captures" >&2; fail=1; }

if [ "$fail" -eq 0 ]; then
  echo "PASS multi-axis-code-review/sha-list.test.sh"
else
  exit 1
fi
