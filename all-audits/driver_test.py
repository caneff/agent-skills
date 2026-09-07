#!/usr/bin/env python3
"""Tests for the audit sweep driver (#558) — ports run-audits.test.sh's
hermetic index test to Python (parses the index rather than grepping it, per
the family's plain-assert convention — see crap-audit/test_audit.py), plus a
new cache-decision test against a real temporary git repo, including the
bad-last-run-SHA case, which must mean RUN.
"""
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("AUDITS_NO_OPEN", "1")
os.environ.setdefault("AUDITS_NO_SYNTH", "1")
import driver  # noqa: E402


def _run_driver(*args):
    return subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(__file__), "driver.py"), *args],
        capture_output=True, text=True,
        env={**os.environ, "AUDITS_NO_OPEN": "1", "AUDITS_NO_SYNTH": "1"},
    )


def test_index_rebuild_runs_no_audits():
    with tempfile.TemporaryDirectory() as tmp:
        for name in ("dead-code", "test-audit"):
            d = os.path.join(tmp, "collection", name)
            os.makedirs(d)
            with open(os.path.join(d, "report.html"), "w") as f:
                f.write(f"<html><body>{name} report</body></html>")

        r = _run_driver("--index", "--out", tmp)
        assert r.returncode == 0, r.stdout + r.stderr

        index = os.path.join(tmp, "collection", "index.html")
        assert os.path.isfile(index)
        text = open(index).read()
        assert "dead-code" in text
        assert "test-audit" in text
        assert 'href="dead-code/report.html"' in text

        logs = os.path.join(tmp, "logs")
        assert not (os.path.isdir(logs) and os.listdir(logs)), "--index must run no audits"


def test_index_rerun_replaces_assets_without_nesting():
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "collection", "dead-code", "assets", "base"))
        with open(os.path.join(tmp, "collection", "dead-code", "assets", "base", "base.css"), "w") as f:
            f.write("body{}")

        r = _run_driver("--index", "--out", tmp)
        assert r.returncode == 0, r.stdout + r.stderr
        assert os.path.isfile(os.path.join(tmp, "collection", "assets", "base", "base.css"))

        r = _run_driver("--index", "--out", tmp)
        assert r.returncode == 0, r.stdout + r.stderr
        assert os.path.isfile(os.path.join(tmp, "collection", "assets", "base", "base.css"))
        assert not os.path.isdir(os.path.join(tmp, "collection", "assets", "assets")), "assets/assets nesting"


def test_collect_from_manifest_mutation_style():
    """#580: mutation mode now finds its report the same way the sweep does
    — through a manifest, never by grepping a log for a stray .html path
    (the marker this replaced, `ALL_AUDITS_REPORT=`, is gone from every
    doc)."""
    with tempfile.TemporaryDirectory() as manifests_dir, tempfile.TemporaryDirectory() as collection, tempfile.TemporaryDirectory() as reportdir:
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


def test_collect_from_manifest_no_manifest_or_missing_report():
    with tempfile.TemporaryDirectory() as manifests_dir, tempfile.TemporaryDirectory() as collection:
        assert driver.collect_from_manifest(manifests_dir, "missing", collection, "missing") == "no manifest"

        manifest = driver.manifest_path_for(manifests_dir, "ghost")
        os.makedirs(os.path.dirname(manifest), exist_ok=True)
        with open(manifest, "w") as f:
            json.dump({"report_path": "/no/such/report.html", "count": 0, "headline": "x"}, f)
        reason = driver.collect_from_manifest(manifests_dir, "ghost", collection, "ghost")
        assert reason == "manifest names a missing report: /no/such/report.html"


def test_audit_prompt_whole_repo_override_and_ignore_file():
    prompt = driver.audit_prompt("dead-code", "/some/repo")
    assert prompt.startswith("/dead-code /some/repo")
    assert "ENTIRE repository" in prompt
    assert "not a git diff" in prompt
    assert "rejected" not in prompt

    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, ".audit-ignore.md"), "w") as f:
            f.write("### god object in solver.py\n- adr: docs/adr/0009-solver-shape.md\n")
        with_file = driver.audit_prompt("dead-code", tmp)
        assert "ENTIRE repository" in with_file
        assert "god object in solver.py" in with_file
        assert "0009-solver-shape.md" in with_file


def test_mutation_subindex_and_single_main_row():
    with tempfile.TemporaryDirectory() as tmp:
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

        r = _run_driver("--index", "--out", tmp)
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


def test_no_mutation_reports_no_row():
    with tempfile.TemporaryDirectory() as tmp:
        for name in ("dead-code", "test-audit"):
            d = os.path.join(tmp, "collection", name)
            os.makedirs(d)
            open(os.path.join(d, "report.html"), "w").write("<html>x</html>")

        r = _run_driver("--index", "--out", tmp)
        assert r.returncode == 0, r.stdout + r.stderr
        index_text = open(os.path.join(tmp, "collection", "index.html")).read()
        assert "<td>mutation</td>" not in index_text
        assert not os.path.exists(os.path.join(tmp, "collection", "mutation"))


def test_no_test_modules_section():
    with tempfile.TemporaryDirectory() as tmp:
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

        r = _run_driver("--index", "--out", tmp)
        assert r.returncode == 0, r.stdout + r.stderr

        index_text = open(os.path.join(tmp, "collection", "index.html")).read()
        assert "with no tests" in index_text and "2 with no tests" in index_text

        sub = open(os.path.join(tmp, "collection", "mutation", "index.html")).read()
        assert "2 of 6 source modules have no tests" in sub
        assert "widget.py" in sub and "gadget.py" in sub
        assert "8/13" in sub
        assert "weak" in sub.lower()
        assert "no-coverage" in sub.lower() or "no coverage" in sub.lower()


def test_index_from_manifests_missing_manifest_is_a_failure_row():
    """#559: the driver reads each audit's manifest, never a transcript. A
    fixture log containing an unrelated .html path must not land in the
    index — the audit that never wrote a manifest renders as a named
    failure row instead of silently reusing a stray path from its log."""
    fake_claude_dir = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as cache_dir, tempfile.TemporaryDirectory() as bin_dir:
        os.symlink(os.path.join(fake_claude_dir, "fake_claude_fixture.sh"), os.path.join(bin_dir, "claude"))

        # A stray .html path in duplication's log — must never be mistaken
        # for its report now that the driver reads manifests, not logs.
        env = {
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "XDG_CACHE_HOME": cache_dir,
            "AUDITS_NO_OPEN": "1",
            "AUDITS_NO_SYNTH": "1",
        }
        r = subprocess.run(
            [sys.executable, os.path.join(fake_claude_dir, "driver.py"), tmp, "--only", "dead-code,duplication", "--out", os.path.join(tmp, "out")],
            capture_output=True, text=True, env=env,
        )
        assert r.returncode == 0, r.stdout + r.stderr

        # duplication's fake process printed a stray .html path to its own
        # log (see fake_claude_fixture.sh) and wrote no manifest — a
        # log-grepping collector would wrongly pick that path up.
        dup_log = open(os.path.join(tmp, "out", "logs", "duplication.log")).read()
        assert "unrelated-1234" in dup_log, "fixture setup: the stray path must land in duplication's own log"

        index_text = open(os.path.join(tmp, "out", "collection", "index.html")).read()
        assert "dead-code/report.html" in index_text, "the manifest-backed report must be linked"
        assert "unrelated-1234" not in index_text, "the driver must never pick up a stray path from a log"
        assert "no manifest" in index_text, "duplication (no manifest written) must render as a named failure"


def _init_git_repo(path):
    subprocess.run(["git", "init", "-q", path], check=True)
    subprocess.run(["git", "-C", path, "config", "user.email", "t@example.com"], check=True)
    subprocess.run(["git", "-C", path, "config", "user.name", "t"], check=True)
    open(os.path.join(path, "a.py"), "w").write("x = 1\n")
    subprocess.run(["git", "-C", path, "add", "."], check=True)
    subprocess.run(["git", "-C", path, "commit", "-q", "-m", "init"], check=True)


def test_cache_decision_bad_sha_forces_run():
    """AC: a bad/unknown last-run SHA on a real temp git repo must yield
    RUN — `git diff` against a SHA that doesn't exist can't prove the repo
    is unchanged, so it must never read as SKIP. The timestamp here is
    fresh (regression witness: an old timestamp would trip the backstop
    and pass even if the bad-SHA path itself silently read as unchanged —
    that's exactly the bug this test caught)."""
    with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as cache_dir:
        _init_git_repo(repo)
        record_path = driver._record_file(repo, cache_dir)
        driver.save_record(record_path, {
            "domain-drift": {
                "last_sha": "0" * 40,  # a SHA that was never a real commit
                "timestamp": driver._dt.datetime.now(driver._dt.timezone.utc).isoformat(),
                "report_dir": os.path.join(cache_dir, "nope"),
            }
        })
        d = driver.decide(repo, "domain-drift", ["CONTEXT.md"], base=cache_dir)
        assert d.run is True, d


def test_cache_decision_clean_recent_repo_skips():
    with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as cache_dir:
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
        d = driver.decide(repo, "domain-drift", ["CONTEXT.md"], base=cache_dir)
        assert d.run is False, d
        assert d.report_dir == report_dir


def test_corrupt_cache_record_forces_run():
    """#580: a truncated/corrupt record file must read as "no cached run",
    never crash the sweep — matches the old bash cache.py, whose crashing
    subprocess printed nothing, failed the `= "SKIP"` check, and let the
    audit run."""
    with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as cache_dir:
        _init_git_repo(repo)
        record_path = driver._record_file(repo, cache_dir)
        os.makedirs(os.path.dirname(record_path), exist_ok=True)
        with open(record_path, "w") as f:
            f.write('{"domain-drift": {"last_s')  # truncated mid-write
        d = driver.decide(repo, "domain-drift", ["CONTEXT.md"], base=cache_dir)
        assert d.run is True, d


def test_legacy_cache_entry_missing_report_dir_forces_run():
    with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as cache_dir:
        _init_git_repo(repo)
        sha = driver.head_sha(repo)
        driver.save_record(driver._record_file(repo, cache_dir), {
            "domain-drift": {
                "last_sha": sha,
                "timestamp": driver._dt.datetime.now(driver._dt.timezone.utc).isoformat(),
                # no "report_dir" — a legacy/incomplete entry
            }
        })
        d = driver.decide(repo, "domain-drift", ["CONTEXT.md"], base=cache_dir)
        assert d.run is True, d


def test_save_record_is_atomic_no_tmp_left_behind():
    with tempfile.TemporaryDirectory() as cache_dir:
        path = os.path.join(cache_dir, "sub", "record.json")
        driver.save_record(path, {"a": 1})
        assert json.load(open(path)) == {"a": 1}
        assert not os.path.exists(path + ".tmp")


def test_crashed_no_tests_probe_renders_could_not_determine_not_zero():
    """#559: a no-tests probe that crashes or returns garbage must render as
    "could not determine" in the sub-index and the main-index verdict —
    never as a silent zero, which would read as a clean 0%-no-tests repo."""
    with tempfile.TemporaryDirectory() as tmp:
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

        r = _run_driver("--index", "--out", tmp)
        assert r.returncode == 0, r.stdout + r.stderr

        index_text = open(os.path.join(tmp, "collection", "index.html")).read()
        assert "could not be determined" in index_text
        assert "0 with no tests" not in index_text

        sub = open(os.path.join(tmp, "collection", "mutation", "index.html")).read()
        assert "could not be determined" in sub


def test_mutation_run_dir_prunes_old_runs_and_makes_worktrees():
    """#606: mutation mode resolves its run folder through the same `RunDir`
    as the sweep, so it inherits the 3-day prune of old `run-*` dirs that it
    used to skip. No `claude` is needed: naming the module skips the prepass,
    and a module with no env manifest fails setup before any audit runs."""
    with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as cache_dir:
        _init_git_repo(repo)
        base = os.path.join(cache_dir, "all-audits")
        stale = os.path.join(base, "run-20200101-000000")
        os.makedirs(stale)
        os.utime(stale, (0, 0))

        r = subprocess.run(
            [sys.executable, os.path.join(os.path.dirname(__file__), "driver.py"), repo, "--mutation", "solver.py"],
            capture_output=True, text=True,
            env={**os.environ, "XDG_CACHE_HOME": cache_dir, "AUDITS_NO_OPEN": "1", "AUDITS_NO_SYNTH": "1"},
        )
        assert r.returncode == 0, r.stdout + r.stderr
        assert not os.path.exists(stale), "mutation mode must prune run dirs past the TTL"

        runs = [d for d in os.listdir(base) if d.startswith("run-")]
        assert len(runs) == 1, runs
        run_dir = os.path.join(base, runs[0])
        for sub in ("logs", "collection", "manifests", "worktrees"):
            assert os.path.isdir(os.path.join(run_dir, sub)), sub
        assert os.listdir(os.path.join(run_dir, "worktrees")) == [], "the worktree must be cleaned up on the setup-failure path"


def _seed_run_dir(tmp):
    run = driver.RunDir(
        root=tmp,
        logs=os.path.join(tmp, "logs"),
        collection=os.path.join(tmp, "collection"),
        manifests=os.path.join(tmp, "manifests"),
    )
    for d in (run.logs, run.collection, run.manifests):
        os.makedirs(d, exist_ok=True)
    return run


def test_plan_reuses_the_cached_report_and_runs_the_rest():
    """#606: the plan step decides alone — cache in, lists out. No audit
    process is spawned, so it needs a tmp dir and no fake `claude`."""
    with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as cache_dir:
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


def test_collect_copies_both_report_kinds_and_returns_the_index():
    """#606: the collect step assembles the collection from what is already
    on disk — a manifest for what ran, the cache dir for what was reused —
    and renders. Also needs only a tmp dir and no fake `claude`."""
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as srcdir:
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


def test_index_only_rebuild_spawns_nothing_and_needs_no_run_branch():
    """#606: `--index --out DIR` calls the collect step over an existing
    collection. Nothing is spawned — the PATH here holds no `claude` and no
    `git` — and no logs/ or manifests/ content is read."""
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as empty_bin:
        d = os.path.join(tmp, "collection", "dead-code")
        os.makedirs(d)
        open(os.path.join(d, "report.html"), "w").write("<html>x</html>")

        r = subprocess.run(
            [sys.executable, os.path.join(os.path.dirname(__file__), "driver.py"), "--index", "--out", tmp],
            capture_output=True, text=True,
            env={**os.environ, "PATH": empty_bin, "AUDITS_NO_OPEN": "1", "AUDITS_NO_SYNTH": "1"},
        )
        assert r.returncode == 0, r.stdout + r.stderr
        assert 'href="dead-code/report.html"' in open(os.path.join(tmp, "collection", "index.html")).read()
        assert os.listdir(os.path.join(tmp, "manifests")) == []
        assert os.listdir(os.path.join(tmp, "logs")) == []


def test_help_prints_the_docstring_and_an_unknown_flag_exits_2():
    """#606: argparse parses the flags and the module docstring is the help
    text, so the flag reference has one home (all-audits/SKILL.md points at
    it rather than restating it)."""
    driver_py = os.path.join(os.path.dirname(__file__), "driver.py")
    r = subprocess.run([sys.executable, driver_py, "--help"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.startswith("usage:"), r.stdout
    assert driver.__doc__.splitlines()[0] in r.stdout
    for flag in ("--out", "--only", "--short", "--index", "--force", "--mutation"):
        assert flag in r.stdout, flag

    bad = subprocess.run([sys.executable, driver_py, "--nope"], capture_output=True, text=True)
    assert bad.returncode == 2, bad.stdout + bad.stderr


def test_mutation_worktree_is_removed_even_when_the_failure_report_raises():
    """#606: worktree cleanup is one try/finally per worktree. Before it, an
    exception between `git worktree add` and the explicit cleanup call left
    the worktree registered and on disk; here the failure-report write is made
    to fail (unwritable collection) and the worktree must still be gone."""
    with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as run_dir:
        _init_git_repo(repo)
        logs, collection = os.path.join(run_dir, "logs"), os.path.join(run_dir, "collection")
        worktrees, manifests = os.path.join(run_dir, "worktrees"), os.path.join(run_dir, "manifests")
        for d in (logs, collection, worktrees, manifests):
            os.makedirs(d)
        os.chmod(collection, 0o555)  # the module has no env manifest, so the driver writes a setup-failure report here
        try:
            driver._run_mutation_module(repo, "solver.py", logs, collection, worktrees, manifests)
        except OSError:
            pass
        finally:
            os.chmod(collection, 0o755)
        assert os.listdir(worktrees) == [], "the worktree must be removed on every exit path"


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"{len(tests)} passed")


if __name__ == "__main__":
    main()
