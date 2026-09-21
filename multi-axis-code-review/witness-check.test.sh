#!/usr/bin/env bash
# Guards #938, #939 and #957: the hollow-witness check has one owner
# (correctness), it re-runs the covering suite in a throwaway git worktree
# rather than the whole gate over a whole-tree copy, and it runs its mutations
# concurrently — each with its own worktree, its own captured output, and an
# unreached mutation reported as `unknown` rather than as a pass.
# Prose assertions over two skill files; there is no harness that runs a
# skill's own prose.
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

# Each axis brief scoped to its own bullet block: a needle this generic is
# satisfied by the wrong axis otherwise, which is the whole defect #938 names.
section() { # <file> <start-marker> <end-marker>
  awk -v s="$2" -v e="$3" '
    index($0, s) { on = 1; next }
    on && index($0, e) { exit }
    on { print }
  ' "$1"
}
flatten() { tr '\n' ' ' | tr -s ' '; }

standards="$(section "$skill" '**Standards sub-agent prompt**' '**Spec sub-agent prompt**' | flatten)"
spec="$(section "$skill" '**Spec sub-agent prompt**' '**Correctness sub-agent prompt**' | flatten)"
correctness="$(section "$skill" '**Correctness sub-agent prompt**' '**What the witness check costs' | flatten)"
costs="$(section "$skill" '**What the witness check costs' 'If the spec is missing' | flatten)"
[ -n "$costs" ] || { echo "FAIL: could not extract the witness-cost section from $skill" >&2; exit 1; }
for pair in "standards:$standards" "spec:$spec" "correctness:$correctness"; do
  [ -n "${pair#*:}" ] || { echo "FAIL: could not extract the ${pair%%:*} axis brief from $skill" >&2; exit 1; }
done

fail=0
check_in() {
  local haystack="$1" needle="$2" where="$3"
  case "$haystack" in
    *"$needle"*) ;;
    *) echo "FAIL: $where is missing: $needle" >&2; fail=1 ;;
  esac
}
check_not_in() {
  local haystack="$1" needle="$2" where="$3"
  case "$haystack" in
    *"$needle"*) echo "FAIL: $where still carries: $needle" >&2; fail=1 ;;
  esac
}

# #938: one owner. Correctness keeps the check; standards loses it. Two opus
# agents mutating the same tests over the same diff cost two dispositions for
# one finding (#910 round 1 reported S1 and C2 as the same finding).
check_in "$correctness" 'strip the constraint under test' 'the correctness axis brief'
check_not_in "$standards" 'strip the constraint under test' 'the standards axis brief'
check_not_in "$standards" 'hollow witness' 'the standards axis brief'
check_not_in "$spec" 'strip the constraint under test' 'the spec axis brief'

# The count is the assertion a needle cannot make: a witness brief restated
# somewhere else in § 4 is the same duplicated mutation pass.
spawn="$(sed -n '/^###[[:space:]]*4\./,/^###[[:space:]]/{/^###[[:space:]]*4\./d; /^###[[:space:]]/d; p}' "$skill")"
[ -n "$spawn" ] || { echo "FAIL: $skill has no § 4 step" >&2; exit 1; }
witness="$(printf '%s\n' "$spawn" | grep -cF 'strip the constraint under test' || true)"
if [ "$witness" -ne 1 ]; then
  echo "FAIL: § 4 states the witness check in $witness axis briefs, not 1" >&2
  fail=1
fi

# The standing brief names the same one owner: diff-reviewer.md's Axes section
# attaches the check to correctness and to no other axis.
# `|| true` because an absent phrase makes `grep -o` exit 1, and under
# `set -euo pipefail` the suite would then die here with no output at all —
# red for the right reason, telling the operator nothing.
reviewer_witness="$(flatten <"$reviewer" | { grep -oF 'strip the constraint under test' || true; } | wc -l)"
if [ "$reviewer_witness" -ne 1 ]; then
  echo "FAIL: flow/claude/agents/diff-reviewer.md states the witness check $reviewer_witness times, not 1" >&2
  fail=1
fi

# #961: a guard's body mutation reddens the unit test that calls the guard
# directly and says nothing about whether anything calls it. The call-site
# mutation is its own required step in the correctness brief, with a stated
# meaning for a survivor, and it is not restated in another axis.
check_in "$correctness" 'mutate its call site' 'the correctness axis brief'
check_in "$correctness" 'every entry point the guard exists to protect' 'the correctness axis brief'
check_in "$correctness" 'unprotected entry point' 'the correctness axis brief'
check_not_in "$standards" 'mutate its call site' 'the standards axis brief'
check_not_in "$spec" 'unprotected entry point' 'the spec axis brief'
check_in "$costs" 'call-site mutation' 'the witness-check cost section'
callsite="$(printf '%s\n' "$spawn" | grep -cF 'unprotected entry point' || true)"
[ "$callsite" -eq 1 ] || { echo "FAIL: § 4 states the call-site finding in $callsite places, not 1" >&2; fail=1; }

# #939, first cost: the brief never said what to re-run, so an axis could take
# `bash tests/all.sh` (2m51s wall, 62 suites) once per mutated test. It names
# the covering suite, and says the whole gate is not this axis's to re-run.
# The brief is what the sub-agent is handed, so it carries the mechanics itself
# rather than pointing "below" at prose the caller keeps. The old end marker
# swept that prose into "$correctness", so these needles passed on text no
# sub-agent ever receives — and this build's own correctness prompt had to
# hand-inline the two commands, which is the tell.
check_in "$correctness" 'the suite that covers' 'the correctness axis brief'
check_in "$correctness" 'never the whole gate' 'the correctness axis brief'
check_in "$correctness" 'git worktree add --detach' 'the correctness axis brief'
check_in "$correctness" 'git worktree remove --force' 'the correctness axis brief'
check_not_in "$correctness" 'scratch copy of the tree' 'the correctness axis brief'

# #957: the mutations run together, and the pairing survives the concurrency.
# The serial loop cost the covering suite's runtime once per mutated test —
# 31.96s x 10 on caneff/sudokupad-art, a 22-minute correctness pass.
# Whole clauses, not single common words: 'unknown' or 'sequential' on their
# own are satisfied by prose that says the opposite, which is the same shape as
# the needles the count assertions above exist to replace.
check_in "$correctness" 'launch them at once' 'the correctness axis brief'
check_in "$correctness" 'its own worktree and its own captured output' 'the correctness axis brief'
# Class 1, the day's recurring defect: a mutation that never ran is not a pass.
check_in "$correctness" 'never counted as an assertion that held' 'the correctness axis brief'
# The bound, the count that produces it, and the degradation. The brief is what
# the sub-agent is handed, so it carries the counting command itself rather than
# pointing at prose only the caller reads (#939).
check_in "$correctness" 'ps -eo comm= | grep -cx claude' 'the correctness axis brief'
check_in "$correctness" 'never `ps aux | grep`' 'the correctness axis brief'
check_in "$costs" 'ps -eo comm= | grep -cx claude' 'the witness-cost section'
# The anti-pattern is asserted with its negation attached: a bare 'ps aux'
# needle passes just as well on prose recommending it.
check_in "$costs" 'never `ps aux | grep`' 'the witness-cost section'
check_in "$costs" 'the sequential check this replaces' 'the witness-cost section'
# #957: nothing is restored, because nothing is shared. Said out loud so a
# later pass does not reintroduce a restore that reaches into the checkout.
check_in "$costs" 'nothing to restore' 'the witness-cost section'

# #939's real reason, not just its price: a byte copy of a LINKED worktree
# shares the checkout's index, so `cp -a` is not weak isolation, it is none.
check_in "$costs" 'gitdir pointer' 'the witness-cost section'
check_in "$costs" 'cp -a' 'the witness-cost section'
# The three axis briefs point at the one copy of the defect classes; the
# correctness axis, which owns the witness check since #938, names the two
# classes it is most exposed to.
for axis in standards spec correctness; do
  eval "brief=\$$axis"
  check_in "$brief" 'docs/agents/defect-classes.md' "the $axis axis brief"
done
check_in "$correctness" 'class 1' 'the correctness axis brief'
check_in "$correctness" 'class 3' 'the correctness axis brief'
[ -f "$here/../docs/agents/defect-classes.md" ] ||
  { echo "FAIL: the axis briefs point at a docs/agents/defect-classes.md that does not exist" >&2; fail=1; }
# The standing brief says the same, since an axis reads it whether or not the
# caller's paste survived. A bare 'worktree' needle would pass on `git -C
# <worktree>`, which that file already carried before this change.
reviewer_text="$(flatten <"$reviewer")"
check_in "$reviewer_text" 'never in a copy of it' flow/claude/agents/diff-reviewer.md
check_not_in "$reviewer_text" 'a witness check runs on a copy' flow/claude/agents/diff-reviewer.md

# Prose can claim isolation and concurrency; only running the documented
# recipe witnesses either. Extracting it out of SKILL.md rather than retyping
# it here is what keeps the test honest — a copy in this file would pass
# forever while the doc drifted.
recipe="$(awk '
  /^```$/ { if (inb) { if (buf ~ /mutate\(\)/) printf "%s", buf; buf = ""; inb = 0 }
            else inb = 1
            next }
  inb { buf = buf $0 "\n" }
' "$skill")"
case "$recipe" in
  *'mutate()'*) ;;
  *) echo "FAIL: could not extract the concurrent witness recipe from $skill" >&2; exit 1 ;;
esac

scratch="$(mktemp -d)" || { echo "FAIL: mktemp -d" >&2; exit 1; }
trap 'git -C "$scratch/repo" worktree prune 2>/dev/null; rm -rf "$scratch"' EXIT
(
  cd "$scratch"
  git init -q -b main repo
  cd repo
  git config user.email t@example.com
  git config user.name t
  printf 'assert 1 == 1\n' >m1.py
  printf 'assert 1 == 1\n' >m2.py
  git add m1.py m2.py
  git commit -qm base
  # The reviewed tree is a LINKED worktree, which is what every review in this
  # lane runs on. Its `.git` is a file holding a gitdir pointer, so a byte copy
  # of it shares this repo's index — the failure `cp -a` hides and the reason
  # the recipe is a worktree (2026-09-20: a worker's two `git rm --cached` runs
  # inside its "isolated" copy staged deletions in the real checkout).
  git worktree add -q --detach "$scratch/reviewed" HEAD
) || { echo "FAIL: could not build the scratch repo" >&2; exit 1; }
repo="$scratch/reviewed"
[ -f "$repo/.git" ] ||
  { echo "FAIL: the fixture's reviewed tree is not a linked worktree" >&2; exit 1; }

# The stand-in for "strip this test's constraint and run its covering suite".
# It records the pair (id, worktree), waits for its sibling to start, and notes
# whether both worktrees were on disk at that instant — the honest witness that
# the launch really was concurrent, rather than a wall-clock assertion that
# goes flaky on a loaded box. Then it fails, with a message of its own: a
# working witness check MAKES the covering suite fail.
cat >"$scratch/mutate.sh" <<MUTATE
#!/usr/bin/env bash
id="\$1"; wt="\$2"
scratch="$scratch"
printf '%s\n' "\$wt" >"\$scratch/\$id.wt"
: >"\$scratch/\$id.up"
other="\${id%?}"; case "\$id" in *1) other="\${other}2";; *2) other="\${other}1";; esac
# A two-phase barrier, not "the sibling started": in a SERIAL run the second
# mutation still finds the first one's marker and its worktree on disk, since
# nothing is removed until the whole run ends. Only a sibling that reaches the
# barrier too is a sibling still running, and neither can pass the barrier
# unless both were launched — which is the assertion, with no timing window.
for _ in \$(seq 1 50); do [ -e "\$scratch/\$other.up" ] && break; sleep 0.1; done
if [ -e "\$scratch/\$other.up" ]; then
  : >"\$scratch/\$id.barrier"
  for _ in \$(seq 1 50); do [ -e "\$scratch/\$other.barrier" ] && break; sleep 0.1; done
  if [ -e "\$scratch/\$other.barrier" ] && [ -d "\$wt" ] &&
     [ -d "\$(cat "\$scratch/\$other.wt" 2>/dev/null)" ]; then
    : >"\$scratch/\$id.overlap"
  fi
fi
printf 'assert 1 == 2\n' >"\$wt/\$id.py"
git -C "\$wt" rm -q --cached "\$id.py" 2>/dev/null
: >"\$3"
echo "MUTANT-\$id: covering suite red, its own message"
exit 1
MUTATE

substitute() { # <ids> <mutate body> -> a runnable script on stdout
  local body="${2//&/\\&}"   # & in a sed replacement means the whole matched line
  printf '%s\n' "$recipe" |
    sed -e "s|^worktree=<.*|worktree=$repo|" \
        -e "s|^ids=<.*|ids=\"$1\"|" \
        -e "s|^mutate() .*|mutate() { $body; }|"
}

# The recipe computes its bound from the live process table, so on a loaded box
# it degrades to sequential — the behaviour #957 mandates — and an unconditional
# overlap assertion would go red for the machine's state rather than the code's.
# A `ps` shim pins the box instead: this run gets an idle one, the run below a
# full one, and both assertions become deterministic.
mkdir -p "$scratch/bin"
real_git="$(command -v git)"
cat >"$scratch/bin/ps" <<'IDLE'
#!/usr/bin/env bash
printf 'claude\nbash\ninit\n'
IDLE
chmod +x "$scratch/bin/ps"

substitute 'm1 m2' "bash \"$scratch/mutate.sh\" \"\$1\" \"\$2\" \"\$3\"" >"$scratch/recipe.sh"
grep -q "^worktree=$repo\$" "$scratch/recipe.sh" ||
  { echo "FAIL: the recipe's worktree placeholder did not substitute" >&2; exit 1; }
grep -q '^ids="m1 m2"$' "$scratch/recipe.sh" ||
  { echo "FAIL: the recipe's ids placeholder did not substitute" >&2; exit 1; }
grep -q '^mutate() { bash ' "$scratch/recipe.sh" ||
  { echo "FAIL: the recipe's mutate placeholder did not substitute" >&2; exit 1; }

# The run itself exits non-zero or not depending on how the doc ends it; what
# this suite asserts is what it left behind, not its status.
( cd "$repo" && PATH="$scratch/bin:$PATH" bash "$scratch/recipe.sh" ) >"$scratch/run.out" 2>&1 || true

# Concurrent, asserted by the two worktrees existing at the same instant.
# Serialising the launch fails exactly here, and for its own reason: the first
# mutation waits out its 10s for a sibling that has not been started yet.
for id in m1 m2; do
  [ -e "$scratch/$id.overlap" ] || {
    echo "FAIL: $id never saw the other mutation's worktree — the launch was serial" >&2
    fail=1; }
done

# Each message stays paired with the mutation that produced it. Reading the
# message rather than the exit code is what catches defect class 3, and N
# concurrent reds collected into one stream is how that pairing is lost.
for id in m1 m2; do
  other=m1; [ "$id" = m1 ] && other=m2
  if ! grep -q "MUTANT-$id" "$scratch/run.out"; then
    echo "FAIL: the run never reported $id's own failure message" >&2
    fail=1
  fi
  # The message LINE itself carries its id: a header above a bare concatenation
  # of N suite outputs satisfies a looser needle and loses exactly the pairing
  # this check exists for, once two mutations are red at the same time.
  if ! grep -q "$id|.*MUTANT-$id" "$scratch/run.out"; then
    echo "FAIL: $id's message line is not tagged with $id in the run output" >&2
    fail=1
  fi
  if grep -q "$id|.*MUTANT-$other" "$scratch/run.out"; then
    echo "FAIL: $other's message was attributed to $id" >&2
    fail=1
  fi
done

for id in m1 m2; do
  if [ "$(cat "$repo/$id.py")" != 'assert 1 == 1' ]; then
    echo "FAIL: the witness recipe wrote $id's mutation back into the checkout" >&2
    fail=1
  fi
done
if [ -n "$(git -C "$repo" status --porcelain)" ]; then
  echo "FAIL: the witness recipe left the checkout dirty" >&2
  fail=1
fi
# The index directly, because porcelain catches a staged removal only by luck:
# a `git config`, ref, or object write inside a `cp -a` copy leaves porcelain
# clean and the real repository changed anyway.
if [ -n "$(git -C "$repo" diff --cached --name-only)" ]; then
  echo "FAIL: the witness recipe staged its mutation in the reviewed tree's index" >&2
  git -C "$repo" diff --cached --name-only >&2
  fail=1
fi
# A worktree left registered stalls the next `git worktree remove` and any
# later `merge-cleanup` on this repo; a bare `rm -rf` would leave exactly that.
# Every mutation failed here — the ordinary outcome of a check that works — so
# this is the failure path's cleanup, N traps and not one.
trees="$(git -C "$repo" worktree list | wc -l)"
if [ "$trees" -ne 2 ]; then
  echo "FAIL: the witness recipe left $trees worktrees registered, not the fixture's 2" >&2
  git -C "$repo" worktree list >&2
  fail=1
fi
for id in m1 m2; do
  if [ -e "$(cat "$scratch/$id.wt" 2>/dev/null)" ]; then
    echo "FAIL: the covering suite failing left $id's throwaway worktree on disk" >&2
    fail=1
  fi
done

# Defect class 1, the one this ticket would refuse a PR over: a mutation whose
# worktree never got created must report as `unknown` by name, never as a pass.
# The `git` shim refuses exactly one `worktree add`, so the failure is the one
# under test and not a broken fixture.
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
chmod +x "$scratch/bin-git/git"

substitute 'ok bad' ": >\"\$3\"; echo \"MUTANT-\$1: covering suite red\"; exit 1" >"$scratch/recipe-unknown.sh"
( cd "$repo" && PATH="$scratch/bin-git:$scratch/bin:$PATH" bash "$scratch/recipe-unknown.sh" ) \
  >"$scratch/unknown.out" 2>&1 || true
if ! grep -i 'unknown' "$scratch/unknown.out" | grep -q 'bad'; then
  echo "FAIL: a mutation whose worktree could not be created was not reported as unknown" >&2
  cat "$scratch/unknown.out" >&2
  fail=1
fi
if ! grep -q 'MUTANT-ok' "$scratch/unknown.out"; then
  echo "FAIL: the reachable mutation was lost when its sibling could not start" >&2
  fail=1
fi
trees_after="$(git -C "$repo" worktree list | wc -l)"
if [ "$trees_after" -ne 2 ]; then
  echo "FAIL: the unknown-mutation run left $trees_after worktrees registered, not 2" >&2
  git -C "$repo" worktree list >&2
  fail=1
fi

# Class 1 on the bound itself (C3): a process table that cannot be read must
# mean a full box, not an idle one. The buggy form counts 0 claude processes and
# runs at maximum concurrency on an unknown machine, so the witness is the
# ABSENCE of overlap — these two mutations must run one after the other.
mkdir -p "$scratch/bin-nops"
{ echo '#!/usr/bin/env bash'; echo 'exit 1'; } >"$scratch/bin-nops/ps"
chmod +x "$scratch/bin-nops/ps"
substitute 'u1 u2' "bash \"$scratch/mutate.sh\" \"\$1\" \"\$2\" \"\$3\"" >"$scratch/recipe-nops.sh"
( cd "$repo" && PATH="$scratch/bin-nops:$PATH" bash "$scratch/recipe-nops.sh" ) \
  >"$scratch/nops.out" 2>&1 || true
for id in u1 u2; do
  if ! grep -q "MUTANT-$id" "$scratch/nops.out"; then
    echo "FAIL: with no readable process table the witness check lost mutation $id" >&2
    fail=1
  fi
  if [ -e "$scratch/$id.overlap" ]; then
    echo "FAIL: an unreadable process table was read as an idle box — $id ran concurrently" >&2
    fail=1
  fi
done

# A full box degrades to sequential and still runs every mutation. The ticket
# refuses the other reading: a check that declines because the machine is loaded
# is worse than a slow one, and nothing else here would notice a refusal.
mkdir -p "$scratch/bin-busy"
{ echo '#!/usr/bin/env bash'; echo 'for _ in $(seq 1 30); do echo claude; done'; } >"$scratch/bin-busy/ps"
chmod +x "$scratch/bin-busy/ps"
substitute 'b1 b2' ": >\"\$3\"; echo \"MUTANT-\$1: covering suite red\"; exit 1" >"$scratch/recipe-busy.sh"
( cd "$repo" && PATH="$scratch/bin-busy:$PATH" bash "$scratch/recipe-busy.sh" ) \
  >"$scratch/busy.out" 2>&1 || true
for id in b1 b2; do
  if ! grep -q "MUTANT-$id" "$scratch/busy.out"; then
    echo "FAIL: on a full box the witness check lost mutation $id instead of running it sequentially" >&2
    cat "$scratch/busy.out" >&2
    fail=1
  fi
done

# The EXIT/INT/TERM trap, witnessed: the normal tail cleans up by itself, so
# only an interrupted run proves the trap is wired. A minutes-long check ended
# with ctrl-C is the ordinary way this happens, and N leaked worktrees stall the
# next `worktree remove` and any later `merge-cleanup`.
cat >"$scratch/sleeper.sh" <<SLEEP
#!/usr/bin/env bash
printf '%s\n' "\$2" >"$scratch/\$1.wt"
printf '%s\n' "\$\$" >"$scratch/\$1.pid"
: >"\$3"
: >"$scratch/\$1.up"
sleep 8
: >"$scratch/\$1.late"
SLEEP
substitute 'k1 k2' "bash \"$scratch/sleeper.sh\" \"\$1\" \"\$2\" \"\$3\"" >"$scratch/recipe-kill.sh"
( cd "$repo" && PATH="$scratch/bin:$PATH" exec bash "$scratch/recipe-kill.sh" ) >/dev/null 2>&1 &
killpid=$!
for _ in $(seq 1 100); do
  [ -e "$scratch/k1.up" ] && [ -e "$scratch/k2.up" ] && break
  sleep 0.1
done
if [ ! -e "$scratch/k1.up" ] || [ ! -e "$scratch/k2.up" ]; then
  echo "FAIL: the interrupted run never got both mutations started" >&2
  fail=1
fi
kill -TERM "$killpid" 2>/dev/null || true
wait "$killpid" 2>/dev/null || true
trees_killed="$(git -C "$repo" worktree list | wc -l)"
if [ "$trees_killed" -ne 2 ]; then
  echo "FAIL: an interrupted run left $trees_killed worktrees registered, not the fixture's 2" >&2
  git -C "$repo" worktree list >&2
  fail=1
fi
for id in k1 k2; do
  if [ -e "$(cat "$scratch/$id.wt" 2>/dev/null)" ]; then
    echo "FAIL: an interrupted run left $id's throwaway worktree on disk" >&2
    fail=1
  fi
  # Registrations and directories cannot see a surviving child: a covering suite
  # still running after its worktree was force-removed holds the box and writes
  # into deleted paths. The run has exited by now, so the process must be gone.
  child="$(cat "$scratch/$id.pid" 2>/dev/null)"
  if [ -n "$child" ] && kill -0 "$child" 2>/dev/null; then
    echo "FAIL: $id's covering suite was still running after the interrupted run returned" >&2
    kill -KILL "$child" 2>/dev/null || true
    fail=1
  fi
done

# An id that cannot name a directory and an output file is refused by name,
# before anything is created — never mangled into a path inside its own
# worktree, which is how a message gets attached to the wrong mutation.
substitute 'tests/a.py::t1' ": >\"\$3\"; echo \"MUTANT-\$1\"; exit 1" >"$scratch/recipe-badid.sh"
if ( cd "$repo" && PATH="$scratch/bin:$PATH" bash "$scratch/recipe-badid.sh" ) \
     >"$scratch/badid.out" 2>&1; then
  echo "FAIL: a pytest nodeid was accepted as a mutation id" >&2
  cat "$scratch/badid.out" >&2
  fail=1
elif ! grep -q 'tests/a.py::t1' "$scratch/badid.out"; then
  echo "FAIL: the unusable mutation id was refused without naming it" >&2
  cat "$scratch/badid.out" >&2
  fail=1
fi

# Class 1 again, one layer out (#961): the wrapper that never reached the suite.
# A mutation that exits nonzero having printed nothing did not demonstrate an
# assertion — there is no message to read — so it is `unknown`, by name, not a
# red. Status alone cannot tell the two apart.
substitute 's1' "exit 4" >"$scratch/recipe-silent.sh"
( cd "$repo" && PATH="$scratch/bin:$PATH" bash "$scratch/recipe-silent.sh" ) \
  >"$scratch/silent.out" 2>&1 || true
if ! grep -i 'unknown' "$scratch/silent.out" | grep -q 's1'; then
  echo "FAIL: a mutation that exited nonzero with no output was not reported as unknown" >&2
  cat "$scratch/silent.out" >&2
  fail=1
fi
if grep -q 's1: red' "$scratch/silent.out"; then
  echo "FAIL: a silent nonzero mutation was reported as a red with no message to read" >&2
  fail=1
fi

# Two ids that are both legal and collide in a shared namespace: worktree
# `x.out` and mutation `x`'s output file want the same path, and whichever the
# parent creates first makes the other fail — a red with no suite behind it and
# an output file inside a worktree, both at once. Disjoint directories are what
# make this pair ordinary.
substitute 'x x.out' ": >\"\$3\"; echo \"MUTANT-\$1: covering suite red\"; exit 1" >"$scratch/recipe-collide.sh"
( cd "$repo" && PATH="$scratch/bin:$PATH" bash "$scratch/recipe-collide.sh" ) \
  >"$scratch/collide.out" 2>&1 || true
for id in x x.out; do
  if ! grep -q "$id|.*MUTANT-$id" "$scratch/collide.out"; then
    echo "FAIL: colliding-but-legal id $id lost its own message" >&2
    cat "$scratch/collide.out" >&2
    fail=1
  fi
done

# The same id twice would have one mutation overwrite the other's output, so it
# is refused by name rather than silently halving the check.
substitute 'd1 d1' "exit 1" >"$scratch/recipe-dup.sh"
if ( cd "$repo" && PATH="$scratch/bin:$PATH" bash "$scratch/recipe-dup.sh" ) \
     >"$scratch/dup.out" 2>&1; then
  echo "FAIL: a duplicated mutation id was accepted" >&2
  fail=1
elif ! grep -q 'twice' "$scratch/dup.out"; then
  echo "FAIL: a duplicated mutation id was refused without saying why" >&2
  cat "$scratch/dup.out" >&2
  fail=1
fi

# Cleanup's own failure path. `git worktree remove` failing and `rm -rf` running
# anyway is how a stale registration gets created by the recipe whose prose
# forbids exactly that — and the run would exit 0 having created it. This shim
# fails every removal; the run must exit non-zero and name the worktree it could
# not deregister.
mkdir -p "$scratch/bin-norm"
cat >"$scratch/bin-norm/git" <<NORM
#!/usr/bin/env bash
prev=""
for a in "\$@"; do
  if [ "\$prev" = worktree ] && [ "\$a" = remove ]; then
    echo "fatal: shim refuses worktree remove" >&2; exit 128
  fi
  prev="\$a"
done
exec "$real_git" "\$@"
NORM
chmod +x "$scratch/bin-norm/git"
cp "$scratch/bin/ps" "$scratch/bin-norm/ps"
substitute 'r1' ": >\"\$3\"; echo \"MUTANT-\$1: covering suite red\"; exit 1" >"$scratch/recipe-norm.sh"
if ( cd "$repo" && PATH="$scratch/bin-norm:$PATH" bash "$scratch/recipe-norm.sh" ) \
     >"$scratch/norm.out" 2>&1; then
  echo "FAIL: a witness run whose worktree removal failed still exited 0" >&2
  cat "$scratch/norm.out" >&2
  fail=1
fi
if ! grep -q 'could not remove worktree' "$scratch/norm.out"; then
  echo "FAIL: a failed worktree removal was not reported" >&2
  cat "$scratch/norm.out" >&2
  fail=1
fi
# The directory is still there because git never deregistered it — that is the
# point of the fix, and the proof that nothing was `rm -rf`d out from under a
# live registration. Clean it up with the real git so the fixture's own count
# assertions above stay meaningful for the next reader.
kept="$(sed -n 's/.*keeping \([^ ]*\) -.*/\1/p' "$scratch/norm.out" | head -1)"
if [ -z "$kept" ] || [ ! -d "$kept" ]; then
  echo "FAIL: the failed-removal run did not keep its root directory for a by-hand cleanup" >&2
  cat "$scratch/norm.out" >&2
  fail=1
else
  for w in "$kept"/worktrees/*/; do
    [ -d "$w" ] && git -C "$repo" worktree remove --force "${w%/}" 2>/dev/null
  done
  rm -rf "$kept"
fi
trees_norm="$(git -C "$repo" worktree list | wc -l)"
if [ "$trees_norm" -ne 2 ]; then
  echo "FAIL: after the by-hand cleanup $trees_norm worktrees are registered, not the fixture's 2" >&2
  git -C "$repo" worktree list >&2
  fail=1
fi

# Non-empty output was a proxy for "the suite ran", and it is the wrong proxy:
# a wrapper that dies before invoking the covering suite — a missing test path, a
# denied command — writes its error to stderr and exits nonzero, which is
# indistinguishable from a red unless the mutation says for itself that it got
# as far as the suite. The marker is that statement.
substitute 'p1' "echo 'bash: no such test file' >&2; exit 2" >"$scratch/recipe-presuite.sh"
( cd "$repo" && PATH="$scratch/bin:$PATH" bash "$scratch/recipe-presuite.sh" ) \
  >"$scratch/presuite.out" 2>&1 || true
if ! grep -i 'unknown' "$scratch/presuite.out" | grep -q 'p1'; then
  echo "FAIL: a mutation that died before its covering suite was not reported as unknown" >&2
  cat "$scratch/presuite.out" >&2
  fail=1
fi
if grep -q 'p1: red' "$scratch/presuite.out"; then
  echo "FAIL: a pre-suite failure with stderr output was reported as a red" >&2
  cat "$scratch/presuite.out" >&2
  fail=1
fi

# An empty list is a failed enumeration upstream. Run as a success it is the
# whole ticket's defect inside the tool the ticket builds: a check that
# witnessed nothing, reporting clean.
substitute '' ": >\"\$3\"; exit 1" >"$scratch/recipe-empty.sh"
if ( cd "$repo" && PATH="$scratch/bin:$PATH" bash "$scratch/recipe-empty.sh" ) \
     >"$scratch/empty.out" 2>&1; then
  echo "FAIL: an empty mutation list exited 0 as a clean witness check" >&2
  cat "$scratch/empty.out" >&2
  fail=1
elif ! grep -q 'no mutations supplied' "$scratch/empty.out"; then
  echo "FAIL: an empty mutation list was refused without saying so" >&2
  cat "$scratch/empty.out" >&2
  fail=1
fi

# The marker proves the wrapper reached the line before the suite, not that the
# suite started. A command that does not exist writes the marker, exits 127, and
# without the kernel's own answer being read that is a red whose failure message
# is "command not found" — the same unreached-suite defect, one line further on.
substitute 'e1' ": >\"\$3\"; /nonexistent/covering-suite" >"$scratch/recipe-noexec.sh"
( cd "$repo" && PATH="$scratch/bin:$PATH" bash "$scratch/recipe-noexec.sh" ) \
  >"$scratch/noexec.out" 2>&1 || true
if ! grep -i 'unknown' "$scratch/noexec.out" | grep -q 'e1'; then
  echo "FAIL: a marked mutation whose suite command never executed was not reported as unknown" >&2
  cat "$scratch/noexec.out" >&2
  fail=1
fi
if grep -q 'e1: red' "$scratch/noexec.out"; then
  echo "FAIL: a command-not-found was reported as a red with its own failure message" >&2
  cat "$scratch/noexec.out" >&2
  fail=1
fi

# `ids='*'` must not expand before validation: unquoted, it becomes the
# checkout's filenames, every one of which passes the character check, and the
# run mutates a set nobody asked for while omitting the requested id.
substitute '*' ": >\"\$3\"; echo \"MUTANT-\$1\"; exit 1" >"$scratch/recipe-glob.sh"
if ( cd "$repo" && PATH="$scratch/bin:$PATH" bash "$scratch/recipe-glob.sh" ) \
     >"$scratch/glob.out" 2>&1; then
  echo "FAIL: ids='*' was accepted" >&2
  cat "$scratch/glob.out" >&2
  fail=1
fi
if grep -q 'MUTANT-' "$scratch/glob.out"; then
  echo "FAIL: ids='*' expanded to the checkout's files and mutated them" >&2
  cat "$scratch/glob.out" >&2
  fail=1
fi
if ! grep -q 'not usable as a mutation id' "$scratch/glob.out"; then
  echo "FAIL: ids='*' was rejected for some reason other than the id check" >&2
  cat "$scratch/glob.out" >&2
  fail=1
fi
trees_glob="$(git -C "$repo" worktree list | wc -l)"
if [ "$trees_glob" -ne 2 ]; then
  echo "FAIL: the ids='*' run created $trees_glob worktrees, not the fixture's 2" >&2
  git -C "$repo" worktree list >&2
  fail=1
fi

if [ "$fail" -eq 0 ]; then
  echo "PASS multi-axis-code-review/witness-check.test.sh"
else
  exit 1
fi
