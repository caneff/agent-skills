#!/usr/bin/env bash
# The wizard template's prompt helper, run with piped stdin (no tty): one
# `ask` serves visible and secret input, a re-run offers the .env value, and
# Enter keeps it. Sources only the library above the STAGES marker.
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
work=$(mktemp -d) || exit 1
trap 'rm -rf "$work"' EXIT
sed '/^# STAGES/,$d' "$here/template.sh" >"$work/lib.sh"
fail=0
check() { # name expected actual
  [[ "$2" == "$3" ]] || { echo "FAIL: $1: expected [$2] got [$3]"; fail=1; }
}
run() { # stdin-text, then ask args; prints $KEY_VAL
  (cd "$work" && ENV_FILE="$work/.env" bash -c 'source ./lib.sh; ask "$@"; printf "%s" "$KEY_VAL" >out' _ "${@:2}" <<<"$1" >/dev/null 2>&1)
  cat "$work/out"
}

rm -f "$work/.env"
check "visible ask" "typed" "$(run typed KEY_VAL "Prompt:")"
check "secret ask" "hush" "$(run hush --secret KEY_VAL "Prompt:")"
printf 'KEY_VAL=kept\n' >"$work/.env"
check "visible Enter keeps" "kept" "$(run "" KEY_VAL "Prompt:")"
check "secret Enter keeps" "kept" "$(run "" --secret KEY_VAL "Prompt:")"
check "typed overrides" "new" "$(run new --secret KEY_VAL "Prompt:")"
if grep -qE '^ask_secret\(\)' "$work/lib.sh"; then echo "FAIL: ask_secret still defined"; fail=1; fi

[[ $fail == 0 ]] && echo "ALL PASS"
exit $fail
