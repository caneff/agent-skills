#!/usr/bin/env python3
"""The Codex usage preflight (#1204): `codex-usage-gate.py` reads the usage
cache and answers with an exit status a controller can branch on — 0 proceed,
10 tell Chris first, 20 capped (skip, no run), 30 unknown (skip, no run).

Seam: the script's command line — stdout line and exit status — against a
cache file under a temporary `$CODEX_HOME`. `PATH` is emptied so a stale or
missing cache cannot reach a real `codex app-server`.
"""
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
        env = {"CODEX_HOME": d, "PATH": "/nonexistent"}
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


def run_live(stale_cache, limits):
    """A stale cache with a fake `codex app-server` answering `limits` (or nothing).

    Returns (exit status, stdout, the cache file's content after the run)."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "usage-cache.json")
        with open(path, "w") as f:
            json.dump(stale_cache, f)
        bindir = os.path.join(d, "bin")
        os.mkdir(bindir)
        fake = os.path.join(bindir, "codex")
        with open(fake, "w") as f:
            f.write(FAKE_CODEX.format(py=sys.executable))
        os.chmod(fake, 0o755)
        env = {"CODEX_HOME": d, "PATH": bindir}
        if limits is not None:
            env["FAKE_LIMITS"] = json.dumps(limits)
        p = subprocess.run([sys.executable, GATE], env=env, capture_output=True, text=True)
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
check("just under threshold", run(cache(79)), 0)
check("at threshold", run(cache(80)), 10, "80%")
check("above threshold", run(cache(95)), 10)
status, out = run(cache(100, resets=time.time() + 5 * DAY))
check("capped", (status, out), 20, "100%")
assert "resets" in out and time.strftime("%Y-%m-%d", time.localtime(time.time() + 5 * DAY)) in out, out
check("over 100", run(cache(103)), 20)
# The worst window governs.
check("secondary governs",
      run(cache(10, secondary={"usedPercent": 100, "resetsAt": time.time() + DAY})), 20)
# `--percent` prints the reading alone, for the review ledger's before/after rows (#1269),
# and `unknown` (exit 30) where the gate itself would be 30 — never a number it did not read.
check("percent", run(cache(44), "--percent"), 0, "44")
assert run(cache(44), "--percent")[1] == "44\n", run(cache(44), "--percent")
assert run(cache(103), "--percent")[1] == "103\n"
assert run(cache(44.5), "--percent")[1] == "44.5\n"
check("percent, capped still reads", run(cache(100), "--percent"), 0, "100")
assert run(None, "--percent") == (30, "unknown\n"), run(None, "--percent")
assert run(cache(100, resets=time.time() - 60), "--percent") == (30, "unknown\n")
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
