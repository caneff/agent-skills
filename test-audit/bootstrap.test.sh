#!/usr/bin/env bash
# bootstrap.sh is what the suites that run node call before they need
# node_modules/. tests/all.sh runs them at once, so a caller that sees the
# directory a sibling's `npm ci` just created must wait for the install to
# finish, not run against it (#1845). A fake `npm` stands in for the real one:
# it creates node_modules/ at once, the package a second later, npm's hidden
# lockfile a second after that, and logs each call. Concurrent callers,
# including one that arrives mid-install, must see the finished tree on
# return and trigger one install; a finished tree must trigger none. The
# last section checks every suite here that runs node calls bootstrap.sh.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
work=$(mktemp -d); trap 'rm -rf "$work"' EXIT
mkdir "$work/ta" "$work/bin"
cp "$here/package.json" "$here/package-lock.json" "$here/bootstrap.sh" "$work/ta/"
cat >"$work/bin/npm" <<FAKE
#!/usr/bin/env bash
echo "\$*" >>"$work/npm.log"
[ -z "\${FAKE_NPM_FAILS:-}" ] || exit 0
mkdir -p node_modules/@babel/types
sleep 1
mkdir -p node_modules/@babel/parser
echo '{}' >node_modules/@babel/parser/package.json
sleep 1
echo '{}' >node_modules/.package-lock.json
FAKE
chmod +x "$work/bin/npm"
export PATH="$work/bin:$PATH"

fail=0
calls() { wc -l <"$work/npm.log" 2>/dev/null || echo 0; }
finished() { [ -f node_modules/@babel/parser/package.json ] && [ -f node_modules/.package-lock.json ]; }

for i in 1 2 3 4; do
  ( cd "$work/ta" && bash ./bootstrap.sh && finished ) >"$work/out.$i" 2>&1 &
  pids[$i]=$!
done
sleep 1.5   # the package is there, npm's hidden lockfile is not yet
( cd "$work/ta" && bash ./bootstrap.sh && finished ) >"$work/out.5" 2>&1 &
pids[5]=$!
for i in 1 2 3 4 5; do
  wait "${pids[$i]}" || { echo "FAIL caller $i returned before the install finished, or errored: $(cat "$work/out.$i")"; fail=1; }
done
[ "$(calls)" -eq 1 ] || { echo "FAIL five concurrent callers ran npm $(calls) times, want 1"; fail=1; }

( cd "$work/ta" && bash ./bootstrap.sh ) || { echo "FAIL rerun on a finished tree errored"; fail=1; }
[ "$(calls)" -eq 1 ] || { echo "FAIL a finished tree ran npm again ($(calls) calls)"; fail=1; }

# A tree with the directory but not the package is not installed.
rm -rf "$work/ta/node_modules"; mkdir -p "$work/ta/node_modules/@babel/types"
( cd "$work/ta" && bash ./bootstrap.sh && finished ) || { echo "FAIL half-installed rerun errored or stayed incomplete"; fail=1; }
[ "$(calls)" -eq 2 ] || { echo "FAIL a half-installed tree did not trigger an install ($(calls) calls)"; fail=1; }

# A tree with npm's lockfile but no package is not installed either.
rm -rf "$work/ta/node_modules"; mkdir -p "$work/ta/node_modules"; echo '{}' >"$work/ta/node_modules/.package-lock.json"
( cd "$work/ta" && bash ./bootstrap.sh && finished ) || { echo "FAIL lockfile-only tree errored or stayed incomplete"; fail=1; }
[ "$(calls)" -eq 3 ] || { echo "FAIL a tree without the package did not trigger an install ($(calls) calls)"; fail=1; }

# An npm that exits 0 without installing must fail the caller, not pass it.
rm -rf "$work/ta/node_modules"
set +e
( cd "$work/ta" && FAKE_NPM_FAILS=1 bash ./bootstrap.sh ) >"$work/out.fail" 2>&1; rc=$?
set -e
[ "$rc" -eq 2 ] || { echo "FAIL a bootstrap that installed nothing exited $rc, want 2: $(cat "$work/out.fail")"; fail=1; }

# Every suite here that runs node bootstraps through bootstrap.sh.
for f in "$here"/*.test.sh; do
  [ "$f" = "$here/bootstrap.test.sh" ] && continue
  if grep -Eq '(^|[^[:alnum:]_.-])node( |$)|audit\.mjs' "$f"; then
    grep -q '^bash \./bootstrap\.sh$' "$f" || { echo "FAIL $(basename "$f") runs node without calling bootstrap.sh"; fail=1; }
  fi
done
[ "$(ls "$here"/*.test.sh | wc -l)" -ge 5 ] || { echo "FAIL expected the four node suites beside bootstrap.test.sh"; fail=1; }

[ "$fail" -eq 0 ] && echo "bootstrap.test.sh: ok"
exit "$fail"
