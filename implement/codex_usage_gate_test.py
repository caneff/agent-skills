"""The Codex usage preflight (#1204): `codex-usage-gate.py` reads the usage
cache and answers with an exit status a controller can branch on — 0 proceed,
20 capped (skip, no run), 30 unknown (skip, no run), 40 under the size threshold.

Every run gets `HOME` set to its temporary directory, so the kill-switch file
(#1354) on the real box never reaches a test.

Seam: the script's command line — stdout line and exit status — against a
cache file under a temporary `$CODEX_HOME`. `PATH` is emptied so a stale or
missing cache cannot reach a real `codex app-server`.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
GATE = os.path.join(HERE, "codex-usage-gate.py")
DAY = 86400
SWITCH_REL = os.path.join(".config", "agent-skills", "codex-reviews-off")
GIT = shutil.which("git")

FAKE_CODEX = """#!{py}
import json, os, sys, time
for line in sys.stdin:
    msg = json.loads(line)
    if msg.get("id") == 1:
        print(json.dumps({{"id": 1, "result": {{}}}}), flush=True)
    elif msg.get("id") == 2:
        limits = json.loads(os.environ["FAKE_LIMITS"]) if os.environ.get("FAKE_LIMITS") else None
        print(json.dumps({{"id": 2, "result": {{"rateLimits": limits}}}}), flush=True)
"""

FAKE_GH = """#!{py}
import json, os, sys
# gh issue view <n> --json labels
n = sys.argv[3]
names = json.loads(os.environ.get("FAKE_LABELS", "{{}}")).get(n, [])
print(json.dumps({{"labels": [{{"name": x}} for x in names]}}))
"""


@pytest.fixture
def newdir(tmp_path_factory):
    """A factory of fresh, empty directories under pytest's temp dir."""
    return lambda: tmp_path_factory.mktemp("d")


def cache(pct, resets=None, fetched=None, secondary=None):
    now = time.time()
    return {
        "fetchedAt": now if fetched is None else fetched,
        "primary": {"usedPercent": pct, "windowDurationMins": 10080,
                    "resetsAt": now + 3 * DAY if resets is None else resets},
        "secondary": secondary,
    }


def run(newdir, cache, *args):
    """(exit status, stdout) with `cache` (a dict, a str, or None) as the cache file."""
    d = newdir()
    if cache is not None:
        (d / "usage-cache.json").write_text(cache if isinstance(cache, str) else json.dumps(cache))
    env = {"CODEX_HOME": str(d), "HOME": str(d), "PATH": "/nonexistent"}
    p = subprocess.run([sys.executable, GATE, *args], env=env, capture_output=True, text=True)
    return p.returncode, p.stdout


def run_live(newdir, stale_cache, limits, *args, switch=False):
    """A stale cache with a fake `codex app-server` answering `limits` (or nothing).

    Returns (exit status, stdout, the cache file's content after the run)."""
    d = newdir()
    path = d / "usage-cache.json"
    path.write_text(json.dumps(stale_cache))
    if switch:
        (d / ".config" / "agent-skills").mkdir(parents=True)
        (d / SWITCH_REL).touch()
    bindir = d / "bin"
    bindir.mkdir()
    fake = bindir / "codex"
    fake.write_text(FAKE_CODEX.format(py=sys.executable))
    fake.chmod(0o755)
    env = {"CODEX_HOME": str(d), "HOME": str(d), "PATH": str(bindir)}
    if limits is not None:
        env["FAKE_LIMITS"] = json.dumps(limits)
    p = subprocess.run([sys.executable, GATE, *args], env=env, capture_output=True, text=True)
    return p.returncode, p.stdout, json.loads(path.read_text())


def assert_gate(got, want_status, want_text=None):
    status, out = got
    assert status == want_status, f"exit {status}, want {want_status}: {out!r}"
    if want_text:
        assert want_text in out, f"{want_text!r} not in {out!r}"


# --- the usage read ---------------------------------------------------------


def test_headroom(newdir):
    assert_gate(run(newdir, cache(44)), 0, "44%")


# The reserve ceiling (#1359): a launch stops at 70%, so the weekly audit keeps the rest.
def test_one_below_the_ceiling(newdir):
    assert_gate(run(newdir, cache(69)), 0, "69%")


def test_at_the_ceiling_names_the_percent_and_reset(newdir):
    resets = time.time() + 2 * DAY
    status, out = run(newdir, cache(70, resets=resets))
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(resets))
    assert (status, out) == (20, f"usage 70% at or above reserve ceiling 70%, resets {when}\n"), (status, out)


def test_above_the_ceiling(newdir):
    assert_gate(run(newdir, cache(95)), 20, "reserve ceiling 70%")


# `--audit` lifts the ceiling to the 100% cap: the audit may spend the reserve.
def test_audit_above_the_ceiling(newdir):
    assert_gate(run(newdir, cache(95), "--audit"), 0, "95%")


def test_audit_at_the_cap(newdir):
    assert_gate(run(newdir, cache(100), "--audit"), 20, "capped")


def test_capped(newdir):
    status, out = run(newdir, cache(100, resets=time.time() + 5 * DAY))
    assert_gate((status, out), 20, "100%")
    # A PR gated at the cap answers the ceiling line, never a line of its own: the audit reads only
    # `ceiling` skip rows, so a cap-worded line would leave that PR out of the audit for good (#1405 C1).
    assert "reserve ceiling 70%" in out and "capped" not in out, out
    assert "resets" in out and time.strftime("%Y-%m-%d", time.localtime(time.time() + 5 * DAY)) in out, out


def test_over_100(newdir):
    assert_gate(run(newdir, cache(103)), 20, "reserve ceiling 70%")


# The worst window governs.
def test_secondary_governs(newdir):
    assert_gate(run(newdir, cache(10, secondary={"usedPercent": 100, "resetsAt": time.time() + DAY})), 20)


# Absent or malformed is never headroom.
@pytest.mark.parametrize("make", [
    pytest.param(lambda: None, id="no cache"),
    pytest.param(lambda: cache(5, fetched=time.time() - 3600), id="stale cache"),
    pytest.param(lambda: "not json", id="corrupt cache"),
    pytest.param(lambda: cache("5"), id="string percent"),
    pytest.param(lambda: {"fetchedAt": time.time(), "primary": None, "secondary": None}, id="null primary"),
    pytest.param(lambda: {"fetchedAt": time.time(), "primary": {"usedPercent": 5}}, id="no reset time"),
    pytest.param(lambda: cache(100, resets=time.time() - 60), id="rolled-over window"),
    pytest.param(lambda: cache(True), id="bool percent"),
    # Values json.loads accepts that are not a usage percentage or a reset time.
    pytest.param(lambda: '{"fetchedAt": %f, "primary": {"usedPercent": NaN, "resetsAt": %f}}'
                 % (time.time(), time.time() + DAY), id="NaN percent"),
    pytest.param(lambda: cache(-5), id="negative percent"),
    pytest.param(lambda: '{"fetchedAt": %f, "primary": {"usedPercent": 100, "resetsAt": Infinity}}'
                 % time.time(), id="infinite reset"),
    pytest.param(lambda: "[]", id="list cache"),
    pytest.param(lambda: "5", id="scalar cache"),
])
def test_absent_or_malformed_cache_is_unknown(newdir, make):
    assert_gate(run(newdir, make()), 30)


# A stale cache is refreshed from the live answer, and the refreshed reading —
# not the stale one — decides. The stale cache says 5%; the live answer says 100%.
def test_refresh_reads_live(newdir):
    stale = cache(5, fetched=time.time() - 3600)
    live = {"usedPercent": 100, "resetsAt": time.time() + 4 * DAY}
    status, out, after = run_live(newdir, stale, {"primary": live, "secondary": None})
    assert_gate((status, out), 20, "100%")
    assert "reserve ceiling 70%" in out, out
    assert after["primary"]["usedPercent"] == 100, f"cache not rewritten: {after}"
    assert time.time() - after["fetchedAt"] < 60, f"fetchedAt not renewed: {after}"


def test_refresh_returns_nothing(newdir):
    stale = cache(5, fetched=time.time() - 3600)
    status, out, after = run_live(newdir, stale, None)
    assert_gate((status, out), 30)
    assert after == stale, f"a failed refresh must leave the cache alone: {after}"


# --- --percent ---------------------------------------------------------------
# `--percent` (#1269) prints the worst window's percentage and reset time from a live read,
# never the cache: a cached 10% must not stand in for the 12% the pass just spent.


def test_percent_reads_live_not_the_cache(newdir):
    reset = int(time.time() + 4 * DAY)
    live = {"primary": {"usedPercent": 12.5, "resetsAt": reset}, "secondary": None}
    status, out, _ = run_live(newdir, cache(10), live, "--percent")
    assert (status, out) == (0, f"12.5 {reset}\n"), (status, out)


# The worst window governs, and its reset time names it.
def test_percent_worst_window_governs(newdir):
    reset = int(time.time() + 4 * DAY)
    live = {"primary": {"usedPercent": 5, "resetsAt": reset},
            "secondary": {"usedPercent": 30, "resetsAt": reset + DAY}}
    assert run_live(newdir, cache(10), live, "--percent")[:2] == (0, f"30 {reset + DAY}\n")


# A fresh-looking cache with no live answer is unknown, never the cached number.
def test_percent_fresh_cache_without_live_answer_is_unknown(newdir):
    status, out, _ = run_live(newdir, cache(10), None, "--percent")
    assert (status, out) == (30, "unknown\n"), (status, out)


def test_percent_rolled_over_live_window_is_unknown(newdir):
    live = {"primary": {"usedPercent": 5, "resetsAt": time.time() - 60}, "secondary": None}
    assert run_live(newdir, cache(10), live, "--percent")[:2] == (30, "unknown\n")


def test_percent_with_no_cache_is_unknown(newdir):
    assert run(newdir, None, "--percent") == (30, "unknown\n")


# --- the kill switch ---------------------------------------------------------
# The kill switch (#1354): `~/.config/agent-skills/codex-reviews-off`, any content, turns the
# gate to CAPPED before any cache read or live fetch.


def run_switch(newdir, content, *args):
    """(exit status, stdout, switch path) with the switch file under a temporary HOME holding
    `content` (None: no file), and a headroom cache that would proceed if it were read."""
    d = newdir()
    path = d / SWITCH_REL
    if content is not None:
        path.parent.mkdir(parents=True)
        path.write_text(content)
    (d / "usage-cache.json").write_text(json.dumps(cache(5)))
    env = {"CODEX_HOME": str(d), "HOME": str(d), "PATH": "/nonexistent"}
    p = subprocess.run([sys.executable, GATE, *args], env=env, capture_output=True, text=True)
    return p.returncode, p.stdout, str(path)


@pytest.mark.parametrize("content", ["", "off\n"], ids=["empty", "any content"])
def test_switch_present_is_capped(newdir, content):
    status, out, path = run_switch(newdir, content)
    want = f"codex reviews off by Chris's ruling ({path}) — remove the file to re-enable\n"
    assert (status, out) == (20, want), f"switch {content!r}: {(status, out)!r}"


def test_switch_absent(newdir):
    status, out, _ = run_switch(newdir, None)
    assert_gate((status, out), 0, "5%")


# The audit's launch is still a launch: the switch wins over `--audit` too.
def test_switch_beats_audit(newdir):
    assert_gate(run_switch(newdir, "", "--audit")[:2], 20, "codex reviews off")


# `--percent` is a reading, not a launch: the switch leaves it alone.
# A number in the output proves the switch was ignored: honouring it would print no number.
def test_switch_leaves_percent_alone(newdir):
    reset = int(time.time() + 4 * DAY)
    live = {"primary": {"usedPercent": 12.5, "resetsAt": reset}, "secondary": None}
    status, out, _ = run_live(newdir, cache(10), live, "--percent", switch=True)
    assert (status, out) == (0, f"12.5 {reset}\n"), (status, out)


# With the switch present the helper is never loaded: a disabled gate costs no RPC.
def test_switch_loads_no_helper(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    path = tmp_path / SWITCH_REL
    path.parent.mkdir(parents=True)
    path.touch()
    spec = importlib.util.spec_from_file_location("gate", GATE)
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)

    def boom():
        raise AssertionError("load_helper called with the kill switch present")

    monkeypatch.setattr(gate, "load_helper", boom)
    assert gate.check() == (20, f"codex reviews off by Chris's ruling ({path}) — remove the file to re-enable")


# --- the size check ----------------------------------------------------------
# The size check (#1358): `--base <ref> --tickets <n>...` makes the gate measure the PR branch's
# churn against <ref> (added plus deleted lines outside tests and Markdown) and answer 40 when it
# is under SIZE_THRESHOLD, before any usage read. A `needs-codex` label on any ticket bypasses it.


def write_lines(root, rel, count):
    """`count` lines at `rel`, or `count` itself when it is bytes (a binary file)."""
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path) or root, exist_ok=True)
    with open(path, "wb") as f:
        f.write(count if isinstance(count, bytes) else "".join(f"line {i}\n" for i in range(count)).encode())


def fake_repo(newdir, changes, base_files=None, moves=(), labels=None, pct=5, switch=False, stale=False):
    """Returns (repo, env): a fabricated repo whose `main` holds `seed.py` and `base_files`
    ({path: line count}), and whose checked-out `pr` branch renames each (src, dst) of `moves`
    and writes `changes` on top. `labels` maps a ticket number to its label names, served by a
    fake `gh`; `env` runs the gate there with a `pct` usage cache and, with `switch`, the kill
    switch. With `stale` the cache is an hour old, so any usage read runs the fake `codex`, which
    leaves `<HOME>/codex-called` behind."""
    d = str(newdir())
    repo = os.path.join(d, "repo")
    os.mkdir(repo)
    bindir = os.path.join(d, "bin")
    os.mkdir(bindir)
    os.symlink(GIT, os.path.join(bindir, "git"))
    with open(os.path.join(bindir, "gh"), "w") as f:
        f.write(FAKE_GH.format(py=sys.executable))
    os.chmod(os.path.join(bindir, "gh"), 0o755)
    with open(os.path.join(d, "fake_codex.py"), "w") as f:
        f.write(FAKE_CODEX.format(py=sys.executable))
    with open(os.path.join(bindir, "codex"), "w") as f:
        f.write(f'#!/bin/sh\n: >"{d}/codex-called"\nexec {sys.executable} "{d}/fake_codex.py"\n')
    os.chmod(os.path.join(bindir, "codex"), 0o755)
    genv = {"HOME": d, "PATH": bindir, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}

    def g(*a):
        return subprocess.run([GIT, *a], cwd=repo, env=genv, check=True, capture_output=True)

    g("init", "-q", "-b", "main")
    for rel, count in dict({"seed.py": 3}, **(base_files or {})).items():
        write_lines(repo, rel, count)
    g("add", "-A")
    g("commit", "-qm", "base")
    g("checkout", "-qb", "pr")
    for src, dst in moves:
        g("mv", src, dst)
    for rel, count in changes.items():
        write_lines(repo, rel, count)
    g("add", "-A")
    g("commit", "-q", "--allow-empty", "-m", "pr")
    with open(os.path.join(d, "usage-cache.json"), "w") as f:
        json.dump(cache(pct, fetched=time.time() - 3600 if stale else None), f)
    if switch:
        os.makedirs(os.path.join(d, ".config", "agent-skills"))
        open(os.path.join(d, SWITCH_REL), "w").close()
    return repo, dict(genv, CODEX_HOME=d, FAKE_LABELS=json.dumps(labels or {}))


def run_size(newdir, changes, tickets=("1",), base="main", **repo):
    """(exit status, stdout) of the gate run with `--base` and `--tickets` in a `fake_repo`."""
    cwd, env = fake_repo(newdir, changes, **repo)
    p = subprocess.run([sys.executable, GATE, "--base", base, "--tickets", *tickets],
                       cwd=cwd, env=env, capture_output=True, text=True)
    return p.returncode, p.stdout


def test_size_at_threshold(newdir):
    assert_gate(run_size(newdir, {"a.py": 300}), 0, "5%")


# A proceed says why it proceeded (#1405 P1): the churn that passed the threshold, or the label
# that forced a small PR on, with the churn it overrode.
def test_proceed_names_churn(newdir):
    assert_gate(run_size(newdir, {"a.py": 300}), 0, "churn 300 >= 300")


def test_proceed_names_label(newdir):
    assert_gate(run_size(newdir, {"a.py": 5}, labels={"1": ["needs-codex"]}), 0,
          "needs-codex label forced it, churn 5 < 300")


def test_no_size_check_no_churn_in_the_line(newdir):
    assert "churn" not in run(newdir, cache(5))[1], "no size check, no churn in the line"


def test_size_just_under_threshold(newdir):
    assert run_size(newdir, {"a.py": 299}) == (40, "under size threshold (299 < 300)\n")


def test_size_far_above(newdir):
    assert_gate(run_size(newdir, {"a.py": 5000}), 0, "5%")


# Tests and Markdown carry no churn: 2000 lines of them plus 10 counted lines is 10.
TESTS_MD = {"README.md": 400, "docs/x.md": 400, "a_test.py": 400, "b.test.sh": 400,
            "tool/audit.py": 200, "tests/helper.py": 100, "pkg/tests/fixture.json": 100}


def test_tests_and_markdown_carry_no_churn(newdir):
    assert run_size(newdir, TESTS_MD) == (40, "under size threshold (0 < 300)\n")


def test_tests_and_markdown_beside_counted_lines(newdir):
    assert run_size(newdir, dict(TESTS_MD, **{"x.sh": 10})) == (40, "under size threshold (10 < 300)\n")


# Deleted lines count beside added ones: the PR's 3 seed lines removed and 297 added is 300.
def test_deletions_count(newdir):
    assert_gate(run_size(newdir, {"seed.py": 0, "b.py": 297}), 0, "5%")


# The forcing label, on any ticket of the clump, sends a small PR on to the usage read.
def test_label_forces(newdir):
    assert_gate(run_size(newdir, {"a.py": 5}, tickets=("7", "8"), labels={"8": ["needs-codex"]}), 0, "5%")


# The label never bypasses the reserve ceiling.
def test_ceiling_beats_label(newdir):
    assert_gate(run_size(newdir, {"a.py": 5}, labels={"1": ["needs-codex"]}, pct=70), 20,
          "usage 70% at or above reserve ceiling 70%")


def test_ceiling_beats_a_large_pr(newdir):
    assert_gate(run_size(newdir, {"a.py": 5000}, pct=70), 20, "reserve ceiling 70%")


def test_other_labels_do_not_force(newdir):
    assert run_size(newdir, {"a.py": 5}, labels={"1": ["ready-for-agent", "codex"]})[0] == 40


# The label bypasses the size check only: the kill switch still wins.
def test_switch_beats_label(newdir):
    assert_gate(run_size(newdir, {"a.py": 5}, labels={"1": ["needs-codex"]}, switch=True), 20, "codex reviews off")


def test_switch_beats_a_large_pr(newdir):
    assert_gate(run_size(newdir, {"a.py": 5000}, switch=True), 20, "codex reviews off")


def test_switch_beats_a_small_pr(newdir):
    assert_gate(run_size(newdir, {"a.py": 5}, switch=True), 20, "codex reviews off")


# A binary file has no lines to review: it counts 0 and does not break the count.
def test_binary_file_counts_zero(newdir):
    assert run_size(newdir, {"img.png": b"\x00\x89PNG" * 100, "a.py": 5}) == (
        40, "under size threshold (5 < 300)\n")


# Every suite `tests/all.sh` discovers in this repo is a test file the size check skips, so the
# gate's patterns cannot drift from the discovery rules unnoticed. Cargo manifests are not tests.
def test_every_discovered_suite_is_skipped_by_the_size_check(newdir):
    suites = subprocess.run(["bash", os.path.join(HERE, "..", "tests", "all.sh"), "--list"],
                            cwd=HERE, capture_output=True, text=True, check=True).stdout.split("\n")
    suites = [x.removesuffix(" --selfcheck") for x in suites if x and not x.endswith("Cargo.toml")]
    # A mod folder (`flow/mods/<name>`) is one suite label for the `*.test.ts` files inside it.
    repo = os.path.join(HERE, "..")
    mod_tests = [os.path.relpath(os.path.join(d, f), repo)
                 for x in suites if os.path.isdir(os.path.join(repo, x))
                 for d, _, files in os.walk(os.path.join(repo, x)) for f in files if f.endswith(".test.ts")]
    assert mod_tests, suites
    suites = [x for x in suites if not os.path.isdir(os.path.join(repo, x))] + mod_tests
    assert len(suites) > 50, suites
    got = run_size(newdir, {x: 1 for x in suites})
    assert got == (40, "under size threshold (0 < 300)\n"), got


# A pure rename carries no churn, not a 400-line delete plus a 400-line add, and the paths after
# it still parse (`-z` writes a rename's two paths as fields of their own).
def test_pure_rename_carries_no_churn(newdir):
    assert run_size(newdir, {"z.py": 10}, base_files={"big.py": 400}, moves=[("big.py", "moved.py")]) == (
        40, "under size threshold (10 < 300)\n")


# A size skip answers before any usage read: with a stale cache any read would run `codex`, and
# it never runs. The labelled control proves the marker does appear when the read happens.
@pytest.mark.parametrize("labels, want_status, want_called", [
    pytest.param({}, 40, False, id="size skip reads no usage"),
    pytest.param({"1": ["needs-codex"]}, 30, True, id="labelled control reads usage"),
])
def test_size_skip_answers_before_any_usage_read(newdir, labels, want_status, want_called):
    cwd, env = fake_repo(newdir, {"a.py": 5}, labels=labels, stale=True)
    p = subprocess.run([sys.executable, GATE, "--base", "main", "--tickets", "1"],
                       cwd=cwd, env=env, capture_output=True, text=True)
    called = os.path.exists(os.path.join(env["HOME"], "codex-called"))
    assert (p.returncode, called) == (want_status, want_called), (labels, p.returncode, p.stdout, called)


# Malformed size arguments are unknown (30) with a usage line, never a silent full-size pass.
@pytest.mark.parametrize("bad", [
    ["--base", "main"], ["--base", "main", "--tickets"], ["--tickets", "1"],
    ["--base", "main", "--tickets", "#1"], ["--audit", "--base", "main", "--tickets", "1"],
    ["--bogus"], ["--help"], ["-h"], ["--perc"], ["--base", "main", "--tickets", "1", "stray"],
    ["--percent", "--audit"], ["--percent", "--base", "main", "--tickets", "1"], ["stray"],
    ["--audit", "--audit"], ["--base", "main", "--tickets", "1", "--tickets", "2"],
    ["--base", "a", "--tickets", "1", "--base", "b"],
], ids=" ".join)
def test_malformed_size_arguments_are_unknown_with_usage(newdir, bad):
    status, out = run(newdir, cache(5), *bad)
    assert status == 30 and out.startswith("usage: codex-usage-gate.py"), (bad, status, out)


# Flag order is free (#1405 OE1): the same arguments, tickets first.
def test_flag_order_is_free(newdir):
    cwd, env = fake_repo(newdir, {"a.py": 5000})
    p = subprocess.run([sys.executable, GATE, "--tickets", "1", "2", "--base", "main"],
                       cwd=cwd, env=env, capture_output=True, text=True)
    assert (p.returncode, "5%" in p.stdout) == (0, True), (p.returncode, p.stdout)


# A usage refusal names its cause, after the usage line (#1405 S1).
def test_usage_refusal_names_its_cause(newdir):
    status, out = run(newdir, cache(5), "--base", "main", "--tickets", "#1")
    assert status == 30 and "not a ticket number: '#1'" in out, (status, out)


# `--help` must not be argparse's own exit 0, which a caller reads as proceed.
def test_help_is_not_a_proceed(newdir):
    status, out = run(newdir, cache(5), "--help")
    assert status == 30 and out.startswith("usage: codex-usage-gate.py"), (status, out)


# A base git cannot resolve is unknown, never a size verdict either way, and the line names git's
# own error rather than a usage read that never happened.
def test_unresolvable_base_is_unknown(newdir):
    status, out = run_size(newdir, {"a.py": 5}, base="nope")
    assert status == 30 and out.startswith("size check failed: `git diff") and "nope" in out, (status, out)


# A diff with no files at all is HEAD sitting at the base — the wrong checkout — never a 0-line PR.
def test_empty_diff_is_the_wrong_checkout(newdir):
    status, out = run_size(newdir, {})
    assert (status, out) == (30, "size check failed: main...HEAD changes no files — run from the PR's workspace\n"), (
        status, out)


# A missing `gh` is a size check that failed too, never `codex usage unknown` for a read that never ran.
def test_missing_gh_is_a_failed_size_check(newdir):
    cwd, env = fake_repo(newdir, {"a.py": 5})
    os.remove(os.path.join(env["HOME"], "bin", "gh"))
    p = subprocess.run([sys.executable, GATE, "--base", "main", "--tickets", "1"], cwd=cwd, env=env,
                       capture_output=True, text=True)
    assert p.returncode == 30 and p.stdout.startswith("size check failed: ") and "'gh'" in p.stdout, p.stdout
