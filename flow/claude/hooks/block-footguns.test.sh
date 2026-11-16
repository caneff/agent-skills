#!/usr/bin/env bash
# Contract test for block-footguns.py: synthetic PreToolUse JSON on stdin ->
# exit 0 (allow) or exit 2 + message on stderr (block). Three guards:
#   #1860 a bare `rg` (no path, stdin not supplied) hangs on the harness stdin;
#   #1704 a Python `open(p,'w')` that reads p in the same statement empties p;
#   #1923 a backtick command substitution trips Claude Code's built-in rm check.
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

# Findings of the review wave (C2, C5, C6/P3).
allows "rg with a path from a substitution" 'rg -n foo $(git ls-files)'
blocks "rg with a path from backticks hits the backtick guard" 'rg -n foo `git ls-files`' '$(git ls-files)'
blocks "rg inside a substitution, no path" 'echo "x: $(rg foo)"; echo $(rg foo | head)' "Pass a path"
blocks "rg inside a backtick substitution, no path" 'echo `rg foo`' "Pass a path"
# Only comment handling keeps this quiet: the `;` would split off a bare rg.
allows "separator inside a comment" 'ls # x; rg foo'
blocks "rg under timeout" 'timeout 30 rg foo' "Pass a path"
blocks "rg under nice -n" 'nice -n 5 rg foo' "Pass a path"
blocks "rg under stdbuf" 'stdbuf -oL rg foo' "Pass a path"
blocks "rg in a bash -c script" "bash -c 'rg foo'" "Pass a path"
allows "rg with a path in a bash -c script" "bash -c 'rg foo .'"
allows "timeout rg with a path" 'timeout 30 rg foo .'
# A `<<` inside `$(( ))` is a shift: stripping from it would hide the rg below.
blocks "arithmetic shift is not a heredoc" 'echo $((1<<x))
rg foo' "Pass a path"

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
allows "a second write-mode open is not a read" "python3 -c \"open(p,'w').write(open(p,'w').name)\""
# The shape quoted in text, not run as Python (C1, P1).
allows "commit message quoting the shape" "git commit -m \"never open(p,'w').write(open(p).read())\""
allows "issue body quoting the shape" "gh issue comment 5 --body \"open(p,'w').write(open(p).read())\""
allows "notes file quoting the shape" "cat >> notes.md <<'EOF'
open(p,'w').write(open(p).read())
EOF"
blocks "uv run python" "uv run python -c \"open(p,'w').write(open(p).read())\"" "$msg"
allows "read-mode open only" "python3 -c \"print(open(p).read())\""

# ---- backtick command substitution (#1923) ----
bt="backtick"
blocks "the denied elapsed-time line" 'started=$(date +%s); echo secs $((`date +%s`-started))' "$bt"
blocks "rewrite is in the message" 'echo secs $((`date +%s`-started))' '$(date +%s)'
blocks "plain backtick substitution" 'echo `date`' '$(date)'
blocks "backtick inside a double-quoted bash -c script" "bash -c 'echo \`date\`'" "$bt"
blocks "backtick after a pipe" 'ls | wc -l `echo x`' "$bt"
allows "dollar-paren elapsed time" 'started=$(date +%s); echo secs $(( $(date +%s) - started ))'
allows "backtick in a single-quoted commit message" "git commit -m 'run \`date\` here'"
allows "backtick in a heredoc body" "git commit -F - <<'EOF'
use \`date\` not x
EOF"
allows "backtick in a comment" 'ls # \`date\`'
allows "backtick in a single-quoted gh body" "gh pr comment 5 --body 'the \`rg\` flag'"
allows "escaped backtick" 'echo \`date\`'

# ---- the guard never fails silently ----
# A tool call with no command is reported, not read as a clean command (S2).
out=$(printf '%s' '{"tool_name":"Bash","tool_input":{}}' | python3 -I "$hook" 2>&1); rc=$?
if [ "$rc" = 0 ] && [[ "$out" == *"guard did not run"* ]]; then echo "PASS: missing command says the guard did not run"
else echo "FAIL: missing command — got $rc: $out"; fails=1; fi
# The shim is what settings.json registers: with its script missing it says so
# and lets the call through (python3 on a missing path exits 2, which blocks).
cp "$here/block-footguns.sh" "$tmp/shim.sh"
out=$(printf '%s' '{"tool_name":"Bash","tool_input":{"command":"rg foo"}}' | bash "$tmp/shim.sh" 2>&1); rc=$?
if [ "$rc" = 0 ] && [[ "$out" == *"guard did not run"* ]]; then echo "PASS: shim without its script passes through, saying so"
else echo "FAIL: shim without script — got $rc: $out"; fails=1; fi
out=$(printf '%s' '{"tool_name":"Bash","tool_input":{"command":"rg foo"}}' | bash "$here/block-footguns.sh" 2>&1); rc=$?
if [ "$rc" = 2 ] && [[ "$out" == *"Pass a path"* ]]; then echo "PASS: shim runs the guard"
else echo "FAIL: shim — got $rc: $out"; fails=1; fi
# Input that is not JSON is the harness's fault, not a command to judge.
out=$(printf 'not json' | python3 -I "$hook" 2>&1); rc=$?
if [ "$rc" = 0 ] && [[ "$out" == *"guard did not run"* ]]; then echo "PASS: unreadable input says the guard did not run"
else echo "FAIL: unreadable input — want exit 0 saying 'guard did not run', got $rc: $out"; fails=1; fi
# A non-Bash tool is not this guard's.
out=$(printf '%s' '{"tool_name":"Read","tool_input":{"file_path":"x"}}' | python3 -I "$hook" 2>&1); rc=$?
if [ "$rc" = 0 ] && [ -z "$out" ]; then echo "PASS: non-Bash tool ignored"
else echo "FAIL: non-Bash tool — got $rc: $out"; fails=1; fi

[ "$fails" = 0 ] && echo "ALL PASS" || { echo "FAILURES"; exit 1; }
