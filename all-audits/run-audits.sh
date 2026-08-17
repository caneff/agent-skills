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
#   run-audits.sh --mutation a.py,b.py   run mutation-audit on each module, one
#                                         fresh git worktree at a time
#
# The two expensive LLM passes (domain-drift, type-tightness) are gated by a
# per-repo staleness cache: while the repo is materially unchanged since their
# last run, they are skipped and their cached report is reused in the index.
set -euo pipefail

# report_path_from_log LOGFILE — pull the audit's report path out of its
# stdout log. Prefers the machine-readable `ALL_AUDITS_REPORT=/abs/path`
# marker (see all-audits/harness/HTML-REPORT.md); falls back to the legacy
# bare single-line path grep for audits that haven't adopted the marker yet.
report_path_from_log() {
  local log="$1" found
  found="$(grep -oP 'ALL_AUDITS_REPORT=\K/[^ ]+\.html' "$log" 2>/dev/null | head -1 || true)"
  [ -n "$found" ] && { printf '%s\n' "$found"; return; }
  grep -oE '/[^ ]+\.html' "$log" 2>/dev/null | head -1 || true
}

# audit_prompt NAME REPO — the prompt handed to `claude -p`: the slash
# invocation plus a whole-repo override so diff-oriented audits scan the
# entire tree, not a git diff (#397). Mirrors the fan-out sentence in
# SKILL.md so the bash sweep and the agent-fan-out sweep agree on scope.
# Takes repo as $2 (not the global $REPO) so it's callable from a sourced
# test where $REPO is unset.
audit_prompt() {
  printf '/%s %s\n%s\n' "$1" "$2" \
    "Audit the ENTIRE repository at $2 — every source file, not a git diff or recent-changes review. Override any branch-diff or hot-spot default the skill has."
}

# mutation_prepass_prompt REPO — the prompt for the mutation auto-select
# pre-pass (#400): mirrors audit_prompt's plain, one-job tone. Asks claude to
# name the mutation-worthy core modules (solver/oracle modules with a sibling
# test where a silently-passing test is dangerous), one path per line.
mutation_prepass_prompt() {
  printf 'Read the repository at %s and identify the mutation-worthy core modules: solver/oracle modules that have a sibling test, where a silently-passing test would be dangerous. Print ONLY the module file paths, one per line — no prose, no numbering, no markdown.\n' "$1"
}

# mutation_cap N CANDIDATE... — pure (candidates, N) -> (capped, skipped_count)
# step (#400), no subprocess/claude involved. Prints the first N candidates
# (one per line), then a final "SKIPPED:<count>" line — 0 when nothing was
# truncated. ponytail: encoding both outputs on stdout (instead of a nameref
# or a second output stream) is the shortest seam that stays testable via a
# plain `$(...)` capture.
# mutation_cap_targets / mutation_cap_skipped — decode mutation_cap's stdout.
# Both callers of mutation_cap (the script and its tests) need the same two
# facts out of the sentinel-tagged stream; factored here once instead of
# repeating the grep/cut pair at every call site.
mutation_cap_targets() { grep -v '^SKIPPED:' || true; }
mutation_cap_skipped() { grep '^SKIPPED:' | cut -d: -f2; }

replace_dir() {  # replace_dir SRC DEST — drop DEST's slot, refill it from SRC
  rm -rf "$2"
  cp -r "$1" "$2"
}

# module_slug MODULE — a module path (e.g. "foo/bar.py") becomes one safe,
# flat collection-dir name ("foo_bar.py"). ponytail: slashes -> underscores is
# the whole scheme — good enough to keep a nested module's report in a single
# dir without collisions between sibling-named files in different dirs, and
# simple enough to read back by eye in the collection listing.
module_slug() { printf '%s\n' "$1" | tr '/' '_'; }

# collect_module_report LOGFILE COLLECTION_DIR MODULE — THE hermetic seam
# (#401): pull the report path out of a mutation-audit log via #391's path
# contract, then copy its whole directory (report.html, findings.jsonl, any
# assets/) into COLLECTION_DIR/<module_slug>/. No-ops (silently) if the log
# names no report — the caller is expected to have already recorded a setup
# failure in that case.
collect_module_report() {
  local log="$1" collection_dir="$2" module="$3" report
  report="$(report_path_from_log "$log")"
  [ -n "$report" ] && [ -f "$report" ] || return 0
  replace_dir "$(dirname "$report")" "$collection_dir/$(module_slug "$module")"
}

# write_setup_failure_report COLLECTION_DIR MODULE REASON — when a module's
# worktree or env setup fails before mutmut can even run, record that
# explicitly instead of leaving an absent/empty report a later reader could
# mistake for "ran clean, zero survivors." Minimal, self-contained, honors the
# same collection/<module_slug>/ contract a real mutation-audit report uses.
write_setup_failure_report() {
  local collection_dir="$1" module="$2" reason="$3" dir
  dir="$collection_dir/$(module_slug "$module")"
  mkdir -p "$dir"
  printf '<!doctype html><html><body><h1>mutation-audit setup failure</h1><p>Module: %s</p><p>Reason: %s</p></body></html>\n' \
    "$module" "$reason" >"$dir/report.html"
  printf '{"status":"setup_failure","module":"%s","reason":"%s"}\n' "$module" "$reason" >"$dir/findings.jsonl"
}

mutation_cap() {
  local n="$1"; shift
  local total="$#" skipped=0 i=0
  [ "$total" -gt "$n" ] && skipped=$((total - n))
  for c in "$@"; do
    i=$((i + 1))
    [ "$i" -gt "$n" ] && break
    printf '%s\n' "$c"
  done
  printf 'SKIPPED:%s\n' "$skipped"
}

# Guard the rest so a test can `source` this file to reach the functions
# above without triggering a live sweep.
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then

# --- Parse args --------------------------------------------------------------
REPO=""
OUT=""
ONLY=""
INDEX_ONLY=0
FORCE=0
MUTATION=0
MUTATION_LIST=""
while [ $# -gt 0 ]; do
  case "$1" in
    --out) OUT="$2"; shift 2 ;;
    --only) ONLY="$2"; shift 2 ;;
    --index) INDEX_ONLY=1; shift ;;
    --force|--all) FORCE=1; shift ;;
    --mutation)
      MUTATION=1
      # "$2" may be absent (--mutation is the last arg = no list, i.e.
      # trigger the auto-select pre-pass) — guard under set -u.
      if [ $# -ge 2 ]; then MUTATION_LIST="$2"; shift 2; else MUTATION_LIST=""; shift 1; fi
      ;;
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

# --mutation is its own short-circuit mode, mirroring --index: parse the
# target list, echo the selection observably, and run each selected module
# through mutation-audit in its own disposable git worktree — WITHOUT running
# the twelve-audit claude sweep.
#
# An explicit list (--mutation a.py,b.py) bypasses BOTH the pre-pass and the
# cap below — that's the current behavior, entirely offline.
#
# No list (--mutation with nothing, or "") triggers the auto-select pre-pass
# (#400): one `claude -p` reads the repo and names the mutation-worthy core
# modules, one per line. AUDITS_NO_SYNTH=1 skips the pre-pass — the mutation
# analogue of the existing synthesis-pass gate — leaving zero candidates and
# invoking no claude. ponytail: MUTATION_CANDIDATES lets a test inject a
# candidate list instead of calling claude, so the cap/skip-line behavior is
# testable offline without a subprocess.
#
# MUTATION_DRY_RUN=1 stops right after the selection echo — no worktree, no
# claude — the same offline seam #400 gave the empty-list case via
# AUDITS_NO_SYNTH=1. The test suite sets it so selection stays hermetic; the
# per-module worktree/mutmut lifecycle itself is manual/integration-verified
# (non-hermetic, environment-dependent), per the ticket.
if [ "$MUTATION" = 1 ]; then
  MUTATION_TARGETS=()
  IFS=',' read -r -a _mutation_raw <<< "$MUTATION_LIST"
  for t in "${_mutation_raw[@]:-}"; do
    t="${t#"${t%%[![:space:]]*}"}"   # trim leading whitespace
    t="${t%"${t##*[![:space:]]}"}"   # trim trailing whitespace
    [ -n "$t" ] && MUTATION_TARGETS+=("$t")
  done

  FINAL_TARGETS=()
  skipped=0
  if [ "${#MUTATION_TARGETS[@]}" -gt 0 ]; then
    # Explicit list: bypass the pre-pass and the cap entirely.
    FINAL_TARGETS=("${MUTATION_TARGETS[@]}")
  else
    # No explicit list: auto-select the candidates.
    CANDIDATES=()
    if [ -n "${MUTATION_CANDIDATES:-}" ]; then
      while IFS= read -r line; do
        [ -n "$line" ] && CANDIDATES+=("$line")
      done <<< "$MUTATION_CANDIDATES"
    elif [ "${AUDITS_NO_SYNTH:-0}" != 1 ]; then
      prepass_out="$(claude "${CLAUDE_FLAGS[@]}" "$(mutation_prepass_prompt "$REPO")" 2>/dev/null || true)"
      while IFS= read -r line; do
        line="${line#"${line%%[![:space:]]*}"}"
        line="${line%"${line##*[![:space:]]}"}"
        [ -n "$line" ] && CANDIDATES+=("$line")
      done <<< "$prepass_out"
    fi
    # else: AUDITS_NO_SYNTH=1 and no injection — CANDIDATES stays empty, no
    # claude invoked.

    MUTATION_MAX_N="${MUTATION_MAX:-10}"
    cap_out="$(mutation_cap "$MUTATION_MAX_N" "${CANDIDATES[@]:-}")"
    skipped="$(printf '%s\n' "$cap_out" | mutation_cap_skipped)"
    while IFS= read -r line; do
      [ -n "$line" ] && FINAL_TARGETS+=("$line")
    done < <(printf '%s\n' "$cap_out" | mutation_cap_targets)
  fi

  for t in "${FINAL_TARGETS[@]:-}"; do
    [ -n "$t" ] && printf 'mutation-target: %s\n' "$t"
  done
  [ "${skipped:-0}" -gt 0 ] && printf '… %s more modules skipped (raise MUTATION_MAX to include them)\n' "$skipped"

  if [ "${MUTATION_DRY_RUN:-0}" = 1 ]; then
    exit 0
  fi

  if [ "${#FINAL_TARGETS[@]}" -eq 0 ]; then
    exit 0
  fi

  # --- Real per-module run: sequential, one worktree live at a time --------
  BASE="${XDG_CACHE_HOME:-$HOME/.cache}/all-audits"
  mkdir -p "$BASE"
  if [ -n "$OUT" ]; then
    RUN="$(mkdir -p "$OUT" && cd "$OUT" && pwd)"
  else
    RUN="$BASE/run-$(date +%Y%m%d-%H%M%S)"
  fi
  export TMPDIR="$RUN"        # relocate mutation-audit reports off fixed /tmp paths
  OUTLOGS="$RUN/logs"
  COLLECTION="$RUN/collection"
  WORKTREES="$RUN/worktrees"
  mkdir -p "$OUTLOGS" "$COLLECTION" "$WORKTREES"
  echo "run dir: $RUN"
  echo "collecting under: $COLLECTION"
  echo

  # Backstop: if the script crashes mid-loop, sweep any worktree dirs still
  # registered under $WORKTREES on exit. The per-module cleanup below is the
  # normal path; this only catches an abnormal exit between iterations.
  mutation_worktrees_cleanup() {
    local d
    for d in "$WORKTREES"/*/; do
      [ -d "$d" ] || continue
      git -C "$REPO" worktree remove --force "$d" >/dev/null 2>&1 || true
    done
    git -C "$REPO" worktree prune >/dev/null 2>&1 || true
  }
  trap mutation_worktrees_cleanup EXIT

  # cleanup_worktree WT — remove one worktree and prune. Called explicitly on
  # every exit path of run_mutation_module below, NOT via `trap ... RETURN` —
  # bash's RETURN trap fires on every subsequent function return anywhere in
  # the shell (not just the function that set it), so a trap set here would
  # misfire on later helper calls (e.g. module_slug) with stale/unset locals
  # under `set -u`, aborting the whole sweep. Explicit calls avoid that.
  cleanup_worktree() {
    git -C "$REPO" worktree remove --force "$1" >/dev/null 2>&1 || true
    git -C "$REPO" worktree prune >/dev/null 2>&1 || true
  }

  # run_mutation_module MODULE — one module's full lifecycle: fresh worktree,
  # env resolution, `/mutation-audit <module>` scoped to that one module, copy
  # the report into the collection, then always tear the worktree down
  # (success or failure) before returning. Wrapped in `|| true` at every call
  # site's loop so one module's unexpected failure (e.g. a `cp` error inside
  # collect_module_report, under `set -e`) can't abort the rest of the sweep.
  run_mutation_module() {
    local module="$1" slug wt log
    slug="$(module_slug "$module")"
    wt="$WORKTREES/$slug"
    log="$OUTLOGS/mutation-$slug.log"

    echo "[mutation:$module] creating worktree"
    if ! git -C "$REPO" worktree add --detach "$wt" HEAD >"$log" 2>&1; then
      echo "[mutation:$module] worktree creation failed — see $log" >&2
      write_setup_failure_report "$COLLECTION" "$module" "git worktree add failed"
      cleanup_worktree "$wt"
      return 0
    fi

    # ponytail: env-resolution heuristic ceiling — only the uv-managed case
    # (uv.lock / pyproject.toml -> `uv sync`) is handled. A repo on another
    # toolchain (poetry, requirements.txt-only, non-Python) has no resolution
    # path here, so it's reported as an unresolved env rather than silently
    # skipped — never let an unrecognized toolchain fall through to mutmut
    # running against an unresolved env. Widen this when a new toolchain
    # needs support.
    if [ -f "$wt/uv.lock" ] || [ -f "$wt/pyproject.toml" ]; then
      echo "[mutation:$module] resolving env (uv sync)"
      if ! (cd "$wt" && uv sync) >>"$log" 2>&1; then
        echo "[mutation:$module] env resolution failed — see $log" >&2
        write_setup_failure_report "$COLLECTION" "$module" "uv sync failed"
        cleanup_worktree "$wt"
        return 0
      fi
    else
      echo "[mutation:$module] no recognized env manifest (uv.lock/pyproject.toml) — see $log" >&2
      write_setup_failure_report "$COLLECTION" "$module" "no recognized env manifest (uv.lock/pyproject.toml); env resolution heuristic ceiling"
      cleanup_worktree "$wt"
      return 0
    fi

    echo "[mutation:$module] running /mutation-audit $module"
    (cd "$wt" && claude "${CLAUDE_FLAGS[@]}" "$(printf '/mutation-audit %s\n' "$module")") >>"$log" 2>&1 || true

    collect_module_report "$log" "$COLLECTION" "$module" || true
    if [ ! -d "$COLLECTION/$slug" ]; then
      echo "[mutation:$module] no report found — see $log" >&2
      write_setup_failure_report "$COLLECTION" "$module" "mutation-audit produced no report"
    fi
    cleanup_worktree "$wt"
    echo "[mutation:$module] done"
  }

  for t in "${FINAL_TARGETS[@]:-}"; do
    [ -n "$t" ] || continue
    run_mutation_module "$t" || true
  done

  echo
  echo "collection: $COLLECTION"
  exit 0
fi

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

run_one() {
  local name="$1"
  echo "[$name] starting"
  # The report path the skill prints lands in this log; grep it out afterward.
  claude "${CLAUDE_FLAGS[@]}" "$(audit_prompt "$name" "$REPO")" >"$OUTLOGS/$name.log" 2>&1
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
  report="$(report_path_from_log "$OUTLOGS/$name.log")"
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
# AUDITS_NO_OPEN=1 suppresses the launch — the test suite and unattended
# sweeps set it so an index rebuild does not hijack the user's browser.
if [ "${AUDITS_NO_OPEN:-0}" != 1 ] && command -v xdg-open >/dev/null; then
  xdg-open "$index" >/dev/null 2>&1 || true
fi

fi
