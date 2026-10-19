#!/usr/bin/env bash
# Contract test for bin/backstop-nightly (#1595): it runs the backstop once per
# repo in the list file, and a missing, unreadable or empty list fails loudly
# instead of running zero repos. backstop.py is a recording stub.
# Run: bash flow/bin/backstop-nightly.test.sh
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
tool="$here/backstop-nightly"
tmp=$(TMPDIR=/tmp mktemp -d)
trap 'rm -rf "$tmp"' EXIT
fails=0
pass() { echo "PASS $1"; }
fail() { echo "FAIL $1"; fails=1; }

log="$tmp/calls"
cat > "$tmp/stub.py" <<'STUB'
import os, sys
with open(os.environ["STUB_LOG"], "a") as f:
    f.write(" ".join(sys.argv[1:]) + "\n")
sys.exit(int(os.environ.get("STUB_RC", "1")) if os.environ.get("STUB_FAIL_ON", "@@") in sys.argv else 0)
STUB
cat > "$tmp/notify" <<'STUB'
#!/usr/bin/env bash
printf '%s | %s\n' "$1" "$2" >> "$NOTIFY_LOG"
STUB
chmod +x "$tmp/notify"
nlog="$tmp/notified"
export STUB_LOG="$log" BACKSTOP_PY="$tmp/stub.py" BACKSTOP_JOBS=3 BACKSTOP_NOTIFY="$tmp/notify" NOTIFY_LOG="$nlog"
: > "$nlog"

printf '# comment\n\n%s\n~/rel-repo\n%s\n' "$tmp/a" "$tmp/b" > "$tmp/list"
: > "$log"
out=$(HOME="$tmp/home" "$tool" "$tmp/list" 2>&1); rc=$?
if [ "$rc" = 0 ] && [ "$(wc -l < "$log")" = 3 ] \
   && grep -qx -- "--repo $tmp/a --jobs 3" "$log" \
   && grep -qx -- "--repo $tmp/home/rel-repo --jobs 3" "$log" \
   && grep -qx -- "--repo $tmp/b --jobs 3" "$log"; then
  pass "one backstop run per listed repo; comments and blanks skipped, ~ expanded"
else
  fail "list of three repos (rc=$rc): $out / $(cat "$log")"
fi

: > "$log"
out=$("$tool" "$tmp/absent" 2>&1); rc=$?
if [ "$rc" -ne 0 ] && [ ! -s "$log" ] && printf '%s' "$out" | grep -q "absent"; then
  pass "a missing list file fails and names the file"
else
  fail "missing list (rc=$rc): $out"
fi

: > "$tmp/empty"; printf '# nothing\n' > "$tmp/comments"
for f in empty comments; do
  : > "$log"
  out=$("$tool" "$tmp/$f" 2>&1); rc=$?
  if [ "$rc" -ne 0 ] && [ ! -s "$log" ]; then pass "a list with no repo ($f) fails instead of running zero repos"
  else fail "list $f (rc=$rc): $out"; fi
done

if [ "$(id -u)" != 0 ]; then
  cp "$tmp/list" "$tmp/locked"; chmod 000 "$tmp/locked"
  : > "$log"
  out=$("$tool" "$tmp/locked" 2>&1); rc=$?
  if [ "$rc" -ne 0 ] && [ ! -s "$log" ]; then pass "an unreadable list file fails"
  else fail "unreadable list (rc=$rc): $out"; fi
fi

# One repo failing must not skip the rest, and the job still ends non-zero.
: > "$log"
out=$(STUB_FAIL_ON="$tmp/a" HOME="$tmp/home" "$tool" "$tmp/list" 2>&1); rc=$?
if [ "$rc" -ne 0 ] && [ "$(wc -l < "$log")" = 3 ]; then
  pass "a failing repo does not skip the others and the job exits non-zero"
else
  fail "failing first repo (rc=$rc, calls $(wc -l < "$log")): $out"
fi

# A workflow= field passes --workflow to that repo's run only.
printf '%s workflow=gate.yml\n%s\n' "$tmp/w" "$tmp/x" > "$tmp/wlist"
: > "$log"
"$tool" "$tmp/wlist" >/dev/null 2>&1; rc=$?
if [ "$rc" = 0 ] && grep -qx -- "--repo $tmp/w --jobs 3 --workflow gate.yml" "$log" \
   && grep -qx -- "--repo $tmp/x --jobs 3" "$log"; then
  pass "a workflow= field becomes --workflow for that repo only"
else
  fail "workflow field (rc=$rc): $(cat "$log")"
fi

# A list that cannot be used notifies, and the exit stays non-zero.
: > "$nlog"
"$tool" "$tmp/absent" >/dev/null 2>&1; rc=$?
if [ "$rc" -ne 0 ] && grep -q "could not run | .*absent" "$nlog"; then pass "a missing list notifies"
else fail "missing list notify (rc=$rc): $(cat "$nlog")"; fi
: > "$nlog"
"$tool" "$tmp/empty" >/dev/null 2>&1; rc=$?
if [ "$rc" -ne 0 ] && [ -s "$nlog" ]; then pass "an empty list notifies"
else fail "empty list notify (rc=$rc): $(cat "$nlog")"; fi

# backstop.py exits 1-3 after notifying itself; any other exit is a crash the
# wrapper must announce. Both stay non-zero.
for code in 1 2 3; do
  : > "$nlog"
  STUB_RC=$code STUB_FAIL_ON="$tmp/a" HOME="$tmp/home" "$tool" "$tmp/list" >/dev/null 2>&1; rc=$?
  if [ "$rc" -ne 0 ] && [ ! -s "$nlog" ]; then pass "exit $code is not re-notified by the wrapper"
  else fail "exit $code (rc=$rc): $(cat "$nlog")"; fi
done
for code in 4 137; do
  : > "$nlog"
  STUB_RC=$code STUB_FAIL_ON="$tmp/a" HOME="$tmp/home" "$tool" "$tmp/list" >/dev/null 2>&1; rc=$?
  if [ "$rc" -ne 0 ] && [ "$(wc -l < "$nlog")" = 1 ] && grep -q "$tmp/a crashed" "$nlog"; then pass "exit $code (a crash) notifies once and exits non-zero"
  else fail "exit $code (rc=$rc): $(cat "$nlog")"; fi
done

# The shipped list names the four repos.
for r in .agents/skills sudokumaker-custom-constraints grid-hunts twitch-rules-scroller; do
  grep -q "$r" "$here/../backstop-repos" && pass "backstop-repos lists $r" || fail "backstop-repos lacks $r"
done

[ "$fails" = 0 ] && echo "ALL PASS"
exit "$fails"
