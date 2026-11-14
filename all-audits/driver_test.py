"""Tests for the audit sweep driver (#558) — ports run-audits.test.sh's
hermetic index test to Python (parses the index rather than grepping it, per
the family's plain-assert pytest convention — see crap-audit/audit_test.py), plus a
new cache-decision test against a real temporary git repo, including the
bad-last-run-SHA case, which must mean RUN.
"""
import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("AUDITS_NO_OPEN", "1")
os.environ.setdefault("AUDITS_NO_SYNTH", "1")
import driver  # noqa: E402
import mutation_run  # noqa: E402
import procs  # noqa: E402


def _run_driver(*args):
    return subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(__file__), "driver.py"), *args],
        capture_output=True, text=True,
        env={**os.environ, "AUDITS_NO_OPEN": "1", "AUDITS_NO_SYNTH": "1"},
    )

def _mkdirs(base, *names):
    """Create `names` as directories under `base` and return their paths."""
    paths = [str(base / name) for name in names]
    for path in paths:
        os.mkdir(path)
    return paths


def test_index_rerun_replaces_assets_without_nesting(tmp_path):
    tmp = str(tmp_path)
    os.makedirs(os.path.join(tmp, "collection", "dead-code", "assets", "base"))
    with open(os.path.join(tmp, "collection", "dead-code", "assets", "base", "base.css"), "w") as f:
        f.write("body{}")

    r = _run_driver("index", "--out", tmp)
    assert r.returncode == 0, r.stdout + r.stderr
    assert os.path.isfile(os.path.join(tmp, "collection", "assets", "base", "base.css"))

    r = _run_driver("index", "--out", tmp)
    assert r.returncode == 0, r.stdout + r.stderr
    assert os.path.isfile(os.path.join(tmp, "collection", "assets", "base", "base.css"))
    assert not os.path.isdir(os.path.join(tmp, "collection", "assets", "assets")), "assets/assets nesting"


def test_index_over_an_empty_collection_still_links_to_real_assets(tmp_path):
    """#613: assets come from pagelib.copy_assets, not hoisted out of the
    first report folder — so an index whose audits all skipped still links to
    files that exist."""
    tmp = str(tmp_path)
    os.makedirs(os.path.join(tmp, "collection"))

    r = _run_driver("index", "--out", tmp)
    assert r.returncode == 0, r.stdout + r.stderr

    index = os.path.join(tmp, "collection", "index.html")
    text = open(index).read()
    assert 'href="assets/base/base.css"' in text
    for linked in ("assets/base/base.css", "assets/base/base.js",
                   "assets/components/callout/callout.css",
                   "assets/components/table/table.css"):  # vt-table-wrap's CSS
        assert os.path.isfile(os.path.join(tmp, "collection", linked)), linked


def test_index_over_an_old_run_dir_does_not_prune_it(tmp_path):
    """#606 round 2: `index --out <run older than the TTL>` must index that
    run, not delete it — pruning happens after `--out` is resolved and skips
    the resolved dir."""
    cache_dir = str(tmp_path)
    base = os.path.join(cache_dir, "all-audits")
    old_run = os.path.join(base, "run-20200101-000000")
    report = os.path.join(old_run, "collection", "dead-code", "report.html")
    os.makedirs(os.path.dirname(report))
    open(report, "w").write("<html>old report</html>")
    os.utime(old_run, (0, 0))

    r = subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(__file__), "driver.py"), "index", "--out", old_run],
        capture_output=True, text=True,
        env={**os.environ, "XDG_CACHE_HOME": cache_dir, "AUDITS_NO_OPEN": "1", "AUDITS_NO_SYNTH": "1"},
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert os.path.isfile(report), "the run being indexed was pruned"
    assert "dead-code" in open(os.path.join(old_run, "collection", "index.html")).read()


def test_collect_from_manifest_mutation_style(tmp_path):
    """#580: mutation mode now finds its report the same way the sweep does
    — through a manifest, never by grepping a log for a stray .html path
    (the marker this replaced, `ALL_AUDITS_REPORT=`, is gone from every
    doc)."""
    manifests_dir, collection, reportdir = _mkdirs(tmp_path, "manifests_dir", "collection", "reportdir")
    report = os.path.join(reportdir, "report.html")
    with open(report, "w") as f:
        f.write("<html>module report</html>")
    manifest = driver.manifest_path_for(manifests_dir, "solver_py")
    os.makedirs(os.path.dirname(manifest), exist_ok=True)
    with open(manifest, "w") as f:
        json.dump({"report_path": report, "count": 1, "headline": "one finding"}, f)

    reason = driver.collect_from_manifest(manifests_dir, "solver_py", collection, "solver_py")
    assert reason is None, reason
    assert os.path.isfile(os.path.join(collection, "solver_py", "report.html"))


def test_collect_from_manifest_no_manifest_or_missing_report(tmp_path):
    manifests_dir, collection = _mkdirs(tmp_path, "manifests_dir", "collection")
    assert driver.collect_from_manifest(manifests_dir, "missing", collection, "missing") == "no manifest"

    manifest = driver.manifest_path_for(manifests_dir, "ghost")
    os.makedirs(os.path.dirname(manifest), exist_ok=True)
    with open(manifest, "w") as f:
        json.dump({"report_path": "/no/such/report.html", "count": 0, "headline": "x"}, f)
    reason = driver.collect_from_manifest(manifests_dir, "ghost", collection, "ghost")
    assert reason == "manifest names a missing report: /no/such/report.html"


def test_audit_prompt_whole_repo_override_and_ignore_file(tmp_path):
    prompt = driver.audit_prompt("dead-code", "/some/repo")
    assert prompt.startswith("/dead-code /some/repo")
    assert "ENTIRE repository" in prompt
    assert "not a git diff" in prompt
    assert "rejected" not in prompt

    tmp = str(tmp_path)
    with open(os.path.join(tmp, ".audit-ignore.md"), "w") as f:
        f.write("### god object in solver.py\n- adr: docs/adr/0009-solver-shape.md\n")
    with_file = driver.audit_prompt("dead-code", tmp)
    assert "ENTIRE repository" in with_file
    assert "god object in solver.py" in with_file
    assert "0009-solver-shape.md" in with_file


def test_mutation_subindex_and_single_main_row(tmp_path):
    tmp = str(tmp_path)
    for name in ("dead-code", "test-audit"):
        d = os.path.join(tmp, "collection", name)
        os.makedirs(d)
        open(os.path.join(d, "report.html"), "w").write(f"<html>{name}</html>")

    for module, killed, survived, nocov in (("solver.py", 8, 2, 0), ("oracle.py", 5, 1, 2)):
        d = os.path.join(tmp, "collection", module)
        os.makedirs(d)
        open(os.path.join(d, "report.html"), "w").write("<html>report</html>")
        row = {
            "bucket": "rewrite", "file": module, "line": 1, "category": "surviving-mutant",
            "summary": "s", "failure": "",
            "extra": {"mutant": "x", "killed": False, "survived": True,
                      "killed_count": killed, "survived_count": survived, "no_coverage_count": nocov},
        }
        open(os.path.join(d, "findings.jsonl"), "w").write(json.dumps(row) + "\n")

    r = _run_driver("index", "--out", tmp)
    assert r.returncode == 0, r.stdout + r.stderr

    index_text = open(os.path.join(tmp, "collection", "index.html")).read()
    assert index_text.count("<td>mutation</td>") == 1
    assert 'href="mutation/index.html"' in index_text
    assert 'href="solver.py/report.html"' not in index_text

    sub = open(os.path.join(tmp, "collection", "mutation", "index.html")).read()
    assert "solver.py" in sub and "oracle.py" in sub
    assert 'href="../solver.py/report.html"' in sub
    assert 'href="../oracle.py/report.html"' in sub
    assert "8/10" in sub  # solver: killed 8, total 8+2+0
    assert "5/8" in sub  # oracle: killed 5, total 5+1+2


def test_a_corrupt_mutation_log_line_shows_in_the_module_row_not_as_a_tally(tmp_path):
    tmp = str(tmp_path)
    d = os.path.join(tmp, "collection", "solver.py")
    os.makedirs(d)
    open(os.path.join(d, "report.html"), "w").write("<html>x</html>")
    row = {"extra": {"killed_count": 8, "survived_count": 2, "no_coverage_count": 0}}
    open(os.path.join(d, "findings.jsonl"), "w").write("{not json\n" + json.dumps(row) + "\n")

    r = _run_driver("index", "--out", tmp)
    assert r.returncode == 0, r.stdout + r.stderr
    sub = open(os.path.join(tmp, "collection", "mutation", "index.html")).read()
    assert "CORRUPT: findings.jsonl line 1" in sub and "8/10" not in sub


def test_no_mutation_reports_no_row(tmp_path):
    tmp = str(tmp_path)
    for name in ("dead-code", "test-audit"):
        d = os.path.join(tmp, "collection", name)
        os.makedirs(d)
        open(os.path.join(d, "report.html"), "w").write("<html>x</html>")

    r = _run_driver("index", "--out", tmp)
    assert r.returncode == 0, r.stdout + r.stderr
    index_text = open(os.path.join(tmp, "collection", "index.html")).read()
    assert "<td>mutation</td>" not in index_text
    assert not os.path.exists(os.path.join(tmp, "collection", "mutation"))


def test_no_test_modules_section(tmp_path):
    tmp = str(tmp_path)
    d = os.path.join(tmp, "collection", "solver.py")
    os.makedirs(d)
    open(os.path.join(d, "report.html"), "w").write("<html>x</html>")
    row = {
        "bucket": "rewrite", "file": "solver.py", "line": 1, "category": "surviving-mutant",
        "summary": "s", "failure": "",
        "extra": {"mutant": "x", "killed": False, "survived": True,
                  "killed_count": 8, "survived_count": 2, "no_coverage_count": 3},
    }
    open(os.path.join(d, "findings.jsonl"), "w").write(json.dumps(row) + "\n")
    open(os.path.join(tmp, "collection", "mutation-no-tests.json"), "w").write(
        json.dumps({"no_tests": ["widget.py", "gadget.py"], "total": 6})
    )

    r = _run_driver("index", "--out", tmp)
    assert r.returncode == 0, r.stdout + r.stderr

    index_text = open(os.path.join(tmp, "collection", "index.html")).read()
    assert "with no tests" in index_text and "2 with no tests" in index_text

    sub = open(os.path.join(tmp, "collection", "mutation", "index.html")).read()
    assert "2 of 6 source modules have no tests" in sub
    assert "widget.py" in sub and "gadget.py" in sub
    # solver.py's row: killed/total, weak (survived) and no-coverage counts, in that order
    assert "<td>solver.py</td><td>8/13</td><td>2</td><td>3</td>" in sub


def test_index_from_manifests_missing_manifest_is_a_failure_row(tmp_path):
    """#559: the driver reads each audit's manifest, never a transcript. A
    fixture log containing an unrelated .html path must not land in the
    index — the audit that never wrote a manifest renders as a named
    failure row instead of silently reusing a stray path from its log."""
    tmp, cache_dir, bin_dir = _mkdirs(tmp_path, "tmp", "cache_dir", "bin_dir")
    # A stray .html path in duplication's log — must never be mistaken
    # for its report now that the driver reads manifests, not logs.
    r = _sweep_with_fake_claude(tmp, cache_dir, bin_dir, "dead-code,duplication")
    assert r.returncode != 0, "an audit that wrote no manifest must fail the sweep (#1278)"
    assert "[dead-code] done" in r.stdout, r.stdout
    assert "[duplication] done" not in r.stdout, "no manifest must never print done (#1278)"
    assert "[duplication] FAILED: no manifest" in r.stdout, r.stdout

    # duplication's fake process printed a stray .html path to its own
    # log (see fake_claude_fixture.sh) and wrote no manifest — a
    # log-grepping collector would wrongly pick that path up.
    dup_log = open(os.path.join(tmp, "out", "logs", "duplication.log")).read()
    assert "unrelated-1234" in dup_log, "fixture setup: the stray path must land in duplication's own log"

    index_text = open(os.path.join(tmp, "out", "collection", "index.html")).read()
    assert "dead-code/report.html" in index_text, "the manifest-backed report must be linked"
    assert "unrelated-1234" not in index_text, "the driver must never pick up a stray path from a log"
    assert "no manifest" in index_text, "duplication (no manifest written) must render as a named failure"


def _sweep_with_fake_claude(tmp, cache_dir, bin_dir, only, extra_args=(), **extra_env):
    here = os.path.dirname(os.path.abspath(__file__))
    for name, fixture in (("claude", "fake_claude_fixture.sh"), ("gh", "fake_gh_fixture.sh")):
        if not os.path.lexists(os.path.join(bin_dir, name)):  # a second run reuses the same bin_dir
            os.symlink(os.path.join(here, fixture), os.path.join(bin_dir, name))
    # The ceiling variable is dropped from the ambient env so a shell that
    # already exports it cannot make the driver's own setting look unneeded.
    ambient = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS", "SWEEP_JOBS")}
    env = {
        **ambient, "PATH": f"{bin_dir}:{os.environ['PATH']}", "XDG_CACHE_HOME": cache_dir,
        # Never the machine's stored sweeps or its real `gh` (#1678): the sweep prunes closed records.
        "XDG_DATA_HOME": os.path.join(tmp, "data"),
        "AUDITS_NO_OPEN": "1", "AUDITS_NO_SYNTH": "1", **extra_env,
    }
    return subprocess.run(
        [sys.executable, os.path.join(here, "driver.py"), "sweep", tmp, "--only", only, *extra_args, "--out", os.path.join(tmp, "out")],
        capture_output=True, text=True, env=env,
    )


def _inflight_counts(inflight):
    """What each fake `claude` saw in flight when it started (#1666)."""
    return [int(n) for n in open(os.path.join(inflight, "counts")).read().split()]


def test_sweep_runs_at_most_sweep_jobs_audits_at_once(tmp_path):
    """#1666: with SWEEP_JOBS=2 and five audits, no audit starts with more than
    two in flight and some overlap; SWEEP_JOBS=1 never overlaps."""
    only = "dead-code,duplication,test-audit,comment-audit,error-handling"
    for jobs, overlaps in (("2", True), ("1", False)):
        (tmp_path / jobs).mkdir()
        tmp, cache_dir, bin_dir, inflight = _mkdirs(tmp_path / jobs, "tmp", "cache_dir", "bin_dir", "inflight")
        _sweep_with_fake_claude(tmp, cache_dir, bin_dir, only, SWEEP_JOBS=jobs, FAKE_CLAUDE_INFLIGHT=inflight)
        counts = _inflight_counts(inflight)
        assert len(counts) == 5, counts
        assert max(counts) <= int(jobs), (jobs, counts)
        assert (max(counts) >= 2) is overlaps, (jobs, counts)


def test_sweep_jobs_defaults_to_four(tmp_path):
    only = "dead-code,duplication,test-audit,comment-audit,error-handling,type-tightness,domain-drift,docstring-coverage"
    tmp, cache_dir, bin_dir, inflight = _mkdirs(tmp_path, "tmp", "cache_dir", "bin_dir", "inflight")
    _sweep_with_fake_claude(tmp, cache_dir, bin_dir, only, FAKE_CLAUDE_INFLIGHT=inflight)
    counts = _inflight_counts(inflight)
    assert len(counts) == 8, counts
    assert 2 <= max(counts) <= 4, counts


def test_sweep_jobs_must_be_a_positive_integer(tmp_path):
    for bad in ("0", "many", "-1"):
        (tmp_path / bad).mkdir()
        tmp, cache_dir, bin_dir = _mkdirs(tmp_path / bad, "tmp", "cache_dir", "bin_dir")
        r = _sweep_with_fake_claude(tmp, cache_dir, bin_dir, "dead-code", SWEEP_JOBS=bad)
        assert r.returncode == 2 and "SWEEP_JOBS must be a positive integer" in r.stderr, r.stdout + r.stderr
        assert "smoke test" not in r.stdout
        assert not os.path.exists(os.path.join(tmp, "out")), "a bad value must stop before the run dir exists"


def test_audit_claude_gets_the_unlimited_bg_wait_ceiling(tmp_path):
    """#1278: `claude -p` kills itself after 600 s of background tasks unless
    the ceiling variable is 0; the audit's own log records what it received."""
    tmp, cache_dir, bin_dir = _mkdirs(tmp_path, "tmp", "cache_dir", "bin_dir")
    r = _sweep_with_fake_claude(tmp, cache_dir, bin_dir, "dead-code")
    assert r.returncode == 0, r.stdout + r.stderr
    log = open(os.path.join(tmp, "out", "logs", "dead-code.log")).read()
    assert "ceiling=0" in log, log


def test_audit_exiting_nonzero_fails_the_sweep_even_with_a_manifest(tmp_path):
    """#1278: a nonzero `claude` exit is a failure line and a nonzero sweep
    exit, never `done`, whatever is on disk."""
    tmp, cache_dir, bin_dir = _mkdirs(tmp_path, "tmp", "cache_dir", "bin_dir")
    r = _sweep_with_fake_claude(tmp, cache_dir, bin_dir, "dead-code", FAKE_CLAUDE_EXIT_DEAD_CODE="3")
    assert r.returncode != 0, r.stdout + r.stderr
    assert "[dead-code] FAILED: exit 3" in r.stdout, r.stdout
    assert "[dead-code] done" not in r.stdout, r.stdout
    assert "smoke test passed" not in r.stdout, "a failed smoke audit must not be announced as passed"
    assert os.path.isfile(os.path.join(tmp, "out", "collection", "index.html")), "the index is still built"


def test_manifest_naming_a_missing_report_fails_the_sweep(tmp_path):
    """#1292: success in `run_one` is what `collect_from_manifest` means —
    the manifest's report file exists. The console and exit code must agree
    with the index's failure row."""
    tmp, cache_dir, bin_dir = _mkdirs(tmp_path, "tmp", "cache_dir", "bin_dir")
    r = _sweep_with_fake_claude(tmp, cache_dir, bin_dir, "dead-code", FAKE_CLAUDE_MISSING_REPORT="1")
    assert r.returncode != 0, r.stdout + r.stderr
    assert "[dead-code] FAILED: manifest names a missing report:" in r.stdout, r.stdout
    assert "[dead-code] done" not in r.stdout, r.stdout


def test_stale_manifest_from_an_earlier_run_does_not_count_as_success(tmp_path):
    """#1278: `--out` accumulates, so a rerun into the same dir (the issue's
    own recovery command) finds the last run's manifest. An audit that writes
    nothing this time must still fail, not inherit the old manifest."""
    tmp, cache_dir, bin_dir = _mkdirs(tmp_path, "tmp", "cache_dir", "bin_dir")
    (tmp_path / "tmp" / "mod.py").write_text("")  # a Python repo: out/ later holds .js assets, which must not matter
    first = _sweep_with_fake_claude(tmp, cache_dir, bin_dir, "dead-code")
    assert first.returncode == 0, first.stdout + first.stderr
    assert os.path.isfile(os.path.join(tmp, "out", "manifests", "dead-code", "manifest.json")), "fixture setup: run 1 leaves a manifest"
    again = _sweep_with_fake_claude(tmp, cache_dir, bin_dir, "dead-code", extra_args=("--force",), FAKE_CLAUDE_NOOP="1")
    assert again.returncode != 0, again.stdout + again.stderr
    assert "[dead-code] FAILED: no manifest" in again.stdout, again.stdout


@contextlib.contextmanager
def _leaked_git_env(victim):
    """Run the body with GIT_DIR/GIT_WORK_TREE pointing at `victim`, the way a
    caller's shell (or a git hook) leaks them into the driver (#625)."""
    saved = {k: os.environ.get(k) for k in procs.GIT_REDIRECT_VARS}
    os.environ["GIT_DIR"] = os.path.join(victim, ".git")
    os.environ["GIT_WORK_TREE"] = victim
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _init_git_repo(path):
    # A caller's leaked GIT_DIR/GIT_WORK_TREE would redirect these calls at
    # that repo instead of `path` (#620) — scrub them from the child env.
    env = driver.scrubbed_env()
    subprocess.run(["git", "-C", path, "init", "-q"], check=True, env=env)
    subprocess.run(["git", "-C", path, "config", "user.email", "t@example.com"], check=True, env=env)
    subprocess.run(["git", "-C", path, "config", "user.name", "t"], check=True, env=env)
    open(os.path.join(path, "a.py"), "w").write("x = 1\n")
    subprocess.run(["git", "-C", path, "add", "."], check=True, env=env)
    subprocess.run(["git", "-C", path, "commit", "-q", "-m", "init"], check=True, env=env)


def test_init_git_repo_ignores_leaked_git_dir(tmp_path):
    """AC (#620): _init_git_repo must write only inside its own temp dir even
    when the caller's shell leaked GIT_DIR/GIT_WORK_TREE pointing at a real
    repo — regression witness for the 2026-09-07 incident, where a leaked
    GIT_DIR made `git init` on a /tmp path silently reinitialize that other
    repo instead and rewrite its .git/config."""
    victim, target = _mkdirs(tmp_path, "victim", "target")
    clean_env = driver.scrubbed_env()
    subprocess.run(["git", "init", "-q", victim], check=True, env=clean_env)
    subprocess.run(["git", "-C", victim, "-c", "user.email=v@example.com", "-c", "user.name=v",
                    "commit", "-q", "--allow-empty", "-m", "victim"], check=True, env=clean_env)
    config_path = os.path.join(victim, ".git", "config")
    before = open(config_path).read()
    head_before = subprocess.run(["git", "-C", victim, "rev-parse", "HEAD"], check=True,
                                 capture_output=True, text=True, env=clean_env).stdout

    with _leaked_git_env(victim):
        _init_git_repo(target)

    after = open(config_path).read()
    assert after == before, "a leaked GIT_DIR must not let _init_git_repo touch another repo's config"
    head_after = subprocess.run(["git", "-C", victim, "rev-parse", "HEAD"], check=True,
                                capture_output=True, text=True, env=clean_env).stdout
    assert head_after == head_before, "a leaked GIT_DIR must not let _init_git_repo commit onto another repo (#622)"
    assert os.path.isdir(os.path.join(target, ".git")), "_init_git_repo must still create a repo in its own temp dir"


def test_decide_and_head_sha_ignore_leaked_git_dir(tmp_path):
    """AC (#625): the driver's own git calls must read the repo they were
    handed. Under a leaked GIT_DIR pointing at a dirty repo, decide() on a
    clean, freshly-cached repo returned run=True "dirty working tree" and
    head_sha() returned the other repo's SHA."""
    victim, repo, cache_dir = _mkdirs(tmp_path, "victim", "repo", "cache_dir")
    _init_git_repo(victim)
    # a second commit, so the victim's HEAD can never coincide with the
    # audited repo's (both repos hold the same tree otherwise)
    clean_env = driver.scrubbed_env()
    subprocess.run(["git", "-C", victim, "commit", "-q", "--allow-empty", "-m", "second"],
                   check=True, env=clean_env)
    open(os.path.join(victim, "untracked.py"), "w").write("x = 2\n")  # victim reads dirty
    _init_git_repo(repo)
    sha = driver.head_sha(repo)
    report_dir = os.path.join(cache_dir, "report")
    os.makedirs(report_dir)
    driver.save_record(driver._record_file(repo, cache_dir), {
        "domain-drift": {
            "last_sha": sha,
            "timestamp": driver._dt.datetime.now(driver._dt.timezone.utc).isoformat(),
            "report_dir": report_dir,
        }
    })

    with _leaked_git_env(victim):
        leaked_sha = driver.head_sha(repo)
        d = driver.decide(repo, "domain-drift", ["GLOSSARY.md"], base=cache_dir)

    assert leaked_sha == sha, "head_sha must read the repo it was handed, not the leaked GIT_DIR"
    assert d.run is False, d
    assert d.report_dir == report_dir, d


def test_mutation_worktree_add_ignores_leaked_git_dir(tmp_path):
    """AC (#625): the mutation worktree is the one git call that bypasses
    _run — under a leaked GIT_DIR it registered its worktree in the caller's
    repo instead of the audited one."""
    victim, repo, tmp = _mkdirs(tmp_path, "victim", "repo", "tmp")
    # the victim has no commit, so a `worktree add HEAD` aimed at it by a
    # leak fails outright while the same call on `repo` succeeds
    clean_env = driver.scrubbed_env()
    subprocess.run(["git", "init", "-q", victim], check=True, env=clean_env)
    _init_git_repo(repo)
    run = _seed_run_dir(tmp, worktrees=True)
    with _leaked_git_env(victim):
        driver._run_mutation_module(repo, "solver.py", run)  # no env manifest: setup-failure, then cleanup

    report = open(os.path.join(run.collection, "solver.py", "report.html")).read()
    assert "git worktree add failed" not in report, \
        "a leaked GIT_DIR must not aim `git worktree add` at another repo"
    assert "no recognized env manifest" in report, report
    assert os.listdir(run.worktrees) == [], "the worktree must still be cleaned up"


def test_cache_decision_bad_sha_forces_run(tmp_path):
    """AC: a bad/unknown last-run SHA on a real temp git repo must yield
    RUN — `git diff` against a SHA that doesn't exist can't prove the repo
    is unchanged, so it must never read as SKIP. The timestamp here is
    fresh (regression witness: an old timestamp would trip the backstop
    and pass even if the bad-SHA path itself silently read as unchanged —
    that's exactly the bug this test caught)."""
    repo, cache_dir = _mkdirs(tmp_path, "repo", "cache_dir")
    _init_git_repo(repo)
    record_path = driver._record_file(repo, cache_dir)
    driver.save_record(record_path, {
        "domain-drift": {
            "last_sha": "0" * 40,  # a SHA that was never a real commit
            "timestamp": driver._dt.datetime.now(driver._dt.timezone.utc).isoformat(),
            "report_dir": os.path.join(cache_dir, "nope"),
        }
    })
    d = driver.decide(repo, "domain-drift", ["GLOSSARY.md"], base=cache_dir)
    assert d.run is True, d


def test_cache_decision_clean_recent_repo_skips(tmp_path):
    repo, cache_dir = _mkdirs(tmp_path, "repo", "cache_dir")
    _init_git_repo(repo)
    sha = driver.head_sha(repo)
    report_dir = os.path.join(cache_dir, "report")
    os.makedirs(report_dir)
    driver.save_record(driver._record_file(repo, cache_dir), {
        "domain-drift": {
            "last_sha": sha,
            "timestamp": driver._dt.datetime.now(driver._dt.timezone.utc).isoformat(),
            "report_dir": report_dir,
        }
    })
    d = driver.decide(repo, "domain-drift", ["GLOSSARY.md"], base=cache_dir)
    assert d.run is False, d
    assert d.report_dir == report_dir


def test_corrupt_cache_record_forces_run(tmp_path):
    """#580: a truncated/corrupt record file must read as "no cached run",
    never crash the sweep — matches the old bash cache.py, whose crashing
    subprocess printed nothing, failed the `= "SKIP"` check, and let the
    audit run."""
    repo, cache_dir = _mkdirs(tmp_path, "repo", "cache_dir")
    _init_git_repo(repo)
    record_path = driver._record_file(repo, cache_dir)
    os.makedirs(os.path.dirname(record_path), exist_ok=True)
    with open(record_path, "w") as f:
        f.write('{"domain-drift": {"last_s')  # truncated mid-write
    d = driver.decide(repo, "domain-drift", ["GLOSSARY.md"], base=cache_dir)
    assert d.run is True, d


def test_legacy_cache_entry_missing_report_dir_forces_run(tmp_path):
    repo, cache_dir = _mkdirs(tmp_path, "repo", "cache_dir")
    _init_git_repo(repo)
    sha = driver.head_sha(repo)
    driver.save_record(driver._record_file(repo, cache_dir), {
        "domain-drift": {
            "last_sha": sha,
            "timestamp": driver._dt.datetime.now(driver._dt.timezone.utc).isoformat(),
            # no "report_dir" — a legacy/incomplete entry
        }
    })
    d = driver.decide(repo, "domain-drift", ["GLOSSARY.md"], base=cache_dir)
    assert d.run is True, d


def test_save_record_is_atomic_no_tmp_left_behind(tmp_path):
    cache_dir = str(tmp_path)
    path = os.path.join(cache_dir, "sub", "record.json")
    driver.save_record(path, {"a": 1})
    assert json.load(open(path)) == {"a": 1}
    assert not os.path.exists(path + ".tmp")


def test_crashed_no_tests_probe_renders_could_not_determine_not_zero(tmp_path):
    """#559: a no-tests probe that crashes or returns garbage must render as
    "could not determine" in the sub-index and the main-index verdict —
    never as a silent zero, which would read as a clean 0%-no-tests repo."""
    tmp = str(tmp_path)
    d = os.path.join(tmp, "collection", "solver.py")
    os.makedirs(d)
    open(os.path.join(d, "report.html"), "w").write("<html>x</html>")
    row = {
        "bucket": "rewrite", "file": "solver.py", "line": 1, "category": "surviving-mutant",
        "summary": "s", "failure": "",
        "extra": {"mutant": "x", "killed": False, "survived": True,
                  "killed_count": 1, "survived_count": 0, "no_coverage_count": 0},
    }
    open(os.path.join(d, "findings.jsonl"), "w").write(json.dumps(row) + "\n")
    # The crash shape driver.mutation_mode now writes instead of a silent
    # {"no_tests": [], "total": 0}.
    open(os.path.join(tmp, "collection", "mutation-no-tests.json"), "w").write(
        json.dumps({"error": "no-tests probe crashed or returned unparseable output"})
    )

    r = _run_driver("index", "--out", tmp)
    assert r.returncode == 0, r.stdout + r.stderr

    index_text = open(os.path.join(tmp, "collection", "index.html")).read()
    assert "could not be determined" in index_text
    assert "0 with no tests" not in index_text

    sub = open(os.path.join(tmp, "collection", "mutation", "index.html")).read()
    assert "could not be determined" in sub


def test_mutation_run_dir_prunes_old_runs_and_makes_worktrees(tmp_path):
    """#606: mutation mode resolves its run folder through the same `RunDir`
    as the sweep, so it inherits the 3-day prune of old `run-*` dirs that it
    used to skip. No `claude` is needed: naming the module skips the prepass,
    and a module with no env manifest fails setup before any audit runs."""
    repo, cache_dir = _mkdirs(tmp_path, "repo", "cache_dir")
    _init_git_repo(repo)
    base = os.path.join(cache_dir, "all-audits")
    stale = os.path.join(base, "run-20200101-000000")
    os.makedirs(stale)
    os.utime(stale, (0, 0))

    r = subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(__file__), "driver.py"), "mutation", repo, "--modules", "solver.py"],
        capture_output=True, text=True,
        env={**os.environ, "XDG_CACHE_HOME": cache_dir, "AUDITS_NO_OPEN": "1", "AUDITS_NO_SYNTH": "1"},
    )
    # A setup failure is a failed module (#1309), so the run exits nonzero.
    assert r.returncode != 0, r.stdout + r.stderr
    assert "[mutation:solver.py] FAILED: no recognized env manifest" in r.stdout, r.stdout
    assert not os.path.exists(stale), "mutation mode must prune run dirs past the TTL"

    runs = [d for d in os.listdir(base) if d.startswith("run-")]
    assert len(runs) == 1, runs
    run_dir = os.path.join(base, runs[0])
    for sub in ("logs", "collection", "manifests", "worktrees"):
        assert os.path.isdir(os.path.join(run_dir, sub)), sub
    assert os.listdir(os.path.join(run_dir, "worktrees")) == [], "the worktree must be cleaned up on the setup-failure path"
    # round 2: the setup-failure page links ../assets/, so mutation mode
    # delivers the shell's assets into the collection like the sweep does.
    failure_page = open(os.path.join(run_dir, "collection", "solver.py", "report.html")).read()
    assert '../assets/base/base.css' in failure_page
    assert os.path.isfile(os.path.join(run_dir, "collection", "assets", "base", "base.css"))


def _fake_tools_env(tmp, **extra_env):
    """An env whose PATH has the fake `claude` and a succeeding `uv`; `tmp`
    holds both the cache and the fake binaries."""
    here = os.path.dirname(os.path.abspath(__file__))
    if not os.path.lexists(os.path.join(tmp, "claude")):
        os.symlink(os.path.join(here, "fake_claude_fixture.sh"), os.path.join(tmp, "claude"))
        with open(os.path.join(tmp, "uv"), "w") as f:
            f.write("#!/bin/sh\nexit 0\n")
        os.chmod(os.path.join(tmp, "uv"), 0o755)
    # The ceiling is dropped from the ambient env, as in `_sweep_with_fake_claude`.
    ambient = {k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS"}
    return {**ambient, "PATH": f"{tmp}:{os.environ['PATH']}", "XDG_CACHE_HOME": tmp,
            "AUDITS_NO_OPEN": "1", "AUDITS_NO_SYNTH": "1", **extra_env}


def _mutation_with_fake_claude(repo, tmp, out, **extra_env):
    """Mutation mode over `solver.py` with the fake `claude` and a `uv` that
    succeeds, so the module reaches its audit. `tmp` holds both the cache and
    the fake binaries."""
    here = os.path.dirname(os.path.abspath(__file__))
    return subprocess.run(
        [sys.executable, os.path.join(here, "driver.py"), "mutation", repo, "--modules", "solver.py", "--out", out],
        capture_output=True, text=True, env=_fake_tools_env(tmp, **extra_env),
    )


def _repo_with_env_manifest(path):
    _init_git_repo(path)
    open(os.path.join(path, "pyproject.toml"), "w").write("[project]\nname = 'x'\n")
    env = driver.scrubbed_env()
    subprocess.run(["git", "-C", path, "add", "."], check=True, env=env)
    subprocess.run(["git", "-C", path, "commit", "-q", "-m", "env"], check=True, env=env)


def test_mutation_audit_that_succeeds_prints_done_and_exits_zero(tmp_path):
    repo, tmp = _mkdirs(tmp_path, "repo", "tmp")
    _repo_with_env_manifest(repo)
    r = _mutation_with_fake_claude(repo, tmp, os.path.join(tmp, "out"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "[mutation:solver.py] done" in r.stdout, r.stdout
    log = open(os.path.join(tmp, "out", "logs", "mutation-solver.py.log")).read()
    assert "ceiling=0" in log, log  # the mutation audit gets claude_env's wait ceiling too (#1278)


def test_mutation_audit_exiting_nonzero_fails_the_run_even_with_a_manifest(tmp_path):
    """#1309, the sweep's #1278 rule in mutation mode: a nonzero `claude`
    exit is a failure line and a nonzero exit, never `done`."""
    repo, tmp = _mkdirs(tmp_path, "repo", "tmp")
    _repo_with_env_manifest(repo)
    r = _mutation_with_fake_claude(repo, tmp, os.path.join(tmp, "out"), FAKE_CLAUDE_EXIT_MUTATION="3")
    assert r.returncode != 0, r.stdout + r.stderr
    assert "[mutation:solver.py] FAILED: exit 3" in r.stdout, r.stdout
    assert "[mutation:solver.py] done" not in r.stdout, r.stdout


def test_mutation_stale_manifest_from_an_earlier_run_does_not_count_as_success(tmp_path):
    repo, tmp = _mkdirs(tmp_path, "repo", "tmp")
    _repo_with_env_manifest(repo)
    out = os.path.join(tmp, "out")
    first = _mutation_with_fake_claude(repo, tmp, out)
    assert first.returncode == 0, first.stdout + first.stderr
    again = _mutation_with_fake_claude(repo, tmp, out, FAKE_CLAUDE_NOOP="1")
    assert again.returncode != 0, again.stdout + again.stderr
    assert "[mutation:solver.py] FAILED: no manifest" in again.stdout, again.stdout


def _seed_run_dir(tmp, worktrees=False):
    run = driver.RunDir(
        root=tmp,
        logs=os.path.join(tmp, "logs"),
        collection=os.path.join(tmp, "collection"),
        manifests=os.path.join(tmp, "manifests"),
        worktrees=os.path.join(tmp, "worktrees") if worktrees else "",
    )
    for d in (run.logs, run.collection, run.manifests, run.worktrees):
        if d:
            os.makedirs(d, exist_ok=True)
    return run


def test_plan_reuses_the_cached_report_and_runs_the_rest(tmp_path):
    """#606: the plan step decides alone — cache in, lists out. No audit
    process is spawned, so it needs a tmp dir and no fake `claude`."""
    repo, cache_dir = _mkdirs(tmp_path, "repo", "cache_dir")
    _init_git_repo(repo)
    report_dir = os.path.join(cache_dir, "domain-drift-report")
    os.makedirs(report_dir)
    driver.save_record(driver._record_file(repo, cache_dir), {
        "domain-drift": {
            "last_sha": driver.head_sha(repo),
            "timestamp": driver._dt.datetime.now(driver._dt.timezone.utc).isoformat(),
            "report_dir": report_dir,
        }
    })

    plan = driver.plan_sweep(repo, ["domain-drift", "dead-code"], force=False, base=cache_dir)
    assert plan.to_run == ["dead-code"], plan
    assert plan.reused == {"domain-drift": report_dir}, plan
    assert plan.skip_note["domain-drift"].startswith("unchanged since"), plan

    forced = driver.plan_sweep(repo, ["domain-drift", "dead-code"], force=True, base=cache_dir)
    assert forced.to_run == ["domain-drift", "dead-code"], forced
    assert forced.reused == {} and forced.skip_note == {}, forced


def test_collect_copies_both_report_kinds_and_returns_the_index(tmp_path):
    """#606: the collect step assembles the collection from what is already
    on disk — a manifest for what ran, the cache dir for what was reused —
    and renders. Also needs only a tmp dir and no fake `claude`."""
    tmp, srcdir = _mkdirs(tmp_path, "tmp", "srcdir")
    run = _seed_run_dir(tmp)
    ran = os.path.join(srcdir, "ran")
    os.makedirs(ran)
    open(os.path.join(ran, "report.html"), "w").write("<html>dead-code</html>")
    manifest = driver.manifest_path_for(run.manifests, "dead-code")
    os.makedirs(os.path.dirname(manifest))
    json.dump({"report_path": os.path.join(ran, "report.html"), "count": 1, "headline": "h"}, open(manifest, "w"))

    cached = os.path.join(srcdir, "cached")
    os.makedirs(cached)
    open(os.path.join(cached, "report.html"), "w").write("<html>domain-drift</html>")

    plan = driver.Plan(
        to_run=["dead-code", "duplication"],
        reused={"domain-drift": cached},
        skip_note={"domain-drift": "unchanged since abcd1234"},
    )
    index = driver.collect(run, "/some/repo", plan, base=os.path.join(tmp, "cache"))

    assert index == os.path.join(run.collection, "index.html")
    assert os.path.isfile(os.path.join(run.collection, "dead-code", "report.html"))
    assert os.path.isfile(os.path.join(run.collection, "domain-drift", "report.html"))
    text = open(index).read()
    assert 'href="dead-code/report.html"' in text
    assert 'href="domain-drift/report.html"' in text
    assert "unchanged since abcd1234" in text
    assert "no manifest" in text, "duplication ran and wrote no manifest — a named failure row"


def test_index_only_rebuild_spawns_nothing_and_needs_no_run_branch(tmp_path):
    """#606: `index --out DIR` calls the collect step over an existing
    collection. Nothing is spawned — the PATH here holds no `claude` and no
    `git` — and no logs/ or manifests/ content is read."""
    tmp, empty_bin = _mkdirs(tmp_path, "tmp", "empty_bin")
    d = os.path.join(tmp, "collection", "dead-code")
    os.makedirs(d)
    open(os.path.join(d, "report.html"), "w").write("<html>x</html>")

    r = subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(__file__), "driver.py"), "index", "--out", tmp],
        capture_output=True, text=True,
        env={**os.environ, "PATH": empty_bin, "AUDITS_NO_OPEN": "1", "AUDITS_NO_SYNTH": "1"},
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert 'href="dead-code/report.html"' in open(os.path.join(tmp, "collection", "index.html")).read()
    assert os.listdir(os.path.join(tmp, "manifests")) == []
    assert os.listdir(os.path.join(tmp, "logs")) == []


def _main_exit(argv, capsys):
    """`driver.main` on `argv`, which must exit through argparse: (code, stdout, stderr)."""
    with pytest.raises(SystemExit) as e:
        driver.main(["driver.py", *argv])
    out = capsys.readouterr()
    return e.value.code, out.out, out.err


MODE_FLAGS = {
    "sweep": ("--out", "--only", "--short", "--force"),
    "index": ("--out",),
    "multi": ("--out", "--only", "--short", "--force"),
    "multi-index": (),
    "load": (),
    "suggest": ("--roots",),
    "mutation": ("--out", "--modules", "--all"),
}
EVERY_FLAG = sorted({f for flags in MODE_FLAGS.values() for f in flags})


def test_top_level_help_prints_the_docstring_and_names_every_mode(capsys):
    """#606, #1747: the module docstring is the help text, so the reference has
    one home, and the modes are subcommands it lists."""
    code, out, _ = _main_exit(["--help"], capsys)
    assert code == 0 and out.startswith("usage:"), out
    assert driver.__doc__.splitlines()[0] in out and "SWEEP_JOBS" in out
    for mode in MODE_FLAGS:
        assert mode in out, mode


@pytest.mark.parametrize("mode", sorted(MODE_FLAGS))
def test_each_mode_help_lists_its_own_flags_and_no_other(mode, capsys):
    """#1747: a mode's `--help` names exactly the flags it takes."""
    code, out, _ = _main_exit([mode, "--help"], capsys)
    assert code == 0, out
    for flag in EVERY_FLAG:
        assert (re.search(rf"(?<![\w-]){flag}(?![\w-])", out) is not None) == (flag in MODE_FLAGS[mode]), (mode, flag, out)


@pytest.mark.parametrize("argv, refusal", [
    ([], "required"),
    (["--nope"], "required: MODE"),
    (["nope"], "invalid choice"),
    (["load", "42", "--force"], "unrecognized arguments: --force"),
    (["load", "42", "--only", "dead-code"], "unrecognized arguments: --only"),
    (["suggest", "--short"], "unrecognized arguments: --short"),
    (["multi-index", "20990101-000000", "--force"], "unrecognized arguments: --force"),
    (["multi-index", "20990101-000000", "--roots", "/x"], "unrecognized arguments: --roots"),
    (["index", "--out", "/x", "--only", "dead-code"], "unrecognized arguments: --only"),
    (["index"], "--out"),
    (["sweep", "--roots", "/x"], "unrecognized arguments: --roots"),
    (["sweep", "--modules", "a.py"], "unrecognized arguments: --modules"),
    (["multi", "a", "--all"], "unrecognized arguments: --all"),
    (["multi"], "REPO"),
    (["mutation", "--all", "--modules", "a.py"], "not allowed with"),
    (["mutation", "--only", "dead-code"], "unrecognized arguments: --only"),
    (["mutation", "--modules", ""], "names no module"),
    (["mutation", "--modules", " , "], "names no module"),
    (["load", "x"], "invalid int value"),
])
def test_each_mode_refuses_a_flag_it_does_not_take_through_argparse(argv, refusal, capsys, monkeypatch):
    """#1747: argparse, not a hand-written exclusion chain, refuses the flag,
    exit 2, before any mode starts. Every mode entry is replaced with one that
    fails the test, so a refusal that came late cannot pass."""
    for entry in ("sweep", "rebuild_index", "multi_mode", "multi_index_mode", "load_mode", "suggest_mode",
                  "mutation_mode"):
        monkeypatch.setattr(driver, entry, lambda *a, _e=entry, **k: pytest.fail(f"{_e} ran on {argv}"))
    code, _, err = _main_exit(argv, capsys)
    assert code == 2 and refusal in err, err


@pytest.mark.parametrize("argv, entry, call", [
    (["sweep", "/r", "--only", "a,b", "--short", "--force", "--out", "/o"], "sweep",
     (("/r", "/o", ["a", "b"], True, True), {})),
    (["sweep"], "sweep", ((os.getcwd(), None, None, False, False), {})),
    (["index", "/r", "--out", "/o"], "rebuild_index", (("/r", "/o"), {})),
    (["multi", "/a", "/b", "--only", "x", "--force"], "multi_mode",
     ((["/a", "/b"], None, ["x"], False, True), {})),
    (["multi-index", "20990101-000000"], "multi_index_mode", (("20990101-000000",), {})),
    (["load", "42", "skills"], "load_mode", ((42, "skills"), {})),
    (["load", "42"], "load_mode", ((42, None), {})),
    (["suggest", "--roots", "/a,/b"], "suggest_mode", ((["/a", "/b"],), {})),
    (["suggest"], "suggest_mode", (([driver.DEFAULT_ROOTS.split(",")[0], driver.DEFAULT_ROOTS.split(",")[1]],), {})),
    (["mutation", "/r", "--modules", "a.py,b.py", "--out", "/o"], "mutation_mode",
     (("/r", ["a.py", "b.py"], "/o"), {"whole_repo": False})),
    (["mutation", "/r"], "mutation_mode", (("/r", None, None), {"whole_repo": False})),
    (["mutation", "/r", "--all"], "mutation_mode", (("/r", None, None), {"whole_repo": True})),
])
def test_each_mode_calls_its_entry_with_its_own_arguments(argv, entry, call, monkeypatch):
    """#1747: `main(argv)` routes each subcommand to its mode with the values
    its flags were given, and nothing else."""
    calls = []
    monkeypatch.setattr(driver, entry, lambda *a, **k: calls.append((a, k)))
    driver.main(["driver.py", *argv])
    assert calls == [call]


@pytest.mark.parametrize("audit, record, state, run, reason", [
    ({}, None, {"dirty": False, "changed_files": []}, True, "no cached run"),
    ({}, {"age_days": 0}, {"dirty": True, "changed_files": []}, True, "dirty working tree"),
    ({"ground_truth": ["skills/"]}, {"age_days": 0}, {"dirty": False, "changed_files": ["skills/a.md"]},
     True, "ground-truth change: skills/a.md"),
    ({"ground_truth": ["GLOSSARY.md"]}, {"age_days": 0}, {"dirty": False, "changed_files": ["GLOSSARY.md"]},
     True, "ground-truth change: GLOSSARY.md"),
    ({"ground_truth": ["skills"]}, {"age_days": 0}, {"dirty": False, "changed_files": ["skillset/a.md"]},
     False, "unchanged: 1 files < threshold 10, clean, within backstop"),
    ({"backstop_days": 7}, {"age_days": 7.5}, {"dirty": False, "changed_files": []},
     True, "last run older than backstop (7.5d > 7d)"),
    ({"backstop_days": 7}, {"age_days": 7}, {"dirty": False, "changed_files": []},
     False, "unchanged: 0 files < threshold 10, clean, within backstop"),
    ({}, {"age_days": driver.DEFAULT_BACKSTOP_DAYS + 1}, {"dirty": False, "changed_files": []},
     True, f"last run older than backstop ({driver.DEFAULT_BACKSTOP_DAYS + 1}d > {driver.DEFAULT_BACKSTOP_DAYS}d)"),
    ({"threshold": 2}, {"age_days": 0}, {"dirty": False, "changed_files": ["a", "b"]},
     True, "2 files changed >= threshold 2"),
    ({"threshold": 3}, {"age_days": 0}, {"dirty": False, "changed_files": ["a", "b"]},
     False, "unchanged: 2 files < threshold 3, clean, within backstop"),
    ({}, {"age_days": 0}, {"dirty": False, "changed_files": [str(i) for i in range(driver.DEFAULT_THRESHOLD)]},
     True, f"{driver.DEFAULT_THRESHOLD} files changed >= threshold {driver.DEFAULT_THRESHOLD}"),
])
def test_should_run(audit, record, state, run, reason):
    """#1729: the staleness rule, in its order: no record, a dirty tree, a
    ground-truth path (a prefix only at a `/`), the backstop, the threshold."""
    assert driver.should_run(audit, record, state) == (run, reason)


def test_report_headings_reads_the_first_html_of_the_audit_folder(tmp_path):
    """#1729: the headings come from the audit's first HTML by name; a folder
    with none, or no folder, gives []."""
    collection = str(tmp_path)
    assert driver._report_headings(collection, "dead-code") == []
    os.makedirs(os.path.join(collection, "dead-code"))
    open(os.path.join(collection, "dead-code", "notes.txt"), "w").write("<h1>not html</h1>")
    assert driver._report_headings(collection, "dead-code") == []
    open(os.path.join(collection, "dead-code", "b.html"), "w").write("<h1>Second</h1>")
    open(os.path.join(collection, "dead-code", "a.html"), "w").write(
        "<h1> Dead  code </h1><p>body</p><h2></h2><h3>Kept <em>here</em></h3><h4>Too deep</h4>")
    assert driver._report_headings(collection, "dead-code") == ["Dead code", "Kept here"]


def test_mutation_worktree_is_removed_even_when_the_failure_report_raises(tmp_path):
    """#606: worktree cleanup is one try/finally per worktree. Before it, an
    exception between `git worktree add` and the explicit cleanup call left
    the worktree registered and on disk; here the failure-report write is made
    to fail (a regular file where the collection should be) and the worktree must still be gone."""
    repo, tmp = _mkdirs(tmp_path, "repo", "tmp")
    _init_git_repo(repo)
    run = _seed_run_dir(tmp, worktrees=True)
    # The module has no env manifest, so the driver writes a setup-failure report
    # into the collection. A regular file in its place makes that write fail for
    # root too, where a chmod would be ignored.
    shutil.rmtree(run.collection)
    open(run.collection, "w").close()
    try:
        driver._run_mutation_module(repo, "solver.py", run)
    except OSError:
        pass
    assert os.listdir(run.worktrees) == [], "the worktree must be removed on every exit path"


def test_domain_drift_is_gated_on_the_glossary_file():
    assert "GLOSSARY.md" in driver.GATED["domain-drift"], driver.GATED["domain-drift"]
    assert "CONTEXT.md" not in driver.GATED["domain-drift"], driver.GATED["domain-drift"]


# --- mutation target ordering (#1567) -----------------------------------------

def _rec(sha, date):
    return {"sha": sha, "date": date}


def test_record_mutation_sits_beside_audit_records(tmp_path):
    repo, cache = _mkdirs(tmp_path, "repo", "cache")
    _init_git_repo(repo)
    driver.update_cache(repo, "dead-code", "/r", base=cache)
    driver.record_mutation(repo, "a.py", base=cache)
    rec = driver.load_record(driver._record_file(repo, cache))
    assert rec["dead-code"]["report_dir"] == "/r"
    assert rec[mutation_run.MUTATION_KEY]["a.py"]["sha"] == driver.head_sha(repo)
    assert rec[mutation_run.MUTATION_KEY]["a.py"]["date"]


def _commit_all(repo, msg):
    env = driver.scrubbed_env()
    subprocess.run(["git", "-C", repo, "add", "."], check=True, env=env)
    subprocess.run(["git", "-C", repo, "commit", "-q", "-m", msg], check=True, env=env)


def _mutation_repo(path, modules):
    _init_git_repo(path)
    open(os.path.join(path, "pyproject.toml"), "w").write("[project]\nname = 'x'\n")
    for m in modules:
        open(os.path.join(path, m), "w").write("x = 1\n")
        open(os.path.join(path, f"test_{m}"), "w").write("def test_x(): pass\n")
    _commit_all(path, "mods")


def _mutation_no_modules(repo, tmp, **extra_env):
    """`mutation` with neither `--modules` nor `--all` over a repo, fake claude and uv on PATH."""
    here = os.path.dirname(os.path.abspath(__file__))
    return subprocess.run(
        [sys.executable, os.path.join(here, "driver.py"), "mutation", repo, "--out", os.path.join(tmp, "out")],
        capture_output=True, text=True, env=_fake_tools_env(tmp, **extra_env))


def _cache_record(repo, tmp):
    return driver.load_record(driver._record_file(repo, os.path.join(tmp, "all-audits")))


def test_mutation_without_a_value_runs_the_mechanical_list_unranked_and_records(tmp_path):
    """AUDITS_NO_SYNTH=1 skips the prepass; the candidate list is mechanical,
    so the run still has targets, and each finished module is recorded."""
    repo, tmp = _mkdirs(tmp_path, "repo", "tmp")
    _mutation_repo(repo, ["m.py", "n.py"])
    r = _mutation_no_modules(repo, tmp)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "mutation-target: m.py" in r.stdout and "mutation-target: n.py" in r.stdout, r.stdout
    rec = _cache_record(repo, tmp)
    assert sorted(rec[mutation_run.MUTATION_KEY]) == ["m.py", "n.py"], rec


def test_mutation_prepass_ranks_but_never_adds_and_never_run_goes_first(tmp_path):
    repo, tmp = _mkdirs(tmp_path, "repo", "tmp")
    _mutation_repo(repo, ["m.py", "n.py", "o.py"])
    driver.save_record(driver._record_file(repo, os.path.join(tmp, "all-audits")), {mutation_run.MUTATION_KEY: {
        "o.py": _rec(driver.head_sha(repo), "2026-10-01T00:00:00+00:00")}})
    r = _mutation_no_modules(repo, tmp, AUDITS_NO_SYNTH="0", MUTATION_MAX="2",
                             FAKE_CLAUDE_PREPASS="o.py\nghost.py\nn.py\nm.py")
    assert r.returncode == 0, r.stdout + r.stderr
    targets = [ln for ln in r.stdout.splitlines() if ln.startswith("mutation-target:")]
    # o.py is top-ranked but already ran and is unchanged: pushed behind
    # the never-run n.py and m.py.
    assert targets == ["mutation-target: n.py", "mutation-target: m.py"], r.stdout
    assert "1 more modules skipped" in r.stdout, r.stdout


def test_explicit_mutation_run_records_too(tmp_path):
    repo, tmp = _mkdirs(tmp_path, "repo", "tmp")
    _repo_with_env_manifest(repo)
    r = _mutation_with_fake_claude(repo, tmp, os.path.join(tmp, "out"))
    assert r.returncode == 0, r.stdout + r.stderr
    rec = _cache_record(repo, tmp)
    assert rec[mutation_run.MUTATION_KEY]["solver.py"]["sha"] == driver.head_sha(repo)
    # a dotted spelling of the same module is the same key, never a second one
    again = subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "driver.py"), "mutation", repo,
         "--modules", "./solver.py", "--out", os.path.join(tmp, "out2")],
        capture_output=True, text=True, env=_fake_tools_env(tmp))
    assert again.returncode == 0, again.stdout + again.stderr
    assert list(_cache_record(repo, tmp)[mutation_run.MUTATION_KEY]) == ["solver.py"]


def test_failed_module_is_not_recorded(tmp_path):
    repo, tmp = _mkdirs(tmp_path, "repo", "tmp")
    _repo_with_env_manifest(repo)
    r = _mutation_with_fake_claude(repo, tmp, os.path.join(tmp, "out"), FAKE_CLAUDE_EXIT_MUTATION="3")
    assert r.returncode != 0
    rec = _cache_record(repo, tmp)
    assert "solver.py" not in rec.get(mutation_run.MUTATION_KEY, {}), rec


def test_prepass_prompt_names_the_candidates_and_drops_solver_oracle(tmp_path):
    p = driver.mutation_prepass_prompt("/r", ["a.py", "b.py"])
    assert "a.py" in p and "b.py" in p
    assert "solver" not in p and "oracle" not in p
    assert "wrong result" in p


def test_record_mutation_keys_a_dotted_path_as_the_repo_relative_one(tmp_path):
    repo, cache = _mkdirs(tmp_path, "repo", "cache")
    _init_git_repo(repo)
    driver.record_mutation(repo, "./a.py", base=cache)
    assert list(driver.load_record(driver._record_file(repo, cache))[mutation_run.MUTATION_KEY]) == ["a.py"]


def test_changed_module_runs_first_and_max_cuts_after_ordering(tmp_path):
    """Through the real run: o.py is the newest run and alphabetically last,
    but changed since its sha, so it leads; MUTATION_MAX=1 keeps only it."""
    repo, tmp = _mkdirs(tmp_path, "repo", "tmp")
    _mutation_repo(repo, ["m.py", "n.py", "o.py"])
    before = driver.head_sha(repo)
    open(os.path.join(repo, "o.py"), "w").write("x = 2\n")
    _commit_all(repo, "o changes")
    now = driver.head_sha(repo)
    driver.save_record(driver._record_file(repo, os.path.join(tmp, "all-audits")), {mutation_run.MUTATION_KEY: {
        "m.py": _rec(now, "2026-10-01T00:00:00+00:00"),
        "n.py": _rec(now, "2026-09-01T00:00:00+00:00"),
        "o.py": _rec(before, "2026-10-05T00:00:00+00:00")}})
    r = _mutation_no_modules(repo, tmp, MUTATION_MAX="1")
    assert r.returncode == 0, r.stdout + r.stderr
    targets = [ln for ln in r.stdout.splitlines() if ln.startswith("mutation-target:")]
    assert targets == ["mutation-target: o.py"], r.stdout


def test_a_failed_plan_fails_the_run_not_an_empty_target_list(tmp_path, monkeypatch, capsys):
    repo, tmp = _mkdirs(tmp_path, "repo", "tmp")
    _mutation_repo(repo, ["m.py"])
    monkeypatch.setenv("XDG_CACHE_HOME", tmp)

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(driver.mutation_run, "run", boom)
    with pytest.raises(SystemExit) as e:
        driver.mutation_mode(repo, None, os.path.join(tmp, "out"))
    assert e.value.code == 1
    err = capsys.readouterr()
    assert "mutation-target probe failed" in err.err and "boom" in err.err, err.err
    assert "mutation-target:" not in err.out


def test_a_failed_prepass_is_named_and_the_run_orders_by_recency_alone(tmp_path):
    repo, tmp = _mkdirs(tmp_path, "repo", "tmp")
    _mutation_repo(repo, ["m.py"])
    r = _mutation_no_modules(repo, tmp, AUDITS_NO_SYNTH="0", FAKE_CLAUDE_PREPASS="m.py", FAKE_CLAUDE_PREPASS_EXIT="1")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "mutation prepass gave no ranking (exit 1)" in r.stderr, r.stderr
    assert "mutation-target: m.py" in r.stdout


def test_mutation_estimate_names_count_jobs_and_worst_case():
    """#1588: the whole-repo run prints the module count and a cost estimate
    before it starts. A module is at most two bounded commands (mutmut run and
    results) and `jobs` modules overlap."""
    line = driver.mutation_cost_estimate(4, jobs=2, timeout_s=3600)
    assert "4 modules" in line and "2 at a time" in line and "up to 4h" in line, line
    assert "1 module to" in driver.mutation_cost_estimate(1, timeout_s=3600)
    assert "up to 0.5h" in driver.mutation_cost_estimate(1, timeout_s=900.0)


def test_mutation_estimate_reads_a_decimal_timeout_like_audit_py(monkeypatch):
    monkeypatch.setenv("MUTATION_AUDIT_TIMEOUT", "90.5")
    assert "90.5s per module" in driver.mutation_cost_estimate(1)


def _repo_with_two_tested_modules(path):
    _init_git_repo(path)
    open(os.path.join(path, "pyproject.toml"), "w").write("[project]\nname = 'x'\n")
    for stem in ("alpha", "beta"):
        open(os.path.join(path, f"{stem}.py"), "w").write("def f():\n    return 1\n")
        open(os.path.join(path, f"{stem}_test.py"), "w").write(f"import {stem}\n\ndef test_f():\n    assert {stem}.f() == 1\n")
    env = driver.scrubbed_env()
    subprocess.run(["git", "-C", path, "add", "."], check=True, env=env)
    subprocess.run(["git", "-C", path, "commit", "-q", "-m", "mods"], check=True, env=env)


def _mutation_all(repo, tmp, out, *flags, **extra_env):
    here = os.path.dirname(os.path.abspath(__file__))
    return subprocess.run(
        [sys.executable, os.path.join(here, "driver.py"), "mutation", repo, "--all", "--out", out, *flags],
        capture_output=True, text=True, env=_fake_tools_env(tmp, **extra_env),
    )


def _recorded_mutation_modules(repo, tmp):
    os.environ["XDG_CACHE_HOME"], old = tmp, os.environ.get("XDG_CACHE_HOME")
    try:
        return set(mutation_run.recorded_runs(driver.load_record(driver._record_file(repo))))
    finally:
        if old is None:
            del os.environ["XDG_CACHE_HOME"]
        else:
            os.environ["XDG_CACHE_HOME"] = old


def test_mutation_all_runs_every_candidate_past_the_cap_and_prints_the_estimate_once(tmp_path):
    repo, tmp = _mkdirs(tmp_path, "repo", "tmp")
    _repo_with_two_tested_modules(repo)
    r = _mutation_all(repo, tmp, os.path.join(tmp, "out"), MUTATION_MAX="1")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "2 modules" in r.stdout and "skipped" not in r.stdout, r.stdout
    assert "[mutation:alpha.py] done" in r.stdout and "[mutation:beta.py] done" in r.stdout, r.stdout
    # The repo's own untested a.py makes the no-test filter fire: still one line.
    assert r.stdout.count("mutation-all:") == 1, r.stdout
    assert r.stdout.index("mutation-all:") < r.stdout.index("creating worktree"), r.stdout
    assert _recorded_mutation_modules(repo, tmp) == {"alpha.py", "beta.py"}


def test_mutation_all_skips_the_model_prepass_and_runs_in_recency_order(tmp_path):
    """A prepass ranking beta first would put it first among the never-run
    modules; whole-repo mode has no prepass, so alpha leads."""
    repo, tmp = _mkdirs(tmp_path, "repo", "tmp")
    _repo_with_two_tested_modules(repo)
    r = _mutation_all(repo, tmp, os.path.join(tmp, "out"), AUDITS_NO_SYNTH="0", FAKE_CLAUDE_PREPASS="beta.py\nalpha.py")
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.index("mutation-target: alpha.py") < r.stdout.index("mutation-target: beta.py"), r.stdout


def test_mutation_all_lists_an_inconclusive_module_in_the_report_never_as_clean(tmp_path):
    repo, tmp = _mkdirs(tmp_path, "repo", "tmp")
    _repo_with_two_tested_modules(repo)
    out = os.path.join(tmp, "out")
    why = "mutmut run failed (exit 1)"
    r = _mutation_all(repo, tmp, out, FAKE_CLAUDE_INCONCLUSIVE=why)
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"INCONCLUSIVE: {why}" in r.stdout, r.stdout
    assert _recorded_mutation_modules(repo, tmp) == set(), "an INCONCLUSIVE module measured nothing and is not recorded"
    idx = _run_driver("index", "--out", out)
    assert idx.returncode == 0, idx.stdout + idx.stderr
    sub = open(os.path.join(out, "collection", "mutation", "index.html")).read()
    for module in ("alpha.py", "beta.py"):
        assert f"<td>{module}</td><td>INCONCLUSIVE: {why}</td><td>—</td><td>—</td>" in sub, sub
    assert "2 of 2 modules INCONCLUSIVE" in sub, sub
    top = open(os.path.join(out, "collection", "index.html")).read()
    assert "0 modules measured" in top and "2 INCONCLUSIVE" in top, top


def test_mutation_all_prompt_asks_for_the_findings_log_and_the_inconclusive_key(tmp_path):
    repo, tmp = _mkdirs(tmp_path, "repo", "tmp")
    _repo_with_two_tested_modules(repo)
    r = _mutation_all(repo, tmp, os.path.join(tmp, "out"))
    assert r.returncode == 0, r.stdout + r.stderr
    log = open(os.path.join(tmp, "out", "logs", "mutation-alpha.py.log")).read()
    assert '"inconclusive" key' in log and "findings.jsonl" in log and "still write the report" in log, log


def test_sweep_prompt_carries_the_shared_no_open_instruction():
    assert driver.NO_OPEN_INSTRUCTION in driver.audit_prompt("dead-code", "/some/repo")


def test_mutation_module_prompt_forbids_opening_its_report(tmp_path):
    repo, tmp = _mkdirs(tmp_path, "repo", "tmp")
    _repo_with_two_tested_modules(repo)
    r = _mutation_all(repo, tmp, os.path.join(tmp, "out"))
    assert r.returncode == 0, r.stdout + r.stderr
    log = open(os.path.join(tmp, "out", "logs", "mutation-alpha.py.log")).read()
    assert driver.NO_OPEN_INSTRUCTION in log, log


def _fake_openers(tmp):
    """`xdg-open` and `open` stubs in `tmp` (first on the fake-tools PATH) that
    append their argument to `opened.txt`; returns its path."""
    opened = os.path.join(tmp, "opened.txt")
    for opener in ("xdg-open", "open"):
        with open(os.path.join(tmp, opener), "w") as f:
            f.write(f'#!/bin/sh\necho "$1" >> {opened}\n')
        os.chmod(os.path.join(tmp, opener), 0o755)
    return opened


def _pages_opened(opened):
    return open(opened).read().split() if os.path.exists(opened) else []


def test_mutation_run_opens_one_page_and_it_is_the_index(tmp_path):
    repo, tmp = _mkdirs(tmp_path, "repo", "tmp")
    _repo_with_two_tested_modules(repo)
    opened = _fake_openers(tmp)
    out = os.path.join(tmp, "out")
    r = _mutation_all(repo, tmp, out, AUDITS_NO_OPEN="0")
    assert r.returncode == 0, r.stdout + r.stderr
    index = os.path.join(out, "collection", "mutation", "index.html")
    assert _pages_opened(opened) == [index]
    assert f"index: {index}" in r.stdout, r.stdout


def test_mutation_run_with_no_module_to_mutate_still_opens_the_index(tmp_path):
    """Every target filtered out as testless: no module runs, but the no-tests
    page exists and is the one page opened."""
    repo, tmp = _mkdirs(tmp_path, "repo", "tmp")
    _repo_with_env_manifest(repo)
    open(os.path.join(repo, "solver.py"), "w").write("def f():\n    return 1\n")
    env = driver.scrubbed_env()
    subprocess.run(["git", "-C", repo, "add", "."], check=True, env=env)
    subprocess.run(["git", "-C", repo, "commit", "-q", "-m", "solver"], check=True, env=env)
    opened = _fake_openers(tmp)
    out = os.path.join(tmp, "out")
    r = _mutation_with_fake_claude(repo, tmp, out, AUDITS_NO_OPEN="0")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "[mutation:solver.py] done" not in r.stdout, r.stdout
    assert _pages_opened(opened) == [os.path.join(out, "collection", "mutation", "index.html")], r.stdout


def test_mutation_run_does_not_rebuild_the_top_index_of_a_sweep_in_out(tmp_path):
    repo, tmp = _mkdirs(tmp_path, "repo", "tmp")
    _repo_with_two_tested_modules(repo)
    out = os.path.join(tmp, "out")
    top = os.path.join(out, "collection", "index.html")
    os.makedirs(os.path.dirname(top))
    open(top, "w").write("sweep index")
    r = _mutation_all(repo, tmp, out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert open(top).read() == "sweep index"


def test_mutation_module_answering_neither_findings_nor_inconclusive_is_a_failure(tmp_path):
    """A manifest with no `inconclusive` key and no findings.jsonl is no answer:
    a failure line, never a clean module that went unrecorded."""
    repo, tmp = _mkdirs(tmp_path, "repo", "tmp")
    _repo_with_two_tested_modules(repo)
    r = _mutation_all(repo, tmp, os.path.join(tmp, "out"), FAKE_CLAUDE_NO_FINDINGS_LOG="1")
    assert r.returncode != 0, r.stdout + r.stderr
    assert "FAILED: manifest has no `inconclusive` key and the report has no findings.jsonl" in r.stdout, r.stdout
    assert _recorded_mutation_modules(repo, tmp) == set()


def test_mutation_all_stale_inconclusive_from_an_earlier_run_does_not_label_a_failure(tmp_path):
    repo, tmp = _mkdirs(tmp_path, "repo", "tmp")
    _repo_with_two_tested_modules(repo)
    out = os.path.join(tmp, "out")
    assert _mutation_all(repo, tmp, out, FAKE_CLAUDE_INCONCLUSIVE="OLD REASON").returncode == 0
    again = _mutation_all(repo, tmp, out, FAKE_CLAUDE_NOOP="1")
    assert again.returncode != 0, again.stdout + again.stderr
    _run_driver("index", "--out", out)
    sub = open(os.path.join(out, "collection", "mutation", "index.html")).read()
    assert "OLD REASON" not in sub, sub


def test_mutation_modules_run_at_once_up_to_mutation_jobs(tmp_path):
    """#1588: two modules in flight together under MUTATION_JOBS=2, one at a
    time under MUTATION_JOBS=1. The fake audit waits for another to start."""
    repo, tmp = _mkdirs(tmp_path, "repo", "tmp")
    _repo_with_two_tested_modules(repo)
    for jobs, overlapped in (("2", True), ("1", False)):
        rv = os.path.join(tmp, f"rv{jobs}")
        os.mkdir(rv)
        r = _mutation_all(repo, tmp, os.path.join(tmp, f"out{jobs}"), MUTATION_JOBS=jobs, FAKE_CLAUDE_RENDEZVOUS=rv)
        assert r.returncode == 0, r.stdout + r.stderr
        assert os.path.exists(os.path.join(rv, "overlap")) is overlapped, (jobs, r.stdout)
        assert f"{jobs} at a time" in r.stdout, r.stdout
        for module in ("alpha.py", "beta.py"):
            assert f"[mutation:{module}] done" in r.stdout


def test_parallel_modules_keep_one_log_each_and_a_failed_one_is_listed(tmp_path):
    repo, tmp = _mkdirs(tmp_path, "repo", "tmp")
    _repo_with_two_tested_modules(repo)
    r = _mutation_all(repo, tmp, os.path.join(tmp, "out"), MUTATION_JOBS="2", FAKE_CLAUDE_EXIT_MUTATION="3")
    assert r.returncode != 0, r.stdout + r.stderr
    assert "FAILED modules: alpha.py, beta.py" in r.stderr, r.stderr
    for module in ("alpha.py", "beta.py"):
        log = open(os.path.join(tmp, "out", "logs", f"mutation-{module}.log")).read()
        assert f"/mutation-audit {module}" in log and f"/mutation-audit {'beta.py' if module == 'alpha.py' else 'alpha.py'}" not in log
    assert _recorded_mutation_modules(repo, tmp) == set()


def test_mutation_jobs_must_be_a_positive_integer(tmp_path):
    repo, tmp = _mkdirs(tmp_path, "repo", "tmp")
    _repo_with_two_tested_modules(repo)
    for bad in ("0", "many"):
        r = _mutation_all(repo, tmp, os.path.join(tmp, "out"), MUTATION_JOBS=bad)
        assert r.returncode == 2 and "MUTATION_JOBS must be a positive integer" in r.stderr, r.stdout + r.stderr
        assert "creating worktree" not in r.stdout


# --- --multi (#1679) -----------------------------------------------------------

def _multi_fixture(tmp, names):
    """Local clones named `names`, each with a bare `origin` holding `main`;
    returns (repo paths, env with the fake claude and fake gh on PATH)."""
    here = os.path.dirname(os.path.abspath(__file__))
    bindir = os.path.join(tmp, "bin")
    os.makedirs(bindir)
    os.symlink(os.path.join(here, "fake_claude_fixture.sh"), os.path.join(bindir, "claude"))
    os.symlink(os.path.join(here, "fake_gh_fixture.sh"), os.path.join(bindir, "gh"))
    genv = driver.scrubbed_env()
    repos = []
    for name in names:
        bare, repo = os.path.join(tmp, "bare-" + name), os.path.join(tmp, name)
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", bare], check=True, env=genv)
        os.mkdir(repo)
        _init_git_repo(repo)
        subprocess.run(["git", "-C", repo, "branch", "-M", "main"], check=True, env=genv)
        subprocess.run(["git", "-C", repo, "remote", "add", "origin", bare], check=True, env=genv)
        subprocess.run(["git", "-C", repo, "push", "-q", "origin", "main"], check=True, env=genv)
        repos.append(repo)
    ambient = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS", "SWEEP_JOBS")}
    env = {**ambient, "PATH": f"{bindir}:{os.environ['PATH']}", "XDG_CACHE_HOME": os.path.join(tmp, "cache"),
           "XDG_DATA_HOME": os.path.join(tmp, "data"), "AUDITS_NO_OPEN": "1", "AUDITS_NO_SYNTH": "1",
           "FAKE_GH_LOG": os.path.join(tmp, "gh.log"), "FAKE_CLAUDE_STARTS": os.path.join(tmp, "starts.log")}
    return repos, env


def _multi(repos, env, *args, **extra_env):
    return subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "driver.py"),
         "multi", *repos, "--only", "dead-code", *args],
        capture_output=True, text=True, env={**env, **extra_env},
    )


def _git_out(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, env=driver.scrubbed_env()).stdout.strip()


def test_multi_sweeps_two_owned_repos_in_turn_from_origin_main(tmp_path):
    tmp = str(tmp_path)
    (a, b), env = _multi_fixture(tmp, ["alpha", "beta"])
    # Local clone: dirty tree on a non-main branch must not reach the sweep.
    _git_out(a, "checkout", "-q", "-b", "wip")
    open(os.path.join(a, "wip.py"), "w").write("y = 2\n")
    r = _multi([a, b], env, FAKE_GH_BODIES=os.path.join(tmp, "bodies.log"))
    assert r.returncode == 0, r.stdout + r.stderr
    for name, repo in (("alpha", a), ("beta", b)):
        sweeps = os.listdir(os.path.join(tmp, "data", "all-audits", name))
        assert len(sweeps) == 1
        stored = os.path.join(tmp, "data", "all-audits", name, sweeps[0])
        assert os.path.isfile(os.path.join(stored, "collection", "index.html"))
        assert os.path.isfile(os.path.join(stored, "collection", "dead-code", "report.html"))
        assert f"{name}: swept" in r.stdout
    paths = [l.split()[1] for l in open(env["FAKE_CLAUDE_STARTS"]).read().splitlines()]
    assert all(p.endswith(os.sep + "checkout") and p not in (a, b) for p in paths), paths
    owners = ["alpha" if os.sep + "alpha-" in p else "beta" for p in paths]
    # Never overlapping: all of alpha's audits start before any of beta's.
    assert owners == sorted(owners) and set(owners) == {"alpha", "beta"}, owners
    # Each record names its repo's origin/main sha as the audited commit, and
    # alpha's wip branch tip is not it.
    bodies = _bodies(env)
    for repo in (a, b):
        assert f"Audited commit: {_git_out(repo, 'rev-parse', 'origin/main')}" in bodies, bodies[:400]
    # No worktree is left registered in either clone.
    for repo in (a, b):
        assert _git_out(repo, "worktree", "list").count("\n") == 0


def test_multi_refuses_a_repo_not_owned_by_caneff_before_any_claude_starts_for_it(tmp_path):
    tmp = str(tmp_path)
    (a, b), env = _multi_fixture(tmp, ["alpha", "beta"])
    r = _multi([a, b], env, FAKE_GH_OWNER_FOR="beta=someoneelse")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "beta: refused (owner is someoneelse, not caneff)" in r.stdout, r.stdout
    assert "alpha: swept" in r.stdout
    assert not os.path.exists(os.path.join(tmp, "data", "all-audits", "beta"))
    starts = open(env["FAKE_CLAUDE_STARTS"]).read()
    assert "beta" not in starts and "alpha" in starts


def test_multi_gh_failure_refuses_the_repo(tmp_path):
    tmp = str(tmp_path)
    (a,), env = _multi_fixture(tmp, ["alpha"])
    r = _multi([a], env, FAKE_GH_EXIT="1")
    assert "alpha: refused (owner check failed" in r.stdout, r.stdout + r.stderr
    assert not os.path.exists(env["FAKE_CLAUDE_STARTS"])


def test_multi_sweeps_origin_main_not_a_dirty_or_other_branch_checkout(tmp_path):
    tmp = str(tmp_path)
    (a,), env = _multi_fixture(tmp, ["alpha"])
    _git_out(a, "checkout", "-q", "-b", "wip")
    open(os.path.join(a, "wip.py"), "w").write("y = 2\n")
    _git_out(a, "add", ".")
    _git_out(a, "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-q", "-m", "wip")
    open(os.path.join(a, "dirty.py"), "w").write("z = 3\n")
    r = _multi([a], env, FAKE_GH_BODIES=os.path.join(tmp, "bodies.log"))
    assert r.returncode == 0, r.stdout + r.stderr
    # The audit ran in a worktree outside the clone, at origin/main, which the
    # wip commit is not.
    prompts = [l for l in open(env["FAKE_CLAUDE_STARTS"]).read().splitlines()]
    wt = prompts[0].split()[1]
    assert wt.endswith("checkout") and os.path.dirname(wt) != a
    body = _bodies(env)
    assert f"Audited commit: {_git_out(a, 'rev-parse', 'origin/main')}" in body, body[:400]
    assert _git_out(a, "rev-parse", "wip") not in body


def test_multi_short_runs_only_the_short_set_in_each_repo(tmp_path):
    from audits_data import SHORT_SET
    tmp = str(tmp_path)
    (a, b), env = _multi_fixture(tmp, ["alpha", "beta"])
    r = subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "driver.py"), "multi", a, b, "--short"],
        capture_output=True, text=True, env=env)
    starts = [l.split()[0] for l in open(env["FAKE_CLAUDE_STARTS"]).read().splitlines()]
    assert sorted(set(starts)) == sorted("/" + n for n in SHORT_SET), (starts, r.stdout)
    assert len(starts) == 2 * len(SHORT_SET)


def test_single_repo_sweep_is_unchanged_by_multi(tmp_path):
    tmp = str(tmp_path)
    os.mkdir(os.path.join(tmp, "bin"))
    r = _sweep_with_fake_claude(tmp, os.path.join(tmp, "cache"), os.path.join(tmp, "bin"), "dead-code")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "multi-repo summary" not in r.stdout
    assert os.path.isfile(os.path.join(tmp, "out", "collection", "index.html"))
    assert not os.path.exists(os.path.join(tmp, "data"))


# --- the audit record (#1680) --------------------------------------------------

def _finding(n, **over):
    row = {"bucket": "cut", "file": f"src/mod{n}.py", "line": 10 + n, "category": "unused",
           "summary": f"unused helper number {n}", "failure": f"nothing calls helper{n}",
           "after": f"delete helper{n}"}
    return {**row, **over}


def _findings_file(tmp, rows, name="findings.jsonl"):
    path = os.path.join(tmp, name)
    with open(path, "w") as f:
        for row in rows:
            f.write((row if isinstance(row, str) else json.dumps(row)) + "\n")
    return path


def _record_env(tmp, rows, **extra):
    return {"FAKE_CLAUDE_FINDINGS_FILE": _findings_file(tmp, rows), "FAKE_GH_BODIES": os.path.join(tmp, "bodies.log"),
            "AUDITS_NO_SYNTH": "1", **extra}


def _gh_calls(env, verb):
    lines = [l.split("\t", 1)[1] for l in open(env["FAKE_GH_LOG"]).read().splitlines()]
    return [l for l in lines if l.startswith(verb)]


def _bodies(env):
    path = os.path.join(os.path.dirname(env["FAKE_GH_LOG"]), "bodies.log")
    return open(path).read() if os.path.exists(path) else ""


def _stored_record(tmp, name):
    sweeps = os.listdir(os.path.join(tmp, "data", "all-audits", name))
    return json.load(open(os.path.join(tmp, "data", "all-audits", name, sweeps[0], "audit-record.json")))


def test_record_one_issue_with_the_mapped_label_holding_every_finding_of_every_audit(tmp_path):
    tmp = str(tmp_path)
    (a,), env = _multi_fixture(tmp, ["alpha"])
    os.makedirs(os.path.join(a, "docs", "agents"))
    open(os.path.join(a, "docs", "agents", "triage-labels.md"), "w").write(
        "| Label in mattpocock/skills | Label in our tracker | Meaning |\n| --- | --- | --- |\n"
        "| `needs-triage` | `to-look-at` | x |\n| `needs-info` | `info` | y |\n")
    _git_out(a, "add", ".")
    _git_out(a, "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-q", "-m", "labels")
    _git_out(a, "push", "-q", "origin", "main")
    rows = [_finding(1), _finding(2), _finding(3)]
    r = _multi([a], env, "--only", "dead-code,domain-drift", **_record_env(tmp, rows, FAKE_GH_LABELS='[{"name":"to-look-at"}]'))
    assert r.returncode == 0, r.stdout + r.stderr
    creates = _gh_calls(env, "issue create")
    assert len(creates) == 1, creates
    assert "--label to-look-at" in creates[0], creates[0]
    body = _bodies(env)
    for audit in ("dead-code", "domain-drift"):
        section = body.split(f"### {audit}\n", 1)[1].split("\n### ", 1)[0]
        for n in (1, 2, 3):
            assert f"unused helper number {n}" in section, (audit, n)
            assert f"src/mod{n}.py:{10 + n}" in section and f"delete helper{n}" in section
    assert "issues/1" in r.stdout and "alpha: swept" in r.stdout, r.stdout


def test_record_names_the_commit_the_clean_worktree_and_the_stored_path(tmp_path):
    tmp = str(tmp_path)
    (a,), env = _multi_fixture(tmp, ["alpha"])
    r = _multi([a], env, **_record_env(tmp, [_finding(1)]))
    assert r.returncode == 0, r.stdout + r.stderr
    body = _bodies(env)
    sha = _git_out(a, "rev-parse", "origin/main")
    stored = os.path.join(tmp, "data", "all-audits", "alpha")
    assert f"Audited commit: {sha}" in body, body[:600]
    assert "Worktree clean: yes" in body
    assert f"Stored sweep: {stored}" in body
    assert "Audits run: dead-code" in body


def test_record_shows_a_failed_audit_with_its_error_tail_and_files_for_that_alone(tmp_path):
    tmp = str(tmp_path)
    (a,), env = _multi_fixture(tmp, ["alpha"])
    r = _multi([a], env, "--only", "duplication", **_record_env(tmp, []))
    assert len(_gh_calls(env, "issue create")) == 1, r.stdout + r.stderr
    body = _bodies(env)
    assert "## Failed audits" in body and "Skipped as unchanged" not in body, body[:600]
    failed = body.split("Failed audits", 1)[1].split("\n## ", 1)[0]
    assert "duplication" in failed and "no manifest" in failed
    assert "see /tmp/unrelated-1234/other.html" in failed, failed
    assert r.returncode == 1 and "alpha: failed" in r.stdout and "issues/1" in r.stdout, r.stdout


def test_record_lists_an_unchanged_audit_with_the_earlier_sha_and_copies_none_of_its_findings(tmp_path):
    tmp = str(tmp_path)
    (a,), env = _multi_fixture(tmp, ["alpha"])
    out = os.path.join(tmp, "out")
    only = ("--only", "domain-drift,duplication", "--out", out)
    first = _multi([a], env, *only, **_record_env(tmp, [_finding(1)]))
    assert first.returncode == 1, first.stdout + first.stderr
    assert "unused helper number 1" in _bodies(env).split("### domain-drift", 1)[1]
    open(os.path.join(tmp, "bodies.log"), "w").close()
    time.sleep(1.1)  # the sweep id is a second-resolution timestamp
    second = _multi([a], env, *only, **_record_env(tmp, [_finding(1)], FAKE_GH_ISSUE_STATE="CLOSED"))  # triaged since
    assert len(_gh_calls(env, "issue create")) == 2, second.stdout + second.stderr
    body = _bodies(env)
    sha = _git_out(a, "rev-parse", "origin/main")
    skipped = body.split("Skipped as unchanged", 1)[1].split("\n## ", 1)[0]
    assert "domain-drift" in skipped and sha in skipped, skipped
    assert "Earlier audit record: https://github.com/caneff/fake/issues/1" in skipped, skipped
    assert "unused helper number" not in body


def test_record_not_filed_for_a_repo_with_no_findings_and_no_failure(tmp_path):
    tmp = str(tmp_path)
    (a,), env = _multi_fixture(tmp, ["alpha"])
    r = _multi([a], env, **_record_env(tmp, []))
    assert r.returncode == 0, r.stdout + r.stderr
    assert _gh_calls(env, "issue create") == []
    assert "alpha: swept" in r.stdout and "issues/" not in r.stdout
    stored = os.path.join(tmp, "data", "all-audits", "alpha")
    assert os.path.isfile(os.path.join(stored, os.listdir(stored)[0], "collection", "index.html"))
    assert not os.path.exists(os.path.join(stored, os.listdir(stored)[0], "audit-record.json"))


def test_record_past_the_limit_continues_in_ordered_comments_holding_every_finding_once(tmp_path):
    tmp = str(tmp_path)
    (a,), env = _multi_fixture(tmp, ["alpha"])
    rows = [_finding(n, summary=f"S{n:03d}-" + "x" * 900) for n in range(150)]
    r = _multi([a], env, **_record_env(tmp, rows))
    assert r.returncode == 0, r.stdout + r.stderr
    comments = _gh_calls(env, "issue comment")
    assert len(comments) >= 1 and all(c.startswith("issue comment 1 ") for c in comments), comments
    parts = re.split(r"^=== (issue [^\n]*) ===\n", _bodies(env), flags=re.M)[1:]
    texts = parts[1::2]
    assert parts[0].startswith("issue create") and all(p.startswith("issue comment") for p in parts[2::2])
    assert all(len(t) <= 65536 for t in texts), [len(t) for t in texts]
    joined = "\n".join(texts)
    for n in range(150):
        assert joined.count(f"S{n:03d}-") == 1, n
    order = [int(m) for m in re.findall(r"S(\d{3})-", joined)]
    assert order == sorted(order)


def test_repo_without_its_triage_label_is_refused_before_any_claude_starts(tmp_path):
    tmp = str(tmp_path)
    (a, b), env = _multi_fixture(tmp, ["alpha", "beta"])
    r = _multi([a, b], env, FAKE_GH_LABELS='[{"name":"bug"}]')
    assert "alpha: refused (label `needs-triage` is missing" in r.stdout, r.stdout + r.stderr
    assert "beta: refused (label `needs-triage` is missing" in r.stdout
    assert not os.path.exists(env["FAKE_CLAUDE_STARTS"])
    assert _gh_calls(env, "label create") == []
    # Only the pass's own page (#1721) is stored: no sweep of either repo.
    assert sorted(os.listdir(os.path.join(tmp, "data", "all-audits"))) == ["multi"]


def test_stored_sweep_records_the_issue_number(tmp_path):
    tmp = str(tmp_path)
    (a,), env = _multi_fixture(tmp, ["alpha"])
    r = _multi([a], env, **_record_env(tmp, [_finding(1)], FAKE_GH_ISSUE_URL="https://github.com/caneff/alpha/issues/42"))
    assert r.returncode == 0, r.stdout + r.stderr
    rec = _stored_record(tmp, "alpha")
    assert rec["issue"] == 42 and rec["url"] == "https://github.com/caneff/alpha/issues/42", rec
    assert "https://github.com/caneff/alpha/issues/42" in r.stdout


# --- triage pending (#1681) ----------------------------------------------------

def _first_sweep_then(tmp, env, repo, url):
    """Sweep `repo` once, filing record `url`, then clear the logs a second
    sweep's assertions read."""
    r = _multi([repo], env, **_record_env(tmp, [_finding(1)], FAKE_GH_ISSUE_URL=url))
    assert r.returncode == 0, r.stdout + r.stderr
    base = os.path.join(tmp, "data", "all-audits", os.path.basename(repo))
    os.rename(os.path.join(base, os.listdir(base)[0]), os.path.join(base, "20200101-000000"))  # an earlier day's sweep
    os.remove(env["FAKE_CLAUDE_STARTS"])
    os.remove(os.path.join(tmp, "bodies.log"))
    open(env["FAKE_GH_LOG"], "w").close()


def test_open_earlier_record_means_no_sweep_and_triage_pending_with_the_link(tmp_path):
    tmp = str(tmp_path)
    (a,), env = _multi_fixture(tmp, ["alpha"])
    url = "https://github.com/caneff/alpha/issues/42"
    _first_sweep_then(tmp, env, a, url)
    r = _multi([a], env, **_record_env(tmp, [_finding(1)], FAKE_GH_ISSUE_STATE="OPEN"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"alpha: triage pending ({url})" in r.stdout, r.stdout
    assert not os.path.exists(env["FAKE_CLAUDE_STARTS"])
    assert any(c.startswith("issue view 42") for c in _gh_calls(env, "issue view")), _gh_calls(env, "issue view")
    assert _gh_calls(env, "issue create") == []


def test_closed_earlier_record_is_swept_normally(tmp_path):
    tmp = str(tmp_path)
    (a,), env = _multi_fixture(tmp, ["alpha"])
    _first_sweep_then(tmp, env, a, "https://github.com/caneff/alpha/issues/42")
    r = _multi([a], env, **_record_env(tmp, [_finding(1)], FAKE_GH_ISSUE_STATE="CLOSED",
                                       FAKE_GH_ISSUE_URL="https://github.com/caneff/alpha/issues/43"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "triage pending" not in r.stdout and "alpha: swept" in r.stdout, r.stdout
    assert os.path.exists(env["FAKE_CLAUDE_STARTS"])
    assert "issues/42" not in _bodies(env)


def test_force_sweeps_a_pending_repo_and_the_new_record_names_the_open_one(tmp_path):
    tmp = str(tmp_path)
    (a,), env = _multi_fixture(tmp, ["alpha"])
    url = "https://github.com/caneff/alpha/issues/42"
    _first_sweep_then(tmp, env, a, url)
    r = _multi([a], env, "--force", **_record_env(tmp, [_finding(1)], FAKE_GH_ISSUE_STATE="OPEN",
                                                  FAKE_GH_ISSUE_URL="https://github.com/caneff/alpha/issues/43"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert os.path.exists(env["FAKE_CLAUDE_STARTS"]) and "triage pending" not in r.stdout
    assert f"Earlier open audit record: {url}" in _bodies(env), _bodies(env)


def test_unanswerable_earlier_record_check_refuses_the_repo_and_starts_nothing(tmp_path):
    tmp = str(tmp_path)
    (a,), env = _multi_fixture(tmp, ["alpha"])
    _first_sweep_then(tmp, env, a, "https://github.com/caneff/alpha/issues/42")
    r = _multi([a], env, **_record_env(tmp, [_finding(1)], FAKE_GH_ISSUE_STATE="BOGUS"))
    assert "alpha: refused (earlier record check failed" in r.stdout, r.stdout + r.stderr
    assert not os.path.exists(env["FAKE_CLAUDE_STARTS"])


def _stored_log(tmp, name, audit):
    root = os.path.join(tmp, "data", "all-audits", name)
    return open(os.path.join(root, sorted(os.listdir(root))[-1], "logs", audit + ".log")).read()


def test_record_counts_what_the_ignore_file_suppressed(tmp_path):
    tmp = str(tmp_path)
    (a,), env = _multi_fixture(tmp, ["alpha"])
    open(os.path.join(a, ".audit-ignore.md"), "w").write("- src/mod1.py: rejected\n")
    _git_out(a, "add", ".audit-ignore.md")
    _git_out(a, "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-q", "-m", "ignore")
    _git_out(a, "push", "-q", "origin", "main")
    r = _multi([a], env, **_record_env(tmp, [_finding(1)], FAKE_CLAUDE_SUPPRESSED="7"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Suppressed by .audit-ignore.md: 7" in _bodies(env)
    assert 'Also put "suppressed" in the manifest' in _stored_log(tmp, "alpha", "dead-code")


def test_no_suppressed_count_is_asked_for_without_an_ignore_file(tmp_path):
    tmp = str(tmp_path)
    (a,), env = _multi_fixture(tmp, ["alpha"])
    r = _multi([a], env, **_record_env(tmp, [_finding(1)]))
    assert r.returncode == 0, r.stdout + r.stderr
    log = _stored_log(tmp, "alpha", "dead-code")
    assert "prompt=" in log and '"suppressed"' not in log, log[:400]


def test_record_carries_the_synthesis_as_is_and_a_malformed_finding_line_is_kept(tmp_path):
    tmp = str(tmp_path)
    (a,), env = _multi_fixture(tmp, ["alpha"])
    r = _multi([a], env, **_record_env(tmp, [_finding(1), "{not json"], AUDITS_NO_SYNTH="0"))
    assert r.returncode == 0, r.stdout + r.stderr
    body = _bodies(env)
    assert "## Synthesis" in body and "ceiling=" in body.split("## Synthesis", 1)[1]
    assert "line 2: {not json" in body  # the corrupt line is named by its number, not skipped


# --- prune stored sweeps whose record is closed (#1682) --------------------------

def _stored(tmp, repo_name, sweep, issue):
    d = os.path.join(tmp, "data", "all-audits", repo_name, sweep)
    os.makedirs(os.path.join(d, "collection"))
    json.dump({"issue": issue, "url": f"https://github.com/caneff/{repo_name}/issues/{issue}", "repo": repo_name},
              open(os.path.join(d, "audit-record.json"), "w"))
    os.utime(d, (0, 0))  # far older than 3 days: age must not decide
    return d


def _single(repo, env, **extra):
    return subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "driver.py"), "sweep", repo, "--only", "dead-code"],
        capture_output=True, text=True, env={**env, **extra},
    )


def test_closed_record_sweep_is_deleted_open_and_unreadable_are_kept_on_a_multi_sweep(tmp_path):
    tmp = str(tmp_path)
    (a,), env = _multi_fixture(tmp, ["alpha"])
    closed, opened, broken = (_stored(tmp, "beta", "20200101-000000", 1), _stored(tmp, "beta", "20200102-000000", 2),
                              _stored(tmp, "gamma", "20200103-000000", 3))
    r = _multi([a], env, FAKE_GH_ISSUE_STATES="1=CLOSED,2=OPEN,3=FAIL")
    assert r.returncode == 0, r.stdout + r.stderr
    assert not os.path.exists(closed)
    assert os.path.isdir(opened) and os.path.isdir(broken)
    assert "#3" in r.stdout + r.stderr and "fake gh: issue view 3 failed" in r.stdout + r.stderr


def test_closed_record_sweep_is_deleted_at_the_start_of_a_single_repo_sweep(tmp_path):
    tmp = str(tmp_path)
    (a,), env = _multi_fixture(tmp, ["alpha"])
    closed, opened = _stored(tmp, "beta", "20200101-000000", 1), _stored(tmp, "beta", "20200102-000000", 2)
    r = _single(a, env, FAKE_GH_ISSUE_STATES="1=CLOSED,2=OPEN")
    assert r.returncode == 0, r.stdout + r.stderr
    assert not os.path.exists(closed) and os.path.isdir(opened)


def test_unanswerable_state_keeps_the_stored_sweep(tmp_path):
    tmp = str(tmp_path)
    (a,), env = _multi_fixture(tmp, ["alpha"])
    d = _stored(tmp, "beta", "20200101-000000", 1)
    _single(a, env, FAKE_GH_ISSUE_STATE="BOGUS")
    assert os.path.isdir(d)


def test_single_repo_run_folders_past_three_days_are_still_pruned(tmp_path):
    tmp = str(tmp_path)
    (a,), env = _multi_fixture(tmp, ["alpha"])
    old = os.path.join(tmp, "cache", "all-audits", "run-20200101-000000")
    os.makedirs(old)
    os.utime(old, (0, 0))
    r = _single(a, env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert not os.path.exists(old)


# --- --suggest (#1683) ---------------------------------------------------------

def _suggest_fixture(tmp, clones):
    """`clones` maps a directory name under <tmp>/src to the origin URL it
    carries; returns (roots dir, env with the fake gh on PATH)."""
    here = os.path.dirname(os.path.abspath(__file__))
    bindir, roots = os.path.join(tmp, "bin"), os.path.join(tmp, "src")
    os.makedirs(bindir)
    os.makedirs(roots)
    os.symlink(os.path.join(here, "fake_gh_fixture.sh"), os.path.join(bindir, "gh"))
    genv = driver.scrubbed_env()
    for dirname, url in clones.items():
        path = os.path.join(roots, dirname)
        os.mkdir(path)
        subprocess.run(["git", "init", "-q", path], check=True, env=genv)
        subprocess.run(["git", "-C", path, "remote", "add", "origin", url], check=True, env=genv)
    env = {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}", "FAKE_GH_LOG": os.path.join(tmp, "gh.log")}
    return roots, env


def _prs(*names):
    return json.dumps([{"repository": {"nameWithOwner": n}} for n in names])


def _suggest(roots, env, **extra_env):
    return subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "driver.py"),
         "suggest", "--roots", roots],
        capture_output=True, text=True, env={**env, **extra_env},
    )


def _suggested(r):
    return sorted(l.split(": ", 1)[1] for l in r.stdout.splitlines() if l.startswith("suggest: "))


def test_suggest_lists_exactly_the_owned_repos_with_a_recent_pr_and_a_local_checkout(tmp_path):
    tmp = str(tmp_path)
    roots, env = _suggest_fixture(tmp, {
        "alpha": "https://github.com/caneff/alpha.git", "beta": "git@github.com:caneff/beta.git",
        "idle": "https://github.com/caneff/idle.git", "theirs": "https://github.com/other/theirs.git"})
    r = _suggest(roots, env, FAKE_GH_PRS=_prs("caneff/alpha", "caneff/beta", "caneff/alpha", "other/theirs"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert _suggested(r) == [os.path.join(roots, "alpha"), os.path.join(roots, "beta")]
    assert "search prs" in open(env["FAKE_GH_LOG"]).read()


def test_suggest_lists_a_repo_with_two_checkouts_once(tmp_path):
    tmp = str(tmp_path)
    roots, env = _suggest_fixture(tmp, {
        "alpha": "https://github.com/caneff/alpha.git", "alpha-wt-9": "https://github.com/caneff/alpha"})
    r = _suggest(roots, env, FAKE_GH_PRS=_prs("caneff/alpha"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert _suggested(r) == [os.path.join(roots, "alpha")]


def test_suggest_names_a_repo_with_no_local_checkout_as_skipped(tmp_path):
    tmp = str(tmp_path)
    roots, env = _suggest_fixture(tmp, {"alpha": "https://github.com/caneff/alpha.git"})
    r = _suggest(roots, env, FAKE_GH_PRS=_prs("caneff/alpha", "caneff/ghost"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert _suggested(r) == [os.path.join(roots, "alpha")]
    assert "skipped: caneff/ghost (no local checkout)" in r.stdout.splitlines()


def test_suggest_with_a_failed_gh_search_exits_nonzero_with_the_error_never_an_empty_list(tmp_path):
    tmp = str(tmp_path)
    roots, env = _suggest_fixture(tmp, {"alpha": "https://github.com/caneff/alpha.git"})
    r = _suggest(roots, env, FAKE_GH_EXIT="4", FAKE_GH_STDERR="HTTP 401: bad credentials")
    assert r.returncode != 0
    assert "HTTP 401: bad credentials" in r.stderr
    assert "suggest:" not in r.stdout


def test_suggest_with_an_unreadable_gh_reply_exits_nonzero(tmp_path):
    tmp = str(tmp_path)
    roots, env = _suggest_fixture(tmp, {"alpha": "https://github.com/caneff/alpha.git"})
    r = _suggest(roots, env, FAKE_GH_PRS="not json")
    assert r.returncode != 0
    assert "suggest:" not in r.stdout


def test_suggest_with_no_recent_prs_says_so_and_exits_zero(tmp_path):
    tmp = str(tmp_path)
    roots, env = _suggest_fixture(tmp, {"alpha": "https://github.com/caneff/alpha.git"})
    r = _suggest(roots, env, FAKE_GH_PRS="[]")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "no owned repo has a PR in the last 14 days" in r.stdout


# --- --load: reopen a stored sweep for triage (#1684) ---------------------------

def _swept_with_record(tmp, url="https://github.com/caneff/alpha/issues/42"):
    (a,), env = _multi_fixture(tmp, ["alpha"])
    r = _multi([a], env, **_record_env(tmp, [_finding(1)], FAKE_GH_ISSUE_URL=url))
    assert r.returncode == 0, r.stdout + r.stderr
    return env


def _load(env, *args):
    return subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "driver.py"), "load", *args],
        capture_output=True, text=True, env=env,
    )


def test_load_rebuilds_a_working_index_from_the_issue_number_alone(tmp_path):
    tmp = str(tmp_path)
    env = _swept_with_record(tmp)
    stored_dir = os.path.join(tmp, "data", "all-audits", "alpha")
    stored = os.path.join(stored_dir, os.listdir(stored_dir)[0])
    index = os.path.join(stored, "collection", "index.html")
    os.remove(index)  # prove the verb rebuilds it, not that --multi left one
    r = _load(env, "42")
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"index: {index}" in r.stdout, r.stdout
    page = open(index, encoding="utf-8").read()
    assert "dead-code" in page, page[:500]


def test_load_missing_stored_sweep_exits_nonzero_naming_the_issue_and_the_path(tmp_path):
    tmp = str(tmp_path)
    env = _swept_with_record(tmp)
    r = _load(env, "7")
    assert r.returncode != 0
    assert "#7" in r.stderr and os.path.join(tmp, "data", "all-audits") in r.stderr, r.stderr
    assert "audit-record.json" in r.stderr, r.stderr


def test_load_with_the_record_but_no_collection_exits_nonzero_naming_the_path(tmp_path):
    tmp = str(tmp_path)
    env = _swept_with_record(tmp)
    stored_dir = os.path.join(tmp, "data", "all-audits", "alpha")
    stored = os.path.join(stored_dir, os.listdir(stored_dir)[0])
    shutil.rmtree(os.path.join(stored, "collection"))
    r = _load(env, "42")
    assert r.returncode != 0
    assert "#42" in r.stderr and os.path.join(stored, "collection") in r.stderr, r.stderr


def test_load_two_repos_sharing_an_issue_number_needs_the_repo_name(tmp_path):
    tmp = str(tmp_path)
    (a, b), env = _multi_fixture(tmp, ["alpha", "beta"])
    for repo, name in ((a, "alpha"), (b, "beta")):
        r = _multi([repo], env, **_record_env(tmp, [_finding(1)], FAKE_GH_ISSUE_URL=f"https://github.com/caneff/{name}/issues/42"))
        assert r.returncode == 0, r.stdout + r.stderr
    r = _load(env, "42")
    assert r.returncode != 0 and "alpha" in r.stderr and "beta" in r.stderr, r.stderr
    r = _load(env, "42", "beta")
    assert r.returncode == 0, r.stdout + r.stderr
    assert os.path.join("beta", "") in r.stdout


# --- spec-level review fixes (#1678) ------------------------------------------

def _stored_sweeps(tmp, name):
    root = os.path.join(tmp, "data", "all-audits", name)
    return sorted(os.path.join(root, s) for s in os.listdir(root)) if os.path.isdir(root) else []


def test_stored_sweeps_are_keyed_on_the_github_name_and_pruned_in_that_repo(tmp_path):
    tmp = str(tmp_path)
    (a,), env = _multi_fixture(tmp, ["skills"])
    named = {"FAKE_GH_NAME_FOR": "skills=agent-skills"}
    r = _multi([a], env, **_record_env(tmp, [_finding(1)], **named))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "agent-skills: swept" in r.stdout, r.stdout
    assert _stored_sweeps(tmp, "skills") == []
    (first,) = _stored_sweeps(tmp, "agent-skills")
    rec = json.load(open(os.path.join(first, "audit-record.json")))
    assert rec["repo"] == "caneff/agent-skills" and rec["checkout"] == a, rec
    time.sleep(1.1)  # the sweep id is a second-resolution timestamp
    r = _multi([a], env, **_record_env(tmp, [_finding(1)], FAKE_GH_ISSUE_STATE="CLOSED", **named))
    assert r.returncode == 0, r.stdout + r.stderr
    views = _gh_calls(env, "issue view")
    assert views and all("--repo caneff/agent-skills" in v for v in views), views
    assert first not in _stored_sweeps(tmp, "agent-skills")


def test_two_checkouts_of_one_repo_share_its_stored_sweeps(tmp_path):
    tmp = str(tmp_path)
    (a, a2), env = _multi_fixture(tmp, ["alpha", "alpha-wt"])
    named = {"FAKE_GH_NAME_FOR": "alpha-wt=alpha"}
    r = _multi([a, a2], env, **_record_env(tmp, [_finding(1)], **named))
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"alpha: skipped ({a2} is caneff/alpha again, already swept from {a})" in r.stdout, r.stdout
    assert len(_gh_calls(env, "issue create")) == 1
    r = _multi([a2], env, **_record_env(tmp, [_finding(1)], **named))
    assert "alpha: triage pending (https://github.com/caneff/fake/issues/1)" in r.stdout, r.stdout


def test_multi_reuses_the_staleness_cache_across_sweeps_with_no_out(tmp_path):
    tmp = str(tmp_path)
    (a,), env = _multi_fixture(tmp, ["alpha"])
    only = ("--only", "domain-drift")
    assert _multi([a], env, *only, **_record_env(tmp, [_finding(1)])).returncode == 0
    time.sleep(1.1)
    open(os.path.join(tmp, "bodies.log"), "w").close()
    second = _multi([a], env, *only, **_record_env(tmp, [_finding(1)], FAKE_GH_ISSUE_STATE="CLOSED"))
    assert second.returncode == 0, second.stdout + second.stderr
    starts = open(env["FAKE_CLAUDE_STARTS"]).read().splitlines()
    assert len(starts) == 1, starts
    assert "[domain-drift] skipped (unchanged since" in second.stdout, second.stdout
    assert "alpha: swept -> " in second.stdout and "no audit record" in second.stdout, second.stdout


def test_a_sweep_stopped_by_the_guard_still_files_a_failure_record(tmp_path):
    tmp = str(tmp_path)
    (a,), env = _multi_fixture(tmp, ["alpha"])
    r = _multi([a], env, **_record_env(tmp, [], FAKE_CLAUDE_GUARD="1"))
    assert r.returncode == 1 and "alpha: failed (sweep stopped before collecting: exit 1)" in r.stdout, r.stdout
    assert len(_gh_calls(env, "issue create")) == 1, r.stdout + r.stderr
    failed = _bodies(env).split("## Failed audits", 1)[1]
    assert "the sweep failed" in failed and "disable-model-invocation" in failed, failed[:600]


def test_a_failed_continuation_comment_keeps_every_chunk_and_names_the_unposted_ones(tmp_path):
    tmp = str(tmp_path)
    (a,), env = _multi_fixture(tmp, ["alpha"])
    rows = [_finding(n, summary=f"S{n:03d}-" + "x" * 900) for n in range(150)]
    r = _multi([a], env, **_record_env(tmp, rows, FAKE_GH_COMMENT_EXIT="1"))
    assert r.returncode == 1, r.stdout + r.stderr
    assert "is missing continuation comments audit-record-1.md" in r.stdout, r.stdout
    (stored,) = _stored_sweeps(tmp, "alpha")
    rec = json.load(open(os.path.join(stored, "audit-record.json")))
    chunks = sorted(f for f in os.listdir(stored) if re.fullmatch(r"audit-record-\d+\.md", f))
    assert rec["issue"] == 1 and rec["unposted"] == chunks[1:] and len(chunks) >= 2, (rec, chunks)
    joined = "".join(open(os.path.join(stored, c)).read() for c in chunks)
    assert all(joined.count(f"S{n:03d}-") == 1 for n in range(150))


def test_load_keeps_the_sweeps_failure_notes_and_its_synthesis_and_runs_no_claude(tmp_path):
    tmp = str(tmp_path)
    (a,), env = _multi_fixture(tmp, ["alpha"])
    r = _multi([a], env, "--only", "dead-code,duplication",
               **_record_env(tmp, [_finding(1)], FAKE_GH_ISSUE_URL="https://github.com/caneff/alpha/issues/42"))
    assert r.returncode == 1 and "issues/42" in r.stdout, r.stdout + r.stderr
    (stored,) = _stored_sweeps(tmp, "alpha")
    open(os.path.join(stored, "collection", driver.SYNTHESIS_FILE), "w").write("the stored synthesis")
    os.remove(env["FAKE_CLAUDE_STARTS"])
    load_env = {k: v for k, v in env.items() if k != "AUDITS_NO_SYNTH"}
    r = _load(load_env, "42")
    assert r.returncode == 0, r.stdout + r.stderr
    assert not os.path.exists(env["FAKE_CLAUDE_STARTS"]), "load started a claude"
    page = open(os.path.join(stored, "collection", "index.html"), encoding="utf-8").read()
    assert "FAILED: " in page and "the stored synthesis" in page, page[:800]
    assert f"checkout: {a}" in r.stdout and "repo: caneff/alpha" in r.stdout, r.stdout


def test_a_repo_that_cannot_be_read_does_not_stop_the_others(tmp_path):
    tmp = str(tmp_path)
    (a,), env = _multi_fixture(tmp, ["alpha"])
    r = _multi([os.path.join(tmp, "gone"), a], env)
    assert "gone: refused (no such directory)" in r.stdout, r.stdout + r.stderr
    assert "alpha: swept" in r.stdout and "== multi-repo summary ==" in r.stdout


def test_a_stored_sweep_with_no_record_is_deleted_after_three_days(tmp_path):
    tmp = str(tmp_path)
    root = os.path.join(tmp, "data", "all-audits", "alpha")
    old, new = os.path.join(root, "20200101-000000"), os.path.join(root, "20991231-000000")
    for d in (old, new):
        os.makedirs(os.path.join(d, "collection"))
    past = time.time() - 4 * 86400
    os.utime(old, (past, past))
    os.mkdir(os.path.join(tmp, "bin"))
    r = _sweep_with_fake_claude(tmp, os.path.join(tmp, "cache"), os.path.join(tmp, "bin"), "dead-code")
    assert r.returncode == 0, r.stdout + r.stderr
    assert not os.path.exists(old) and os.path.isdir(new)


def test_suggest_looks_under_dot_agents_by_default(tmp_path):
    tmp = str(tmp_path)
    roots, env = _suggest_fixture(tmp, {"x": "git@github.com:caneff/x.git"})
    skills = os.path.join(tmp, ".agents", "skills")
    os.makedirs(skills)
    subprocess.run(["git", "init", "-q", skills], check=True, env=driver.scrubbed_env())
    subprocess.run(["git", "-C", skills, "remote", "add", "origin", "https://github.com/caneff/agent-skills.git"],
                   check=True, env=driver.scrubbed_env())
    r = subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "driver.py"), "suggest"],
        capture_output=True, text=True,
        env={**env, "HOME": tmp, "FAKE_GH_PRS": _prs("caneff/agent-skills", "caneff/x")})
    assert r.returncode == 0, r.stdout + r.stderr
    assert _suggested(r) == sorted([skills, os.path.join(roots, "x")]), r.stdout


def test_suggest_refuses_a_search_cut_off_at_its_limit(tmp_path):
    tmp = str(tmp_path)
    roots, env = _suggest_fixture(tmp, {})
    r = _suggest(roots, env, FAKE_GH_PRS=_prs(*["caneff/x"] * driver.SEARCH_LIMIT))
    assert r.returncode != 0 and "cut off" in r.stderr, r.stdout + r.stderr


def test_end_to_end_multi_sweep_record_load_and_prune(tmp_path):
    """The spec's path at the subprocess seam: an owned repo is swept from
    origin/main and files its audit record, one not owned is refused before
    any audit, the record loads back by issue number, and closing it frees the
    stored sweep at the next sweep's start.

    Blind to: the live `/all-audits multi` ask and its job-run launch, the
    triage grill and `/triage`'s routing (SKILL.md prose a model follows), and
    real GitHub: every `gh` reply here is the fake's."""
    tmp = str(tmp_path)
    (a, c), env = _multi_fixture(tmp, ["alpha", "gamma"])
    url = "https://github.com/caneff/alpha/issues/42"
    r = _multi([a, c], env, **_record_env(
        tmp, [_finding(1)], FAKE_GH_ISSUE_URL=url, FAKE_GH_OWNER_FOR="gamma=someoneelse"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "gamma: refused (owner is someoneelse, not caneff)" in r.stdout, r.stdout
    assert "alpha: swept -> " in r.stdout and f"audit record: {url}" in r.stdout, r.stdout
    assert len(_gh_calls(env, "issue create")) == 1
    assert "unused helper number 1" in _bodies(env)
    assert "gamma" not in open(env["FAKE_CLAUDE_STARTS"]).read()
    loaded = _load(env, "42", "alpha")
    assert loaded.returncode == 0 and "index: " in loaded.stdout, loaded.stdout + loaded.stderr
    time.sleep(1.1)
    r = _multi([a], env, **_record_env(tmp, [_finding(1)], FAKE_GH_ISSUE_URL=url, FAKE_GH_ISSUE_STATE="CLOSED"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert len(_stored_sweeps(tmp, "alpha")) == 1, _stored_sweeps(tmp, "alpha")


def test_the_next_sweep_posts_the_comments_a_record_was_missing_first(tmp_path):
    tmp = str(tmp_path)
    (a,), env = _multi_fixture(tmp, ["alpha"])
    rows = [_finding(n, summary=f"S{n:03d}-" + "x" * 900) for n in range(150)]
    assert _multi([a], env, **_record_env(tmp, rows, FAKE_GH_COMMENT_EXIT="1")).returncode == 1
    open(os.path.join(tmp, "bodies.log"), "w").close()
    r = _multi([a], env, **_record_env(tmp, rows))
    assert "alpha: posted the missing comments of https://github.com/caneff/fake/issues/1" in r.stdout, r.stdout
    assert "alpha: triage pending" in r.stdout, r.stdout
    (stored,) = _stored_sweeps(tmp, "alpha")
    assert json.load(open(os.path.join(stored, "audit-record.json")))["unposted"] == []
    posted = _bodies(env)
    first = open(os.path.join(stored, "audit-record-0.md")).read()
    assert all((first + posted).count(f"S{n:03d}-") == 1 for n in range(150))


def test_multi_fetches_so_a_stale_clone_still_sweeps_the_newest_origin_main(tmp_path):
    tmp = str(tmp_path)
    (a,), env = _multi_fixture(tmp, ["alpha"])
    other = os.path.join(tmp, "other")
    genv = driver.scrubbed_env()
    subprocess.run(["git", "clone", "-q", os.path.join(tmp, "bare-alpha"), other], check=True, env=genv)
    open(os.path.join(other, "new.py"), "w").write("n = 1\n")
    for argv in (["add", "new.py"], ["-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-q", "-m", "n"],
                 ["push", "-q", "origin", "HEAD:main"]):
        subprocess.run(["git", "-C", other, *argv], check=True, env=genv)
    newest = _git_out(other, "rev-parse", "HEAD")
    assert _git_out(a, "rev-parse", "origin/main") != newest  # the clone has not fetched it
    r = _multi([a], env, FAKE_GH_BODIES=os.path.join(tmp, "bodies.log"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"Audited commit: {newest}" in _bodies(env), _bodies(env)[:400]


# --- the multi-repo index (#1721) -- ------------------------------------------

def _multi_page_dirs(tmp):
    base = os.path.join(tmp, "data", "all-audits", "multi")
    return [os.path.join(base, d) for d in sorted(os.listdir(base))] if os.path.isdir(base) else []


def _page_rows(page_html):
    """{repo: (status, row html)} from the page's `<tr data-repo=..>` rows, in order."""
    rows = re.findall(r'<tr data-repo="([^"]+)" data-status="([^"]+)">(.*?)</tr>', page_html, re.S)
    return {repo: (status, body) for repo, status, body in rows}


def test_multi_page_after_repo_one_of_two_shows_it_swept_and_the_other_not_yet_run(tmp_path):
    tmp = str(tmp_path)
    (a, b), env = _multi_fixture(tmp, ["alpha", "beta"])
    snaps = os.path.join(tmp, "snaps")
    r = _multi([a, b], env, **_record_env(tmp, [_finding(1)], FAKE_CLAUDE_SNAPSHOT=snaps,
                                         FAKE_GH_ISSUE_URL="https://github.com/caneff/alpha/issues/7"))
    assert r.returncode == 0, r.stdout + r.stderr
    # start-1 is alpha's audit, start-2 beta's: the page as beta began.
    rows = _page_rows(open(os.path.join(snaps, "start-2.html")).read())
    assert list(rows) == ["alpha", "beta"], rows
    assert rows["alpha"][0] == "swept" and rows["beta"][0] == "not yet run", rows
    (stored,) = [os.path.join(tmp, "data", "all-audits", "alpha", d)
                 for d in os.listdir(os.path.join(tmp, "data", "all-audits", "alpha"))]
    (page_dir,) = _multi_page_dirs(tmp)
    hrefs = re.findall(r'href="([^"]+)"', rows["alpha"][1])
    resolved = [os.path.normpath(os.path.join(page_dir, h)) for h in hrefs if not h.startswith("http")]
    assert os.path.join(stored, "collection", "index.html") in resolved, hrefs
    assert os.path.join(stored, "collection", "dead-code", "report.html") in resolved, hrefs
    assert "https://github.com/caneff/alpha/issues/7" in hrefs, hrefs


def test_multi_page_marks_a_failed_audit_beside_the_report_of_one_that_ran(tmp_path):
    tmp = str(tmp_path)
    (a,), env = _multi_fixture(tmp, ["alpha"])
    r = _multi([a], env, "--only", "dead-code,duplication", **_record_env(tmp, [_finding(1)]))
    assert r.returncode == 1, r.stdout + r.stderr  # duplication writes no manifest
    (page_dir,) = _multi_page_dirs(tmp)
    status, row = _page_rows(open(os.path.join(page_dir, "index.html")).read())["alpha"]
    assert status == "failed", row
    items = dict(re.findall(r"<li>(?:<a [^>]*>)?([\w-]+)(.*?)</li>", row))
    assert "FAILED: no manifest" in items["duplication"], items
    assert "FAILED" not in items["dead-code"], items


def test_multi_opens_only_its_own_page_once_at_the_end(tmp_path):
    tmp = str(tmp_path)
    (a, b), env = _multi_fixture(tmp, ["alpha", "beta"])
    opened = _fake_openers(os.path.join(tmp, "bin"))
    r = _multi([a, b], env, **_record_env(tmp, [_finding(1)], AUDITS_NO_OPEN="0"))
    assert r.returncode == 0, r.stdout + r.stderr
    (page_dir,) = _multi_page_dirs(tmp)
    page = os.path.join(page_dir, "index.html")
    assert _pages_opened(opened) == [page]
    assert r.stdout.rstrip().splitlines()[-1] == f"index: {page}", r.stdout[-400:]


def test_a_single_repo_sweep_still_opens_its_own_index(tmp_path):
    tmp = str(tmp_path)
    (a,), env = _multi_fixture(tmp, ["alpha"])
    opened = _fake_openers(os.path.join(tmp, "bin"))
    r = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "driver.py"),
                        "sweep", a, "--only", "dead-code", "--out", os.path.join(tmp, "out")],
                       capture_output=True, text=True, env={**env, "AUDITS_NO_OPEN": "0"})
    assert r.returncode == 0, r.stdout + r.stderr
    assert _pages_opened(opened) == [os.path.join(tmp, "out", "collection", "index.html")]


def _multi_index(env, *args):
    return subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "driver.py"),
                           "multi-index", *args], capture_output=True, text=True, env=env)


def test_multi_index_rebuilds_the_page_byte_identically_and_runs_no_claude(tmp_path):
    tmp = str(tmp_path)
    (a, b, c), env = _multi_fixture(tmp, ["alpha", "beta", "gamma"])
    r = _multi([a, b, c], env, "--only", "dead-code,duplication",
               **_record_env(tmp, [_finding(1)], FAKE_GH_OWNER_FOR="beta=someoneelse"))
    (page_dir,) = _multi_page_dirs(tmp)
    page = os.path.join(page_dir, "index.html")
    before = open(page, "rb").read()
    assert list(_page_rows(before.decode())) == ["alpha", "beta", "gamma"], r.stdout
    os.remove(page)
    starts = open(env["FAKE_CLAUDE_STARTS"]).read()
    rebuilt = _multi_index(env, os.path.basename(page_dir))
    assert rebuilt.returncode == 0, rebuilt.stdout + rebuilt.stderr
    assert f"index: {page}" in rebuilt.stdout
    assert open(page, "rb").read() == before
    assert open(env["FAKE_CLAUDE_STARTS"]).read() == starts


def test_multi_index_without_a_state_file_rebuilds_from_the_stored_sweeps(tmp_path):
    """A pass started before state.json existed (sweep 20261113-082113)."""
    tmp = str(tmp_path)
    (a, b), env = _multi_fixture(tmp, ["alpha", "beta"])
    _multi([a, b], env, **_record_env(tmp, [_finding(1)], FAKE_GH_OWNER_FOR="alpha=someoneelse",
                                      FAKE_GH_ISSUE_URL="https://github.com/caneff/beta/issues/9"))
    (page_dir,) = _multi_page_dirs(tmp)
    shutil.rmtree(page_dir)
    r = _multi_index(env, os.path.basename(page_dir))
    assert r.returncode == 0, r.stdout + r.stderr
    rows = _page_rows(open(os.path.join(page_dir, "index.html")).read())
    assert list(rows) == ["beta"], rows  # the refused repo left no stored sweep
    assert rows["beta"][0] == "swept" and "https://github.com/caneff/beta/issues/9" in rows["beta"][1]


def test_multi_index_with_nothing_stored_or_a_bad_id_exits_nonzero(tmp_path):
    tmp = str(tmp_path)
    _, env = _multi_fixture(tmp, [])
    r = _multi_index(env, "20990101-000000")
    assert r.returncode == 1 and "20990101-000000" in r.stderr and "state.json" in r.stderr, r.stderr
    r = _multi_index(env, "../alpha")
    assert r.returncode == 1 and "not a sweep id" in r.stderr, r.stderr


def _old_multi_page(tmp, sweep_id):
    d = os.path.join(tmp, "data", "all-audits", "multi", sweep_id)
    os.makedirs(d)
    open(os.path.join(d, "index.html"), "w").write("<html></html>")
    os.utime(d, (0, 0))
    return d


def test_an_old_multi_page_is_kept_while_a_stored_sweep_it_links_lives_and_deleted_after(tmp_path):
    tmp = str(tmp_path)
    (a,), env = _multi_fixture(tmp, ["alpha"])
    linked = _old_multi_page(tmp, "20200102-000000")
    _stored(tmp, "beta", "20200102-000000", 2)  # open record: the stored sweep stays
    orphan = _old_multi_page(tmp, "20200101-000000")
    r = _single(a, env, FAKE_GH_ISSUE_STATES="2=OPEN")
    assert r.returncode == 0, r.stdout + r.stderr
    assert os.path.isdir(linked) and not os.path.exists(orphan), r.stderr


def test_a_multi_page_folder_is_never_read_as_a_stored_sweep(tmp_path):
    tmp = str(tmp_path)
    (a,), env = _multi_fixture(tmp, ["alpha"])
    d = _old_multi_page(tmp, "20200102-000000")
    _stored(tmp, "beta", "20200102-000000", 2)
    # A record file under multi/ would be pruned as a closed sweep if it were read as one.
    json.dump({"issue": 1, "url": "https://github.com/caneff/multi/issues/1"},
              open(os.path.join(d, "audit-record.json"), "w"))
    r = _single(a, env, FAKE_GH_ISSUE_STATES="1=CLOSED,2=OPEN")
    assert r.returncode == 0, r.stdout + r.stderr
    assert os.path.isdir(d)
    assert "issue view 1 " not in open(env["FAKE_GH_LOG"]).read()


def test_a_repo_named_multi_is_refused_before_any_claude_starts(tmp_path):
    tmp = str(tmp_path)
    (a,), env = _multi_fixture(tmp, ["multi"])
    r = _multi([a], env)
    assert "multi: refused (a repo named `multi` collides" in r.stdout, r.stdout + r.stderr
    assert not os.path.exists(env["FAKE_CLAUDE_STARTS"])


def test_multi_page_marks_an_audit_reused_as_unchanged_with_its_sha(tmp_path):
    tmp = str(tmp_path)
    (a,), env = _multi_fixture(tmp, ["alpha"])
    only = ("--only", "domain-drift", "--out", os.path.join(tmp, "out"))
    assert _multi([a], env, *only, **_record_env(tmp, [_finding(1)])).returncode == 0
    time.sleep(1.1)  # the sweep id is a second-resolution timestamp
    r = _multi([a], env, *only, **_record_env(tmp, [_finding(1)], FAKE_GH_ISSUE_STATE="CLOSED"))
    assert r.returncode == 0, r.stdout + r.stderr
    _, second = _multi_page_dirs(tmp)
    _, row = _page_rows(open(os.path.join(second, "index.html")).read())["alpha"]
    sha = _git_out(a, "rev-parse", "origin/main")[:8]
    assert re.search(rf'>domain-drift</a> <em class="mark-unchanged">unchanged since {sha}</em>', row), row


def _rebuild_without_state(tmp, env):
    """Drop the pass's page folder, state.json with it, and rebuild: the rows
    of a pass that recorded none."""
    (page_dir,) = _multi_page_dirs(tmp)
    shutil.rmtree(page_dir)
    r = _multi_index(env, os.path.basename(page_dir))
    page = os.path.join(page_dir, "index.html")
    return r, _page_rows(open(page).read()) if os.path.isfile(page) else {}


def test_multi_index_refuses_a_corrupt_state_file_never_renders_it_as_no_repos(tmp_path):
    tmp = str(tmp_path)
    (a,), env = _multi_fixture(tmp, ["alpha"])
    _multi([a], env, **_record_env(tmp, [_finding(1)]))
    (page_dir,) = _multi_page_dirs(tmp)
    state = os.path.join(page_dir, "state.json")
    for broken in ('{"sweep_id": "x", "repos": [', '{"repos": [{"label": "alpha", "bogus": 1}]}'):
        open(state, "w").write(broken)
        r = _multi_index(env, os.path.basename(page_dir))
        assert r.returncode == 1 and state in r.stderr, r.stdout + r.stderr
        assert "index:" not in r.stdout and "Traceback" not in r.stderr, r.stdout + r.stderr


def test_fallback_row_of_a_sweep_with_a_failed_audit_is_failed_naming_it(tmp_path):
    tmp = str(tmp_path)
    (a,), env = _multi_fixture(tmp, ["alpha"])
    _multi([a], env, "--only", "dead-code,duplication", **_record_env(tmp, [_finding(1)]))
    r, rows = _rebuild_without_state(tmp, env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert rows["alpha"][0] == "failed" and "1 audit(s) failed: duplication" in rows["alpha"][1], rows


def test_fallback_row_of_a_corrupt_sweep_state_is_failed_and_its_marks_unknown(tmp_path):
    tmp = str(tmp_path)
    (a,), env = _multi_fixture(tmp, ["alpha"])
    _multi([a], env, **_record_env(tmp, [_finding(1)]))
    (stored,) = _stored_sweeps(tmp, "alpha")
    open(os.path.join(stored, "sweep-state.json"), "w").write("{not json")
    r, rows = _rebuild_without_state(tmp, env)
    assert r.returncode == 0, r.stdout + r.stderr
    status, row = rows["alpha"]
    assert status == "failed" and "sweep-state.json unreadable" in row, row
    assert "marks unknown" in row, row


def test_fallback_row_of_a_sweep_whose_record_misses_comments_is_failed(tmp_path):
    tmp = str(tmp_path)
    (a,), env = _multi_fixture(tmp, ["alpha"])
    rows = [_finding(n, summary="S%03d-" % n + "x" * 400) for n in range(150)]
    _multi([a], env, **_record_env(tmp, rows, FAKE_GH_COMMENT_EXIT="1"))
    r, page_rows = _rebuild_without_state(tmp, env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert page_rows["alpha"][0] == "failed" and "misses comments" in page_rows["alpha"][1], page_rows


def test_a_page_that_cannot_be_written_is_named_and_every_repo_is_still_swept(tmp_path):
    tmp = str(tmp_path)
    (a, b), env = _multi_fixture(tmp, ["alpha", "beta"])
    os.makedirs(os.path.join(tmp, "data", "all-audits"))
    open(os.path.join(tmp, "data", "all-audits", "multi"), "w").close()  # a file where the folder goes
    r = _multi([a, b], env, **_record_env(tmp, [_finding(1)]))
    assert r.returncode == 1, r.stdout + r.stderr
    assert "alpha: swept" in r.stdout and "beta: swept" in r.stdout, r.stdout + r.stderr
    assert "multi-repo index not written" in r.stderr, r.stderr


def test_a_multi_pass_prints_exactly_one_index_line_and_it_is_the_page(tmp_path):
    tmp = str(tmp_path)
    (a, b), env = _multi_fixture(tmp, ["alpha", "beta"])
    r = _multi([a, b], env, **_record_env(tmp, [_finding(1)]))
    (page_dir,) = _multi_page_dirs(tmp)
    lines = [l for l in r.stdout.splitlines() if l.startswith("index: ")]
    assert lines == [f"index: {os.path.join(page_dir, 'index.html')}"], r.stdout


def test_python_only_audits_are_not_applicable_on_a_js_repo(tmp_path):
    """#1751: dead-code, type-tightness and docstring-coverage read only Python.
    On a repo of `.js` files the sweep never starts them: each gets a manifest
    saying "not applicable: JavaScript", and the index shows that apart from a
    clean pass. The fake `claude` writes nothing for these audits, so a run
    that did start one would fail with "no manifest"."""
    tmp, cache_dir, bin_dir = _mkdirs(tmp_path, "tmp", "cache_dir", "bin_dir")
    (tmp_path / "tmp" / "app.js").write_text("")
    starts = str(tmp_path / "starts")
    r = _sweep_with_fake_claude(tmp, cache_dir, bin_dir, "dead-code,type-tightness,docstring-coverage,duplication",
                                FAKE_CLAUDE_STARTS=starts)
    assert "[type-tightness] FAILED" not in r.stdout and "[dead-code] FAILED" not in r.stdout, r.stdout
    started = open(starts).read()
    assert "/duplication" in started
    assert not any(n in started for n in ("/dead-code", "/type-tightness", "/docstring-coverage")), started
    for name in ("dead-code", "type-tightness", "docstring-coverage"):
        manifest = json.load(open(os.path.join(tmp, "out", "manifests", name, "manifest.json")))
        assert manifest["not_applicable"] == "JavaScript" and manifest["count"] == 0, manifest
        assert manifest["headline"] == "not applicable: JavaScript"
    index = open(os.path.join(tmp, "out", "collection", "index.html")).read()
    assert index.count("NOT APPLICABLE: JavaScript") == 3, index
