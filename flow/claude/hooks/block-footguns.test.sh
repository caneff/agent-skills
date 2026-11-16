#!/usr/bin/env bash
# Contract test for block-footguns.py: synthetic PreToolUse JSON on stdin ->
# exit 0 (allow) or exit 2 + message on stderr (block). Two guards:
#   #1860 a bare `rg` (no path, stdin not supplied) hangs on the harness stdin;
#   #1704 a Python `open(p,'w')` that reads p in the same statement empties p.
# Run: bash flow/claude/hooks/block-footguns.test.sh
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
hook="$here/block-footguns.py"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
fails=0

# run <command> -> sets rc and err
run() {
  printf '%s' "$1" | jq -Rs '{tool_name:"Bash",tool_input:{command:.}}' > "$tmp/in.json"
  err=$(python3 -I "$hook" < "$tmp/in.json" 2>&1 >"$tmp/out"); rc=$?
}
blocks() { # blocks <name> <command> <substring of the message>
  run "$2"
  if [ "$rc" = 2 ] && [[ "$err" == *"$3"* ]]; then echo "PASS: $1"
  else echo "FAIL: $1 — want exit 2 with '$3', got $rc: $err"; fails=1; fi
}
allows() { # allows <name> <command>
  run "$2"
  if [ "$rc" = 0 ] && [ ! -s "$tmp/out" ] && [ -z "$err" ]; then echo "PASS: $1"
  else echo "FAIL: $1 — want silent exit 0, got $rc: $err $(cat "$tmp/out")"; fails=1; fi
}

# ---- bare rg (#1860) ----
blocks "rg pattern, no path" 'rg foo' "rg <pattern> ."
blocks "the spec-1206 shape" "python3 - <<'PY'
print(1)
PY
rg -n \"warnings-dock-seen|<<<<<<<|>>>>>>>\" --glob '!node_modules'" "git grep"
blocks "rg with flags and a value flag, no path" 'rg -n -g "*.py" -A 3 foo' "Pass a path"
blocks "rg -e pattern, no path" 'rg -e foo -e bar' "Pass a path"
blocks "rg after a separator" 'cd x && rg foo | head' "Pass a path"
blocks "rg in a subshell" 'echo $(rg foo)' "Pass a path"
blocks "rg under sudo/env prefix" 'FOO=1 rg foo' "Pass a path"
blocks "path-qualified rg" '/usr/bin/rg foo' "Pass a path"
blocks "rg fed only by a stderr redirect" 'rg foo 2>&1' "Pass a path"
allows "rg with a path" 'rg foo .'
allows "rg with two paths" 'rg foo src tests'
allows "rg -e with a path" 'rg -e foo docs/'
allows "rg after --" 'rg -- foo src'
allows "rg fed by a pipe" 'git diff | rg foo'
allows "rg fed by a pipe, with flags" 'cat x |& rg -n foo'
allows "rg reading a redirect" 'rg foo < file.txt'
allows "rg reading a here-string" 'rg foo <<< "$x"'
allows "rg reading a heredoc" "rg foo <<'EOF'
foo
EOF"
allows "rg --files needs no pattern" 'rg --files'
allows "rg --files -g" "rg --files -g '*.py'"
allows "rg --version" 'rg --version'
allows "rg with glob value and path" "rg -g '!node_modules' foo ."
allows "short cluster whose value is attached" 'rg -A3 foo .'
allows "short cluster ending in a value flag" 'rg -nA 3 foo .'
allows "rg named in a quoted string" "echo 'rg foo'"
allows "rg named in a comment" 'ls # rg foo'
allows "rg as an argument" 'git log --grep rg'
allows "rg in a heredoc body" "cat > notes.md <<'EOF'
rg foo
EOF"
allows "a quoted pattern starting with #" "rg '#define' src/"
allows "rg on the line after a comment, with a path" "# note
rg foo ."

# ---- truncate-then-read open() (#1704) ----
msg="reads it in the same statement"
blocks "write.open(read) one-liner" "python3 -c \"p='a.txt'; open(p,'w').write(open(p).read().replace('a','b'))\"" "$msg"
blocks "same with a literal path" "python3 -c \"open('a.txt', 'w').write(open('a.txt').read().upper())\"" "$msg"
blocks "with-form on one line" "python3 -c \"with open(p,'w') as f: f.write(open(p).read())\"" "$msg"
blocks "with-form, read in the body" "python3 - <<'PY'
with open(p, 'w') as f:
    f.write(open(p).read().replace('a', 'b'))
PY" "$msg"
blocks "mode wb" "python3 -c \"open(p,'wb').write(open(p,'rb').read())\"" "$msg"
blocks "mode keyword" "python3 -c \"open(p, mode='w').write(open(p, encoding='utf-8').read())\"" "$msg"
blocks "escaped quotes inside python -c" 'python3 -c "open(p,\"w\").write(open(p).read())"' "$msg"
blocks "read in a nested call argument" "python3 -c \"open(p,'w').write(fix(open(p).read()))\"" "$msg"
allows "safe form: read into a variable, then write" "python3 -c \"s=open(p).read(); open(p,'w').write(s.replace('a','b'))\""
allows "safe form on two lines" "python3 - <<'PY'
s = open(p).read()
with open(p, 'w') as f:
    f.write(s.replace('a', 'b'))
PY"
allows "read after the write, separate statement" "python3 -c \"open(p,'w').write('x'); print(open(p).read())\""
allows "write one file, read another" "python3 -c \"open(q,'w').write(open(p).read())\""
allows "read in the first argument position, before the open" "python3 -c \"f(open(p).read(), open(p,'w'))\""
allows "append mode is not a truncation" "python3 -c \"open(p,'a').write(open(p).read())\""
allows "with-body after the block ends" "python3 - <<'PY'
with open(p, 'w') as f:
    f.write('x')
print(open(p).read())
PY"
allows "read-mode open only" "python3 -c \"print(open(p).read())\""

# ---- the guard never fails silently ----
# Input that is not JSON is the harness's fault, not a command to judge.
out=$(printf 'not json' | python3 -I "$hook" 2>&1); rc=$?
if [ "$rc" = 0 ] && [[ "$out" == *"guard did not run"* ]]; then echo "PASS: unreadable input says the guard did not run"
else echo "FAIL: unreadable input — want exit 0 saying 'guard did not run', got $rc: $out"; fails=1; fi
# A non-Bash tool is not this guard's.
out=$(printf '%s' '{"tool_name":"Read","tool_input":{"file_path":"x"}}' | python3 -I "$hook" 2>&1); rc=$?
if [ "$rc" = 0 ] && [ -z "$out" ]; then echo "PASS: non-Bash tool ignored"
else echo "FAIL: non-Bash tool — got $rc: $out"; fails=1; fi

[ "$fails" = 0 ] && echo "ALL PASS" || { echo "FAILURES"; exit 1; }
