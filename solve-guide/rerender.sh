#!/usr/bin/env bash
# Re-render a solve guide from its hand-editable source after an edit:
#
#     rerender.sh <work-dir> [--pdf] [-- <solve-guide flags>]
#
# <work-dir> is the guide's directory, ~/.cache/solve-guide/<slug>: its
# guide.json is the source, out/ the step record, and the puzzle input is
# original.scl.txt (a link import) or else rules.json (an image import). Runs
# `kit.sh solve-guide <input> out --max-steps 0 --guide guide.json`, so the
# record is redrawn and never searched, then copies out/guide.html to the next
# free guide-r<n>.html beside it and prints that path. --pdf also prints it to
# guide-r<n>.pdf through print_pdf.py and prints that path. Flags after `--`
# go to solve-guide as they are: the --time-limit or --proof-limit the record
# was built under, or --image.
#
# Exit codes: the render's own when it fails (2 names what the guide file gets
# wrong, and nothing is copied); 2 when the directory has no guide.json or no
# input; print_pdf.py's when the printout fails; else 0.
set -u
here=$(cd "$(dirname "$0")" && pwd)
usage="usage: rerender.sh <work-dir> [--pdf] [-- <solve-guide flags>]"
[ "$#" -ge 1 ] || { echo "$usage" >&2; exit 2; }
dir=$(cd "$1" 2>/dev/null && pwd) || { echo "rerender.sh: no directory $1" >&2; exit 2; }
shift
pdf=0
if [ "${1:-}" = --pdf ]; then pdf=1; shift; fi
if [ "${1:-}" = -- ]; then shift; elif [ "$#" -gt 0 ]; then echo "$usage" >&2; exit 2; fi

[ -f "$dir/guide.json" ] || { echo "rerender.sh: no guide.json in $dir" >&2; exit 2; }
if [ -f "$dir/original.scl.txt" ]; then input=original.scl.txt
elif [ -f "$dir/rules.json" ]; then input=rules.json
else echo "rerender.sh: $dir has neither original.scl.txt nor rules.json" >&2; exit 2
fi

(cd "$dir" && "$here/kit.sh" solve-guide "$input" out --max-steps 0 --guide guide.json "$@") >&2 || exit

n=1
for f in "$dir"/guide-r*.html; do
  k=${f##*/guide-r}; k=${k%.html}
  case $k in ''|*[!0-9]*) continue ;; esac
  [ "$k" -ge "$n" ] && n=$((k + 1))
done
page="$dir/guide-r$n.html"
cp "$dir/out/guide.html" "$dir/.guide-r$n.html.partial" && mv "$dir/.guide-r$n.html.partial" "$page" || exit 1
echo "$page"
[ "$pdf" -eq 1 ] || exit 0
python3 "$here/print_pdf.py" "$page" "$dir/guide-r$n.pdf"
