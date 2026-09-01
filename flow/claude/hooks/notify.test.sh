#!/usr/bin/env bash
# Contract test for notify.sh: synthetic Notification JSON on stdin -> exit 0
# and a PowerShell toast script handed to $NOTIFY_PS. The stub stands in for
# powershell.exe and records what it was asked to run, so the test asserts on
# the toast text without raising a real toast.
# Run: bash flow/claude/hooks/notify.test.sh
set -u
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
hook="$here/notify.sh"
fails=0

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
stub="$tmp/ps-stub"
cap="$tmp/captured"
cat >"$stub" <<'STUB'
#!/usr/bin/env bash
cat >"$CAPTURE_FILE"
STUB
chmod +x "$stub"
export CAPTURE_FILE="$cap"

# run <name> <json> [<substring the toast script must contain>]...
run() {
  local name=$1 json=$2; shift 2
  local rc needle
  rm -f "$cap"
  printf '%s' "$json" | NOTIFY_PS="$stub" "$hook" >/dev/null 2>&1
  rc=$?
  if [ "$rc" != 0 ]; then
    echo "FAIL: $name — hook exited $rc, must always exit 0"; fails=1; return
  fi
  for needle in "$@"; do
    if ! grep -qF -- "$needle" "$cap" 2>/dev/null; then
      echo "FAIL: $name — toast script missing '$needle'"
      echo "  got: $(cat "$cap" 2>/dev/null | tr '\n' ' ')"; fails=1; return
    fi
  done
  echo "PASS: $name"
}

# The four message shapes the CLI emits for background jobs. cwd is the session
# that raised the notification, so it never names the job — the job's label is
# the front of the message, and it must reach the toast's first line.
run "a finished job names itself in the title" \
  '{"notification_type":"agent_completed","cwd":"/home/me/src/sudoku","message":"gridfind-ring-decode finished"}' \
  "Item(0).AppendChild(\$t.CreateTextNode('gridfind-ring-decode finished')" \
  "Item(1).AppendChild(\$t.CreateTextNode('Claude Code · sudoku')"

run "a failed job names itself in the title" \
  '{"notification_type":"agent_completed","cwd":"/home/me/src/sudoku","message":"gridfind-ring-decode failed"}' \
  "Item(0).AppendChild(\$t.CreateTextNode('gridfind-ring-decode failed')"

run "a blocked job puts its label in the title and the detail in the body" \
  '{"notification_type":"agent_needs_input","cwd":"/home/me/src/sudoku","message":"burndown-42 needs your input: approve the push?"}' \
  "Item(0).AppendChild(\$t.CreateTextNode('burndown-42 needs you')" \
  "Item(1).AppendChild(\$t.CreateTextNode('approve the push?')"

run "a blocked job with no detail still names itself" \
  '{"notification_type":"agent_needs_input","cwd":"/home/me/src/sudoku","message":"burndown-42 needs your input"}' \
  "Item(0).AppendChild(\$t.CreateTextNode('burndown-42 needs you')" \
  "Item(1).AppendChild(\$t.CreateTextNode('Claude Code · sudoku')"

run "any other message keeps the project title and shows the message" \
  '{"hook_event_name":"Notification","notification_type":"permission_prompt","cwd":"/home/me/src/gridfind","message":"Needs your approval to push"}' \
  "Item(0).AppendChild(\$t.CreateTextNode('Claude Code · gridfind')" \
  "Item(1).AppendChild(\$t.CreateTextNode('Needs your approval to push')"

run "a quote in the message is doubled, keeping the literal closed" \
  '{"cwd":"/tmp/x","message":"don'"'"'t stop"}' \
  "don''t stop"

run "no message falls back to the notification type" \
  '{"notification_type":"agent_completed","cwd":"/tmp/x"}' \
  "agent_completed"

run "a multi-line message is flattened to one line" \
  '{"cwd":"/tmp/x","message":"first\nsecond"}' \
  "first second"

run "no cwd still toasts, without a project name" \
  '{"message":"hello"}' \
  "Claude Code" "hello"

run "an unparseable payload still toasts rather than failing" \
  'not json at all' \
  "Claude Code"

# A missing powershell.exe is the ordinary case on any non-WSL machine: the
# hook must go quiet, not error.
rm -f "$cap"
printf '%s' '{"message":"x"}' | NOTIFY_PS="$tmp/no-such-ps" "$hook" >/dev/null 2>&1
rc=$?
if [ "$rc" = 0 ] && [ ! -f "$cap" ]; then
  echo "PASS: a missing powershell.exe exits quietly"
else
  echo "FAIL: a missing powershell.exe — exit $rc, capture present: $([ -f "$cap" ] && echo yes || echo no)"; fails=1
fi

[ "$fails" = 0 ] && echo "ALL PASS" || { echo "FAILURES"; exit 1; }
