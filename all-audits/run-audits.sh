#!/usr/bin/env bash
# Run the guarded audit skills as separate, parallel Claude processes, then
# collect their HTML reports under one folder behind an index.html.
#
# Why a subprocess per audit: the audit skills carry `disable-model-invocation`,
# so an orchestrating agent's Skill tool can't launch them. But `claude -p "/name"`
# is a USER invocation of the slash command, which the guard allows. One process
# per audit => parallelism + context isolation, without loading any skill header
# into a live session.
#
# Usage:
#   run-audits.sh [REPO]                 fresh sweep of all twelve audits (default)
#   run-audits.sh [REPO] --out DIR       write into DIR, accumulating (no wipe)
#   run-audits.sh [REPO] --only a,b      run just these audits (into the run dir)
#   run-audits.sh [REPO] --index --out DIR   rebuild index only, over DIR's reports
#   run-audits.sh [REPO] --force         bypass the staleness cache, run everything
#
# The two expensive LLM passes (domain-drift, type-tightness) are gated by a
# per-repo staleness cache: while the repo is materially unchanged since their
# last run, they are skipped and their cached report is reused in the index.
set -euo pipefail

# --- Parse args --------------------------------------------------------------
REPO=""
OUT=""
ONLY=""
INDEX_ONLY=0
FORCE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --out) OUT="$2"; shift 2 ;;
    --only) ONLY="$2"; shift 2 ;;
    --index) INDEX_ONLY=1; shift ;;
    --force|--all) FORCE=1; shift ;;
    -*) echo "unknown flag: $1" >&2; exit 2 ;;
    *) REPO="$1"; shift ;;
  esac
done
REPO="${REPO:-$PWD}"
REPO="$(cd "$REPO" && pwd)"   # absolute

HERE="$(cd "$(dirname "$0")" && pwd)"

# ponytail: --dangerously-skip-permissions because these run unattended in the
# background and each needs Read/Grep/Bash/Write to produce its HTML report.
# Drop the flag to run one interactively if you'd rather approve tools by hand.
CLAUDE_FLAGS=(-p --dangerously-skip-permissions)

# The full set — six original + six added (spec #365, T5). mutation-audit is
# deliberately NOT here: it is opt-in, targeted at one module, never swept.
AUDITS=(
  ponytail-audit
  test-audit
  comment-audit
  thermo-nuclear-code-quality-review
  improve-codebase-architecture
  audit-instructions
  dead-code
  duplication
  error-handling
  docstring-coverage
  domain-drift
  type-tightness
)

# The two expensive LLM passes gated by the staleness cache, and each one's
# ground-truth override sources (a change to any forces a re-run). type-tightness
# has no vocabulary-source doc, so it gates on file-count + backstop alone.
declare -A GATED_GROUND_TRUTH=(
  [domain-drift]="CONTEXT.md,docs/adr/"
  [type-tightness]=""
)
THRESHOLD="${AUDITS_THRESHOLD:-10}"
BACKSTOP="${AUDITS_BACKSTOP_DAYS:-30}"

is_gated() { [ -n "${GATED_GROUND_TRUTH[$1]+x}" ]; }

# --- Which audits are in play this invocation --------------------------------
if [ -n "$ONLY" ]; then
  IFS=',' read -r -a SELECTED <<< "$ONLY"
else
  SELECTED=("${AUDITS[@]}")
fi

# --- Resolve the run dir -----------------------------------------------------
# Base lives in ~/.cache (persistent) not /tmp, which most Linux boxes wipe on
# reboot. TTL prunes only the ephemeral `run-*` dirs — the per-repo cache
# (`<key>.json` + `<key>/reports/`) must survive to be reused on a skip.
TTL_DAYS="${AUDITS_TTL_DAYS:-3}"
BASE="${XDG_CACHE_HOME:-$HOME/.cache}/all-audits"
mkdir -p "$BASE"
find "$BASE" -mindepth 1 -maxdepth 1 -type d -name 'run-*' -mtime "+$TTL_DAYS" -exec rm -rf {} + 2>/dev/null || true

if [ -n "$OUT" ]; then
  RUN="$(mkdir -p "$OUT" && cd "$OUT" && pwd)"   # accumulate into the given dir
elif [ "$INDEX_ONLY" = 1 ]; then
  echo "ERROR: --index needs --out DIR — the dir whose reports to index." >&2
  exit 2
else
  RUN="$BASE/run-$(date +%Y%m%d-%H%M%S)"
fi
export TMPDIR="$RUN"        # relocate audit reports off fixed /tmp paths
OUTLOGS="$RUN/logs"
COLLECTION="$RUN/collection"
mkdir -p "$OUTLOGS" "$COLLECTION"
echo "run dir: $RUN"
echo "collecting under: $COLLECTION"
echo "repo: $REPO"
echo

replace_dir() {  # replace_dir SRC DEST — drop DEST's slot, refill it from SRC
  rm -rf "$2"
  cp -r "$1" "$2"
}

run_one() {
  local name="$1"
  echo "[$name] starting"
  # The report path the skill prints lands in this log; grep it out afterward.
  claude "${CLAUDE_FLAGS[@]}" "/$name $REPO" >"$OUTLOGS/$name.log" 2>&1
  echo "[$name] done"
}

# name -> "unchanged since <sha>" for a skipped gated audit.
declare -A SKIP_NOTE
KEY="$(python3 "$HERE/cache.py" key "$REPO")"
STABLE="$BASE/$KEY/reports"   # persists across TTL prunes, reused on skip

# --- Decide + run ------------------------------------------------------------
# --index runs nothing: it rebuilds the index over reports already in COLLECTION.
TO_RUN=()
if [ "$INDEX_ONLY" = 0 ]; then
  for name in "${SELECTED[@]}"; do
    if is_gated "$name" && [ "$FORCE" = 0 ]; then
      decision="$(python3 "$HERE/cache.py" decide "$REPO" "$name" \
        "${GATED_GROUND_TRUTH[$name]}" "$THRESHOLD" "$BACKSTOP")"
      verdict="$(printf '%s' "$decision" | cut -f1)"
      if [ "$verdict" = "SKIP" ]; then
        sha="$(printf '%s' "$decision" | cut -f2)"
        cached_dir="$(printf '%s' "$decision" | cut -f3)"
        if [ -d "$cached_dir" ]; then
          replace_dir "$cached_dir" "$COLLECTION/$name"
          SKIP_NOTE["$name"]="unchanged since ${sha:0:8}"
          echo "[$name] skipped (unchanged since ${sha:0:8}), reusing cached report"
          continue
        fi
        echo "[$name] cache says skip but cached report is gone — running fresh"
      fi
    fi
    TO_RUN+=("$name")
  done

  if [ "${#TO_RUN[@]}" -gt 0 ]; then
    # Test one before fanning out. If the guard rejects a -p slash invocation,
    # this fails fast and we don't spawn the rest.
    smoke="${TO_RUN[0]}"
    echo "== smoke test: $smoke =="
    run_one "$smoke"
    if grep -qiE 'cannot be used with Skill tool|disable-model-invocation' "$OUTLOGS/$smoke.log"; then
      echo "ABORT: -p slash invocation was rejected by the guard. See $OUTLOGS/$smoke.log" >&2
      exit 1
    fi
    echo "smoke test passed; fanning out the rest"
    echo
    pids=()
    for name in "${TO_RUN[@]:1}"; do
      run_one "$name" &
      pids+=("$!")
    done
    [ "${#pids[@]}" -gt 0 ] && wait "${pids[@]}"
  fi
fi

# --- Collect fresh reports into the collection -------------------------------
# A skipped gated audit was already copied in above. A fresh one: pull its
# report folder out of the log path, and — if gated — persist it to the stable
# per-repo cache and record this run, so a later sweep can skip and reuse it.
for name in "${TO_RUN[@]}"; do
  report="$(grep -oE '/[^ ]+\.html' "$OUTLOGS/$name.log" | head -1 || true)"
  if [ -n "$report" ] && [ -f "$report" ]; then
    replace_dir "$(dirname "$report")" "$COLLECTION/$name"
    if is_gated "$name"; then
      mkdir -p "$STABLE"
      replace_dir "$COLLECTION/$name" "$STABLE/$name"
      python3 "$HERE/cache.py" update "$REPO" "$name" "$STABLE/$name"
    fi
  fi
done

# --- Build the report links by scanning the collection -----------------------
# Uniform over fresh, skipped-and-reused, and reports left by earlier --only
# runs into this same --out dir: the index reflects whatever sits on disk, not
# only what ran this invocation.
declare -A report_link
for name in "${AUDITS[@]}"; do
  found="$(find "$COLLECTION/$name" -maxdepth 1 -name '*.html' 2>/dev/null | head -1 || true)"
  if [ -n "$found" ]; then
    report_link["$name"]="$name/$(basename "$found")"
  else
    report_link["$name"]=""
  fi
done

# --- Synthesis pass ----------------------------------------------------------
# One claude -p reads the collected reports and writes a short synthesis for the
# index lede. Non-fatal — a missing lede beats no index. AUDITS_NO_SYNTH=1 skips
# it (offline index rebuilds, tests).
report_files=()
for name in "${AUDITS[@]}"; do
  [ -n "${report_link[$name]}" ] && report_files+=("$COLLECTION/${report_link[$name]}")
done
synthesis=""
if [ "${AUDITS_NO_SYNTH:-0}" != 1 ] && [ "${#report_files[@]}" -gt 0 ]; then
  echo "== synthesis pass =="
  synthesis="$(claude "${CLAUDE_FLAGS[@]}" \
    "Read these ${#report_files[@]} audit report HTML files and write a 2-3 sentence synthesis of the repo's overall state for the lede of an index page. Plain prose only — no preamble, no markdown, no headings, no lists. Files: ${report_files[*]}" \
    2>/dev/null || true)"
fi
synthesis="$(printf '%s' "$synthesis" | sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g')"

# --- Build index.html (visual-teach styling, matching the reports) -----------
for name in "${AUDITS[@]}"; do
  if [ -d "$COLLECTION/$name/assets" ]; then
    cp -r "$COLLECTION/$name/assets" "$COLLECTION/assets"
    break
  fi
done

count="${#AUDITS[@]}"
index="$COLLECTION/index.html"
{
  cat <<'HEAD'
<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>All-audits index</title>
<link rel="stylesheet" href="assets/base/base.css">
<link rel="stylesheet" href="assets/components/callout/callout.css">
<script src="assets/base/base.js"></script>
<style>
  main { --vt-measure: 1080px; }
  .audit-table { width:100%; border-collapse:collapse; }
  .audit-table th, .audit-table td { border:1px solid var(--vt-rule); padding:.6rem .8rem; text-align:left; vertical-align:top; }
  .audit-table th { background:var(--vt-soft); font-weight:600; }
  .audit-table tr:nth-child(even) td { background:var(--vt-stripe); }
</style></head><body><main>
HEAD
  printf '<p class="vt-kicker">All-audits sweep</p>\n'
  printf '<h1>%s <span style="color:var(--vt-muted)">· %s-audit sweep</span></h1>\n' "$REPO" "$count"
  [ -n "$synthesis" ] && printf '<p class="vt-lede">%s</p>\n' "$synthesis"
  echo '<h2>Reports</h2><div class="vt-table-wrap"><table class="audit-table">'
  echo '<thead><tr><th>Audit</th><th>Report</th><th>Status</th></tr></thead><tbody>'
  for name in "${AUDITS[@]}"; do
    link="${report_link[$name]}"
    note="${SKIP_NOTE[$name]:-}"
    if [ -n "$link" ]; then
      printf '<tr><td>%s</td><td><a href="%s">open report</a></td><td>%s</td></tr>\n' \
        "$name" "$link" "$note"
    else
      printf '<tr><td>%s</td><td style="color:var(--vt-muted)">no report</td><td>%s</td></tr>\n' \
        "$name" "$note"
    fi
  done
  echo '</tbody></table></div></main></body></html>'
} >"$index"

echo
echo "index: $index"
echo "logs: $OUTLOGS"

# Open the index (Linux). Swap for `open` on macOS.
command -v xdg-open >/dev/null && xdg-open "$index" >/dev/null 2>&1 || true
