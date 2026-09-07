#!/usr/bin/env bash
# Contract test for refresh-landed.sh: synthetic PostToolUse JSON on stdin ->
# exit 0 always; on a push, the landed page regeneration is started in the
# background. `python3` is stubbed via PATH so this runs offline and proves
# generate.py was invoked without actually regenerating anything.
# Run: bash flow/claude/hooks/refresh-landed.test.sh
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
hook="$here/refresh-landed.sh"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# python3 stub: records its argv to a marker file instead of running anything.
stubdir="$tmp/bin"
mkdir -p "$stubdir"
cat > "$stubdir/python3" <<STUB
#!/usr/bin/env bash
printf '%s\n' "\$@" > "$tmp/python3.args"
STUB
chmod +x "$stubdir/python3"

fails=0
# run <name> <expected-exit> <command-string>
run() {
  local name=$1 want=$2 cmd=$3
  local out rc
  out=$(printf '%s' "$cmd" | jq -Rs '{tool_name:"Bash",tool_input:{command:.}}' \
        | PATH="$stubdir:$PATH" bash "$hook" 2>&1)
  rc=$?
  if [ "$rc" != "$want" ]; then
    echo "FAIL: $name — want exit $want, got $rc"; echo "  out: $out"; fails=1; return
  fi
  echo "PASS: $name"
}

# Non-push command: exits 0, no regeneration triggered.
rm -f "$tmp/python3.args"
run "non-push command allowed, no side effects" 0 "git status"
if [ -e "$tmp/python3.args" ]; then
  echo "FAIL: non-push command triggered python3"; fails=1
else
  echo "PASS: non-push command triggered no python3 call"
fi

# Push command: exits 0, and generate.py is invoked in the background.
rm -f "$tmp/python3.args"
run "push command allowed" 0 "git push origin main"
# The hook backgrounds the call; give it a moment to land.
for _ in 1 2 3 4 5; do
  [ -e "$tmp/python3.args" ] && break
  sleep 0.2
done
if [ -e "$tmp/python3.args" ] && grep -q "generate.py" "$tmp/python3.args"; then
  echo "PASS: push command invoked generate.py"
else
  echo "FAIL: push command did not invoke generate.py"; fails=1
fi

# No hard-coded repo path anywhere in the hook.
if grep -qE '/home/[a-zA-Z0-9_-]+/' "$hook"; then
  echo "FAIL: hook contains a hard-coded home path"; fails=1
else
  echo "PASS: hook contains no hard-coded repo path"
fi

[ "$fails" = 0 ] && echo "ALL PASS" || { echo "FAILURES"; exit 1; }
