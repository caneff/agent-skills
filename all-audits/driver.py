#!/usr/bin/env python3
"""The audit sweep driver (#558): replaces run-audits.sh, should_run.py, and
cache.py with one readable Python program.

Runs each guarded audit as its own `claude -p "/name"` process (see
run-audits.sh's original header comment for why: several audit skills carry
`disable-model-invocation`, so only an explicit `-p "/name"` slash invocation
gets past the guard — a subagent fan-out would silently lose them), collects
the report folders under one `collection/` dir, and builds `index.html`.

A sweep is three steps: plan (ask the staleness cache what still needs a run),
execute (the only step that spawns audits), collect (assemble the collection
and render the index). The `index` mode calls collect alone.

Environment: `SWEEP_JOBS` (#1666) caps how many audits a sweep runs at once
after the smoke test (a positive integer, default 4; anything else exits 2
before any audit starts). `MUTATION_JOBS` (#1588) does the same for the
modules of a `mutation` sweep (default 4).
"""
import argparse
import collections
import concurrent.futures
import dataclasses
import datetime as _dt
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import threading
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "harness"))
from audits_data import AUDIT_NAMES, GATED, PYTHON_ONLY, SHORT_SET  # noqa: E402
import auditlib  # noqa: E402
import pagelib  # noqa: E402
import audit_record  # noqa: E402
import findings_log  # noqa: E402
import mutation_run  # noqa: E402
from procs import claude_env, scrubbed_env, run as _run  # noqa: E402
import shellcmd  # noqa: E402
from stored_sweeps import (  # noqa: E402
    MULTI_DIR, OWNER, RECORD_FILE, earlier_record, file_audit_record, find_stored_sweep, label_refusal,
    latest_record_url, prune_closed_sweeps, record_repo, repo_identity, repo_sweep_dirs, resume_unposted,
    stored_sweeps_base, triage_label, write_json,
)
from mutation_run import parse_utc  # noqa: E402

DEFAULT_THRESHOLD = 10
DEFAULT_BACKSTOP_DAYS = 30
CLAUDE_FLAGS = ["-p", "--dangerously-skip-permissions"]


# --- pure decision: should_run (ported from should_run.py) ------------------

def should_run(audit, cache_record, git_state):
    """Return (run: bool, reason: str). Pure — no git/filesystem/clock calls.

    audit: {"threshold", "backstop_days", "ground_truth": [prefix]}.
    cache_record: {"last_sha", "age_days"} or None when the audit never ran.
    git_state: {"dirty": bool, "changed_files": [path]} since last_sha.
    """
    if cache_record is None:
        return True, "no cached run"
    if git_state["dirty"]:
        return True, "dirty working tree"

    hit = None
    for f in git_state["changed_files"]:
        for src in audit.get("ground_truth", []):
            if f == src or f.startswith(src.rstrip("/") + "/"):
                hit = f
                break
        if hit:
            break
    if hit:
        return True, f"ground-truth change: {hit}"

    backstop = audit.get("backstop_days", DEFAULT_BACKSTOP_DAYS)
    if cache_record["age_days"] > backstop:
        return True, f"last run older than backstop ({cache_record['age_days']:g}d > {backstop}d)"

    threshold = audit.get("threshold", DEFAULT_THRESHOLD)
    changed = len(git_state["changed_files"])
    if changed >= threshold:
        return True, f"{changed} files changed >= threshold {threshold}"

    return False, f"unchanged: {changed} files < threshold {threshold}, clean, within backstop"


# --- cache: repo-keyed staleness record --------------------------------------

def cache_base():
    return os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "all-audits")


def repo_key(repo_path):
    digest = hashlib.sha1(repo_path.encode("utf-8")).hexdigest()[:8]
    base = os.path.basename(repo_path.rstrip("/")) or "repo"
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in base)
    return f"{safe}-{digest}"


def load_record(path):
    """An unreadable or corrupt record is "no cached run", never a crash
    (#558 regression fix) — matches the old bash `cache.py decide`, whose
    subprocess crash on bad JSON printed nothing, failed the `= "SKIP"`
    check, and let the audit run."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_record(path, record):
    """Write-then-rename so an interrupted run can never leave a truncated
    record for the next `load_record` to trip over."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)
    os.replace(tmp, path)


def _record_file(repo, base=None):
    return os.path.join(base or cache_base(), repo_key(repo) + ".json")


def git_state(repo, last_sha):
    status = shellcmd.git(["-C", repo, "status", "--porcelain"], ok=range(256))
    # A status that failed proves nothing about cleanliness: force dirty, as for a failed diff below.
    dirty = status.returncode != 0 or bool(status.stdout.strip())
    changed = []
    if last_sha:
        result = shellcmd.git(["-C", repo, "diff", "--name-only", f"{last_sha}..HEAD"], ok=range(256))
        if result.returncode != 0:
            # A SHA `git diff` can't resolve (never a real commit, or pruned)
            # proves nothing about staleness — force dirty so should_run can
            # never read "no diff output" as "unchanged" (#558).
            return {"dirty": True, "changed_files": []}
        changed = [ln for ln in result.stdout.splitlines() if ln.strip()]
    return {"dirty": dirty, "changed_files": changed}


def head_sha(repo):
    return shellcmd.git(["-C", repo, "rev-parse", "HEAD"]).stdout.strip()


def now_iso():
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def age_days(timestamp):
    now = _dt.datetime.now(_dt.timezone.utc)
    return (now - parse_utc(timestamp)).total_seconds() / 86400.0


@dataclasses.dataclass
class CacheDecision:
    run: bool
    reason: str
    sha: str = None
    report_dir: str = None


def decide(repo, name, ground_truth, threshold=DEFAULT_THRESHOLD, backstop=DEFAULT_BACKSTOP_DAYS, base=None,
           key=None):
    """The cache decision as a structured result (#558) — not the old
    tab-separated RUN/SKIP text `cache.py decide` printed. `key` names the
    record when `repo` is a throwaway checkout (#1678); git still reads `repo`."""
    record = load_record(_record_file(key or repo, base))
    entry = record.get(name)
    cache_record = None
    if entry and {"last_sha", "timestamp", "report_dir"} <= entry.keys():
        try:
            cache_record = {"last_sha": entry["last_sha"], "age_days": age_days(entry["timestamp"])}
        except ValueError:
            entry = None
    else:
        entry = None  # a legacy/incomplete entry is "no cached run", never a KeyError
    state = git_state(repo, entry["last_sha"] if entry else None)
    cfg = {"ground_truth": ground_truth, "threshold": threshold, "backstop_days": backstop}
    run, reason = should_run(cfg, cache_record, state)
    if run:
        return CacheDecision(run=True, reason=reason)
    return CacheDecision(run=False, reason=reason, sha=entry["last_sha"], report_dir=entry["report_dir"])


def update_cache(repo, name, report_dir, base=None, key=None):
    path = _record_file(key or repo, base)
    record = load_record(path)
    record[name] = {
        "last_sha": head_sha(repo),
        "timestamp": now_iso(),
        "report_dir": report_dir,
    }
    save_record(path, record)


# --- mutation recency: what each module's last mutation run covered (#1567) --

def record_mutation(repo, module, base=None):
    """Stamp `module` as mutation-run at HEAD now, beside the audit records
    in the same per-repo cache file."""
    path = _record_file(repo, base)
    record = load_record(path)
    mutation_run.stamp(record, module, head_sha(repo), now_iso())
    save_record(path, record)


# --- filesystem / prompt helpers (ported from run-audits.sh) ----------------

def replace_dir(src, dest):
    if os.path.exists(dest):
        shutil.rmtree(dest)
    shutil.copytree(src, dest)


def module_slug(module):
    return module.replace("/", "_")


def manifest_instruction(manifest_path):
    return (
        f"\nAfter writing the report, write a manifest to {manifest_path} — a JSON object with "
        '"report_path" (the report\'s absolute path), "count" (how many actionable findings), and "headline" '
        "(the one-line verdict). This is how the sweep finds your report; it does not scan your output."
    )


# The one no-open instruction (#1598): the sweep's audits and every per-module
# mutation run carry it, so a driver run opens only its final index.
NO_OPEN_INSTRUCTION = (
    "Do NOT open the report: skip every xdg-open/open/start step the skill would run. You are one "
    "run inside an all-audits driver, and the driver opens only the final index — a page per report "
    "would bury it. Just write the report."
)


def audit_prompt(name, repo, manifest_path=None):
    ignore_file = os.path.join(repo, ".audit-ignore.md")
    ignore_block = ""
    if os.path.isfile(ignore_file):
        ignore_block = "\nThe repo has already reviewed and rejected these findings — do not raise them again:\n" + open(
            ignore_file, encoding="utf-8"
        ).read()
    override = (
        f"Audit the ENTIRE repository at {repo} — every source file, not a git diff or recent-changes review. "
        "Override any branch-diff or hot-spot default the skill has. Exclude vendored, generated, and dependency "
        "trees (node_modules, .venv, dist, vendor, build output, lockfiles), any .git/ tree, and any worktrees/ "
        "tree — audit only the project's own tracked source. " + NO_OPEN_INSTRUCTION
    )
    manifest_block = manifest_instruction(manifest_path) if manifest_path else ""
    if manifest_path and ignore_block:
        manifest_block += (' Also put "suppressed" in the manifest: the number of findings you left out '
                           "because the rejected list below already covers them.")
    return f"/{name} {repo}\n{override}{manifest_block}{ignore_block}\n"


def mutation_prepass_prompt(repo, candidates):
    listing = "\n".join(candidates)
    return (
        f"The repository at {repo} has these modules, each with a sibling test:\n{listing}\n\n"
        "Rank them by one test: logic where a wrong result goes unnoticed, so a silently-passing test would be "
        "dangerous. Test fakes and CLI entry files rank last. Print ONLY the module paths from the list above, "
        "most worth mutating first, one per line — no prose, no numbering, no markdown, no path that is not "
        "in the list.\n"
    )


# visual-teach components the driver's pages use: callouts, and the table
# wrapper (`vt-table-wrap`) around the index and mutation sub-index tables.
INDEX_COMPONENTS = ("callout", "table")


def write_setup_failure_report(collection_dir, module, reason):
    d = os.path.join(collection_dir, module_slug(module))
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "report.html"), "w", encoding="utf-8") as f:
        f.write(pagelib.page(
            title="mutation-audit setup failure",
            kicker="Mutation sweep",
            h1="mutation-audit setup failure",
            lede=f"Module: {html.escape(module)}",
            body=f'<div class="vt-callout bad">{html.escape(reason)}</div>\n',
            prefix="../",
        ))
    findings_log.write(os.path.join(d, "findings.jsonl"),
                       [{"status": "setup_failure", "module": module, "reason": reason}])


def manifest_path_for(manifests_dir, name):
    return os.path.join(manifests_dir, name, "manifest.json")


def read_manifest(manifests_dir, name):
    """The manifest an audit wrote — {report_path, count, headline} — or
    None when it never wrote one (#559: the driver reads this, never a
    transcript; a missing manifest is a named failure, not a silent skip)."""
    path = manifest_path_for(manifests_dir, name)
    if not os.path.isfile(path):
        return None
    try:
        data = json.loads(open(path, encoding="utf-8").read())
    except (json.JSONDecodeError, OSError):
        return None
    if not data.get("report_path"):
        return None
    return data


def manifest_failure(manifests_dir, name):
    """Why `name`'s manifest does not prove success, or None: "no manifest",
    or a manifest naming a missing report. What success means for an audit,
    shared by `run_one` and `collect_from_manifest`, which mutation mode
    reaches it through (#1292)."""
    manifest = read_manifest(manifests_dir, name)
    if manifest is None:
        return "no manifest"
    report = manifest["report_path"]
    if not os.path.isfile(report):
        return f"manifest names a missing report: {report}"
    return None


def collect_from_manifest(manifests_dir, name, collection_dir, dest_name):
    """Read `name`'s manifest and copy its report dir into
    `collection_dir/dest_name`. Returns None on success, else
    `manifest_failure`'s reason. The one seam both the audit sweep and
    mutation mode use to find a report — never a log-grepping fallback
    (#559, and #580 for mutation mode)."""
    reason = manifest_failure(manifests_dir, name)
    if reason:
        return reason
    report = read_manifest(manifests_dir, name)["report_path"]
    replace_dir(os.path.dirname(report), os.path.join(collection_dir, dest_name))
    return None


INCONCLUSIVE_INSTRUCTION = (
    "\nAlways write findings.jsonl beside the report, empty when no mutant survived. "
    'If `audit.py --run` exited 3 with `INCONCLUSIVE: <why>`, still write the report (one line '
    'naming the module and `<why>`) and the manifest, and add an "inconclusive" key to the '
    "manifest holding that line's `<why>`; write no finding rows."
)


def inconclusive_path(collection_dir, dest_name):
    return os.path.join(collection_dir, dest_name, "inconclusive.txt")


def clear_inconclusive(collection_dir, dest_name):
    path = inconclusive_path(collection_dir, dest_name)
    if os.path.exists(path):
        os.remove(path)


def mutation_answer_failure(manifests_dir, name):
    """Why a mutation module's manifest is no answer, or None. A module is
    measured (a `findings.jsonl` beside its report, empty for no survivors) or
    INCONCLUSIVE (an `inconclusive` key); a manifest with neither would read
    as a clean module that never ran (#1588)."""
    reason = manifest_failure(manifests_dir, name)
    if reason:
        return reason
    data = read_manifest(manifests_dir, name)
    if "inconclusive" in data:
        return None
    if not os.path.isfile(os.path.join(os.path.dirname(data["report_path"]), "findings.jsonl")):
        return "manifest has no `inconclusive` key and the report has no findings.jsonl"
    return None


def record_inconclusive(manifests_dir, name, collection_dir):
    """A manifest carrying `inconclusive` becomes `inconclusive.txt` in the
    module's collected dir, the file the mutation sub-index reads (#1588): a
    module that measured nothing is listed as such, never as clean."""
    data = read_manifest(manifests_dir, name)
    if "inconclusive" in data:
        with open(inconclusive_path(collection_dir, name), "w", encoding="utf-8") as f:
            f.write(str(data["inconclusive"] or "no reason recorded"))


def clear_manifest(manifest):
    """`--out` accumulates: an earlier sweep's manifest would otherwise prove
    this sweep succeeded (#1278)."""
    if os.path.exists(manifest):
        os.remove(manifest)


def audit_failure(returncode, manifest_check):
    """Why one audit's `claude` run failed, or None: a nonzero exit, else
    what `manifest_check()` finds wrong with its manifest (#1278)."""
    return f"exit {returncode}" if returncode != 0 else manifest_check()


def report_failure(label, reason, log_path):
    print(f"[{label}] FAILED: {reason} — see {log_path}")


NOT_APPLICABLE_FILE = "not-applicable.txt"


def write_not_applicable(name, language, manifest):
    """Write the manifest and one-line report of an audit that does not apply
    here (all-audits/SKILL.md, Not applicable). The manifest carries
    `not_applicable` (the language) and no findings log, so no reader takes it
    for an audit that found nothing; `NOT_APPLICABLE_FILE` beside the report
    carries the language into the collection, where every index reads it."""
    report_dir = os.path.join(os.path.dirname(manifest), "report")
    os.makedirs(report_dir, exist_ok=True)
    report = os.path.join(report_dir, "report.html")
    with open(report, "w", encoding="utf-8") as f:
        f.write(pagelib.page(title=f"{name}: not applicable", kicker=name,
                             h1=f"NOT APPLICABLE: {html.escape(language)}",
                             lede=f"{name} reads Python source and this repo has none; it did not run.", body="",
                             prefix="../"))  # collected as collection/<name>/report.html, assets one up
    with open(os.path.join(report_dir, NOT_APPLICABLE_FILE), "w", encoding="utf-8") as f:
        f.write(language)
    with open(manifest, "w", encoding="utf-8") as f:
        json.dump({"report_path": report, "count": 0, "headline": f"not applicable: {language}",
                   "not_applicable": language}, f)


def collected_not_applicable(collection, name):
    """The language `name`'s collected report was ruled not applicable for,
    or None when it ran (or has no report)."""
    path = os.path.join(collection, name, NOT_APPLICABLE_FILE)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return f.read().strip() or "unknown language"


def run_one(name, repo, outlogs, manifests_dir, not_applicable=None):
    """Run one audit. Returns None on success, else the failure reason —
    a nonzero `claude` exit, no manifest or a manifest naming a missing
    report (#1278, #1292); `done` prints only on success. With
    `not_applicable` (a language, from the plan) no `claude` starts."""
    print(f"[{name}] starting")
    log_path = os.path.join(outlogs, f"{name}.log")
    manifest = manifest_path_for(manifests_dir, name)
    os.makedirs(os.path.dirname(manifest), exist_ok=True)
    clear_manifest(manifest)
    if not_applicable:
        write_not_applicable(name, not_applicable, manifest)
        with open(log_path, "w", encoding="utf-8") as log:
            log.write(f"not applicable: {not_applicable}\n")
        print(f"[{name}] not applicable: {not_applicable}")
        return None
    with open(log_path, "w", encoding="utf-8") as log:
        r = subprocess.run(["claude", *CLAUDE_FLAGS, audit_prompt(name, repo, manifest)], stdout=log, stderr=subprocess.STDOUT, check=False, env=claude_env())
    reason = audit_failure(r.returncode, lambda: manifest_failure(manifests_dir, name))
    if reason:
        report_failure(name, reason, log_path)
        return reason
    print(f"[{name}] done")
    return None


# --- HTML index rendering -----------------------------------------------------

_INDEX_CSS = """main { --vt-measure: 1080px; }
.audit-table { width:100%; border-collapse:collapse; }
.audit-table th, .audit-table td { border:1px solid var(--vt-rule); padding:.6rem .8rem; text-align:left; vertical-align:top; }
.audit-table th { background:var(--vt-soft); font-weight:600; }
.audit-table tr:nth-child(even) td { background:var(--vt-stripe); }"""


@dataclasses.dataclass
class IndexModel:
    """Everything the sweep index renders (#606) — one value the collect step
    fills in, so the renderer takes a model instead of nine positionals."""

    collection: str
    repo: str
    report_link: dict
    skip_note: dict
    synthesis: str = ""
    mutation_modules: list = dataclasses.field(default_factory=list)
    mutation_survivors_sum: int = 0
    mutation_inconclusive: int = 0
    mutation_corrupt: int = 0
    notest_count: int = 0
    notest_error: str = None


def build_index(model):
    out = ['<h2>Reports</h2><div class="vt-table-wrap"><table class="audit-table">\n']
    out.append("<thead><tr><th>Audit</th><th>Report</th><th>Status</th></tr></thead><tbody>\n")
    for name in AUDIT_NAMES:
        link = model.report_link.get(name, "")
        note = model.skip_note.get(name, "")
        if link:
            out.append(f'<tr><td>{name}</td><td><a href="{link}">open report</a></td><td>{note}</td></tr>\n')
        else:
            out.append(f'<tr><td>{name}</td><td style="color:var(--vt-muted)">no report</td><td>{note}</td></tr>\n')
    if model.mutation_modules or model.notest_count > 0 or model.notest_error:
        measured = len(model.mutation_modules) - model.mutation_inconclusive - model.mutation_corrupt
        verdict = f"{measured} modules measured, {model.mutation_survivors_sum} total survivors"
        if model.mutation_inconclusive:
            verdict += f", {model.mutation_inconclusive} INCONCLUSIVE (not measured)"
        if model.mutation_corrupt:
            verdict += f", {model.mutation_corrupt} CORRUPT (findings.jsonl unreadable, not measured)"
        if model.notest_error:
            verdict += " · no-tests count could not be determined"
        elif model.notest_count > 0:
            verdict += f" · {model.notest_count} with no tests"
        out.append(f'<tr><td>mutation</td><td><a href="mutation/index.html">open report</a></td><td>{verdict}</td></tr>\n')
    out.append("</tbody></table></div>\n")
    with open(os.path.join(model.collection, "index.html"), "w", encoding="utf-8") as f:
        f.write(pagelib.page(
            title="All-audits index",
            kicker="All-audits sweep",
            h1=f'{html.escape(model.repo)} <span style="color:var(--vt-muted)">· {len(AUDIT_NAMES)}-audit sweep</span>',
            lede=html.escape(model.synthesis) if model.synthesis else "",
            body="".join(out),
            extra_css=_INDEX_CSS,
        ))


def inconclusive_reason(collection, base):
    """Why module `base` measured nothing, or None when it was measured."""
    path = inconclusive_path(collection, base)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return f.read().strip() or "no reason recorded"


def build_mutation_subindex(collection, repo, mutation_modules, notest_modules, notest_total, notest_error=None):
    d = os.path.join(collection, "mutation")
    os.makedirs(d, exist_ok=True)
    out = []
    notest_count = len(notest_modules)
    if notest_error:
        lede = f"No-tests count could not be determined ({html.escape(notest_error)})."
    elif notest_total > 0:
        lede = f"{notest_count} of {notest_total} source modules have no tests."
    else:
        lede = ""
    inconclusive = []
    if mutation_modules:
        out.append('<h2>Modules</h2><div class="vt-table-wrap"><table class="audit-table">\n')
        out.append("<thead><tr><th>Module</th><th>Killed/total</th><th>Weak-assertion</th><th>No-coverage</th><th>Report</th></tr></thead><tbody>\n")
        for base in mutation_modules:
            tally_row, corrupt = _mutation_tally(collection, base)
            why = inconclusive_reason(collection, base)
            if why is not None:
                inconclusive.append(base)
                tally = f"INCONCLUSIVE: {html.escape(why)}"
                weak = nocov = "—"
            elif corrupt:
                tally = f"CORRUPT: findings.jsonl line {corrupt[0][0]} is not a JSON object"
                weak = nocov = "—"
            elif tally_row:
                k, t, s, n = tally_row
                tally, weak, nocov = f"{k}/{t}", str(s), str(n)
            else:
                tally = weak = nocov = "—"
            report = os.path.join(collection, base, "report.html")
            link = f'<a href="../{base}/report.html">open report</a>' if os.path.isfile(report) else '<span style="color:var(--vt-muted)">no report</span>'
            out.append(f"<tr><td>{base}</td><td>{tally}</td><td>{weak}</td><td>{nocov}</td><td>{link}</td></tr>\n")
        out.append("</tbody></table></div>\n")
    if inconclusive:
        lede = f"{len(inconclusive)} of {len(mutation_modules)} modules INCONCLUSIVE: not measured, not counted as killed or clean. " + lede
    if notest_count > 0:
        out.append("<h2>No tests</h2>\n")
        out.append(
            f'<div class="vt-callout warn">These {notest_count} worthy source modules have no test at all — '
            "0% mutation coverage, the worst case. No mutant can be caught here until a test exists.</div>\n"
        )
        out.append('<div class="vt-table-wrap"><table class="audit-table">\n')
        out.append("<thead><tr><th>Module</th><th>Mutation coverage</th></tr></thead><tbody>\n")
        for m in notest_modules:
            out.append(f"<tr><td>{m}</td><td>0% — no tests</td></tr>\n")
        out.append("</tbody></table></div>\n")
    with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as f:
        f.write(pagelib.page(
            title="Mutation sub-index",
            kicker="Mutation sweep",
            h1=f'{html.escape(repo)} <span style="color:var(--vt-muted)">· {len(mutation_modules)} mutation modules</span>',
            lede=lede,
            body="".join(out),
            prefix="../",
            extra_css=_INDEX_CSS,
        ))


# --- the run folder -----------------------------------------------------------

RUN_TTL_DAYS = 3


@dataclasses.dataclass(frozen=True)
class RunDir:
    """The run folder's layout, made once for every mode (#606). One owner
    for: resolving `--out` or a fresh `run-<timestamp>` under the cache base,
    pruning runs past the TTL, creating the sub-folders, and pointing TMPDIR
    at the run so every audit subprocess writes inside it."""

    root: str
    logs: str
    collection: str
    manifests: str
    worktrees: str = ""

    @classmethod
    def create(cls, out, worktrees=False):
        base = cache_base()
        os.makedirs(base, exist_ok=True)
        root = os.path.abspath(out) if out else os.path.join(base, "run-" + _dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
        # Prune only after `--out` is resolved, and never the run being asked
        # for: `index --out <old run>` must index it, not delete it.
        cutoff = _dt.datetime.now().timestamp() - RUN_TTL_DAYS * 86400
        for entry in os.listdir(base):
            p = os.path.join(base, entry)
            if entry.startswith(("run-", "multi-")) and os.path.isdir(p) and p != root and os.path.getmtime(p) < cutoff:
                shutil.rmtree(p, ignore_errors=True)
        run = cls(
            root=root,
            logs=os.path.join(root, "logs"),
            collection=os.path.join(root, "collection"),
            manifests=os.path.join(root, "manifests"),
            worktrees=os.path.join(root, "worktrees") if worktrees else "",
        )
        for d in (run.root, run.logs, run.collection, run.manifests, run.worktrees):
            if d:
                os.makedirs(d, exist_ok=True)
        os.environ["TMPDIR"] = run.root
        return run


# --- the sweep ----------------------------------------------------------------


@dataclasses.dataclass
class Plan:
    """What the sweep will do before it does anything (#606): which audits
    run, which reuse a cached report, and the note the index prints for
    each skip. Deciding this spawns no audit."""

    to_run: list = dataclasses.field(default_factory=list)
    reused: dict = dataclasses.field(default_factory=dict)
    skip_note: dict = dataclasses.field(default_factory=dict)
    skip_sha: dict = dataclasses.field(default_factory=dict)
    not_applicable: dict = dataclasses.field(default_factory=dict)  # {audit: language} (#1751)


def plan_sweep(repo, selected, force, base=None, key=None):
    """Ask the staleness cache which of `selected` still needs a run, and
    which of those read only Python on a repo that has none."""
    base = base or cache_base()
    plan = Plan()
    for name in selected:
        if name in GATED and not force:
            d = decide(repo, name, GATED[name], base=base, key=key)
            if not d.run:
                if d.report_dir and os.path.isdir(d.report_dir):
                    plan.reused[name] = d.report_dir
                    plan.skip_note[name] = f"unchanged since {d.sha[:8]}"
                    plan.skip_sha[name] = d.sha
                    print(f"[{name}] skipped (unchanged since {d.sha[:8]}), reusing cached report")
                    continue
                print(f"[{name}] cache says skip but cached report is gone — running fresh")
        plan.to_run.append(name)
    python_only = [n for n in plan.to_run if n in PYTHON_ONLY]
    language = auditlib.not_applicable(repo) if python_only else None  # once per sweep
    if language:
        plan.not_applicable = {n: language for n in python_only}
    return plan


def _jobs_from_env(name):
    """A positive-integer concurrency cap from the environment (default 4). A
    value that is not one stops the run with exit 2; it is never rounded to a
    default."""
    raw = os.environ.get(name, "4")
    try:
        jobs = int(raw)
    except ValueError:
        jobs = 0
    if jobs < 1:
        print(f"{name} must be a positive integer, got {raw!r}", file=sys.stderr)
        sys.exit(2)
    return jobs


def sweep_jobs():
    """`SWEEP_JOBS` (#1666): how many audits a sweep runs at once."""
    return _jobs_from_env("SWEEP_JOBS")


def execute(repo, plan, run, jobs):
    """Run the planned audits — the only place a sweep spawns a process.

    The first audit runs alone as a smoke test: if the `-p` slash invocation
    is rejected by the model-invocation guard, every audit would fail the
    same way, so the sweep aborts instead of fanning thirteen failures out.
    Returns the names of the audits that failed (#1278).
    """
    if not plan.to_run:
        return []

    def one(name):
        return run_one(name, repo, run.logs, run.manifests, plan.not_applicable.get(name))

    # The smoke audit must spawn `claude`, or it proves nothing about the guard (#1751).
    smoke = next((n for n in plan.to_run if n not in plan.not_applicable), None)
    failed = []
    if smoke is None:
        print("== no smoke test: no planned audit starts claude ==")
    else:
        print(f"== smoke test: {smoke} ==")
        failed = [smoke] if one(smoke) else []
        log_text = open(os.path.join(run.logs, f"{smoke}.log"), encoding="utf-8", errors="replace").read()
        if re.search(r"cannot be used with Skill tool|disable-model-invocation", log_text, re.IGNORECASE):
            print(f"ABORT: -p slash invocation was rejected by the guard. See {run.logs}/{smoke}.log", file=sys.stderr)
            sys.exit(1)
        print("smoke test passed; fanning out the rest\n" if not failed else f"smoke audit {smoke} failed (not the guard); fanning out the rest anyway\n")
    rest = [n for n in plan.to_run if n != smoke]
    if rest:
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(jobs, len(rest))) as ex:
            results = list(ex.map(one, rest))
        failed += [n for n, reason in zip(rest, results) if reason]
    return failed


MutationScan = collections.namedtuple(
    "MutationScan", "modules survivors_sum inconclusive corrupt notest_modules notest_total notest_error")


def scan_mutation(collection):
    """What mutation mode left in a collection: its module dirs, their tally and
    the no-tests probe's answer. `collect` and `mutation_mode` both read it."""
    mutation_modules = []
    for entry in sorted(os.listdir(collection)):
        d = os.path.join(collection, entry)
        if not os.path.isdir(d) or entry in AUDIT_NAMES:
            continue
        if os.path.isfile(os.path.join(d, "findings.jsonl")) or os.path.isfile(inconclusive_path(collection, entry)):
            mutation_modules.append(entry)

    survivors_sum, corrupt = 0, 0
    inconclusive = sum(1 for b in mutation_modules if inconclusive_reason(collection, b) is not None)
    for base_name in mutation_modules:
        if inconclusive_reason(collection, base_name) is not None:
            continue
        tally, bad_lines = _mutation_tally(collection, base_name)
        if bad_lines:  # the sub-index shows it CORRUPT: not measured, its survivors not counted
            corrupt += 1
        elif tally:
            _, _, s, n = tally
            survivors_sum += s + n

    notest_modules, notest_total, notest_error = [], 0, None
    notest_json = os.path.join(collection, "mutation-no-tests.json")
    if os.path.exists(notest_json):
        try:
            d = json.load(open(notest_json, encoding="utf-8"))
            if "error" in d:
                notest_error = d["error"]
            else:
                notest_total = int(d.get("total", 0))
                notest_modules = d.get("no_tests", [])
        except (json.JSONDecodeError, OSError):
            notest_error = "no-tests probe wrote unparseable output"
    return MutationScan(mutation_modules, survivors_sum, inconclusive, corrupt, notest_modules, notest_total, notest_error)


def render_mutation_subindex(collection, repo, mut):
    if mut.modules or mut.notest_modules or mut.notest_error:
        build_mutation_subindex(collection, repo, mut.modules, mut.notest_modules, mut.notest_total, mut.notest_error)


SYNTHESIS_FILE = "synthesis.txt"


def report_links(collection):
    """{audit: its report's path relative to `collection`, or ""}: the first
    `.html` in each audit's folder."""
    links = {}
    for name in AUDIT_NAMES:
        d = os.path.join(collection, name)
        htmls = sorted(f for f in os.listdir(d) if f.endswith(".html")) if os.path.isdir(d) else []
        links[name] = f"{name}/{htmls[0]}" if htmls else ""
    return links


def collect(run, repo, plan, base=None, key=None, reuse_synthesis=False, index_label="index"):
    """Assemble the collection from what is on disk and render the index.

    Reports arrive two ways — through the manifest each audit that ran wrote,
    or copied from the cache for a skipped one — and this is the only step
    that reads either. Returns the index path. The `index` mode calls it directly
    over an existing collection, which is why it never touches the run
    branch: an empty `Plan` collects a finished folder just as well.
    """
    base = base or cache_base()
    collection = run.collection
    for name, cached in plan.reused.items():
        replace_dir(cached, os.path.join(collection, name))

    stable = os.path.join(base, repo_key(key or repo), "reports")
    manifest_note = {}
    for name in plan.to_run:
        reason = collect_from_manifest(run.manifests, name, collection, name)
        if reason == "no manifest":
            manifest_note[name] = f"no manifest — see {os.path.join(run.logs, name + '.log')}"
            continue
        if reason:
            manifest_note[name] = reason
            continue
        if collected_not_applicable(collection, name):  # never cached as a clean result
            continue
        if name in GATED:
            os.makedirs(stable, exist_ok=True)
            replace_dir(os.path.join(collection, name), os.path.join(stable, name))
            update_cache(repo, name, os.path.join(stable, name), base=base, key=key)

    # Read from the collection, not the plan, so `index --out` and `load` show it too.
    na_note = {n: f"NOT APPLICABLE: {lang}" for n in AUDIT_NAMES
               if (lang := collected_not_applicable(collection, n))}
    report_link = report_links(collection)
    mut = scan_mutation(collection)

    report_files = [os.path.join(collection, report_link[n]) for n in AUDIT_NAMES if report_link[n]]
    synthesis = ""
    synthesis_path = os.path.join(collection, SYNTHESIS_FILE)
    if reuse_synthesis:  # `load` (#1678): the stored synthesis as it was, no new `claude` call
        if os.path.isfile(synthesis_path):
            synthesis = open(synthesis_path, encoding="utf-8").read()
    elif os.environ.get("AUDITS_NO_SYNTH", "0") != "1" and report_files:
        print("== synthesis pass ==")
        prompt = (
            f"Read these {len(report_files)} audit report HTML files and write a 2-3 sentence synthesis of "
            "the repo's overall state for the lede of an index page. Plain prose only — no preamble, no "
            f"markdown, no headings, no lists. Files: {' '.join(report_files)}"
        )
        result = _run(["claude", *CLAUDE_FLAGS, prompt], env=claude_env())
        synthesis = result.stdout.strip()
        if synthesis:  # the audit record (#1680) carries it as-is
            with open(synthesis_path, "w", encoding="utf-8") as f:
                f.write(synthesis)

    pagelib.copy_assets(collection, components=INDEX_COMPONENTS)

    build_index(IndexModel(
        collection=collection,
        repo=repo,
        report_link=report_link,
        skip_note={**plan.skip_note, **na_note, **manifest_note},
        synthesis=synthesis,
        mutation_modules=mut.modules,
        mutation_survivors_sum=mut.survivors_sum,
        mutation_inconclusive=mut.inconclusive,
        mutation_corrupt=mut.corrupt,
        notest_count=len(mut.notest_modules),
        notest_error=mut.notest_error,
    ))
    render_mutation_subindex(collection, repo, mut)

    index_path = os.path.join(collection, "index.html")
    print()
    print(f"{index_label}: {index_path}")
    print(f"logs: {run.logs}")
    return index_path


def open_index(index_path):
    if os.environ.get("AUDITS_NO_OPEN", "0") == "1":
        return
    opener = "xdg-open" if sys.platform.startswith("linux") else ("open" if sys.platform == "darwin" else None)
    if opener:
        subprocess.run([opener, index_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _announce(run, repo):
    print(f"run dir: {run.root}")
    print(f"collecting under: {run.collection}")
    print(f"repo: {repo}")
    print()


@dataclasses.dataclass
class SweepResult:
    run: RunDir
    plan: Plan
    failed: list


def run_sweep(repo, out, only, short, force, key=None, standalone=True):
    """Plan, execute and collect one sweep. Standalone, it prints its index as
    `index:` and opens it; one repo of a `multi` pass prints `repo index:`
    and opens nothing, since the pass's own page is its `index:` (#1721).
    Returns what happened: the audit record (#1680) is built from it."""
    repo = os.path.abspath(repo)
    selected = only if only is not None else (SHORT_SET if short else list(AUDIT_NAMES))
    jobs = sweep_jobs()  # before the run dir exists, as mutation_mode does
    run = RunDir.create(out)
    _announce(run, repo)
    plan = plan_sweep(repo, selected, force, key=key)
    failed = execute(repo, plan, run, jobs)
    index = collect(run, repo, plan, key=key, index_label="index" if standalone else "repo index")
    if standalone:
        open_index(index)
    return SweepResult(run, plan, failed)


def sweep(repo, out, only, short, force):
    prune_closed_sweeps(RUN_TTL_DAYS)
    failed = run_sweep(repo, out, only, short, force).failed
    if failed:
        print(f"FAILED audits: {', '.join(failed)}", file=sys.stderr)
        sys.exit(1)


def rebuild_index(repo, out):
    """`index --out DIR`: collect over a finished collection, nothing else."""
    repo = os.path.abspath(repo)
    run = RunDir.create(out)
    _announce(run, repo)
    open_index(collect(run, repo, Plan()))


# --- multi-repo mode (#1679) --------------------------------------------------

@dataclasses.dataclass
class Outcome:
    status: str          # "swept", "failed" or "refused"
    reason: str = ""
    stored: str = ""
    issue_url: str = ""


def log_tail(path):
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return "(no log)"
    return "\n".join(text.splitlines()[-15:]) or "(empty log)"


def _log_rows(path):
    """A findings log's rows for the audit record: each object, then each
    corrupt line as a string naming its line number, so the record shows it."""
    log = findings_log.read(path)
    return log.rows + [f"line {n}: {text}" for n, text in log.corrupt]


def _mutation_tally(collection, module):
    """(tally, corrupt) for a mutation module's log: `findings_log.tally` of
    its rows, or None, and its corrupt lines. No log is no tally and no corrupt."""
    path = os.path.join(collection, module, "findings.jsonl")
    if not os.path.isfile(path):
        return None, []
    log = findings_log.read(path)
    return findings_log.tally(log.rows), log.corrupt


def _report_headings(collection, name):
    d = os.path.join(collection, name)
    htmls = sorted(f for f in os.listdir(d) if f.endswith(".html")) if os.path.isdir(d) else []
    if not htmls:
        return []
    return audit_record.report_headings(open(os.path.join(d, htmls[0]), encoding="utf-8", errors="replace").read())


def record_model(result, sweep_id, sha, clean, stored, has_ignore_file, open_record="", earlier=""):
    """What the sweep left on disk, as the audit record's inputs. An audit that
    failed contributes a failure and no findings; one reused from the cache
    contributes its earlier sha and no findings."""
    run, plan = result.run, result.plan
    failed = {n: f"{manifest_failure(run.manifests, n) or 'nonzero exit'}\n{log_tail(os.path.join(run.logs, n + '.log'))}"
              for n in result.failed}
    findings, no_log, headings, suppressed, unreported = {}, {}, {}, 0, []
    for name in (n for n in AUDIT_NAMES if n in plan.to_run and n not in failed):
        manifest = read_manifest(run.manifests, name) or {}
        log = os.path.join(run.collection, name, "findings.jsonl")
        if os.path.isfile(log):
            findings[name] = _log_rows(log)
        else:
            no_log[name] = {"count": manifest.get("count"), "headline": manifest.get("headline")}
        if name in audit_record.STRUCTURAL:
            headings[name] = _report_headings(run.collection, name)
        if isinstance(manifest.get("suppressed"), int):
            suppressed += manifest["suppressed"]
        elif has_ignore_file:
            unreported.append(name)
    synthesis_path = os.path.join(run.collection, SYNTHESIS_FILE)
    synthesis = open(synthesis_path, encoding="utf-8").read() if os.path.isfile(synthesis_path) else ""
    return audit_record.RecordModel(
        sweep_id=sweep_id, timestamp=now_iso(), sha=sha, clean=clean, stored_path=stored,
        ran=list(plan.to_run), skipped=dict(plan.skip_sha), failed=failed, findings=findings, no_log=no_log,
        suppressed=suppressed, suppression_unreported=unreported, headings=headings, synthesis=synthesis,
        open_record=open_record, earlier_record=earlier)


def aborted_model(sweep_id, sha, clean, stored, reason, logs, open_record=""):
    """The record of a sweep that stopped before collecting (a guard, a crash):
    a failure, never a clean repo (#1678)."""
    tails = [f"{f}:\n{log_tail(os.path.join(logs, f))}" for f in sorted(os.listdir(logs))] if os.path.isdir(logs) else []
    return audit_record.RecordModel(
        sweep_id=sweep_id, timestamp=now_iso(), sha=sha, clean=clean, stored_path=stored,
        ran=[], skipped={}, failed={"the sweep": "\n\n".join([reason, *tails])}, findings={}, no_log={},
        suppressed=0, suppression_unreported=[], headings={}, synthesis="", open_record=open_record)


SWEEP_STATE_FILE = "sweep-state.json"


def _sweep_origin_main(repo, slug, run_root, sweep_id, only, short, force, open_record=""):
    """Sweep a fresh worktree of `repo`'s origin/main, store the result, and
    file the audit record. Returns an Outcome."""
    name = slug.split("/", 1)[1]
    try:
        shellcmd.git(["-C", repo, "fetch", "origin"])
    except shellcmd.CmdError as e:
        return Outcome("failed", f"git fetch failed: {e}")
    wt = os.path.join(run_root, "checkout")
    os.makedirs(run_root, exist_ok=True)
    added = False
    try:
        with shellcmd.scratch_worktree(repo, "origin/main", wt):
            added = True
            return _sweep_checkout(repo, slug, name, wt, run_root, sweep_id, only, short, force, open_record)
    except shellcmd.CmdError as e:
        if added:
            raise
        return Outcome("failed", f"git worktree add origin/main failed: {e}")


def _sweep_checkout(repo, slug, name, wt, run_root, sweep_id, only, short, force, open_record):
    """The body of `_sweep_origin_main` once its worktree `wt` exists."""
    label = triage_label(wt)
    refusal = label_refusal(repo, label)  # before any audit starts
    if refusal:
        return Outcome("refused", refusal)
    earlier = latest_record_url(name)  # before this sweep stores its own
    result, failure = None, None
    try:
        result = run_sweep(wt, os.path.join(run_root, "run"), only, short, force, key="github:" + slug,
                           standalone=False)
    except SystemExit as e:
        if e.code not in (0, None):
            failure = f"sweep stopped before collecting: {e.code if isinstance(e.code, str) else f'exit {e.code}'}"
    stored = os.path.join(stored_sweeps_base(), name, sweep_id)
    run = os.path.join(run_root, "run")
    os.makedirs(stored, exist_ok=True)
    for sub in ("collection", "logs"):
        if os.path.isdir(os.path.join(run, sub)):
            shutil.copytree(os.path.join(run, sub), os.path.join(stored, sub), dirs_exist_ok=True)
    sha = head_sha(wt)
    dirty = shellcmd.git(["-C", wt, "status", "--porcelain"]).stdout.splitlines()
    clean = "yes" if not dirty else f"no ({len(dirty)} changed paths)"
    if result is None:
        model = aborted_model(sweep_id, sha, clean, stored, failure or "sweep stopped before collecting",
                              os.path.join(stored, "logs"), open_record)
        outcome = Outcome("failed", model.failed["the sweep"].splitlines()[0], stored)
    else:
        model = record_model(result, sweep_id, sha, clean, stored,
                             os.path.isfile(os.path.join(wt, ".audit-ignore.md")), open_record, earlier)
        write_json(os.path.join(stored, SWEEP_STATE_FILE),
                    {"skip_note": result.plan.skip_note,
                     "failed": {n: t.splitlines()[0] for n, t in model.failed.items()}})
        outcome = Outcome("failed" if result.failed else "swept", stored=stored)
        if result.failed:
            outcome.reason = f"{len(result.failed)} audit(s) failed: {', '.join(result.failed)}"
    if not audit_record.worth_filing(model):
        return outcome  # stored with no record: `prune_closed_sweeps` drops it after RUN_TTL_DAYS
    meta = {"repo": slug, "checkout": repo}
    url, error = file_audit_record(repo, stored, f"Audit record: {name} {sweep_id}", label,
                                   audit_record.build(model), meta)
    outcome.issue_url = url
    if error:
        outcome.status, outcome.reason = "failed", "; ".join(x for x in (outcome.reason, error) if x)
    return outcome


@dataclasses.dataclass
class RepoRow:
    """One repo of a `multi` pass: what its summary line and its row on the
    multi-repo index both say (#1721). `status` is one of `REPO_STATUSES`."""

    label: str
    status: str
    reason: str = ""
    stored: str = ""
    issue_url: str = ""

    def summary_line(self):
        if self.status == "swept":
            return f"{self.label}: swept -> {self.stored}" + (
                f"; audit record: {self.issue_url}" if self.issue_url
                else "; no audit record (no findings, no failures)")
        link = f"; audit record: {self.issue_url}" if self.status == "failed" and self.issue_url else ""
        return f"{self.label}: {self.status} ({self.reason}){link}"


NOT_YET_RUN = "not yet run"
REPO_STATUSES = ("swept", "failed", "refused", "triage pending", "skipped", NOT_YET_RUN)


def _path_label(repo):
    return os.path.basename(repo.rstrip("/")) or repo


def _multi_one(repo, base, sweep_id, only, short, force, seen):
    """One repo of a multi-repo sweep: (its RepoRow, whether it failed)."""
    slug, refusal = repo_identity(repo)
    label = slug.split("/", 1)[1] if slug else _path_label(repo)
    if refusal:
        return RepoRow(label, "refused", refusal), False
    if label == MULTI_DIR:  # its stored sweeps would land in the multi-repo index folder
        return RepoRow(label, "refused", f"a repo named `{MULTI_DIR}` collides with the multi-repo index folder"), False
    if slug in seen:
        return RepoRow(label, "skipped", f"{repo} is {slug} again, already swept from {seen[slug]}"), False
    seen[slug] = repo
    why = resume_unposted(label)
    if why:
        return RepoRow(label, "failed", why), True
    open_record, why = earlier_record(label)
    if why:
        return RepoRow(label, "refused", why), False
    if open_record and not force:
        return RepoRow(label, "triage pending", open_record, issue_url=open_record), False
    o = _sweep_origin_main(repo, slug, os.path.join(base, repo_key(repo)), sweep_id, only, short, force, open_record)
    if o.status == "refused":
        return RepoRow(label, "refused", o.reason), False
    return RepoRow(label, o.status, o.reason, o.stored, o.issue_url), o.status == "failed"


def multi_mode(repos, out, only, short, force):
    """Sweep each repo in turn (never overlapping); one summary line per repo.
    Exits 1 if any repo failed; a refused repo is reported, not a failure. A
    repo that crashes is that repo's failure, and the rest still run. The
    multi-repo index is rewritten after each repo and opened once, at the end."""
    sweep_jobs()  # a bad SWEEP_JOBS stops the run before any repo is touched
    prune_closed_sweeps(RUN_TTL_DAYS)
    sweep_id = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    base = os.path.abspath(out) if out else os.path.join(cache_base(), "multi-" + sweep_id)
    paths = [os.path.abspath(p) for p in repos]
    rows = [RepoRow(_path_label(p), NOT_YET_RUN) for p in paths]
    page, failed = _write_page_or_say(sweep_id, rows), False
    if page:
        print(f"multi-repo index (rewritten as each repo finishes): {page}")
    page_ok, seen = bool(page), {}
    for i, repo in enumerate(paths):
        try:
            rows[i], bad = _multi_one(repo, base, sweep_id, only, short, force, seen)
        except Exception as e:  # noqa: BLE001 - reported by name, never swallowed
            rows[i], bad = RepoRow(_path_label(repo), "failed", f"crashed: {e!r}"), True
        failed = failed or bad
        page = _write_page_or_say(sweep_id, rows)
        page_ok = page_ok and bool(page)
    print("\n== multi-repo summary ==")
    print("\n".join(row.summary_line() for row in rows))
    if page:
        print(f"index: {page}")
        open_index(page)
    if failed or not page_ok:
        sys.exit(1)


def _write_page_or_say(sweep_id, rows):
    """The page's path, or None after naming on stderr why it was not written:
    a page that fails never stops the sweeps it reports on, and the pass exits
    1 for it."""
    try:
        return write_multi_page(sweep_id, rows)
    except (OSError, MultiIndexError) as e:
        print(f"multi-repo index not written: {e}", file=sys.stderr)
        return None


# --- the multi-repo index (#1721) --------------------------------------------

MULTI_STATE_FILE = "state.json"
SWEEP_ID = re.compile(r"\d{8}-\d{6}")


class MultiIndexError(Exception):
    """The multi-repo index cannot be rendered truthfully; the message says why."""


def read_json(path):
    """(data, None), or (None, why) for a file that cannot be read or is not
    JSON. Never `{}` for a broken file, which would read as a clean one."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f), None
    except (OSError, ValueError) as e:
        return None, f"{path} unreadable ({e})"


def multi_page_dir(sweep_id):
    return os.path.join(stored_sweeps_base(), MULTI_DIR, sweep_id)


def write_multi_page(sweep_id, rows):
    """Record the pass's rows in its `state.json`, then render the page from
    it: the live pass and `multi-index` render through the same read."""
    save_record(os.path.join(multi_page_dir(sweep_id), MULTI_STATE_FILE),
                {"sweep_id": sweep_id, "repos": [dataclasses.asdict(r) for r in rows]})
    return render_multi_page(sweep_id)


def state_rows(state_path):
    """The rows a pass recorded; raises MultiIndexError for a file that is
    unreadable or does not hold repo rows."""
    data, why = read_json(state_path)
    if why:
        raise MultiIndexError(why)
    try:
        return [RepoRow(**r) for r in data["repos"]]
    except (KeyError, TypeError) as e:
        raise MultiIndexError(f"{state_path} unreadable (not a list of repo rows: {e!r})") from e


def sweep_marks(stored):
    """(failed, skip_note, why) from a stored sweep's sweep-state.json; `why`
    names a file missing or unreadable, whose marks are then unknown."""
    path = os.path.join(stored, SWEEP_STATE_FILE)
    if not os.path.isfile(path):
        return {}, {}, "sweep stopped before collecting"
    data, why = read_json(path)
    if why or not isinstance(data, dict):
        return {}, {}, f"{SWEEP_STATE_FILE} unreadable"
    return data.get("failed") or {}, data.get("skip_note") or {}, None


def stored_record(stored):
    """(issue url or "", why the record is incomplete or None) for a stored
    sweep: never filed although its text was written, missing comments, or
    an unreadable record file."""
    path = os.path.join(stored, RECORD_FILE)
    if not os.path.isfile(path):
        return "", ("audit record not filed" if os.path.isfile(os.path.join(stored, "audit-record-0.md")) else None)
    rec, why = read_json(path)
    if why or not isinstance(rec, dict):
        return "", f"{RECORD_FILE} unreadable"
    url = str(rec.get("url", ""))
    unposted = rec.get("unposted") or []
    return url, (f"audit record {url} misses comments {', '.join(map(str, unposted))}" if unposted else None)


def rows_from_stored_sweeps(sweep_id):
    """The rows a sweep id's stored sweeps alone can give, for a pass that
    wrote no `state.json` (started before #1721): swept, or failed with every
    problem its files show, sorted by name. Refused, skipped and
    triage-pending repos left nothing."""
    rows = []
    for stored in repo_sweep_dirs(sweep_id=sweep_id):
        failed, _, marks_why = sweep_marks(stored)
        url, record_why = stored_record(stored)
        audits_why = f"{len(failed)} audit(s) failed: {', '.join(failed)}" if failed else None
        problems = [p for p in (marks_why, audits_why, record_why) if p]
        rows.append(RepoRow(os.path.basename(os.path.dirname(stored)), "failed" if problems else "swept",
                            "; ".join(problems), stored, url))
    return rows


def _link(href, text):
    return f'<a href="{html.escape(href)}">{html.escape(text)}</a>'


_MUTED = '<span style="color:var(--vt-muted)">{}</span>'


def _row_reports(stored, page_dir):
    """The reports cell: a link per audit report, each failed or unchanged
    audit marked with the note its stored sweep recorded."""
    collection = os.path.join(stored, "collection")
    failed, skipped, why = sweep_marks(stored)
    links = report_links(collection)
    items = []
    for name in AUDIT_NAMES:
        if not (links[name] or name in failed or name in skipped):
            continue
        item = (_link(os.path.relpath(os.path.join(collection, links[name]), page_dir), name)
                if links[name] else html.escape(name))
        if name in failed:
            item += f' <strong class="mark-failed">FAILED: {html.escape(str(failed[name]))}</strong>'
        if name in skipped:
            item += f' <em class="mark-unchanged">{html.escape(str(skipped[name]))}</em>'
        items.append(f"<li>{item}</li>")
    note = f"<p>{_MUTED.format('marks unknown: ' + html.escape(why))}</p>" if why else ""
    return note + (f'<ul>{"".join(items)}</ul>' if items else _MUTED.format("no reports"))


def _multi_row(row, page_dir):
    status = html.escape(row.status) + (f" ({html.escape(row.reason)})" if row.reason else "")
    index = os.path.join(row.stored, "collection", "index.html") if row.stored else ""
    sweep = (_link(os.path.relpath(index, page_dir), "sweep index") if index and os.path.isfile(index)
             else _MUTED.format("no stored sweep"))
    record = _link(row.issue_url, row.issue_url) if row.issue_url else _MUTED.format("no audit record")
    reports = _row_reports(row.stored, page_dir) if index and os.path.isfile(index) else ""
    return (f'<tr data-repo="{html.escape(row.label)}" data-status="{html.escape(row.status)}">'
            f"<td>{html.escape(row.label)}</td><td>{status}</td><td>{sweep}</td><td>{record}</td>"
            f"<td>{reports}</td></tr>\n")


def render_multi_page(sweep_id):
    """Write the pass's `index.html` from its `state.json`, or from its stored
    sweeps when it has none, and return the page's path. Raises
    MultiIndexError for an unreadable `state.json`, or when neither exists.
    Reads only the disk, so the same state renders the same bytes."""
    page_dir = multi_page_dir(sweep_id)
    state_path = os.path.join(page_dir, MULTI_STATE_FILE)
    note = ""
    if os.path.isfile(state_path):
        rows = state_rows(state_path)
    else:
        rows = rows_from_stored_sweeps(sweep_id)
        if not rows:
            raise MultiIndexError(f"no state at {state_path} and no stored sweep at "
                                  f"{os.path.join(stored_sweeps_base(), '*', sweep_id)}")
        note = ('<div class="vt-callout warn">This pass recorded no state.json, so these rows come from its '
                "stored sweeps alone: a repo it refused, skipped or found triage pending is not listed, "
                "and the order is by name, not the order given.</div>\n")
    counts = collections.Counter(r.status for r in rows)
    lede = ", ".join(f"{counts[s]} {s}" for s in REPO_STATUSES if counts[s])
    body = [note, '<h2>Repos</h2><div class="vt-table-wrap"><table class="audit-table">\n',
            "<thead><tr><th>Repo</th><th>Status</th><th>Sweep</th><th>Audit record</th><th>Reports</th></tr>"
            "</thead><tbody>\n", *(_multi_row(r, page_dir) for r in rows), "</tbody></table></div>\n"]
    os.makedirs(page_dir, exist_ok=True)
    pagelib.copy_assets(page_dir, components=INDEX_COMPONENTS)
    path = os.path.join(page_dir, "index.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(pagelib.page(
            title=f"All-audits multi-repo index {sweep_id}",
            kicker="All-audits multi-repo sweep",
            h1=f'{html.escape(sweep_id)} <span style="color:var(--vt-muted)">· {len(rows)} repos</span>',
            lede=html.escape(lede),
            body="".join(body),
            extra_css=_INDEX_CSS,
        ))
    return path


def multi_index_mode(sweep_id):
    """`multi-index SWEEP_ID`: rebuild the pass's page from its `state.json`
    or stored sweeps; no `claude` runs. Prints `index:`; exits 1 naming the
    file or paths at fault when it cannot."""
    if not SWEEP_ID.fullmatch(sweep_id):
        sys.exit(f"all-audits multi-index: {sweep_id!r} is not a sweep id (YYYYMMDD-HHMMSS)")
    try:
        page = render_multi_page(sweep_id)
    except MultiIndexError as e:
        sys.exit(f"all-audits multi-index: {e}")
    print(f"index: {page}")
    open_index(page)


# --- load a stored sweep for triage (#1684) ----------------------------------

def load_mode(issue, repo_name):
    """`load ISSUE [REPO]`: rebuild the stored sweep's index so it can be
    triaged, with the failed and unchanged audits' notes it was swept with and
    its stored synthesis; no `claude` runs. Prints `stored:`, `checkout:` and
    `index:`; exits 1 naming the issue and the path when the sweep or its
    collection is missing."""
    found, why = find_stored_sweep(issue, os.path.basename((repo_name or "").rstrip("/")) or None)
    if why:
        sys.exit(f"all-audits load: {why}")
    stored, rec = found
    collection = os.path.join(stored, "collection")
    if not os.path.isdir(collection):
        sys.exit(f"all-audits load: audit record #{issue}: stored collection missing at {collection}")
    state_path = os.path.join(stored, SWEEP_STATE_FILE)
    state = json.load(open(state_path, encoding="utf-8")) if os.path.isfile(state_path) else {}
    notes = {**state.get("skip_note", {}), **{n: f"FAILED: {why}" for n, why in state.get("failed", {}).items()}}
    run = RunDir.create(stored)
    slug = record_repo(stored, rec)
    print(f"stored: {stored}")
    print(f"repo: {slug}")
    print(f"checkout: {rec.get('checkout', '(not recorded)')}")
    open_index(collect(run, slug, Plan(skip_note=notes), reuse_synthesis=True))


# --- repo suggestions (#1683) -------------------------------------------------

SUGGEST_DAYS = 14
DEFAULT_ROOTS = "~/src,~/.agents"  # agent-skills lives at ~/.agents/skills, as `landed` scans it


SEARCH_LIMIT = 1000  # `gh search` returns at most 1000 results


def recent_pr_repos():
    """Sorted `owner/name`s of owned repos where the user authored a PR in the
    last `SUGGEST_DAYS` days. Raises RuntimeError on any `gh` failure, and on a
    reply that hit the result limit: an empty or short list must mean "no
    more PRs", never "the search broke" or "the search was cut off"."""
    since = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=SUGGEST_DAYS)).strftime("%Y-%m-%d")
    try:
        r = shellcmd.gh(["search", "prs", "--author", "@me", "--created", f">={since}",
                         "--json", "repository", "--limit", str(SEARCH_LIMIT)])
    except shellcmd.CmdError as e:
        raise RuntimeError(f"gh search prs failed: {e}") from e
    try:
        rows = json.loads(r.stdout)
        names = {pr["repository"]["nameWithOwner"] for pr in rows}
    except (ValueError, KeyError, TypeError) as e:
        raise RuntimeError(
            f"gh search prs reply unreadable ({type(e).__name__}: {e}); stdout began: {r.stdout[:200]!r}") from e
    if len(rows) >= SEARCH_LIMIT:
        raise RuntimeError(f"gh search prs returned {len(rows)} PRs, its limit: the list may be cut off")
    return sorted(n for n in names if n.startswith(OWNER + "/"))


def local_checkouts(roots):
    """Map `owner/name` -> one checkout path, from the git checkouts directly
    under each root. Of several checkouts of one repo, a primary checkout (a
    `.git` directory) beats a worktree, then the shorter, then the earlier
    path: either serves, since the sweep comes from `origin`."""
    found = {}
    for root in roots:
        root = os.path.abspath(os.path.expanduser(root))
        for entry in sorted(os.listdir(root)) if os.path.isdir(root) else []:
            path = os.path.join(root, entry)
            if not os.path.exists(os.path.join(path, ".git")):
                continue
            try:
                slug = shellcmd.origin_slug(path)
            except shellcmd.CmdError:
                continue  # a checkout with no origin has no slug to sweep under
            if slug:
                key = (not os.path.isdir(os.path.join(path, ".git")), len(path), path)
                found.setdefault(slug, []).append((key, path))
    return {slug: min(c)[1] for slug, c in found.items()}


def suggest_mode(roots):
    """Print `suggest: <path>` per repo worth sweeping, `skipped: <repo> (no
    local checkout)` per repo that has recent PRs but no checkout."""
    try:
        recent = recent_pr_repos()
    except RuntimeError as e:
        sys.exit(f"driver.py suggest: {e}")
    if not recent:
        print(f"no owned repo has a PR in the last {SUGGEST_DAYS} days")
        return
    checkouts = local_checkouts(roots)
    for slug in recent:
        if slug in checkouts:
            print(f"suggest: {checkouts[slug]}")
        else:
            print(f"skipped: {slug} (no local checkout)")


# --- mutation mode --------------------------------------------------------

def mutation_jobs():
    """`MUTATION_JOBS` (#1588): how many modules run at once."""
    return _jobs_from_env("MUTATION_JOBS")


def mutation_cost_estimate(n, jobs=1, timeout_s=None):
    """The line printed before a whole-repo run (#1588): the module count and
    the worst case. `audit.py` bounds each of its commands by
    `MUTATION_AUDIT_TIMEOUT` seconds and a mutmut module runs two (`run`, then
    `results`), so a module is at most twice that; `jobs` modules overlap."""
    if timeout_s is None:
        timeout_s = float(os.environ.get("MUTATION_AUDIT_TIMEOUT", "3600"))
    rounds = -(-n // jobs)
    hours = rounds * 2 * timeout_s / 3600
    return (f"mutation-all: {n} module{'s' if n != 1 else ''} to mutate, {jobs} at a time; "
            f"up to {hours:g}h worst case (2 x {timeout_s:g}s per module), plus one `claude` run per module")


def _prepass_ranker(repo):
    """The `rank_fn` of `mutation_run.run`: the model prepass's order of the
    candidates, which only breaks ties. A failed prepass is named and gives no
    ranking, so the order is recency alone."""
    def rank(candidates):
        result = _run(["claude", *CLAUDE_FLAGS, mutation_prepass_prompt(repo, candidates)], env=claude_env())
        ranked = mutation_run.parse_rank(result.stdout, candidates)
        if result.returncode != 0 or not ranked:
            print(f"mutation prepass gave no ranking (exit {result.returncode}); "
                  "ordering by recency alone", file=sys.stderr)
        return ranked
    return rank


def mutation_mode(repo, modules, out, whole_repo=False):
    """`whole_repo` (#1588): every candidate, no `MUTATION_MAX` cut and no
    model prepass, so the order is the recency order alone."""
    repo = os.path.abspath(repo)

    use_prepass = not whole_repo and os.environ.get("AUDITS_NO_SYNTH", "0") != "1"
    try:
        planned = mutation_run.run(
            repo, load_record(_record_file(repo)), modules=modules,
            rank_fn=_prepass_ranker(repo) if use_prepass else None)
    except Exception as e:  # noqa: BLE001 - named below, never an empty target list
        if modules is None:
            print(f"mutation-target probe failed: {e!r}", file=sys.stderr)
            sys.exit(1)
        # The targets are given; only the no-tests count is unknown, and why is kept.
        probe_error = f"no-tests probe failed: {e!r}"
        print(probe_error, file=sys.stderr)
        planned = None
    final_targets = list(modules) if planned is None else planned.targets
    skipped = 0
    if modules is None:
        max_n = len(final_targets) if whole_repo else int(os.environ.get("MUTATION_MAX", "10"))
        skipped = max(0, len(final_targets) - max_n)
        final_targets = final_targets[:max_n]

    for t in final_targets:
        print(f"mutation-target: {t}")
    if skipped > 0:
        print(f"… {skipped} more modules skipped (raise MUTATION_MAX to include them)")
    jobs = mutation_jobs()

    run = RunDir.create(out, worktrees=True)
    collection = run.collection
    pagelib.copy_assets(collection, components=INDEX_COMPONENTS)  # setup-failure pages link ../assets/
    print(f"run dir: {run.root}")
    print(f"collecting under: {collection}\n")

    notest_json = os.path.join(collection, "mutation-no-tests.json")
    # A planning failure is a real "don't know", never a silent zero (#559) —
    # the index must render this as could-not-determine, not as a repo with
    # zero testless modules.
    data = ({"error": probe_error} if planned is None
            else {"no_tests": planned.no_tests, "total": planned.total})
    with open(notest_json, "w", encoding="utf-8") as f:
        json.dump(data, f)
    notest_paths = set(data.get("no_tests", []))
    if notest_paths:
        final_targets = [t for t in final_targets if t not in notest_paths]
        print(f"no-test modules (0% coverage, reported not mutated): {len(notest_paths)}")

    if whole_repo:
        print(mutation_cost_estimate(len(final_targets), jobs))

    failed = []
    try:
        if final_targets:
            with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
                results = list(pool.map(lambda m: _guarded_mutation_module(repo, m, run), final_targets))
            failed = [m for m, reason in zip(final_targets, results) if reason]
    finally:
        for d in os.listdir(run.worktrees):
            shellcmd.git(["-C", repo, "worktree", "remove", "--force", os.path.join(run.worktrees, d)], ok=range(256))
        shellcmd.git(["-C", repo, "worktree", "prune"], ok=range(256))

    print(f"\ncollection: {collection}")
    # Only the mutation page: `collect` would rebuild the top index and rerun
    # the synthesis pass over a sweep already sitting in `--out`.
    render_mutation_subindex(collection, repo, scan_mutation(collection))
    sub_index = os.path.join(collection, "mutation", "index.html")
    if os.path.isfile(sub_index):
        print(f"index: {sub_index}")
        open_index(sub_index)
    if failed:
        print(f"FAILED modules: {', '.join(failed)}", file=sys.stderr)
        sys.exit(1)


_RECORD_LOCK = threading.Lock()


def _guarded_mutation_module(repo, module, run):
    """One pool task: a crash inside a module is that module's failure, so the
    other modules still run and it is listed under FAILED modules."""
    try:
        return _run_mutation_module(repo, module, run)
    except Exception as e:  # noqa: BLE001 - reported by name, never swallowed
        reason = f"crashed: {e!r}"
        print(f"[mutation:{module}] FAILED: {reason}")
        return reason


def _run_mutation_module(repo, module, run):
    """Audit one module in its own worktree. Returns None on success, else
    the failure reason — a setup failure, a nonzero `claude` exit or no
    manifest, the sweep's `run_one` rule (#1278); `done` prints only on
    success."""
    slug = module_slug(module)
    collection = run.collection
    wt = os.path.join(run.worktrees, slug)
    log = os.path.join(run.logs, f"mutation-{slug}.log")
    manifest = manifest_path_for(run.manifests, slug)
    os.makedirs(os.path.dirname(manifest), exist_ok=True)
    clear_manifest(manifest)
    # `--out` accumulates: an earlier run's INCONCLUSIVE must not label this one.
    clear_inconclusive(collection, slug)

    print(f"[mutation:{module}] creating worktree")
    reason = None
    try:
        # The one cleanup for this worktree: `scratch_worktree` removes it on
        # every exit, an exception included (#606). mutation_mode keeps an outer
        # sweep of `worktrees/` as the backstop for a crash mid-`add`.
        with shellcmd.scratch_worktree(repo, "HEAD", wt):
            if not (os.path.isfile(os.path.join(wt, "uv.lock")) or os.path.isfile(os.path.join(wt, "pyproject.toml"))):
                reason = "no recognized env manifest (uv.lock/pyproject.toml); env resolution heuristic ceiling"
            else:
                print(f"[mutation:{module}] resolving env (uv sync)")
                with open(log, "w", encoding="utf-8") as f:
                    r = subprocess.run(["uv", "sync"], cwd=wt, stdout=f, stderr=subprocess.STDOUT, env=scrubbed_env())
                if r.returncode != 0:
                    reason = "uv sync failed"
                else:
                    print(f"[mutation:{module}] running /mutation-audit {module}")
                    prompt = (f"/mutation-audit {module}\n{NO_OPEN_INSTRUCTION}"
                              f"{manifest_instruction(manifest)}{INCONCLUSIVE_INSTRUCTION}")
                    with open(log, "a", encoding="utf-8") as f:
                        r = subprocess.run(["claude", *CLAUDE_FLAGS, prompt], cwd=wt, stdout=f, stderr=subprocess.STDOUT, check=False, env=claude_env())
                    reason = audit_failure(
                        r.returncode, lambda: (mutation_answer_failure(run.manifests, slug)
                                               or collect_from_manifest(run.manifests, slug, collection, slug)))
                    if not reason:
                        record_inconclusive(run.manifests, slug, collection)
    except shellcmd.CmdError as e:
        if os.path.isdir(wt):
            raise
        with open(log, "w", encoding="utf-8") as f:
            f.write(f"{e}\n")
        reason = "git worktree add failed"
    if reason:
        report_failure(f"mutation:{module}", reason, log)
        write_setup_failure_report(collection, module, reason)
        return reason
    why = inconclusive_reason(collection, slug)
    if why is None:
        with _RECORD_LOCK:
            record_mutation(repo, module)
    # An INCONCLUSIVE run measured nothing: not recorded, so the recency order
    # offers it again (#1588).
    print(f"[mutation:{module}] done" + (f" — INCONCLUSIVE: {why}" if why is not None else ""))
    return None


# --- CLI ----------------------------------------------------------------

def _split(value):
    """A comma-separated flag value as a list — the one place the CLI splits."""
    return [v.strip() for v in value.split(",") if v.strip()]


def _modules(value):
    """`--modules`: a list naming at least one module. An empty one is refused,
    never read as a run that mutated nothing."""
    modules = _split(value)
    if not modules:
        raise argparse.ArgumentTypeError(f"{value!r} names no module")
    return modules


def _sweep_flags(p):
    """The flags a sweep takes, shared by `sweep` and `multi`."""
    p.add_argument("--out", metavar="DIR", help="write into DIR, accumulating (no wipe)")
    p.add_argument("--only", metavar="A,B", type=_split, help="run just these audits")
    p.add_argument("--short", action="store_true", help="run only the short set (see audits_data.py)")


def _parser():
    p = argparse.ArgumentParser(
        prog="driver.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    modes = p.add_subparsers(dest="mode", metavar="MODE", required=True)

    m = modes.add_parser("sweep", help="sweep one repo", description="Sweep one repo: plan, execute, collect.")
    m.add_argument("repo", nargs="?", default=os.getcwd(), help="repo to audit (default: the current directory)")
    _sweep_flags(m)
    m.add_argument("--force", action="store_true", help="bypass the staleness cache, run everything")
    m.set_defaults(run=lambda a: sweep(a.repo, a.out, a.only, a.short, a.force))

    m = modes.add_parser("index", help="rebuild the index over a finished collection",
                         description="Rebuild the index only, over --out DIR's reports; runs no claude.")
    m.add_argument("repo", nargs="?", default=os.getcwd(), help="the repo the reports are of (default: the current directory)")
    m.add_argument("--out", metavar="DIR", required=True, help="the dir whose reports to index")
    m.set_defaults(run=lambda a: rebuild_index(a.repo, a.out))

    m = modes.add_parser("multi", help="sweep each owned repo from a fresh worktree of its origin/main",
                         description="Sweep each owned repo in turn from a fresh worktree of its origin/main, "
                                     "storing each sweep under ~/.local/share/all-audits/ (#1679), and the "
                                     "multi-repo index linking them under ~/.local/share/all-audits/multi/<sweep-id>/ "
                                     "(#1721; SKILL.md § Multi-repo).")
    m.add_argument("repos", nargs="+", metavar="REPO", help="the repos to sweep")
    _sweep_flags(m)
    m.add_argument("--force", action="store_true",
                   help="bypass the staleness cache, run everything, and sweep a repo whose earlier audit record "
                        "is still open (the new record links the open one) (#1681)")
    m.set_defaults(run=lambda a: multi_mode(a.repos, a.out, a.only, a.short, a.force))

    m = modes.add_parser("multi-index", help="rebuild a multi pass's page",
                         description="Rebuild a multi pass's page from its recorded state (or, for a pass that "
                                     "recorded none, from the stored sweeps carrying SWEEP_ID) and print its "
                                     "index; runs no claude (#1721).")
    m.add_argument("sweep_id", metavar="SWEEP_ID", help="the pass's sweep id, YYYYMMDD-HHMMSS")
    m.set_defaults(run=lambda a: multi_index_mode(a.sweep_id))

    m = modes.add_parser("load", help="rebuild a stored sweep for triage",
                         description="Rebuild the stored sweep of audit record ISSUE and print its index, for "
                                     "/all-audits triage; runs no claude (#1684).")
    m.add_argument("issue", type=int, metavar="ISSUE", help="the audit record's issue number")
    m.add_argument("repo_name", nargs="?", metavar="REPO",
                   help="the repo name, to pick between repos sharing the number")
    m.set_defaults(run=lambda a: load_mode(a.issue, a.repo_name))

    m = modes.add_parser("suggest", help="print the owned repos worth sweeping",
                         description="Print the owned repos with a PR in the last 14 days and a local checkout, "
                                     "one path each, for multi (#1683).")
    m.add_argument("--roots", metavar="DIR,DIR", type=_split, default=_split(DEFAULT_ROOTS),
                   help="the directories holding local checkouts (default ~/src,~/.agents)")
    m.set_defaults(run=lambda a: suggest_mode(a.roots))

    m = modes.add_parser("mutation", help="mutation-audit modules, one fresh git worktree each",
                         description="Run mutation-audit on each module, one fresh git worktree at a time. With "
                                     "neither --modules nor --all, a prepass picks the modules.")
    m.add_argument("repo", nargs="?", default=os.getcwd(), help="repo to audit (default: the current directory)")
    m.add_argument("--out", metavar="DIR", help="write into DIR, accumulating (no wipe)")
    which = m.add_mutually_exclusive_group()
    which.add_argument("--modules", metavar="A.PY,B.PY", type=_modules, help="the modules to mutate")
    which.add_argument("--all", action="store_true",
                       help="every module the suggest list names, no MUTATION_MAX cap "
                            "(prints the module count and a cost estimate first)")
    m.set_defaults(run=lambda a: mutation_mode(a.repo, a.modules, a.out, whole_repo=a.all))
    return p


def main(argv):
    args = _parser().parse_args(argv[1:])
    args.run(args)


if __name__ == "__main__":
    main(sys.argv)
