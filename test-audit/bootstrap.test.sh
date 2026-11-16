#!/usr/bin/env bash
# bootstrap.sh is what the four test-audit suites call before they need
# node_modules/. tests/all.sh runs them at once, so a caller that sees the
# directory a sibling's `npm ci` just created must wait for the install to
# finish, not run against it (#1845). A fake `npm` stands in for the real one:
# it creates node_modules/ at once, puts the package in place a second later, and
# logs each call. Four concurrent callers must see the package on return and
# trigger one install; a finished tree must trigger none.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
work=$(mktemp -d); trap 'rm -rf "$work"' EXIT
mkdir "$work/ta" "$work/bin"
cp "$here/package.json" "$here/package-lock.json" "$work/ta/"
cp "$here/bootstrap.sh" "$work/ta/" 2>/dev/null || true
cat >"$work/bin/npm" <<FAKE
#!/usr/bin/env bash
echo "\$*" >>"$work/npm.log"
mkdir -p node_modules/@babel/types
sleep 1
mkdir -p node_modules/@babel/parser
echo '{}' >node_modules/@babel/parser/package.json
echo '{}' >node_modules/.package-lock.json
FAKE
chmod +x "$work/bin/npm"

fail=0
export PATH="$work/bin:$PATH"
for i in 1 2 3 4; do
  ( cd "$work/ta" && bash ./bootstrap.sh \
    && [ -f node_modules/@babel/parser/package.json ] ) >"$work/out.$i" 2>&1 &
  pids[$i]=$!
done
for i in 1 2 3 4; do
  wait "${pids[$i]}" || { echo "FAIL caller $i returned before the install finished or errored: $(cat "$work/out.$i")"; fail=1; }
done
n=$(wc -l <"$work/npm.log" 2>/dev/null || echo 0)
[ "$n" -eq 1 ] || { echo "FAIL four concurrent callers ran npm $n times, want 1"; fail=1; }

( cd "$work/ta" && bash ./bootstrap.sh ) || { echo "FAIL rerun on a finished tree errored"; fail=1; }
n=$(wc -l <"$work/npm.log" 2>/dev/null || echo 0)
[ "$n" -eq 1 ] || { echo "FAIL a finished tree ran npm again ($n calls)"; fail=1; }

# A half-installed tree (directory present, package missing) is not installed.
rm -rf "$work/ta/node_modules"; mkdir -p "$work/ta/node_modules/@babel/types"
( cd "$work/ta" && bash ./bootstrap.sh ) || { echo "FAIL half-installed rerun errored"; fail=1; }
n=$(wc -l <"$work/npm.log")
[ "$n" -eq 2 ] || { echo "FAIL a half-installed tree did not trigger an install ($n calls)"; fail=1; }
[ -f "$work/ta/node_modules/@babel/parser/package.json" ] || { echo "FAIL half-installed tree still lacks the package"; fail=1; }

[ "$fail" -eq 0 ] && echo "bootstrap.test.sh: ok"
exit "$fail"
