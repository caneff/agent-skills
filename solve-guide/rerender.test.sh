#!/usr/bin/env bash
# rerender.sh at its command line, through the real kit.sh: a stand-in
# sudoku-kit checkout (no dependencies, so no network) and a fake
# `solve-guide` on PATH that records its arguments and writes out/guide.html.
# Each run copies the page to the next free guide-r<n>.html; a refused guide
# file passes its exit status through and copies nothing; --pdf prints the
# copy through print_pdf.py (a fake shot-scraper writes the PDF).
# Blind to: the library's own checks and drawing, and Chrome.
set -u
here=$(cd "$(dirname "$0")" && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
fail=0

kit="$tmp/kit"
mkdir -p "$kit/src/sudoku_kit" "$tmp/bin"
touch "$kit/src/sudoku_kit/guide_file.py"
printf '[project]\nname = "stand-in"\nversion = "0"\nrequires-python = ">=3.10"\ndependencies = []\n' > "$kit/pyproject.toml"
cat > "$tmp/bin/solve-guide" <<'EOF'
#!/bin/sh
echo "$@" > args.txt
[ -f refuse ] && { echo "guide file: entry 2 skips step 9" >&2; exit 2; }
mkdir -p out && echo "<html>page $(cat guide.json)</html>" > out/guide.html
EOF
cat > "$tmp/bin/shot-scraper" <<'EOF'
#!/bin/sh
while [ "$#" -gt 0 ]; do [ "$1" = -o ] && printf '%%PDF-1.4 fake' > "$2"; shift; done
EOF
chmod +x "$tmp/bin/solve-guide" "$tmp/bin/shot-scraper"
run() { PATH="$tmp/bin:$PATH" SUDOKU_KIT="$kit" bash "$here/rerender.sh" "$@" 2>&1; }

w="$tmp/link-puzzle"
mkdir -p "$w/out"
echo v1 > "$w/guide.json"; touch "$w/original.scl.txt" "$w/rules.json"
out=$(run "$w"); rc=$?
if [ "$rc" -ne 0 ] || [ "$out" != "$w/guide-r1.html" ] || [ "$(cat "$w/guide-r1.html")" != "<html>page v1</html>" ]; then
  echo "FAIL: first run did not copy the page to guide-r1.html (rc=$rc): $out"; fail=1
fi
if [ "$(cat "$w/args.txt")" != "original.scl.txt out --max-steps 0 --guide guide.json" ]; then
  echo "FAIL: a link import did not render from original.scl.txt without searching: $(cat "$w/args.txt")"; fail=1
fi

echo v2 > "$w/guide.json"; touch "$w/guide-r5.html"
out=$(run "$w" -- --time-limit 60); rc=$?
if [ "$rc" -ne 0 ] || [ "$out" != "$w/guide-r6.html" ] || [ "$(cat "$w/guide-r6.html")" != "<html>page v2</html>" ]; then
  echo "FAIL: a later run did not take the next free number after guide-r5.html (rc=$rc): $out"; fail=1
fi
if [ "$(cat "$w/args.txt")" != "original.scl.txt out --max-steps 0 --guide guide.json --time-limit 60" ]; then
  echo "FAIL: flags after -- were not passed on: $(cat "$w/args.txt")"; fail=1
fi

i="$tmp/image-puzzle"
mkdir -p "$i"
echo v1 > "$i/guide.json"; touch "$i/rules.json"
out=$(run "$i"); rc=$?
if [ "$rc" -ne 0 ] || [ "$(cat "$i/args.txt")" != "rules.json out --max-steps 0 --guide guide.json" ]; then
  echo "FAIL: an image import did not render from rules.json (rc=$rc): $out"; fail=1
fi

touch "$i/refuse"
out=$(run "$i"); rc=$?
if [ "$rc" -ne 2 ] || [[ "$out" != *"skips step 9"* ]] || [ -e "$i/guide-r2.html" ]; then
  echo "FAIL: a refused guide file did not pass exit 2 through, or a page was copied (rc=$rc): $out"; fail=1
fi
rm "$i/refuse"

out=$(run "$i" --pdf); rc=$?
if [ "$rc" -ne 0 ] || [ ! -f "$i/guide-r2.html" ] || [ "$(head -c 5 "$i/guide-r2.pdf" 2>/dev/null)" != "%PDF-" ] \
   || [ "$out" != "$i/guide-r2.html"$'\n'"$i/guide-r2.pdf" ]; then
  echo "FAIL: --pdf did not print guide-r2.pdf beside guide-r2.html (rc=$rc): $out"; fail=1
fi

e="$tmp/empty"
mkdir -p "$e"; touch "$e/original.scl.txt"
out=$(run "$e"); rc=$?
if [ "$rc" -ne 2 ] || [[ "$out" != *"no guide.json"* ]]; then
  echo "FAIL: a work directory without guide.json was not refused (rc=$rc): $out"; fail=1
fi

n="$tmp/no-input"
mkdir -p "$n"; echo v1 > "$n/guide.json"
out=$(run "$n"); rc=$?
if [ "$rc" -ne 2 ] || [[ "$out" != *"original.scl.txt"* ]] || [[ "$out" != *"rules.json"* ]]; then
  echo "FAIL: a work directory without an input was not refused naming both (rc=$rc): $out"; fail=1
fi

[ "$fail" -eq 0 ] && echo "ok: rerender.sh renders from guide.json to the next guide-r<n>.html, passes refusals through, and prints a PDF on --pdf"
exit "$fail"
