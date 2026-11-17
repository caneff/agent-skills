#!/usr/bin/env bash
# Contract test for worker-dirty-stop.sh: a synthetic Stop event on stdin, a
# synthetic transcript, and a scratch git repo as the event's cwd -> a
# {"decision":"block"} on stdout when a worker stops over an uncommitted tree,
# and nothing otherwise. Runs offline.
# Run: bash flow/claude/hooks/worker-dirty-stop.test.sh
set -uo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
hook="$here/worker-dirty-stop.sh"
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT

repo="$tmp/repo"
git init -q -b implement-77 "$repo"
git -C "$repo" -c user.email=t@example.com -c user.name=t commit -q --allow-empty -m base
printf '.scratch/\n' > "$repo/.gitignore"
git -C "$repo" add .gitignore
git -C "$repo" -c user.email=t@example.com -c user.name=t commit -q -m ignore

brief='<command-message>implement</command-message>\n<command-name>/implement</command-name>\n<command-args>77 --tier heavy --controller \"ctl\"</command-args>'
worker="$tmp/worker.jsonl"
printf '{"type":"user","origin":{"kind":"human"},"message":{"role":"user","content":"%s"}}\n' "$brief" > "$worker"
other="$tmp/other.jsonl"
printf '{"type":"user","origin":{"kind":"human"},"message":{"role":"user","content":"hello"}}\n' > "$other"

fails=0
run() { # <transcript> <cwd> [stop_hook_active] -> hook stdout
  jq -nc --arg t "$1" --arg c "$2" --argjson a "${3:-false}" \
    '{transcript_path:$t, cwd:$c, stop_hook_active:$a}' | bash "$hook" 2>/dev/null
}
check() { # <label> <want: block|pass> <output>
  local got=pass
  jq -e '.decision == "block"' >/dev/null 2>&1 <<<"$3" && got=block
  if [ "$got" = "$2" ]; then echo "PASS $1"; else echo "FAIL $1: want $2, got $got ($3)"; fails=1; fi
}

check "clean tree: worker stops freely" pass "$(run "$worker" "$repo")"

echo x > "$repo/owned.txt"
out=$(run "$worker" "$repo")
check "untracked file blocks a worker's stop" block "$out"
grep -q 'owned.txt' <<<"$(jq -r .reason <<<"$out")" \
  && echo "PASS the reason names the dirty file" || { echo "FAIL reason does not name owned.txt: $out"; fails=1; }

check "a non-worker session is never blocked" pass "$(run "$other" "$repo")"
check "stop_hook_active true never blocks again" pass "$(run "$worker" "$repo" true)"

git -C "$repo" add owned.txt
check "staged-uncommitted file blocks too" block "$(run "$worker" "$repo")"
git -C "$repo" -c user.email=t@example.com -c user.name=t commit -q -m owned
mkdir "$repo/.scratch"; echo y > "$repo/.scratch/note"
check "ignored .scratch/ does not block" pass "$(run "$worker" "$repo")"

# A cwd that is not a git repo cannot be judged clean: the hook says so
# instead of passing silently.
nogit="$tmp/nogit"; mkdir "$nogit"
check "non-repo cwd blocks, naming the failure" block "$(run "$worker" "$nogit")"

exit "$fails"
