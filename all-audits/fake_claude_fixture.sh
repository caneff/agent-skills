#!/usr/bin/env bash
# Test fixture (#559): a fake `claude` binary for driver_test.py's manifest
# tests. Reads the last argv (the audit prompt), and — only for the audit
# named "dead-code" and for "/mutation-audit" — writes a report + the
# manifest the prompt asked for.
# FAKE_CLAUDE_NOOP=1 makes every audit, dead-code included, write nothing.
# FAKE_CLAUDE_MISSING_REPORT=1 makes dead-code write a manifest whose
# report_path names a file that does not exist (#1292).
# FAKE_CLAUDE_INCONCLUSIVE=<why> makes the mutation audit's manifest carry
# an `inconclusive` reason, as the real skill writes on audit.py's exit 3 (#1588).
# FAKE_CLAUDE_RENDEZVOUS / FAKE_CLAUDE_NO_FINDINGS_LOG: see the mutation branch below.
# FAKE_CLAUDE_PREPASS="a.py\nb.py" makes a prompt with no manifest request
# (the mutation prepass) print that ranking (#1567).
# Any other audit (e.g. "duplication" in the same test run) writes nothing,
# simulating a crashed/silent process so the driver must render a missing
# manifest as a named failure, never as a silent skip.
set -euo pipefail
prompt="${*: -1}"

# Record the wait-ceiling variable in this process's log, so a test can see
# what env the driver handed it (#1278).
echo "ceiling=${CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS:-unset}"

# An audit that dies silently: exits 0, writes nothing (#1278).
[ -z "${FAKE_CLAUDE_NOOP:-}" ] || exit 0

# The mutation prepass (#1567) asks for no manifest: it prints a ranking.
if [ -n "${FAKE_CLAUDE_PREPASS:-}" ] && ! printf '%s' "$prompt" | grep -q 'write a manifest to'; then
  printf '%s\n' "$FAKE_CLAUDE_PREPASS"
  exit "${FAKE_CLAUDE_PREPASS_EXIT:-0}"
fi

manifest="$(printf '%s' "$prompt" | grep -oP 'write a manifest to \K\S+' || true)"
[ -n "$manifest" ] || exit 0
# The prompt itself, so a test can see what the driver asked for (#1588). After
# the prepass branch: its candidate lines would read as a ranking.
echo "prompt=$prompt"

case "$prompt" in
  /dead-code\ *)
    dir="$(dirname "$manifest")/report"
    mkdir -p "$dir"
    [ -n "${FAKE_CLAUDE_MISSING_REPORT:-}" ] || echo '<html><body>dead-code report</body></html>' >"$dir/report.html"
    mkdir -p "$(dirname "$manifest")"
    printf '{"report_path": "%s/report.html", "count": 1, "headline": "one finding"}\n' "$dir" >"$manifest"
    # A nonzero exit even with a manifest on disk (#1278), when a test asks.
    exit "${FAKE_CLAUDE_EXIT_DEAD_CODE:-0}"
    ;;
  /mutation-audit\ *)
    # Mutation mode's audit, run inside its worktree: the same report and
    # manifest, and its own exit code when a test asks.
    dir="$(dirname "$manifest")/report"
    mkdir -p "$dir"
    echo '<html><body>mutation report</body></html>' >"$dir/report.html"
    # FAKE_CLAUDE_RENDEZVOUS=<dir> (#1588): mark this module started, wait up
    # to 2s for another module's mark, and write <dir>/overlap if one shows
    # up: two modules were in flight at once.
    if [ -n "${FAKE_CLAUDE_RENDEZVOUS:-}" ]; then
      mark="$FAKE_CLAUDE_RENDEZVOUS/started.$$"
      : >"$mark"
      for _ in $(seq 20); do
        [ "$(ls "$FAKE_CLAUDE_RENDEZVOUS" | grep -c '^started\.')" -lt 2 ] || { : >"$FAKE_CLAUDE_RENDEZVOUS/overlap"; break; }
        sleep 0.1
      done
      rm -f "$mark"
    fi
    # FAKE_CLAUDE_NO_FINDINGS_LOG=1 writes no findings.jsonl and no inconclusive key.
    [ -n "${FAKE_CLAUDE_NO_FINDINGS_LOG:-}" ] || : >"$dir/findings.jsonl"
    if [ -n "${FAKE_CLAUDE_INCONCLUSIVE:-}" ]; then
      # audit.py exited INCONCLUSIVE: no rows, the reason in the manifest.
      printf '{"report_path": "%s/report.html", "count": 0, "headline": "inconclusive", "inconclusive": "%s"}\n' "$dir" "$FAKE_CLAUDE_INCONCLUSIVE" >"$manifest"
    else
      printf '{"report_path": "%s/report.html", "count": 0, "headline": "no survivors"}\n' "$dir" >"$manifest"
    fi
    exit "${FAKE_CLAUDE_EXIT_MUTATION:-0}"
    ;;
  *)
    # Every other audit: no manifest — the crashed/silent-process case. Print
    # a stray .html path to stdout (this becomes its log), the way a real
    # transcript might mention an unrelated file — a log-grepping collector
    # would wrongly pick this up; a manifest-reading one must not.
    echo "see /tmp/unrelated-1234/other.html for context"
    ;;
esac
