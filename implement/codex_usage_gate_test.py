#!/usr/bin/env python3
"""The Codex usage preflight (#1204): `codex-usage-gate.py` reads the usage
cache and answers with an exit status a controller can branch on — 0 proceed,
20 capped (skip, no run), 30 unknown (skip, no run), 40 under the size threshold.

Every run gets `HOME` set to its temporary directory, so the kill-switch file
(#1354) on the real box never reaches a test.

Seam: the script's command line — stdout line and exit status — against a
cache file under a temporary `$CODEX_HOME`. `PATH` is emptied so a stale or
missing cache cannot reach a real `codex app-server`.
"""
import contextlib
import importlib.util
import shutil
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
GATE = os.path.join(HERE, "codex-usage-gate.py")
DAY = 86400


def run(cache, *args):
    """(exit status, stdout) with `cache` (a dict, a str, or None) as the cache file."""
    with tempfile.TemporaryDirectory() as d:
        if cache is not None:
            with open(os.path.join(d, "usage-cache.json"), "w") as f:
                f.write(cache if isinstance(cache, str) else json.dumps(cache))
        env = {"CODEX_HOME": d, "HOME": d, "PATH": "/nonexistent"}
        p = subprocess.run([sys.executable, GATE, *args], env=env, capture_output=True, text=True)
        return p.returncode, p.stdout


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


def run_live(stale_cache, limits, *args, switch=False):
    """A stale cache with a fake `codex app-server` answering `limits` (or nothing).

    Returns (exit status, stdout, the cache file's content after the run)."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "usage-cache.json")
        with open(path, "w") as f:
            json.dump(stale_cache, f)
        if switch:
            os.makedirs(os.path.join(d, ".config", "agent-skills"))
            open(os.path.join(d, ".config", "agent-skills", "codex-reviews-off"), "w").close()
        bindir = os.path.join(d, "bin")
        os.mkdir(bindir)
        fake = os.path.join(bindir, "codex")
        with open(fake, "w") as f:
            f.write(FAKE_CODEX.format(py=sys.executable))
        os.chmod(fake, 0o755)
        env = {"CODEX_HOME": d, "HOME": d, "PATH": bindir}
        if limits is not None:
            env["FAKE_LIMITS"] = json.dumps(limits)
        p = subprocess.run([sys.executable, GATE, *args], env=env, capture_output=True, text=True)
        return p.returncode, p.stdout, json.load(open(path))


def cache(pct, resets=None, fetched=None, secondary=None):
    now = time.time()
    return {
        "fetchedAt": now if fetched is None else fetched,
        "primary": {"usedPercent": pct, "windowDurationMins": 10080,
                    "resetsAt": now + 3 * DAY if resets is None else resets},
        "secondary": secondary,
    }


def check(name, got, want_status, want_text=None):
    status, out = got
    assert status == want_status, f"{name}: exit {status}, want {want_status}: {out!r}"
    if want_text:
        assert want_text in out, f"{name}: {want_text!r} not in {out!r}"


check("headroom", run(cache(44)), 0, "44%")
# The reserve ceiling (#1359): a launch stops at 70%, so the weekly audit keeps the rest.
check("one below the ceiling", run(cache(69)), 0, "69%")
resets = time.time() + 2 * DAY
status, out = run(cache(70, resets=resets))
when = time.strftime("%Y-%m-%d %H:%M", time.localtime(resets))
assert (status, out) == (20, f"usage 70% at or above reserve ceiling 70%, resets {when}\n"), (status, out)
check("above the ceiling", run(cache(95)), 20, "reserve ceiling 70%")
# `--audit` lifts the ceiling to the 100% cap: the audit may spend the reserve.
check("audit above the ceiling", run(cache(95), "--audit"), 0, "95%")
check("audit at the cap", run(cache(100), "--audit"), 20, "capped")
status, out = run(cache(100, resets=time.time() + 5 * DAY))
check("capped", (status, out), 20, "100%")
assert "resets" in out and time.strftime("%Y-%m-%d", time.localtime(time.time() + 5 * DAY)) in out, out
check("over 100", run(cache(103)), 20)
# The worst window governs.
check("secondary governs",
      run(cache(10, secondary={"usedPercent": 100, "resetsAt": time.time() + DAY})), 20)
# Absent or malformed is never headroom.
check("no cache", run(None), 30)
check("stale cache", run(cache(5, fetched=time.time() - 3600)), 30)
check("corrupt cache", run("not json"), 30)
check("string percent", run(cache("5")), 30)
check("null primary", run({"fetchedAt": time.time(), "primary": None, "secondary": None}), 30)
check("no reset time", run({"fetchedAt": time.time(), "primary": {"usedPercent": 5}}), 30)
check("rolled-over window", run(cache(100, resets=time.time() - 60)), 30)
check("bool percent", run(cache(True)), 30)
# Values json.loads accepts that are not a usage percentage or a reset time.
check("NaN percent", run('{"fetchedAt": %f, "primary": {"usedPercent": NaN, "resetsAt": %f}}'
                         % (time.time(), time.time() + DAY)), 30)
check("negative percent", run(cache(-5)), 30)
check("infinite reset", run('{"fetchedAt": %f, "primary": {"usedPercent": 100, "resetsAt": Infinity}}'
                            % time.time()), 30)
check("list cache", run("[]"), 30)
check("scalar cache", run("5"), 30)
# A stale cache is refreshed from the live answer, and the refreshed reading —
# not the stale one — decides. The stale cache says 5%; the live answer says 100%.
stale = cache(5, fetched=time.time() - 3600)
live = {"usedPercent": 100, "resetsAt": time.time() + 4 * DAY}
status, out, after = run_live(stale, {"primary": live, "secondary": None})
check("refresh reads live", (status, out), 20, "100%")
assert after["primary"]["usedPercent"] == 100, f"cache not rewritten: {after}"
assert time.time() - after["fetchedAt"] < 60, f"fetchedAt not renewed: {after}"
status, out, after = run_live(stale, None)
check("refresh returns nothing", (status, out), 30)
assert after == stale, f"a failed refresh must leave the cache alone: {after}"
print("ok")

# `--percent` (#1269) prints the worst window's percentage and reset time from a live read,
# never the cache: a cached 10% must not stand in for the 12% the pass just spent.
fresh = cache(10)
reset = int(time.time() + 4 * DAY)
live = {"primary": {"usedPercent": 12.5, "resetsAt": reset}, "secondary": None}
status, out, _ = run_live(fresh, live, "--percent")
assert (status, out) == (0, f"12.5 {reset}\n"), (status, out)
# The worst window governs, and its reset time names it.
live2 = {"primary": {"usedPercent": 5, "resetsAt": reset}, "secondary": {"usedPercent": 30, "resetsAt": reset + DAY}}
assert run_live(fresh, live2, "--percent")[:2] == (0, f"30 {reset + DAY}\n")
# A fresh-looking cache with no live answer is unknown, never the cached number.
status, out, _ = run_live(fresh, None, "--percent")
assert (status, out) == (30, "unknown\n"), (status, out)
assert run_live(fresh, {"primary": {"usedPercent": 5, "resetsAt": time.time() - 60}, "secondary": None},
                "--percent")[:2] == (30, "unknown\n")
assert run(None, "--percent") == (30, "unknown\n")
print("ok percent")

# The kill switch (#1354): `~/.config/agent-skills/codex-reviews-off`, any content, turns the
# gate to CAPPED before any cache read or live fetch.
SWITCH_REL = os.path.join(".config", "agent-skills", "codex-reviews-off")


def run_switch(content, *args):
    """(exit status, stdout, switch path) with the switch file under a temporary HOME holding
    `content` (None: no file), and a headroom cache that would proceed if it were read."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, SWITCH_REL)
        if content is not None:
            os.makedirs(os.path.dirname(path))
            with open(path, "w") as f:
                f.write(content)
        with open(os.path.join(d, "usage-cache.json"), "w") as f:
            json.dump(cache(5), f)
        env = {"CODEX_HOME": d, "HOME": d, "PATH": "/nonexistent"}
        p = subprocess.run([sys.executable, GATE, *args], env=env, capture_output=True, text=True)
        return p.returncode, p.stdout, path


for content in ("", "off\n"):
    status, out, path = run_switch(content)
    want = f"codex reviews off by Chris's ruling ({path}) — remove the file to re-enable\n"
    assert (status, out) == (20, want), f"switch {content!r}: {(status, out)!r}"
status, out, _ = run_switch(None)
check("switch absent", (status, out), 0, "5%")
# The audit's launch is still a launch: the switch wins over `--audit` too.
check("switch beats audit", run_switch("", "--audit")[:2], 20, "codex reviews off")
# `--percent` is a reading, not a launch: the switch leaves it alone.
# A number in the output proves the switch was ignored: honouring it would print no number.
reset = int(time.time() + 4 * DAY)
live = {"primary": {"usedPercent": 12.5, "resetsAt": reset}, "secondary": None}
status, out, _ = run_live(cache(10), live, "--percent", switch=True)
assert (status, out) == (0, f"12.5 {reset}\n"), (status, out)

# With the switch present the helper is never loaded: a disabled gate costs no RPC.
with tempfile.TemporaryDirectory() as d:
    saved_home = os.environ.get("HOME")
    os.environ["HOME"] = d
    path = os.path.join(d, SWITCH_REL)
    os.makedirs(os.path.dirname(path))
    open(path, "w").close()
    spec = importlib.util.spec_from_file_location("gate", GATE)
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)

    def boom():
        raise AssertionError("load_helper called with the kill switch present")
    gate.load_helper = boom
    try:
        assert gate.check() == (20, f"codex reviews off by Chris's ruling ({path}) — remove the file to re-enable")
    finally:
        if saved_home is None:
            del os.environ["HOME"]
        else:
            os.environ["HOME"] = saved_home
print("ok kill switch")

# The size check (#1358): `--base <ref> --tickets <n>...` makes the gate measure the PR branch's
# churn against <ref> (added plus deleted lines outside tests and Markdown) and answer 40 when it
# is under SIZE_THRESHOLD, before any usage read. A `needs-codex` label on any ticket bypasses it.
GIT = shutil.which("git")
FAKE_GH = """#!{py}
import json, os, sys
# gh issue view <n> --json labels
n = sys.argv[3]
names = json.loads(os.environ.get("FAKE_LABELS", "{{}}")).get(n, [])
print(json.dumps({{"labels": [{{"name": x}} for x in names]}}))
"""


def write_lines(root, rel, count):
    """`count` lines at `rel`, or `count` itself when it is bytes (a binary file)."""
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path) or root, exist_ok=True)
    with open(path, "wb") as f:
        f.write(count if isinstance(count, bytes) else "".join(f"line {i}\n" for i in range(count)).encode())


@contextlib.contextmanager
def fake_repo(changes, base_files=None, moves=(), labels=None, pct=5, switch=False, stale=False):
    """Yields (repo, env): a fabricated repo whose `main` holds `seed.py` and `base_files`
    ({path: line count}), and whose checked-out `pr` branch renames each (src, dst) of `moves`
    and writes `changes` on top. `labels` maps a ticket number to its label names, served by a
    fake `gh`; `env` runs the gate there with a `pct` usage cache and, with `switch`, the kill
    switch. With `stale` the cache is an hour old, so any usage read runs the fake `codex`, which
    leaves `<HOME>/codex-called` behind."""
    with tempfile.TemporaryDirectory() as d:
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
        g = lambda *a: subprocess.run([GIT, *a], cwd=repo, env=genv, check=True, capture_output=True)
        g("init", "-q", "-b", "main")
        for rel, count in dict({"seed.py": 3}, **(base_files or {})).items():
            write_lines(repo, rel, count)
        g("add", "-A"); g("commit", "-qm", "base")
        g("checkout", "-qb", "pr")
        for src, dst in moves:
            g("mv", src, dst)
        for rel, count in changes.items():
            write_lines(repo, rel, count)
        g("add", "-A"); g("commit", "-q", "--allow-empty", "-m", "pr")
        with open(os.path.join(d, "usage-cache.json"), "w") as f:
            json.dump(cache(pct, fetched=time.time() - 3600 if stale else None), f)
        if switch:
            os.makedirs(os.path.join(d, ".config", "agent-skills"))
            open(os.path.join(d, SWITCH_REL), "w").close()
        yield repo, dict(genv, CODEX_HOME=d, FAKE_LABELS=json.dumps(labels or {}))


def run_size(changes, tickets=("1",), base="main", **repo):
    """(exit status, stdout) of the gate run with `--base` and `--tickets` in a `fake_repo`."""
    with fake_repo(changes, **repo) as (cwd, env):
        p = subprocess.run([sys.executable, GATE, "--base", base, "--tickets", *tickets],
                           cwd=cwd, env=env, capture_output=True, text=True)
        return p.returncode, p.stdout


check("size at threshold", run_size({"a.py": 300}), 0, "5%")
assert run_size({"a.py": 299}) == (40, "under size threshold (299 < 300)\n"), run_size({"a.py": 299})
check("size far above", run_size({"a.py": 5000}), 0, "5%")
# Tests and Markdown carry no churn: 2000 lines of them plus 10 counted lines is 10.
tests_md = {"README.md": 400, "docs/x.md": 400, "a_test.py": 400, "b.test.sh": 400,
            "tool/audit.py": 200, "tests/helper.py": 100, "pkg/tests/fixture.json": 100}
assert run_size(tests_md) == (40, "under size threshold (0 < 300)\n"), run_size(tests_md)
assert run_size(dict(tests_md, **{"x.sh": 10})) == (40, "under size threshold (10 < 300)\n")
# Deleted lines count beside added ones: the PR's 3 seed lines removed and 297 added is 300.
check("deletions count", run_size({"seed.py": 0, "b.py": 297}), 0, "5%")
# The forcing label, on any ticket of the clump, sends a small PR on to the usage read.
check("label forces", run_size({"a.py": 5}, tickets=("7", "8"), labels={"8": ["needs-codex"]}), 0, "5%")
# The label never bypasses the reserve ceiling.
check("ceiling beats label", run_size({"a.py": 5}, labels={"1": ["needs-codex"]}, pct=70), 20,
      "usage 70% at or above reserve ceiling 70%")
check("ceiling beats a large PR", run_size({"a.py": 5000}, pct=70), 20, "reserve ceiling 70%")
assert run_size({"a.py": 5}, labels={"1": ["ready-for-agent", "codex"]})[0] == 40
# The label bypasses the size check only: the kill switch still wins.
status, out = run_size({"a.py": 5}, labels={"1": ["needs-codex"]}, switch=True)
check("switch beats label", (status, out), 20, "codex reviews off")
check("switch beats a large PR", run_size({"a.py": 5000}, switch=True), 20, "codex reviews off")
check("switch beats a small PR", run_size({"a.py": 5}, switch=True), 20, "codex reviews off")
# A binary file has no lines to review: it counts 0 and does not break the count.
assert run_size({"img.png": b"\x00\x89PNG" * 100, "a.py": 5}) == (40, "under size threshold (5 < 300)\n")
# Every suite `tests/all.sh` discovers in this repo is a test file the size check skips, so the
# gate's patterns cannot drift from the discovery rules unnoticed. Cargo manifests are not tests.
suites = subprocess.run(["bash", os.path.join(HERE, "..", "tests", "all.sh"), "--list"],
                        cwd=HERE, capture_output=True, text=True, check=True).stdout.split("\n")
suites = [x.removesuffix(" --selfcheck") for x in suites if x and not x.endswith("Cargo.toml")]
assert len(suites) > 50, suites
assert run_size({x: 1 for x in suites}) == (40, "under size threshold (0 < 300)\n"), run_size({x: 1 for x in suites})
# A pure rename carries no churn, not a 400-line delete plus a 400-line add, and the paths after
# it still parse (`-z` writes a rename's two paths as fields of their own).
assert run_size({"z.py": 10}, base_files={"big.py": 400}, moves=[("big.py", "moved.py")]) == (
    40, "under size threshold (10 < 300)\n")
# A size skip answers before any usage read: with a stale cache any read would run `codex`, and
# it never runs. The labelled control proves the marker does appear when the read happens.
for labels, want_status, want_called in (({}, 40, False), ({"1": ["needs-codex"]}, 30, True)):
    with fake_repo({"a.py": 5}, labels=labels, stale=True) as (cwd, env):
        p = subprocess.run([sys.executable, GATE, "--base", "main", "--tickets", "1"],
                           cwd=cwd, env=env, capture_output=True, text=True)
        called = os.path.exists(os.path.join(env["HOME"], "codex-called"))
        assert (p.returncode, called) == (want_status, want_called), (labels, p.returncode, p.stdout, called)
# Malformed size arguments are unknown (30) with a usage line, never a silent full-size pass.
for bad in (["--base", "main"], ["--base", "main", "--tickets"], ["--tickets", "1", "--base", "main"],
            ["--base", "main", "--tickets", "#1"], ["--audit", "--base", "main", "--tickets", "1"],
            ["--audit", "--audit"]):
    status, out = run(cache(5), *bad)
    assert status == 30 and out.startswith("usage: codex-usage-gate.py"), (bad, status, out)
# A base git cannot resolve is unknown, never a size verdict either way, and the line names git's
# own error rather than a usage read that never happened.
status, out = run_size({"a.py": 5}, base="nope")
assert status == 30 and out.startswith("size check failed: `git diff") and "nope" in out, (status, out)
# A diff with no files at all is HEAD sitting at the base — the wrong checkout — never a 0-line PR.
status, out = run_size({})
assert (status, out) == (30, "size check failed: main...HEAD changes no files — run from the PR's workspace\n"), (
    status, out)
print("ok size")

# `--size --base <ref> --tickets <n>...` (#1401) answers only the size question, for the first
# ablation: no usage read and no kill switch, since a small PR is small whether or not Codex is on.
def run_size_only(changes, tickets=("1",), base="main", **repo):
    with fake_repo(changes, **repo) as (cwd, env):
        p = subprocess.run([sys.executable, GATE, "--size", "--base", base, "--tickets", *tickets],
                           cwd=cwd, env=env, capture_output=True, text=True)
        called = os.path.exists(os.path.join(env["HOME"], "codex-called"))
        return p.returncode, p.stdout, called
assert run_size_only({"a.py": 299}, tickets=("1", "2"))[0] == 40  # a clump names every ticket
assert run_size_only({"a.py": 299}) == (40, "under size threshold (299 < 300)\n", False)
assert run_size_only({"a.py": 300}) == (0, "at or above size threshold (300 >= 300)\n", False)
# The kill switch and the usage ceiling answer a launch, not a size: both still say large.
assert run_size_only({"a.py": 5000}, switch=True)[0] == 0
assert run_size_only({"a.py": 5000}, pct=99)[0] == 0
assert run_size_only({"a.py": 5}, switch=True)[0] == 40
# No usage read even from a stale cache, which would run the fake `codex`.
assert run_size_only({"a.py": 5000}, stale=True) == (0, "at or above size threshold (5000 >= 300)\n", False)
# The forcing label does not make a small PR large: the ablation measures size, not Codex's reach.
assert run_size_only({"a.py": 5}, labels={"1": ["needs-codex"]})[0] == 40
# Unmeasurable is unknown (30), never small.
status, out, _ = run_size_only({"a.py": 5}, base="nope")
assert status == 30 and out.startswith("size check failed:"), (status, out)
for bad in (["--size"], ["--size", "--audit"], ["--size", "--base", "main"], ["--size", "--percent"]):
    status, out = run(cache(5), *bad)
    assert status == 30 and out.startswith("usage: codex-usage-gate.py"), (bad, status, out)
print("ok size-only")
