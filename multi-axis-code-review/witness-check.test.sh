#!/usr/bin/env bash
# Guards the witness check (#939, #957, #1708): one mutation per call, given by flags
# (--id --file --old --new --test), applied as one literal string replacement in a throwaway
# git worktree, its covering command run there, and an unreached mutation reported as
# `unknown` rather than as a pass. Runs the script for real.
# BASH_SOURCE rather than `git rev-parse --show-toplevel`, and GIT_* scrubbed:
# a caller's leaked GIT_DIR/GIT_WORK_TREE would point git at the caller's repo
# (#620).
set -euo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$here/.." && pwd)"
fail=0

# Prose can claim isolation; only running the check witnesses it. Every run below calls the
# script the skill tells reviewers to call, never a copy.
checker="$here/witness-check.sh"
[ -f "$checker" ] || { echo "FAIL: missing $checker" >&2; exit 1; }

scratch="$(mktemp -d)" || { echo "FAIL: mktemp -d" >&2; exit 1; }
trap 'git -C "$scratch/repo" worktree prune 2>/dev/null; rm -rf "$scratch"' EXIT
. "$here/../tests/fixture-identity.sh"
make_repo() { # <name> <setup commands, run in the new repo> -> the reviewed worktree's path
  # The reviewed tree is a LINKED worktree, which is what every review in this lane runs on: its
  # `.git` is a file holding a gitdir pointer, so a byte copy of it would share this repo's index.
  (
    cd "$scratch" && git init -q -b main "$1" && cd "$1" &&
    fixture_identity "$scratch/$1" "$scratch" && eval "$2" &&
    git add -A && git commit -qm base &&
    git worktree add -q --detach "$scratch/$1-reviewed" HEAD
  ) >/dev/null 2>&1 || { echo "FAIL: could not build fixture repo $1" >&2; exit 1; }
  printf '%s\n' "$scratch/$1-reviewed"
}
base_setup='printf "assert 1 == 1\n" >m1.py
printf "assert 1 == 1\n" >m2.py
printf "x = 1\nx = 1\n" >dup.py
printf "aaa\n" >ov.txt
printf "start\nold line\nend\n" >lit.txt'
repo="$(make_repo repo "$base_setup")"
[ -f "$repo/.git" ] || { echo "FAIL: the fixture's reviewed tree is not a linked worktree" >&2; exit 1; }

# A scratch HOME so nothing a run writes reaches the real one, and a ledger path always
# substituted in, never the real one. The idle-box `ps` shim pins the box: the bound reads the
# live process table, so on a loaded box an overlap assertion would go red for the machine's state.
home="$scratch/home"; mkdir -p "$home/.agents" "$scratch/bin"
ln -s "$repo_root" "$home/.agents/skills"
printf '#!/usr/bin/env bash\nprintf "claude\\nbash\\ninit\\n"\n' >"$scratch/bin/ps"; chmod +x "$scratch/bin/ps"
real_git="$(command -v git)"
cache="$home/.cache/agent-reviews/skills"

run() { # <reviewed tree> <checker args...>: stdout+stderr of one call; exit status is the call's
  local tree="$1"; shift
  ( cd "$tree" && env -u PYTHONDONTWRITEBYTECODE HOME="$home" PATH="${shim:-$scratch/bin}:$PATH" \
      bash "$checker" --worktree "$tree" "$@" 2>&1 )
}
trees() { git -C "$repo" worktree list | wc -l; }
ledger="$scratch/ledger.jsonl"
LA=(--repo skills --ticket 1 --round 1 --ledger "$ledger")
break_m1=(--file m1.py --old 'assert 1 == 1' --new 'assert 1 == 2')
row_field() { # <ledger> <mutation id> <dotted field>... -> the values, space-joined, or MISSING
  python3 - "$@" <<'PY'
import json, os, sys
path, mid, *fields = sys.argv[1:]
rows = [json.loads(l) for l in open(path)] if os.path.exists(path) else []
hit = [r for r in rows if r.get("mutation_id") == mid]
def get(row, dotted):
    for key in dotted.split("."):
        row = row[key]
    return row
print(" ".join(str(get(hit[0], f)) for f in fields) if len(hit) == 1 else "MISSING")
PY
}
rows_in() { [ -s "$1" ] && wc -l <"$1" || echo 0; }
check() { # <description> <command...>: fails the suite with the description when the command is false
  local why="$1"; shift
  "$@" || { echo "FAIL: $why" >&2; fail=1; }
}

# --- the one-shot interface: a test that catches the mutation reads red, one that misses it green ---
out="$(run "$repo" --id r1 "${break_m1[@]}" --test 'python3 m1.py' "${LA[@]}")" ||
  { echo "FAIL: a red mutation exited non-zero" >&2; echo "$out" >&2; fail=1; }
check "a catching test did not read 'r1: red' with its own AssertionError tagged r1" \
  bash -c 'grep -q "^r1: red" <<<"$1" && grep -q "r1|.*AssertionError" <<<"$1"' _ "$out"
check "the ledger row of the red mutation is not witness-mutation/red" \
  [ "$(row_field "$ledger" r1 type outcome)" = "witness-mutation red" ]
check "the row carries no known wall clock" [ "$(row_field "$ledger" r1 cost.wall_clock.status)" = known ]
out="$(run "$repo" --id g1 "${break_m1[@]}" --test 'python3 m2.py' "${LA[@]}")" || true
check "a test that misses the mutation did not read HOLLOW" grep -q '^g1: HOLLOW' <<<"$out"
check "the missed mutation's ledger row is not green" [ "$(row_field "$ledger" g1 outcome)" = green ]
# The reviewed checkout is untouched: the mutation lives in the witness only.
check "the mutation reached the reviewed tree's file" [ "$(cat "$repo/m1.py")" = 'assert 1 == 1' ]
check "the run left the reviewed tree dirty" [ -z "$(git -C "$repo" status --porcelain)" ]
check "the run staged something in the reviewed tree's index" [ -z "$(git -C "$repo" diff --cached --name-only)" ]
check "the run left throwaway worktrees registered, not the fixture's 2" [ "$(trees)" -eq 2 ]
# #1324: the witness lives under the review cache's one home and the run leaves nothing there.
out="$(run "$repo" --id loc1 "${break_m1[@]}" --test 'pwd; exit 1' "${LA[@]}")" || true
case "$out" in *"loc1| $home/.cache/agent-reviews/skills/witness."*"/worktrees/loc1"*) ;;
  *) echo "FAIL: the witness did not run under $home/.cache/agent-reviews/skills/witness.*/: $out" >&2; fail=1 ;; esac
check "the run left entries in the review cache home" \
  [ "$(find "$cache" -mindepth 1 -maxdepth 1 2>/dev/null | wc -l)" -eq 0 ]
# The covering command's own message stays paired with the id that produced it.
out="$(run "$repo" --id pair1 "${break_m1[@]}" --test 'echo MUTANT-pair1; exit 1' --no-ledger)" || true
check "the message line is not tagged with its id" grep -q 'pair1|.*MUTANT-pair1' <<<"$out"

# --- --old that does not occur exactly once is refused before anything runs, and no row is written ---
before_rows="$(rows_in "$ledger")"
refused() { # <why> <message needle> <checker args...>
  local why="$1" needle="$2"; shift 2
  local rc=0 o
  o="$(run "$repo" "$@")" || rc=$?
  { [ "$rc" -eq 2 ] && grep -qF -- "$needle" <<<"$o"; } ||
    { echo "FAIL: $why was not refused with exit 2 and '$needle' (exit $rc)" >&2; echo "$o" >&2; fail=1; }
  check "$why: ran something (a worktree is registered)" [ "$(trees)" -eq 2 ]
  check "$why: left something in the cache home" [ "$(find "$cache" -mindepth 1 -maxdepth 1 2>/dev/null | wc -l)" -eq 0 ]
}
refused '--old occurring zero times' 'occurs 0 times' --id z0 --file m1.py --old 'no such text' --new x --test 'exit 1' "${LA[@]}"
refused '--old occurring twice' 'occurs 2 times' --id z2 --file dup.py --old 'x = 1' --new 'x = 2' --test 'exit 1' "${LA[@]}"
refused '--old occurring twice, overlapping' 'occurs 2 times' --id z3 --file ov.txt --old 'aa' --new y --test 'exit 1' "${LA[@]}"
check "a refused --old wrote a ledger row" [ "$(rows_in "$ledger")" -eq "$before_rows" ]
refused 'an empty --old' '--old' --id e0 --file m1.py --old '' --new x --test 'exit 1' --no-ledger
refused 'an --old equal to --new' 'identical' --id eq --file m1.py --old 'assert 1 == 1' --new 'assert 1 == 1' --test 'exit 1' --no-ledger
refused 'an absolute --file' 'is outside the reviewed tree' --id ab --file /etc/hostname --old a --new b --test 'exit 1' --no-ledger
refused 'a --file that climbs out of the tree' 'is outside the reviewed tree' --id up --file ../x --old a --new b --test 'exit 1' --no-ledger
refused 'a --file not tracked at HEAD' 'not tracked at HEAD' --id nt --file nope.py --old a --new b --test 'exit 1' --no-ledger
refused 'a call with no --test' '--test' --id nt1 "${break_m1[@]}" --no-ledger
refused 'a call with no --id' '--id is required' "${break_m1[@]}" --test 'exit 1' --no-ledger
refused 'a call with no --file' '--file is missing' --id nm --old a --new b --test 'exit 1' --no-ledger
refused 'a call with no --old' '--old is missing' --id no --file m1.py --new b --test 'exit 1' --no-ledger
refused 'a call with no --new' '--new is missing' --id nn --file m1.py --old 'assert 1 == 1' --test 'exit 1' --no-ledger
refused 'an id of .' 'not usable as a mutation id' --id . "${break_m1[@]}" --test 'exit 1' --no-ledger
refused 'an id of ..' 'not usable as a mutation id' --id .. "${break_m1[@]}" --test 'exit 1' --no-ledger
refused '--worker with --call-site' 'not both' --id wc "${break_m1[@]}" --test 'exit 1' --no-ledger --worker --call-site
refused 'the removed --mutate file form' 'unknown argument' --id mu --mutate /dev/null --test 'exit 1' --no-ledger
refused 'a mutation given by --patch and by --old together' 'not both' --id pb --patch /dev/null "${break_m1[@]}" --test 'exit 1' --no-ledger
refused 'two mutations in one call (a second positional id)' 'unknown argument' --id two "${break_m1[@]}" --test 'exit 1' --no-ledger -- other
refused 'an id that names a pytest nodeid' 'tests/a.py::t1' --id 'tests/a.py::t1' "${break_m1[@]}" --test 'exit 1' --no-ledger
refused "an id of '*'" 'not usable as a mutation id' --id '*' "${break_m1[@]}" --test 'exit 1' --no-ledger
refused 'ledger rows without --repo/--ticket' 'need --repo and --ticket' --id nl "${break_m1[@]}" --test 'exit 1'
refused '--no-ledger with ledger arguments' '--no-ledger with ledger arguments' --id nl2 "${break_m1[@]}" --test 'exit 1' --no-ledger --repo skills
refused 'a non-numeric --timeout' '--timeout needs a positive integer' --id t1 "${break_m1[@]}" --test 'exit 1' --no-ledger --timeout x
refused 'a non-numeric --baseline-seconds' '--baseline-seconds needs a positive integer' --id t2 "${break_m1[@]}" --test 'exit 1' --no-ledger --baseline-seconds x
refused '--timeout together with --baseline-seconds' 'not both' --id t3 "${break_m1[@]}" --test 'exit 1' --no-ledger --timeout 5 --baseline-seconds 5
refused '--slots 0' '--slots' --id s0 "${break_m1[@]}" --test 'exit 1' --no-ledger --slots 0

# --- strings with quotes, $, newlines and backslashes apply literally ---
old_lit=$'old line'
new_lit=$'a "dq" \'sq\' $HOME $(echo SUBST) `echo BT` \\n *.py\nsecond\\ line  '
out="$(run "$repo" --id lit1 --file lit.txt --old "$old_lit" --new "$new_lit" --test 'cat lit.txt; exit 1' --no-ledger)" || true
got="$(printf '%s\n' "$out" | sed -n 's/^  lit1| //p')"
check "quotes, \$, backticks, backslashes and a newline did not arrive literally; got: $got" \
  [ "$got" = "$(printf 'start\n%s\nend' "$new_lit")" ]
# An --old holding the same characters matches literally too (here: a multi-line --old).
out="$(run "$repo" --id lit2 --file lit.txt --old $'start\nold line' --new 'S' --test 'cat lit.txt; exit 1' --no-ledger)" || true
got="$(printf '%s\n' "$out" | sed -n 's/^  lit2| //p' | paste -sd'|')"
check "a multi-line --old did not match literally; got: $got" [ "$got" = 'S|end' ]
# The same characters in --old match literally too: it takes a separate path (the count at HEAD).
cat >"$scratch/mk_special.py" <<'MKPY'
open("sp.txt", "w").write("q \"a\" 'b' $HOME $(x) `y` \\n *\n")
MKPY
special_repo="$(make_repo specialrepo "python3 '$scratch/mk_special.py'")"
sp_old="$(cat "$special_repo/sp.txt")"
out="$(run "$special_repo" --id sp2 --file sp.txt --old "$sp_old" --new 'REPLACED' --test 'cat sp.txt; exit 1' --no-ledger)" || true
got="$(printf '%s\n' "$out" | sed -n 's/^  sp2| //p')"
check "an --old with quotes, \$, backticks and a backslash did not match literally; got: $got" [ "$got" = REPLACED ]
# A deletion (--new '') is a valid mutation.
out="$(run "$repo" --id lit3 --file lit.txt --old $'old line\n' --new '' --test 'cat lit.txt; exit 1' --no-ledger)" || true
got="$(printf '%s\n' "$out" | sed -n 's/^  lit3| //p' | paste -sd'|')"
check "an empty --new did not delete the text; got: $got" [ "$got" = 'start|end' ]

# --- --patch: the second way to give the one mutation (mutation-audit/witness.sh hands it over) ---
patch_repo="$(make_repo patchrepo 'printf "def f():\n    return 1\n" >mod.py
printf "import mod\nassert mod.f() == 1, \"MUTANT-mod: mod.f() no longer returns 1\"\n" >test_mod.py')"
sed 's/return 1/return 2/' "$patch_repo/mod.py" >"$scratch/mod.new"
( cd "$patch_repo" && diff -u mod.py "$scratch/mod.new" | sed '1s|.*|--- a/mod.py|; 2s|.*|+++ b/mod.py|' ) >"$scratch/breaks.patch" || true
out="$(run "$patch_repo" --id pt1 --patch "$scratch/breaks.patch" --test 'python3 test_mod.py' --no-ledger)" || true
check "a --patch mutation did not read red with its own assertion" bash -c 'grep -q "^pt1: red" <<<"$1" && grep -q "MUTANT-mod" <<<"$1"' _ "$out"
printf -- '--- a/absent.py\n+++ b/absent.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n' >"$scratch/stale.patch"
out="$(run "$patch_repo" --id pt2 --patch "$scratch/stale.patch" --test 'python3 test_mod.py' --no-ledger)" || true
check "a --patch that does not apply was not reported unknown" bash -c 'grep -q "^pt2: unknown" <<<"$1" && ! grep -q "^pt2: red" <<<"$1"' _ "$out"
check "a --patch that does not apply never ran the covering command" bash -c '! grep -q "MUTANT-mod" <<<"$1"' _ "$out"

# --- ledger rows: the type is the flag's, the outcome the covering command's own status ---
wl="$scratch/kinds.jsonl"
KA=(--repo skills --ticket 2 --ledger "$wl")
run "$repo" --id k1 "${break_m1[@]}" --test 'exit 1' "${KA[@]}" >/dev/null || true
run "$repo" --id k2 "${break_m1[@]}" --test 'echo x; exit 1' --call-site "${KA[@]}" >/dev/null || true
run "$repo" --id k3 "${break_m1[@]}" --test 'echo x; exit 1' --worker "${KA[@]}" >/dev/null || true
for want in "k2|call-site-mutation red" "k3|worker-mutation red"; do
  check "mutation ${want%%|*}'s ledger row is '$(row_field "$wl" "${want%%|*}" type outcome)', wanted '${want#*|}'" \
    [ "$(row_field "$wl" "${want%%|*}" type outcome)" = "${want#*|}" ]
done
# A refused append is reported, not skipped: exit 4 and a line saying so.
corrupt="$scratch/corrupt.jsonl"; printf 'not json\n' >"$corrupt"
rc=0; out="$(run "$repo" --id ra "${break_m1[@]}" --test 'echo x; exit 1' --repo skills --ticket 1 --ledger "$corrupt")" || rc=$?
{ [ "$rc" -eq 4 ] && grep -q 'mutation row was not appended' <<<"$out"; } ||
  { echo "FAIL: a refused ledger append did not exit 4 and say so (exit $rc)" >&2; echo "$out" >&2; fail=1; }
check "the refused-append run left worktrees registered" [ "$(trees)" -eq 2 ]

# --- class 1: a mutation that never reached its covering command is `unknown`, never a pass ---
out="$(run "$repo" --id sil1 "${break_m1[@]}" --test 'exit 4' --no-ledger)" || true
check "a covering command that failed silently was not reported unknown" \
  bash -c 'grep -q "^sil1: unknown" <<<"$1" && ! grep -q "^sil1: red" <<<"$1"' _ "$out"
out="$(run "$repo" --id ne1 "${break_m1[@]}" --test '/nonexistent/covering-suite' --no-ledger)" || true
check "a covering command that never executed was not reported unknown" \
  bash -c 'grep -q "^ne1: unknown" <<<"$1" && ! grep -q "^ne1: red" <<<"$1"' _ "$out"
# A `git worktree add` that fails (a shim refusing exactly this path) is unknown, with a row.
mkdir -p "$scratch/bin-git"
cat >"$scratch/bin-git/git" <<SHIM
#!/usr/bin/env bash
adding=0
for a in "\$@"; do [ "\$a" = add ] && adding=1; done
if [ "\$adding" = 1 ]; then
  for a in "\$@"; do case "\$a" in */bad) echo "fatal: shim refuses \$a" >&2; exit 128;; esac; done
fi
exec "$real_git" "\$@"
SHIM
chmod +x "$scratch/bin-git/git"; cp "$scratch/bin/ps" "$scratch/bin-git/ps"
uw="$scratch/unknown-wt.jsonl"
out="$(shim="$scratch/bin-git" run "$repo" --id bad "${break_m1[@]}" --test 'echo RAN; exit 1' --repo skills --ticket 3 --ledger "$uw")" || true
check "a mutation whose worktree could not be created was not reported unknown" grep -q '^bad: unknown' <<<"$out"
check "its covering command ran anyway" bash -c '! grep -q RAN <<<"$1"' _ "$out"
check "its ledger row is not unknown" [ "$(row_field "$uw" bad outcome)" = unknown ]
check "the failed-worktree run left worktrees registered" [ "$(trees)" -eq 2 ]

# --- pipes and signals: the covering command's own exit status is the outcome ---
out="$(run "$repo" --id pp1 "${break_m1[@]}" --test 'false | tail -1; echo done-after-pipe; false | tail -1' --no-ledger)" || true
check "a failing test piped through tail read as a pass (pipe status, not the test's)" grep -q '^pp1: red' <<<"$out"
out="$(run "$repo" --id sp1 "${break_m1[@]}" --test 'echo x; kill -PIPE $$' --no-ledger)" || true
check "a SIGPIPE status was not reported unknown" grep -q '^sp1: unknown' <<<"$out"

# --- cleanup that reports rather than covers: a failed worktree removal exits non-zero ---
mkdir -p "$scratch/bin-norm"
cat >"$scratch/bin-norm/git" <<NORM
#!/usr/bin/env bash
prev=""
for a in "\$@"; do
  if [ "\$prev" = worktree ] && [ "\$a" = remove ]; then echo "fatal: shim refuses worktree remove" >&2; exit 128; fi
  prev="\$a"
done
exec "$real_git" "\$@"
NORM
chmod +x "$scratch/bin-norm/git"; cp "$scratch/bin/ps" "$scratch/bin-norm/ps"
rc=0; out="$(shim="$scratch/bin-norm" run "$repo" --id r1x "${break_m1[@]}" --test 'echo x; exit 1' --no-ledger)" || rc=$?
check "a run whose worktree removal failed still exited 0" [ "$rc" -ne 0 ]
check "a failed worktree removal was not reported" grep -q 'could not remove worktree' <<<"$out"
kept="$(printf '%s\n' "$out" | sed -n 's/.*keeping \([^ ]*\) -.*/\1/p' | head -1)"
if [ -z "$kept" ] || [ ! -d "$kept" ]; then
  echo "FAIL: the failed-removal run did not keep its root directory for a by-hand cleanup" >&2; fail=1
else
  for w in "$kept"/worktrees/*/; do [ -d "$w" ] && git -C "$repo" worktree remove --force "${w%/}" 2>/dev/null; done
  rm -rf "$kept"
fi
check "after the by-hand cleanup worktrees are still registered" [ "$(trees)" -eq 2 ]

# The EXIT/INT/TERM trap, witnessed: only an interrupted run proves it is wired, and a covering
# command still running after its worktree was force-removed holds the box.
( cd "$repo" && exec env HOME="$home" PATH="$scratch/bin:$PATH" bash "$checker" --worktree "$repo" --id kill1 "${break_m1[@]}" \
    --test "echo \$\$ >'$scratch/kill1.pid'; : >'$scratch/kill1.up'; sleep 8; : >'$scratch/kill1.late'" --no-ledger ) >/dev/null 2>&1 &
killpid=$!
for _ in $(seq 1 100); do [ -e "$scratch/kill1.up" ] && break; sleep 0.1; done
check "the interrupted run never got its covering command started" [ -e "$scratch/kill1.up" ]
kill -TERM "$killpid" 2>/dev/null || true
wait "$killpid" 2>/dev/null || true
check "an interrupted run left worktrees registered" [ "$(trees)" -eq 2 ]
child="$(cat "$scratch/kill1.pid" 2>/dev/null || true)"
if [ -n "$child" ] && kill -0 "$child" 2>/dev/null; then
  echo "FAIL: the covering command was still running after the interrupted run returned" >&2
  kill -KILL "$child" 2>/dev/null || true; fail=1
fi
check "an interrupted run's covering command ran to its end" [ ! -e "$scratch/kill1.late" ]

# --- concurrency across calls: --slots and the box bound live in the script (#957, #1325) ---
# Two calls started together. A two-phase barrier, not a timing window: only a sibling that
# reaches the barrier too is a sibling still running, and neither passes unless both ran at once.
pair() { # <name> <slots args...>: two concurrent calls, each noting whether it saw the other running
  local name="$1"; shift
  local id other
  rm -f "$scratch/$name".*
  for id in a b; do
    other=b; [ "$id" = b ] && other=a
    run "$repo" --id "$name$id" "${break_m1[@]}" --no-ledger "$@" --test "
      : >'$scratch/$name.$id.up'
      for _ in \$(seq 1 40); do [ -e '$scratch/$name.$other.up' ] && break; sleep 0.1; done
      if [ -e '$scratch/$name.$other.up' ]; then : >'$scratch/$name.$id.barrier'
        for _ in \$(seq 1 40); do [ -e '$scratch/$name.$other.barrier' ] && break; sleep 0.1; done
        [ -e '$scratch/$name.$other.barrier' ] && : >'$scratch/$name.$id.overlap'
      fi
      echo \"MUTANT-$name$id\"; exit 1" >"$scratch/$name.$id.out" 2>&1 &
  done
  wait
}
pair idle
check "two calls on an idle box did not run at the same time" \
  bash -c '[ -e "$1/idle.a.overlap" ] && [ -e "$1/idle.b.overlap" ]' _ "$scratch"
pair one --slots 1
check "--slots 1 let two calls overlap" bash -c '[ ! -e "$1/one.a.overlap" ] && [ ! -e "$1/one.b.overlap" ]' _ "$scratch"
check "--slots 1 lost a call instead of running it second" \
  bash -c 'grep -q "MUTANT-onea" "$1/one.a.out" && grep -q "MUTANT-oneb" "$1/one.b.out"' _ "$scratch"
mkdir -p "$scratch/bin-nops"; printf '#!/usr/bin/env bash\nexit 1\n' >"$scratch/bin-nops/ps"; chmod +x "$scratch/bin-nops/ps"
shim="$scratch/bin-nops" pair nops
check "an unreadable process table was read as an idle box: two calls overlapped" \
  bash -c '[ ! -e "$1/nops.a.overlap" ] && [ ! -e "$1/nops.b.overlap" ]' _ "$scratch"
mkdir -p "$scratch/bin-busy"; printf '#!/usr/bin/env bash\nfor _ in $(seq 1 30); do echo claude; done\n' >"$scratch/bin-busy/ps"; chmod +x "$scratch/bin-busy/ps"
shim="$scratch/bin-busy" pair busy
check "a full box refused or overlapped instead of running the calls one after another" \
  bash -c '[ ! -e "$1/busy.a.overlap" ] && grep -q MUTANT-busya "$1/busy.a.out" && grep -q MUTANT-busyb "$1/busy.b.out"' _ "$scratch"

# --- #1219 environment hygiene: each case gets its own fixture, reviewed through a linked worktree ---
py_setup='printf "def f():\n    return 1\n" >mod.py
printf "import mod\nassert mod.f() == 1, \"MUTANT-py: mod.f() no longer returns 1\"\n" >test_mod.py'
pymut=(--file mod.py --old 'return 1' --new 'return 5')

# A same-size mutation whose mtime matches the bytecode written by an earlier suite run in the
# same witness reads that stale .pyc and passes. `touch -d` pins the mtime.
t="$(make_repo pyrepo "$py_setup")"
out="$(run "$t" --id py1 "${pymut[@]}" --no-ledger --test 'python3 -c "import mod; assert mod.f() == 5" && m=$(stat -c %Y mod.py) && sed -i "s/return 5/return 6/" mod.py && touch -d "@$m" mod.py && python3 -c "import mod; assert mod.f() == 5, \"MUTANT-py: stale bytecode\""')" || true
check "a same-size, same-mtime Python edit did not read red with its own assertion (stale bytecode?)" \
  bash -c 'grep -q "^py1: red" <<<"$1" && grep -q "py1|.*MUTANT-py" <<<"$1"' _ "$out"
# A __pycache__ the witness already carries — tracked, compiled unchecked-hash — must be cleared.
t="$(make_repo pycache "$py_setup"'
python3 -c "import py_compile as p; p.compile(\"mod.py\", invalidation_mode=p.PycInvalidationMode.UNCHECKED_HASH)"
git add -f __pycache__')"
out="$(run "$t" --id pc1 --file mod.py --old 'return 1' --new 'return 22' --no-ledger --test 'python3 test_mod.py')" || true
check "a mutation under a tracked unchecked-hash __pycache__ did not read red with its own assertion" \
  bash -c 'grep -q "^pc1: red" <<<"$1" && grep -q "pc1|.*MUTANT-py" <<<"$1"' _ "$out"

# node_modules: a fresh worktree carries no ignored directory, so a Node suite would fail on a
# missing module and read red for the wrong reason. The link goes red only when readable.
node_test='if [ -e node_modules/marker ]; then echo "MARKER-PRESENT: reachable"; exit 1; fi; echo "no marker"; exit 0'
t="$(make_repo noderepo "$py_setup"'
printf "node_modules/\n" >.gitignore')"
mkdir -p "$t/node_modules" && : >"$t/node_modules/marker"
out="$(run "$t" --id n1 "${pymut[@]}" --no-ledger --test "$node_test")" || true
check "the witness did not see the reviewed tree's node_modules" bash -c 'grep -q "^n1: red" <<<"$1" && grep -q "n1|.*MARKER-PRESENT" <<<"$1"' _ "$out"
check "removing the witness deleted the reviewed tree's node_modules contents" [ -e "$t/node_modules/marker" ]
# #1969: a reviewed tree under a directory holding node_modules finds it by walking up; one
# outside the checkout finds the primary checkout's through the git common dir's parent.
t="$(make_repo nestedrepo "$py_setup"'
printf "node_modules/\n" >.gitignore')"
mkdir -p "$scratch/outer/node_modules" "$scratch/outer/sub" && : >"$scratch/outer/node_modules/marker"
git -C "$scratch/nestedrepo" worktree add -q --detach "$scratch/outer/sub/rev" HEAD
out="$(run "$scratch/outer/sub/rev" --id nn1 "${pymut[@]}" --no-ledger --test "$node_test")" || true
check "a worktree under a directory holding node_modules did not get it by walking up" grep -q 'nn1|.*MARKER-PRESENT' <<<"$out"
mkdir -p "$scratch/nestedrepo/node_modules" && : >"$scratch/nestedrepo/node_modules/marker"
out="$(run "$t" --id nc1 "${pymut[@]}" --no-ledger --test "$node_test")" || true
check "a worktree outside the checkout did not get the primary checkout's node_modules" grep -q 'nc1|.*MARKER-PRESENT' <<<"$out"
# Declared dependencies and no node_modules anywhere: a failure that says a module did not load
# is unknown; one that fails for its own reason is still red.
t="$(make_repo nonodes "$py_setup"'
printf "{\"devDependencies\": {\"playwright\": \"1\"}}\n" >package.json')"
out="$(run "$t" --id nx1 "${pymut[@]}" --no-ledger --test 'echo "Error [ERR_MODULE_NOT_FOUND]: Cannot find package playwright"; exit 1')" || true
check "a missing module was not unknown" bash -c 'grep -q "^nx1: unknown" <<<"$1" && ! grep -q "^nx1: red" <<<"$1"' _ "$out"
out="$(run "$t" --id nx2 "${pymut[@]}" --no-ledger --test 'echo "ASSERTION-FAILED: own message"; exit 1')" || true
check "an unrelated failure in the same tree was not red" grep -q '^nx2: red' <<<"$out"
# No node_modules anywhere and no dependencies declared: no link is invented.
t="$(make_repo plainrepo "$py_setup")"
out="$(run "$t" --id nl1 "${pymut[@]}" --no-ledger --test 'if [ -L node_modules ]; then echo UNEXPECTED-LINK; exit 1; fi; exit 0')" || true
check "a reviewed tree without node_modules still got a link in its witness" grep -q '^nl1: HOLLOW' <<<"$out"
# A Rust suite in the witness builds into the witness's own target dir (#1696).
out="$(run "$t" --id cg1 "${pymut[@]}" --no-ledger --test 'echo "CARGO-TARGET: ${CARGO_TARGET_DIR:-unset}"; exit 1')" || true
check "the witness did not get its own CARGO_TARGET_DIR" grep -Eq 'CARGO-TARGET: .*/worktrees/cg1/target' <<<"$out"

# A Python repo with a `uv.lock` gets its own `uv sync` in each witness (#1528), never a link to
# the reviewed tree's `.venv`. A stub `uv` records where it ran and leaves a `.venv` with that record.
mkdir -p "$scratch/bin-uv"
cat >"$scratch/bin-uv/uv" <<'UV'
#!/usr/bin/env bash
[ "${STUB_UV_FAIL:-0}" = 1 ] && { echo "uv: sync failed (stub)" >&2; exit 1; }
mkdir -p .venv && printf '%s\n' "$PWD" >.venv/ran-in && printf '%s\n' "$*" >.venv/args
printf '%s\n' "${UV_PROJECT_ENVIRONMENT-unset}" >.venv/env
UV
chmod +x "$scratch/bin-uv/uv"
uv_setup="$py_setup"'
printf ".venv/\n" >.gitignore
printf "version = 1\n" >uv.lock'
t="$(make_repo uvrepo "$uv_setup")"
mkdir -p "$t/.venv" && printf '%s\n' "$t" >"$t/.venv/ran-in"
out="$(UV_PROJECT_ENVIRONMENT=/nonexistent/shared-venv PATH="$scratch/bin-uv:$PATH" run "$t" --id uv1 "${pymut[@]}" --no-ledger \
  --test 'if [ -L .venv ]; then echo "SYMLINKED-VENV"; exit 1; fi; if [ "$(cat .venv/ran-in 2>/dev/null)" = "$PWD" ]; then echo "SYNCED-HERE: ARGS: $(cat .venv/args); ENV: $(cat .venv/env)"; exit 1; fi; echo "no synced .venv"; exit 0')" || true
check "a repo with a uv.lock did not get a uv sync run inside its witness" grep -q 'uv1|.*SYNCED-HERE' <<<"$out"
check "the sync did not run with --frozen and without UV_PROJECT_ENVIRONMENT" grep -q 'ARGS: sync --frozen --quiet; ENV: unset' <<<"$out"
check "the witness's sync wrote into the reviewed tree's .venv" [ "$(cat "$t/.venv/ran-in")" = "$t" ]
t="$(make_repo nouvrepo "$py_setup")"
out="$(PATH="$scratch/bin-uv:$PATH" run "$t" --id uv2 "${pymut[@]}" --no-ledger --test 'if [ -e .venv ] || [ -L .venv ]; then echo UNEXPECTED-VENV; exit 1; fi; exit 0')" || true
check "a repo without a uv.lock got a .venv in its witness" grep -q '^uv2: HOLLOW' <<<"$out"
check "a repo without a uv.lock was not told its .venv is left unset" grep -q 'no uv.lock at HEAD.*\.venv.*unset' <<<"$out"
t="$(make_repo uvuntracked "$py_setup")"; printf 'version = 1\n' >"$t/uv.lock"
out="$(PATH="$scratch/bin-uv:$PATH" run "$t" --id uv4 "${pymut[@]}" --no-ledger --test 'exit 0')" || true
check "an uncommitted uv.lock was neither synced nor reported" grep -q 'no uv.lock at HEAD' <<<"$out"
t="$(make_repo uvfail "$uv_setup")"
out="$(STUB_UV_FAIL=1 PATH="$scratch/bin-uv:$PATH" run "$t" --id uv3 "${pymut[@]}" --no-ledger --test 'echo RAN; exit 1')" || true
check "a failed uv sync was not reported unknown" grep -q '^uv3: unknown' <<<"$out"

# --- #1547: a killed run is the case the exit sweep misses; each run prunes old witness.* dirs ---
prune_home="$cache"
mkdir -p "$prune_home/witness.OLD001/worktrees" "$prune_home/witness.MID001/worktrees" \
  "$prune_home/witness.NEW001/worktrees" "$prune_home/witness.GONE01/worktrees/orphan" "$prune_home/keep.OLD001"
git -C "$repo" worktree add --detach -q "$prune_home/witness.OLD001/worktrees/stale" HEAD
git -C "$repo" worktree add --detach -q "$prune_home/witness.MID001/worktrees/mid" HEAD
git -C "$repo" worktree add --detach -q "$prune_home/witness.NEW001/worktrees/live" HEAD
touch -d '8 days ago' "$prune_home/witness.OLD001" "$prune_home/keep.OLD001" "$prune_home/witness.GONE01"
touch -d '180 hours ago' "$prune_home/witness.MID001"
touch -d '6 days ago' "$prune_home/witness.NEW001"
out="$(run "$repo" --id pr1 "${break_m1[@]}" --test 'exit 1' "${LA[@]}")" || true
for d in OLD001 MID001 GONE01; do
  check "witness.$d (older than 7 days; GONE01 holds a directory git does not list) was not pruned" [ ! -e "$prune_home/witness.$d" ]
done
check "a pruned witness's worktree is still registered" bash -c '! git -C "$1" worktree list --porcelain | grep -q "witness\.\(OLD001\|MID001\)"' _ "$repo"
check "a witness.* directory under 7 days old was pruned" [ -d "$prune_home/witness.NEW001" ]
check "the prune removed an entry that is not a witness.* directory" [ -d "$prune_home/keep.OLD001" ]
git -C "$repo" worktree remove --force "$prune_home/witness.NEW001/worktrees/live" 2>/dev/null
rm -rf "$prune_home/witness.NEW001" "$prune_home/keep.OLD001"
# A prune that cannot remove a worktree keeps its directory, says so, and still runs the review.
mkdir -p "$prune_home/witness.STUCK1/worktrees"
git -C "$repo" worktree add --detach -q "$prune_home/witness.STUCK1/worktrees/stuck" HEAD
touch -d '8 days ago' "$prune_home/witness.STUCK1"
mkdir -p "$scratch/bin-gitfail"
cat >"$scratch/bin-gitfail/git" <<GITSHIM
#!/usr/bin/env bash
case "\$*" in *"worktree remove"*witness.STUCK1*) echo "git: refused (stub)" >&2; exit 1;; esac
exec "$real_git" "\$@"
GITSHIM
chmod +x "$scratch/bin-gitfail/git"; cp "$scratch/bin/ps" "$scratch/bin-gitfail/ps"
out="$(shim="$scratch/bin-gitfail" run "$repo" --id pr2 "${break_m1[@]}" --test 'echo x; exit 1' "${LA[@]}")" || true
check "a prune whose worktree removal failed deleted the directory anyway" [ -d "$prune_home/witness.STUCK1" ]
check "a failed prune was not reported" grep -q 'could not prune .*witness.STUCK1' <<<"$out"
check "a failed prune stopped the review" grep -q '^pr2: red' <<<"$out"
git -C "$repo" worktree remove --force "$prune_home/witness.STUCK1/worktrees/stuck" 2>/dev/null
rm -rf "$prune_home/witness.STUCK1"

# --- #1854: a mutant that hangs ends at its limit, reads `red (timeout)`, and leaves no child ---
tl="$scratch/timeout.jsonl"
hang="echo 'MUTANT-h1: hanging'; sh -c 'echo \$\$ >$scratch/h1.gpid; exec sleep 30' & wait"
t_start=$(date +%s)
out="$(run "$repo" --id h1 "${break_m1[@]}" --test "$hang" --timeout 2 --repo skills --ticket 4 --ledger "$tl")" ||
  { echo "FAIL: the timeout run exited non-zero" >&2; echo "$out" >&2; fail=1; }
check "a 2 s limit let the hanging mutant run $(( $(date +%s) - t_start )) s" [ $(( $(date +%s) - t_start )) -lt 15 ]
check "the hanging mutant was not reported 'red (timeout)'" grep -q '^h1: red (timeout)' <<<"$out"
check "the hanging mutant's ledger row is '$(row_field "$tl" h1 outcome timeout)', wanted 'red True'" [ "$(row_field "$tl" h1 outcome timeout)" = "red True" ]
gp="$(cat "$scratch/h1.gpid" 2>/dev/null || true)"
if [ -z "$gp" ]; then echo "FAIL: the hanging mutant's grandchild never started" >&2; fail=1
elif kill -0 "$gp" 2>/dev/null; then echo "FAIL: the hanging mutant's grandchild $gp outlived the run" >&2; kill -KILL "$gp" 2>/dev/null || true; fail=1; fi
# C1: a suite's own exit 124 well under the limit is its own red, never a timeout.
out="$(run "$repo" --id h3 "${break_m1[@]}" --test 'echo "MUTANT-h3: own 124"; exit 124' --timeout 30 --repo skills --ticket 4 --ledger "$tl")" || true
check "a mutant exiting 124 under the limit was labelled a timeout" bash -c '! grep -q "red (timeout)" <<<"$1" && grep -q "^h3: red" <<<"$1"' _ "$out"
check "h3's ledger row is not a plain red" [ "$(row_field "$tl" h3 outcome)" = red ]
# A baseline sets the limit at 3x with a 60 s floor; with neither flag it is 240 s, and says so.
limit_of() { run "$repo" --id lim1 "${break_m1[@]}" --test 'exit 1' --no-ledger "$@" | sed -n 's/^witness check: per-mutant limit \([0-9]*\) s.*/\1/p'; }
check "no flags did not give the 240 s default: '$(limit_of)'" [ "$(limit_of)" = 240 ]
check "the default limit's notice does not say no baseline was given" \
  bash -c 'grep -q "no --baseline-seconds given" <<<"$1"' _ "$(run "$repo" --id lim2 "${break_m1[@]}" --test 'exit 1' --no-ledger)"
check "baseline 10 s did not give the 60 s floor" [ "$(limit_of --baseline-seconds 10)" = 60 ]
check "baseline 100 s did not give 300 s" [ "$(limit_of --baseline-seconds 100)" = 300 ]

# --- --with-working-tree: the witness is the tree as it stands (a fan-out sub-worker cannot commit) ---
wt_repo="$(make_repo wtrepo 'printf "committed\n" >a.txt; printf "keep\n" >gone.txt; printf "x\n" >.gitignore')"
printf 'edited\n' >"$wt_repo/a.txt"; rm "$wt_repo/gone.txt"; printf 'brand new\n' >"$wt_repo/fresh.txt"
mkdir -p "$wt_repo/.scratch" && printf 'junk\n' >"$wt_repo/.scratch/j.txt"
out="$(run "$wt_repo" --with-working-tree --id wt1 --file a.txt --old edited --new MUTATED --no-ledger \
  --test 'cat a.txt fresh.txt; ls gone.txt .scratch 2>&1; exit 1')" || true
got="$(printf '%s\n' "$out" | sed -n 's/^  wt1| //p' | paste -sd'|')"
case "$got" in 'MUTATED|brand new|'*) ;; *) echo "FAIL: the witness is not the working tree (edit and untracked file expected); got: $got" >&2; fail=1 ;; esac
case "$got" in *'No such file'*'No such file'*) ;; *) echo "FAIL: a deleted file or .scratch/ reached the witness; got: $got" >&2; fail=1 ;; esac
# Without the flag the same --old is not at HEAD, and is refused by its count.
rc=0; out="$(run "$wt_repo" --id wt2 --file a.txt --old edited --new MUTATED --no-ledger --test 'exit 1')" || rc=$?
{ [ "$rc" -eq 2 ] && grep -q 'occurs 0 times' <<<"$out"; } || { echo "FAIL: HEAD-only mode saw the uncommitted edit (exit $rc)" >&2; fail=1; }
# An untracked file can be the mutated file.
out="$(run "$wt_repo" --with-working-tree --id wt3 --file fresh.txt --old 'brand new' --new NEWER --no-ledger --test 'cat fresh.txt; exit 1')" || true
check "an untracked file was not mutable under --with-working-tree" grep -q 'wt3| NEWER' <<<"$out"

# --- C3: a checkout that differs from HEAD's blob (eol=crlf): the witness's own exactly-once check ---
crlf_repo="$(make_repo crlfrepo 'printf "* text=auto\n*.crlf text eol=crlf\n" >.gitattributes; printf "one\ntwo\n" >c.crlf')"
out="$(run "$crlf_repo" --id crlf1 --file c.crlf --old $'one\ntwo' --new X --no-ledger --test 'echo RAN; exit 1')" || true
check "a --old that matches HEAD's blob but not the witness's checkout was not reported unknown" \
  bash -c 'grep -q "^crlf1: unknown" <<<"$1" && ! grep -q "RAN" <<<"$1"' _ "$out"

# --- C1: a flock that fails for a reason other than contention must not wait forever ---
mkdir -p "$scratch/bin-noflock"; cp "$scratch/bin/ps" "$scratch/bin-noflock/ps"
printf '#!/usr/bin/env bash\nexit 127\n' >"$scratch/bin-noflock/flock"; chmod +x "$scratch/bin-noflock/flock"
rc=0; out="$(shim="$scratch/bin-noflock" timeout 20 bash -c "$(declare -f run); checker='$checker' home='$home' repo='$repo' shim='$scratch/bin-noflock' scratch='$scratch'; run \"\$repo\" --id fl1 --file m1.py --old 'assert 1 == 1' --new 'assert 1 == 2' --test 'exit 1' --no-ledger")" || rc=$?
{ [ "$rc" -eq 1 ] && grep -q 'flock failed' <<<"$out"; } || { echo "FAIL: a failing flock did not exit 1 naming it (exit $rc): $out" >&2; fail=1; }

# --- #1708: no doc shows the sourced `--mutate <file>` form, or a hand-rolled runner ---
# The skill, the briefs, the agent file and the scripts are the docs a reviewer or worker reads.
# Dated records under docs/research/ describe history and stay.
doc_files=( "$repo_root/multi-axis-code-review/SKILL.md" "$repo_root"/multi-axis-code-review/briefs/*.md
  "$repo_root/multi-axis-code-review/render-brief.py" "$repo_root/multi-axis-code-review/witness-check.sh"
  "$repo_root/implement/SKILL.md" "$repo_root"/implement/briefs/*.md "$repo_root/implement/fanout-brief.py"
  "$repo_root/flow/claude/agents/diff-reviewer.md"
  "$repo_root/mutation-audit/witness.sh" "$repo_root"/tests/review_cache_e2e_golden/*.md )
left="$(grep -nE -e '--mutate <|--mutate "|--mutate \$|defines? `mutate`|defining `mutate`|write one file, outside the checkout|a file outside the checkout defining|worktree add --detach [^ ]*mutation|cp --parents' "${doc_files[@]}" 2>/dev/null | cut -c1-200 || true)"
check "a doc still shows the sourced --mutate file form:
$left" [ -z "$left" ]
for f in "$repo_root/multi-axis-code-review/SKILL.md" "$repo_root/flow/claude/agents/diff-reviewer.md" \
         "$repo_root/multi-axis-code-review/briefs/correctness.md" "$repo_root/implement/SKILL.md" \
         "$repo_root/implement/briefs/fanout-worker.md"; do
  check "$f does not show the flag form" grep -q -e '--old' "$f"
done
# The ban is stated once, in the skill that owns the script; the other docs show the flag form.
check "multi-axis-code-review/SKILL.md does not say no other runner may be used" \
  grep -qi 'no other runner may be used' "$repo_root/multi-axis-code-review/SKILL.md"

if [ "$fail" -eq 0 ]; then
  echo "PASS multi-axis-code-review/witness-check.test.sh"
else
  exit 1
fi
