#!/usr/bin/env bash
# Covers page-shot and page-eval against a real headless render of a local
# file:// fixture — the thing they exist to do, and the thing Orca's browser
# got wrong (a Linux file:/// path loaded as ERR_FILE_NOT_FOUND there).
# Skips cleanly when Playwright or its Chromium is not installed, so the merge
# gate stays green on a machine that has not run `npx playwright install`.
# Run: bash flow/bin/page-shot.test.sh
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! node --input-type=module -e "
  import { loadPlaywright } from '$here/browser.mjs'
  loadPlaywright().chromium.executablePath()
" >/dev/null 2>&1; then
  echo "SKIP: playwright or its chromium is not installed"; exit 0
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cat > "$tmp/fixture.html" <<'HTML'
<title>Fixture</title>
<p id="out">before</p>
<input id="who">
<button id="go" onclick="
  document.getElementById('out').textContent =
    'clicked:' + document.getElementById('who').value
">go</button>
HTML

fail() { echo "FAIL: $*"; exit 1; }

# --- page-shot writes a real PNG and prints its absolute path ---------------
got=$("$here/page-shot" "$tmp/fixture.html" "$tmp/a.png") || fail "page-shot exited non-zero"
[ "$got" = "$tmp/a.png" ] || fail "page-shot printed '$got', want '$tmp/a.png'"
[ -s "$tmp/a.png" ] || fail "page-shot wrote no bytes"
head -c 8 "$tmp/a.png" | grep -q 'PNG' || fail "page-shot output is not a PNG"

# --- a bare path that does not exist is a usage error, not a blank image ----
if "$here/page-shot" "$tmp/nope.html" "$tmp/b.png" 2>"$tmp/err"; then
  fail "page-shot accepted a missing file"
fi
grep -q 'no such file' "$tmp/err" || fail "page-shot did not say why: $(cat "$tmp/err")"
if [ -e "$tmp/b.png" ]; then fail "page-shot wrote a PNG for a missing input"; fi

# --- no arguments prints usage and exits 2 ---------------------------------
code=0; "$here/page-shot" >/dev/null 2>&1 || code=$?
[ "$code" -eq 2 ] || fail "page-shot with no args should exit 2, got $code"

# --- page-eval reads text and evaluates an expression ----------------------
json=$("$here/page-eval" "$tmp/fixture.html" --text '#out' --js 'document.title') \
  || fail "page-eval exited non-zero"
echo "$json" | grep -q '"before"' || fail "page-eval did not read #out: $json"
echo "$json" | grep -q '"Fixture"' || fail "page-eval did not evaluate document.title: $json"

# --- fills run before clicks, so the click sees the filled value -----------
json=$("$here/page-eval" "$tmp/fixture.html" --fill '#who=chris' --click '#go' --text '#out')
echo "$json" | grep -q 'clicked:chris' || fail "fill-then-click did not take effect: $json"

# --- a bad selector degrades to an ERR entry, it does not kill the run -----
json=$("$here/page-eval" "$tmp/fixture.html" --text '#missing' --js 'document.title') \
  || fail "page-eval died on a bad selector instead of reporting it"
echo "$json" | grep -q 'ERR:' || fail "page-eval did not report the bad selector: $json"
echo "$json" | grep -q '"Fixture"' || fail "page-eval dropped the good probe: $json"

# --- --shot from page-eval writes a PNG too --------------------------------
json=$("$here/page-eval" "$tmp/fixture.html" --shot "$tmp/c.png")
[ -s "$tmp/c.png" ] || fail "page-eval --shot wrote no bytes"
echo "$json" | grep -q "$tmp/c.png" || fail "page-eval --shot did not report the path: $json"

echo "PASS: page-shot and page-eval render, drive and report a local file:// page"
