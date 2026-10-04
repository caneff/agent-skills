#!/usr/bin/env bash
# Guards #937: the caller derives the diff once, writes it to a file, and
# hands every axis that path — so three opus reviewers read one capture
# instead of each re-running the same `git diff`. The command stays in the
# prompt as provenance and as the fallback: an axis whose file is missing or
# empty re-derives and says so, rather than reviewing nothing.
# Runs the documented capture blocks for real against a scratch repo.
# BASH_SOURCE rather than `git rev-parse --show-toplevel`, and GIT_* scrubbed:
# a caller's leaked GIT_DIR/GIT_WORK_TREE would point git at the caller's repo
# (#620).
set -euo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="$here/SKILL.md"
reviewer="$here/../flow/claude/agents/diff-reviewer.md"

for f in "$skill" "$reviewer"; do
  [ -f "$f" ] || { echo "FAIL: missing $f" >&2; exit 1; }
done

# § 4 scoped to itself: needles this generic must not be satisfied by prose
# in another step. Runs from the step-4 heading to the next `### `.
spawn="$(sed -n '/^###[[:space:]]*4\./,/^###[[:space:]]/{/^###[[:space:]]*4\./d; /^###[[:space:]]/d; p}' "$skill")"
[ -n "$spawn" ] || { echo "FAIL: multi-axis-code-review/SKILL.md has no § 4 step" >&2; exit 1; }

fail=0

# Rule 5 (PR #943 round 2): run the documented block itself, twice, for the
# same issue number at two distinct revisions, and prove the second capture
# does not disturb the first. Extracting the fenced block out of SKILL.md
# rather than retyping it here is what makes this a witness of the shell a
# caller actually pastes; a copy in this file would pass forever while the
# doc drifted.
fenced() { # <needle> -> every fenced block of § 4 containing the needle, fences dropped
  awk -v m="$1" '
    /^```/ { if (inb) { if (index(buf, m)) printf "%s", buf; buf = ""; inb = 0 } else inb = 1; next }
    inb { buf = buf $0 "\n" }
  ' <<<"$spawn"
}
preamble="$(fenced 'rev-parse --path-format=absolute')"
block="$(fenced 'diff "$fixed_point"...HEAD')"
case "$preamble" in
  *'publish_capture()'*) ;;
  *) echo "FAIL: could not extract § 4's report-directory preamble from multi-axis-code-review/SKILL.md" >&2; exit 1 ;;
esac
[ -n "$block" ] || { echo "FAIL: could not extract § 4's capture block from multi-axis-code-review/SKILL.md" >&2; exit 1; }

# The two capture modes share one publish protocol, stated once in the
# preamble (#948). Run end-to-end, each suite only catches a break inside its
# own block; this is the check that fails when the range block and the
# sha-list block disagree about it — one keeps its own nonce scheme, its own
# `mv`, or its own retention. Neither mode may restate a step of the
# protocol, and both must call it.
range_mode="$block"
sha_mode="$(fenced 'sha-list review: the commit list is empty')"
[ -n "$sha_mode" ] || { echo "FAIL: could not extract § 4's sha-list capture block from multi-axis-code-review/SKILL.md" >&2; exit 1; }
for mode in range_mode sha_mode; do
  body="${!mode}"
  for step in 'mktemp' 'mv ' 'wc -l' 'find ' '-mtime'; do
    if grep -qF -- "$step" <<<"$body"; then
      echo "FAIL: the $mode capture restates the shared publish protocol step '$step' instead of calling the preamble's" >&2
      fail=1
    fi
  done
  # Each mode on its own, not the two summed: one mode calling twice and the
  # other not at all is a disagreement that a total of 2 hides. The nonce and
  # the shared file stem stay per-mode text, so they are pinned here too.
  for fn in 'new_capture' 'publish_capture "$tmp" "$patch"' '"$dir/diff-$n-'; do
    calls="$(grep -cF -- "$fn" <<<"$body" || true)"
    [ "$calls" -eq 1 ] || { echo "FAIL: the $mode capture uses $fn $calls time(s), not once" >&2; fail=1; }
  done
done

scratch="$(mktemp -d)" || { echo "FAIL: mktemp -d" >&2; exit 1; }
trap 'rm -rf "$scratch"' EXIT

(
  cd "$scratch"
  git init -q -b main repo
  cd repo
  . "$here/../tests/fixture-identity.sh"
  fixture_identity "$scratch/repo" "$scratch" || exit 1
  echo base >f.txt; git add f.txt; git commit -qm base
  git checkout -qb work
  echo first >f.txt; git commit -qam first
  echo second >>f.txt; git commit -qam second
) || { echo "FAIL: could not build the scratch repo" >&2; exit 1; }

repo="$scratch/repo"
rev_b="$(git -C "$repo" rev-parse HEAD~1)"
rev_c="$(git -C "$repo" rev-parse HEAD)"

# The block's placeholders are assignments, so a real value substitutes in
# without touching any other line of what the doc publishes.
run_block() { # <rev> -> prints the published path
  local rev="$1"
  git -C "$repo" checkout -q "$rev"
  { printf '%s\n' "$preamble"; printf '%s\n' "$block"; } |
    sed -e "s|^n=<.*|n=937|" \
        -e "s|^worktree=<.*|worktree=$repo|" \
        -e "s|^fixed_point=<.*|fixed_point=main|" >"$scratch/block.sh"
  ( cd "$repo" && HOME="$scratch/home" bash "$scratch/block.sh" ) | tail -1 | awk '{print $NF}'
}

mkdir -p "$scratch/home"
first_path="$(run_block "$rev_b")"
[ -n "$first_path" ] && [ -f "$first_path" ] || {
  echo "FAIL: § 4's block published no capture at $rev_b" >&2; fail=1; }
first_sum="$(md5sum <"$first_path")"

second_path="$(run_block "$rev_c")"
[ -n "$second_path" ] && [ -f "$second_path" ] || {
  echo "FAIL: § 4's block published no capture at $rev_c" >&2; fail=1; }

if [ "$first_path" = "$second_path" ]; then
  echo "FAIL: two captures of issue 937 at distinct revisions share one path: $first_path" >&2
  fail=1
fi
if [ ! -f "$first_path" ]; then
  echo "FAIL: the second capture removed the first" >&2
  fail=1
elif [ "$(md5sum <"$first_path")" != "$first_sum" ]; then
  echo "FAIL: the second capture rewrote the first under its readers" >&2
  fail=1
fi
if cmp -s "$first_path" "$second_path"; then
  echo "FAIL: captures of two distinct revisions are byte-identical" >&2
  fail=1
fi
# No temp file is left behind to be handed to an axis or to stall merge-cleanup.
leftovers="$(find "$(dirname "$first_path")" -maxdepth 1 -type f ! -name '*.patch' | wc -l)"
[ "$leftovers" -eq 0 ] || {
  echo "FAIL: the block left $leftovers non-patch file(s) beside the captures" >&2; fail=1; }

git -C "$repo" checkout -q "$rev_c"
{ printf '%s\n' "$preamble"; printf '%s\n' "$block"; printf '%s\n' "$block"; } |
  sed -e "s|^n=<.*|n=937|" -e "s|^worktree=<.*|worktree=$repo|" -e "s|^fixed_point=<.*|fixed_point=main|" >"$scratch/twice.sh"
twice_out="$( cd "$repo" && HOME="$scratch/twice-home" bash "$scratch/twice.sh" 2>&1 )" ||
  { echo "FAIL: two same-revision captures in one shell did not both publish: $twice_out" >&2; fail=1; }
tw1="$(printf '%s\n' "$twice_out" | grep ' /' | sed -n 1p | awk '{print $NF}')"
tw2="$(printf '%s\n' "$twice_out" | grep ' /' | sed -n 2p | awk '{print $NF}')"
if [ -z "$tw1" ] || [ -z "$tw2" ] || [ "$tw1" = "$tw2" ]; then
  echo "FAIL: two captures at one revision in one shell share a final path: '$tw1' '$tw2'" >&2
  fail=1
elif [ ! -s "$tw1" ]; then
  echo "FAIL: the second same-revision capture replaced the first at $tw1" >&2
  fail=1
fi

# The range block run in a shell that never ran the preamble refuses by name.
printf '%s\n' "$block" |
  sed -e "s|^fixed_point=<.*|fixed_point=main|" >"$scratch/nofunc.sh"
if nofunc_out="$( cd "$repo" && HOME="$scratch/home" n=937 worktree="$repo" dir="$scratch/home" bash "$scratch/nofunc.sh" 2>&1 )"; then
  echo "FAIL: the range block ran without the preamble's functions" >&2
  fail=1
elif ! printf '%s' "$nofunc_out" | grep -qF 'in this same shell'; then
  echo "FAIL: the range block refused missing preamble functions without saying why: $nofunc_out" >&2
  fail=1
fi

# A nonce per invocation means more files, not more lifetime: the same
# 14-day sweep in the same block still collects a capture under the new key.
touch -d '20 days ago' "$(dirname "$first_path")/diff-937-deadbee-1234.patch"
run_block "$rev_c" >/dev/null
[ ! -e "$(dirname "$first_path")/diff-937-deadbee-1234.patch" ] || {
  echo "FAIL: the block's 14-day sweep no longer collects a capture under the unique key" >&2
  fail=1; }

if [ "$fail" -eq 0 ]; then
  echo "PASS multi-axis-code-review/diff-capture.test.sh"
else
  exit 1
fi
