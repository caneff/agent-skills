#!/usr/bin/env python3
"""The Codex usage preflight (#1204): `codex-usage-gate.py` reads the usage
cache and answers with an exit status a controller can branch on — 0 proceed,
10 tell Chris first, 20 capped (skip, no run), 30 unknown (skip, no run).

Every run gets `HOME` set to its temporary directory, so the kill-switch file
(#1354) on the real box never reaches a test.

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


def run_live(stale_cache, limits, *args):
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
import importlib.util

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
# `--percent` is a reading, not a launch: the switch leaves it alone.
status, out, _ = run_switch("", "--percent")
assert out == "unknown\n" and status == 30, (status, out)  # no live codex on PATH, same as ever

# With the switch present the helper is never loaded: a disabled gate costs no RPC.
with tempfile.TemporaryDirectory() as d:
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
    assert gate.check() == (20, f"codex reviews off by Chris's ruling ({path}) — remove the file to re-enable")
print("ok kill switch")
