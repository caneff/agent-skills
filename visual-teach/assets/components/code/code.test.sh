#!/usr/bin/env bash
# code component: the export surface is one object, and the code and io blocks
# share one CSS rule per repeated block instead of copies.
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
fail=0
out=$(node -e '
const fs = require("fs"), vm = require("vm");
const src = fs.readFileSync(process.argv[1], "utf8");
const want = ["wireCopyButton", "wireCodeBlock", "wireIO", "initPrism"];
const mod = { exports: {} };
vm.runInNewContext(src, { module: mod, console: { warn() {} } });
const win = {};
vm.runInNewContext(src, { window: win, console: { warn() {} } });
const same = (o) => JSON.stringify(Object.keys(o).sort()) === JSON.stringify(want.slice().sort());
if (!same(mod.exports)) console.log("FAIL: module.exports keys " + Object.keys(mod.exports));
if (!win.vtCode || !same(win.vtCode)) console.log("FAIL: window.vtCode keys");
const n = (src.match(/wireCopyButton:/g) || []).length;
if (n !== 1) console.log("FAIL: export list written " + n + " times");
' "$here/code.js") || fail=1
[[ -n "$out" ]] && { echo "$out"; fail=1; }
css=$(cat "$here/code.css")
for pat in '\.vt-code-head,' '\.vt-code pre,' '\.vt-code pre code,'; do
  grep -qE "$pat" <<<"$css" || { echo "FAIL: no shared selector $pat"; fail=1; }
done
for sel in '.vt-io-head' '.vt-io pre' '.vt-io pre code'; do
  c=$(grep -cE "^${sel//./\\.}(,| \\{)" <<<"$css")
  [[ $c == 1 ]] || { echo "FAIL: $sel is a selector line $c times, want 1 (shared)"; fail=1; }
done
[[ $fail == 0 ]] && echo "ALL PASS"
exit $fail
