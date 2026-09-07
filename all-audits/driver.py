#!/usr/bin/env python3
"""The audit sweep driver (#558): replaces run-audits.sh, should_run.py, and
cache.py with one readable Python program.

Runs each guarded audit as its own `claude -p "/name"` process (see
run-audits.sh's original header comment for why: several audit skills carry
`disable-model-invocation`, so only an explicit `-p "/name"` slash invocation
gets past the guard — a subagent fan-out would silently lose them), collects
the report folders under one `collection/` dir, and builds `index.html`.

A run is three steps: plan (ask the staleness cache what still needs a run),
execute (the only step that spawns audits), collect (assemble the collection
and render the index). `--index` calls collect alone.
"""
import argparse
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
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "harness"))
from audits_data import AUDIT_NAMES, GATED, SHORT_SET  # noqa: E402
import pagelib  # noqa: E402

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


def _run(cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)


def git_state(repo, last_sha):
    dirty = bool(_run(["git", "-C", repo, "status", "--porcelain"]).stdout.strip())
    changed = []
    if last_sha:
        result = _run(["git", "-C", repo, "diff", "--name-only", f"{last_sha}..HEAD"])
        if result.returncode != 0:
            # A SHA `git diff` can't resolve (never a real commit, or pruned)
            # proves nothing about staleness — force dirty so should_run can
            # never read "no diff output" as "unchanged" (#558).
            return {"dirty": True, "changed_files": []}
        changed = [ln for ln in result.stdout.splitlines() if ln.strip()]
    return {"dirty": dirty, "changed_files": changed}


def head_sha(repo):
    return _run(["git", "-C", repo, "rev-parse", "HEAD"]).stdout.strip()


def age_days(timestamp):
    then = _dt.datetime.fromisoformat(timestamp)
    now = _dt.datetime.now(_dt.timezone.utc)
    if then.tzinfo is None:
        then = then.replace(tzinfo=_dt.timezone.utc)
    return (now - then).total_seconds() / 86400.0


@dataclasses.dataclass
class CacheDecision:
    run: bool
    reason: str
    sha: str = None
    report_dir: str = None


def decide(repo, name, ground_truth, threshold=DEFAULT_THRESHOLD, backstop=DEFAULT_BACKSTOP_DAYS, base=None):
    """The cache decision as a structured result (#558) — not the old
    tab-separated RUN/SKIP text `cache.py decide` printed."""
    record = load_record(_record_file(repo, base))
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


def update_cache(repo, name, report_dir, base=None):
    path = _record_file(repo, base)
    record = load_record(path)
    record[name] = {
        "last_sha": head_sha(repo),
        "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "report_dir": report_dir,
    }
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
        '"report_path" (the report\'s absolute path), "count" (how many findings), and "headline" '
        "(the one-line verdict). This is how the sweep finds your report; it does not scan your output."
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
        "tree — audit only the project's own tracked source. Do NOT open the report: skip every "
        "xdg-open/open/start step the skill would run. You are one audit inside an all-audits sweep, and the "
        "sweep opens only the final index — thirteen reports opening at once would bury it. Just write the "
        "report."
    )
    manifest_block = manifest_instruction(manifest_path) if manifest_path else ""
    return f"/{name} {repo}\n{override}{manifest_block}{ignore_block}\n"


def mutation_prepass_prompt(repo):
    return (
        f"Read the repository at {repo} and identify the mutation-worthy core modules: solver/oracle modules "
        "that have a sibling test, where a silently-passing test would be dangerous. Print ONLY the module "
        "file paths, one per line — no prose, no numbering, no markdown.\n"
    )


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
    with open(os.path.join(d, "findings.jsonl"), "w", encoding="utf-8") as f:
        f.write(json.dumps({"status": "setup_failure", "module": module, "reason": reason}) + "\n")


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


def collect_from_manifest(manifests_dir, name, collection_dir, dest_name):
    """Read `name`'s manifest and copy its report dir into
    `collection_dir/dest_name`. Returns None on success, else a failure
    reason: "no manifest" or a manifest naming a missing report. The one
    seam both the audit sweep and mutation mode use to find a report —
    never a log-grepping fallback (#559, and #580 for mutation mode)."""
    manifest = read_manifest(manifests_dir, name)
    if manifest is None:
        return "no manifest"
    report = manifest["report_path"]
    if not os.path.isfile(report):
        return f"manifest names a missing report: {report}"
    replace_dir(os.path.dirname(report), os.path.join(collection_dir, dest_name))
    return None


def run_one(name, repo, outlogs, manifests_dir):
    print(f"[{name}] starting")
    log_path = os.path.join(outlogs, f"{name}.log")
    manifest = manifest_path_for(manifests_dir, name)
    os.makedirs(os.path.dirname(manifest), exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as log:
        subprocess.run(["claude", *CLAUDE_FLAGS, audit_prompt(name, repo, manifest)], stdout=log, stderr=subprocess.STDOUT, check=False)
    print(f"[{name}] done")


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
        verdict = f"{len(model.mutation_modules)} modules run, {model.mutation_survivors_sum} total survivors"
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


def mutation_tally(findings_jsonl):
    if not os.path.exists(findings_jsonl):
        return None
    for line in open(findings_jsonl, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            extra = (json.loads(line) or {}).get("extra") or {}
        except json.JSONDecodeError:
            continue
        keys = {"killed_count", "survived_count", "no_coverage_count"}
        if keys <= extra.keys():
            k, s, n = extra["killed_count"], extra["survived_count"], extra["no_coverage_count"]
            return k, k + s + n, s, n
    return None


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
    if mutation_modules:
        out.append('<h2>Modules</h2><div class="vt-table-wrap"><table class="audit-table">\n')
        out.append("<thead><tr><th>Module</th><th>Killed/total</th><th>Weak-assertion</th><th>No-coverage</th><th>Report</th></tr></thead><tbody>\n")
        for base in mutation_modules:
            tally_row = mutation_tally(os.path.join(collection, base, "findings.jsonl"))
            if tally_row:
                k, t, s, n = tally_row
                tally, weak, nocov = f"{k}/{t}", str(s), str(n)
            else:
                tally = weak = nocov = "—"
            report = os.path.join(collection, base, "report.html")
            link = f'<a href="../{base}/report.html">open report</a>' if os.path.isfile(report) else '<span style="color:var(--vt-muted)">no report</span>'
            out.append(f"<tr><td>{base}</td><td>{tally}</td><td>{weak}</td><td>{nocov}</td><td>{link}</td></tr>\n")
        out.append("</tbody></table></div>\n")
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
        cutoff = _dt.datetime.now().timestamp() - RUN_TTL_DAYS * 86400
        for entry in os.listdir(base):
            p = os.path.join(base, entry)
            if entry.startswith("run-") and os.path.isdir(p) and os.path.getmtime(p) < cutoff:
                shutil.rmtree(p, ignore_errors=True)
        root = os.path.abspath(out) if out else os.path.join(base, "run-" + _dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
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


def plan_sweep(repo, selected, force, base=None):
    """Ask the staleness cache which of `selected` still needs a run."""
    base = base or cache_base()
    plan = Plan()
    for name in selected:
        if name in GATED and not force:
            d = decide(repo, name, GATED[name], base=base)
            if not d.run:
                if d.report_dir and os.path.isdir(d.report_dir):
                    plan.reused[name] = d.report_dir
                    plan.skip_note[name] = f"unchanged since {d.sha[:8]}"
                    print(f"[{name}] skipped (unchanged since {d.sha[:8]}), reusing cached report")
                    continue
                print(f"[{name}] cache says skip but cached report is gone — running fresh")
        plan.to_run.append(name)
    return plan


def execute(repo, plan, run):
    """Run the planned audits — the only place a sweep spawns a process.

    The first audit runs alone as a smoke test: if the `-p` slash invocation
    is rejected by the model-invocation guard, every audit would fail the
    same way, so the sweep aborts instead of fanning thirteen failures out.
    """
    if not plan.to_run:
        return
    smoke = plan.to_run[0]
    print(f"== smoke test: {smoke} ==")
    run_one(smoke, repo, run.logs, run.manifests)
    log_text = open(os.path.join(run.logs, f"{smoke}.log"), encoding="utf-8", errors="replace").read()
    if re.search(r"cannot be used with Skill tool|disable-model-invocation", log_text, re.IGNORECASE):
        print(f"ABORT: -p slash invocation was rejected by the guard. See {run.logs}/{smoke}.log", file=sys.stderr)
        sys.exit(1)
    print("smoke test passed; fanning out the rest\n")
    rest = plan.to_run[1:]
    if rest:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(rest)) as ex:
            list(ex.map(lambda n: run_one(n, repo, run.logs, run.manifests), rest))


def collect(run, repo, plan, base=None):
    """Assemble the collection from what is on disk and render the index.

    Reports arrive two ways — through the manifest each audit that ran wrote,
    or copied from the cache for a skipped one — and this is the only step
    that reads either. Returns the index path. `--index` calls it directly
    over an existing collection, which is why it never touches the run
    branch: an empty `Plan` collects a finished folder just as well.
    """
    base = base or cache_base()
    collection = run.collection
    for name, cached in plan.reused.items():
        replace_dir(cached, os.path.join(collection, name))

    stable = os.path.join(base, repo_key(repo), "reports")
    manifest_note = {}
    for name in plan.to_run:
        reason = collect_from_manifest(run.manifests, name, collection, name)
        if reason == "no manifest":
            manifest_note[name] = f"no manifest — see {os.path.join(run.logs, name + '.log')}"
            continue
        if reason:
            manifest_note[name] = reason
            continue
        if name in GATED:
            os.makedirs(stable, exist_ok=True)
            replace_dir(os.path.join(collection, name), os.path.join(stable, name))
            update_cache(repo, name, os.path.join(stable, name), base=base)

    report_link = {}
    for name in AUDIT_NAMES:
        d = os.path.join(collection, name)
        found = None
        if os.path.isdir(d):
            htmls = sorted(f for f in os.listdir(d) if f.endswith(".html"))
            found = htmls[0] if htmls else None
        report_link[name] = f"{name}/{found}" if found else ""

    mutation_modules = []
    for entry in sorted(os.listdir(collection)):
        d = os.path.join(collection, entry)
        if not os.path.isdir(d) or entry in AUDIT_NAMES:
            continue
        if os.path.isfile(os.path.join(d, "findings.jsonl")):
            mutation_modules.append(entry)

    mutation_survivors_sum = 0
    for base_name in mutation_modules:
        tally = mutation_tally(os.path.join(collection, base_name, "findings.jsonl"))
        if tally:
            _, _, s, n = tally
            mutation_survivors_sum += s + n

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

    report_files = [os.path.join(collection, report_link[n]) for n in AUDIT_NAMES if report_link[n]]
    synthesis = ""
    if os.environ.get("AUDITS_NO_SYNTH", "0") != "1" and report_files:
        print("== synthesis pass ==")
        prompt = (
            f"Read these {len(report_files)} audit report HTML files and write a 2-3 sentence synthesis of "
            "the repo's overall state for the lede of an index page. Plain prose only — no preamble, no "
            f"markdown, no headings, no lists. Files: {' '.join(report_files)}"
        )
        result = _run(["claude", *CLAUDE_FLAGS, prompt])
        synthesis = result.stdout.strip()

    pagelib.copy_assets(collection)

    build_index(IndexModel(
        collection=collection,
        repo=repo,
        report_link=report_link,
        skip_note={**plan.skip_note, **manifest_note},
        synthesis=synthesis,
        mutation_modules=mutation_modules,
        mutation_survivors_sum=mutation_survivors_sum,
        notest_count=len(notest_modules),
        notest_error=notest_error,
    ))
    if mutation_modules or notest_modules or notest_error:
        build_mutation_subindex(collection, repo, mutation_modules, notest_modules, notest_total, notest_error)

    index_path = os.path.join(collection, "index.html")
    print()
    print(f"index: {index_path}")
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


def sweep(repo, out, only, short, force):
    repo = os.path.abspath(repo)
    selected = only if only is not None else (SHORT_SET if short else list(AUDIT_NAMES))
    run = RunDir.create(out)
    _announce(run, repo)
    plan = plan_sweep(repo, selected, force)
    execute(repo, plan, run)
    open_index(collect(run, repo, plan))


def rebuild_index(repo, out):
    """`--index --out DIR`: collect over a finished collection, nothing else."""
    repo = os.path.abspath(repo)
    run = RunDir.create(out)
    _announce(run, repo)
    open_index(collect(run, repo, Plan()))


# --- mutation mode --------------------------------------------------------

def mutation_mode(repo, modules, out):
    repo = os.path.abspath(repo)
    here = os.path.dirname(os.path.abspath(__file__))

    final_targets = None if modules is None else list(modules)
    skipped = 0
    if final_targets is None:
        candidates = []
        if os.environ.get("AUDITS_NO_SYNTH", "0") != "1":
            result = _run(["claude", *CLAUDE_FLAGS, mutation_prepass_prompt(repo)])
            candidates = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
        max_n = int(os.environ.get("MUTATION_MAX", "10"))
        final_targets = candidates[:max_n]
        skipped = max(0, len(candidates) - max_n)

    for t in final_targets:
        print(f"mutation-target: {t}")
    if skipped > 0:
        print(f"… {skipped} more modules skipped (raise MUTATION_MAX to include them)")

    run = RunDir.create(out, worktrees=True)
    collection = run.collection
    print(f"run dir: {run.root}")
    print(f"collecting under: {collection}\n")

    notest_json = os.path.join(collection, "mutation-no-tests.json")
    r = _run(["python3", os.path.join(here, "..", "mutation-audit", "audit.py"), "--no-tests", repo])
    data = None
    if r.returncode == 0:
        try:
            data = json.loads(r.stdout)
        except json.JSONDecodeError:
            data = None
    if data is None:
        # A crash or unparseable output is a real "don't know", never a
        # silent zero (#559) — the index must render this as could-not-
        # determine, not as a repo with zero testless modules.
        data = {"error": "no-tests probe crashed or returned unparseable output"}
    with open(notest_json, "w", encoding="utf-8") as f:
        json.dump(data, f)
    notest_paths = set(data.get("no_tests", []))
    if notest_paths:
        final_targets = [t for t in final_targets if t not in notest_paths]
        print(f"no-test modules (0% coverage, reported not mutated): {len(notest_paths)}")

    if not final_targets:
        print(f"\ncollection: {collection}")
        return

    try:
        for module in final_targets:
            _run_mutation_module(repo, module, run)
    finally:
        for d in os.listdir(run.worktrees):
            _run(["git", "-C", repo, "worktree", "remove", "--force", os.path.join(run.worktrees, d)])
        _run(["git", "-C", repo, "worktree", "prune"])

    print(f"\ncollection: {collection}")


def _run_mutation_module(repo, module, run):
    slug = module_slug(module)
    collection = run.collection
    wt = os.path.join(run.worktrees, slug)
    log = os.path.join(run.logs, f"mutation-{slug}.log")
    manifest = manifest_path_for(run.manifests, slug)
    os.makedirs(os.path.dirname(manifest), exist_ok=True)

    print(f"[mutation:{module}] creating worktree")
    try:
        with open(log, "w", encoding="utf-8") as f:
            r = subprocess.run(["git", "-C", repo, "worktree", "add", "--detach", wt, "HEAD"], stdout=f, stderr=subprocess.STDOUT)
        if r.returncode != 0:
            print(f"[mutation:{module}] worktree creation failed — see {log}", file=sys.stderr)
            write_setup_failure_report(collection, module, "git worktree add failed")
            return

        if not (os.path.isfile(os.path.join(wt, "uv.lock")) or os.path.isfile(os.path.join(wt, "pyproject.toml"))):
            print(f"[mutation:{module}] no recognized env manifest (uv.lock/pyproject.toml) — see {log}", file=sys.stderr)
            write_setup_failure_report(collection, module, "no recognized env manifest (uv.lock/pyproject.toml); env resolution heuristic ceiling")
            return

        print(f"[mutation:{module}] resolving env (uv sync)")
        with open(log, "a", encoding="utf-8") as f:
            r = subprocess.run(["uv", "sync"], cwd=wt, stdout=f, stderr=subprocess.STDOUT)
        if r.returncode != 0:
            print(f"[mutation:{module}] env resolution failed — see {log}", file=sys.stderr)
            write_setup_failure_report(collection, module, "uv sync failed")
            return

        print(f"[mutation:{module}] running /mutation-audit {module}")
        prompt = f"/mutation-audit {module}\n{manifest_instruction(manifest)}"
        with open(log, "a", encoding="utf-8") as f:
            subprocess.run(["claude", *CLAUDE_FLAGS, prompt], cwd=wt, stdout=f, stderr=subprocess.STDOUT, check=False)

        reason = collect_from_manifest(run.manifests, slug, collection, slug)
        if reason:
            print(f"[mutation:{module}] {reason} — see {log}", file=sys.stderr)
            write_setup_failure_report(collection, module, reason)
    finally:
        # The one cleanup for this worktree — every exit path, including an
        # exception, comes through here (#606). mutation_mode keeps an outer
        # sweep of `worktrees/` as the backstop for a crash mid-`add`.
        _run(["git", "-C", repo, "worktree", "remove", "--force", wt])
        _run(["git", "-C", repo, "worktree", "prune"])
    print(f"[mutation:{module}] done")


# --- CLI ----------------------------------------------------------------

def _split(value):
    """A comma-separated flag value as a list — the one place the CLI splits."""
    return [v.strip() for v in value.split(",") if v.strip()] if value else []


def main(argv):
    p = argparse.ArgumentParser(
        prog="driver.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("repo", nargs="?", help="repo to audit (default: the current directory)")
    p.add_argument("--out", metavar="DIR", help="write into DIR, accumulating (no wipe)")
    p.add_argument("--only", metavar="A,B", help="run just these audits")
    p.add_argument("--short", action="store_true", help="run only the short set (see audits_data.py)")
    p.add_argument("--index", action="store_true", help="rebuild the index only, over --out DIR's reports")
    p.add_argument("--force", action="store_true", help="bypass the staleness cache, run everything")
    p.add_argument("--mutation", nargs="?", const="", metavar="A.PY,B.PY",
                   help="run mutation-audit on each module, one fresh git worktree at a time "
                        "(no value: pick the modules with a prepass)")
    args = p.parse_args(argv[1:])

    repo = args.repo or os.getcwd()
    if args.mutation is not None:
        mutation_mode(repo, None if args.mutation == "" else _split(args.mutation), args.out)
    elif args.index:
        if not args.out:
            p.error("--index needs --out DIR — the dir whose reports to index.")
        rebuild_index(repo, args.out)
    else:
        sweep(repo, args.out, _split(args.only) if args.only is not None else None, args.short, args.force)


if __name__ == "__main__":
    main(sys.argv)
