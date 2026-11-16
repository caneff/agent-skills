"""`codex-gate-run.py` launches the Codex adversarial gate and writes its record.

Seam: the command line, against a fake plugin tree under a temporary `$HOME`
(its `installed_plugins.json` and a fake `codex-companion.mjs` run by a fake
`node`), a fake usage gate named by `CODEX_USAGE_GATE`, and a real git repo.
Asserts on the `.out` and `.json` files the run leaves in the review cache.
"""
import json
import os
import shutil
import subprocess
import sys

import pytest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../common"))
import fixture_identity  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "codex-gate-run.py")

FAKE_NODE = """#!/bin/sh
# argv: <companion> adversarial-review --wait --base <ref> -- <focus text>, one line per arg
printf 'arg:%s\n' "$@"
if [ -n "$FAKE_COMMIT" ]; then git commit --allow-empty -qm race; fi
exit ${FAKE_STATUS:-0}
"""
FAKE_USAGE = """#!{py}
import os
p = os.environ["FAKE_USAGE_FILE"]
n = int(open(p).read() or 0) if os.path.exists(p) else 0
open(p, "w").write(str(n + 1))
print(["10.0 1790000000", "11.5 1790000000"][min(n, 1)])
"""


@pytest.fixture
def env(tmp_path):
    home = tmp_path / "home"
    plugin = tmp_path / "plugin"
    (plugin / "scripts").mkdir(parents=True)
    (plugin / "scripts" / "codex-companion.mjs").write_text("")
    (home / ".claude" / "plugins").mkdir(parents=True)
    (home / ".claude" / "plugins" / "installed_plugins.json").write_text(json.dumps(
        {"plugins": {"codex@openai-codex": [{"installPath": str(plugin)}]}}))
    bindir = tmp_path / "bin"
    bindir.mkdir()
    node = bindir / "node"
    node.write_text(FAKE_NODE)
    node.chmod(0o755)
    usage = tmp_path / "usage"
    usage.write_text(FAKE_USAGE.format(py=sys.executable))
    usage.chmod(0o755)
    repo = tmp_path / "repo"
    repo.mkdir()
    g = lambda *a: subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True)
    g("init", "-q")
    fixture_identity.configure(str(repo), str(tmp_path))
    g("commit", "--allow-empty", "-qm", "init")
    body = tmp_path / "body.md"
    body.write_text('ticket "quoted" $(not run) `x` two  words')
    e = {**os.environ, "HOME": str(home), "PATH": f"{bindir}:{os.environ['PATH']}",
         "CODEX_USAGE_GATE": str(usage), "FAKE_USAGE_FILE": str(tmp_path / "n")}
    e.pop("FAKE_COMMIT", None)
    e.pop("FAKE_STATUS", None)
    return e, repo, body, home


def run(env, repo, body, **over):
    return subprocess.run([sys.executable, SCRIPT, "--ticket", "7", "--body-file", str(body),
                           "--base", "HEAD"],
                          cwd=repo, env={**env, **over}, capture_output=True, text=True)


def cache(home):
    d = home / ".cache" / "agent-reviews" / "repo"
    return (d / "codex-adversarial-7-gate.out", d / "codex-adversarial-7-gate.json")


def test_clean_run_writes_out_and_record(env):
    e, repo, body, home = env
    r = run(e, repo, body)
    assert r.returncode == 0, r.stderr
    out, rec = cache(home)
    text = out.read_text()
    assert text.startswith("arg:") and "\narg:adversarial-review\narg:--wait\narg:--base\narg:HEAD\narg:--\n" in text
    assert text.endswith('arg:ticket "quoted" $(not run) `x` two  words\n')  # one literal arg
    j = json.loads(rec.read_text())
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True,
                         text=True).stdout.strip()
    assert (j["ticket"], j["phase"], j["status"]) == (7, "gate", 0)
    assert j["launch_sha"] == j["completion_sha"] == sha
    assert j["usage_before"] == "10.0 1790000000"
    assert j["usage_after"] == "11.5 1790000000"
    assert j["started"] and j["completed"]


def test_node_failure_is_recorded_not_hidden(env):
    e, repo, body, home = env
    r = run(e, repo, body, FAKE_STATUS="3")
    out, rec = cache(home)
    assert json.loads(rec.read_text())["status"] == 3
    assert "arg:adversarial-review" in out.read_text()
    assert r.returncode == 0  # the record, not the exit, carries the refusal


def test_commit_during_run_shows_in_shas(env):
    e, repo, body, home = env
    run(e, repo, body, FAKE_COMMIT="1")
    j = json.loads(cache(home)[1].read_text())
    assert j["launch_sha"] != j["completion_sha"]


def test_missing_plugin_entry_fails_and_writes_no_record(env):
    e, repo, body, home = env
    (home / ".claude" / "plugins" / "installed_plugins.json").write_text('{"plugins": {}}')
    r = run(e, repo, body)
    assert r.returncode != 0
    assert "cannot start: no codex@openai-codex entry" in r.stderr
    assert "Traceback" not in r.stderr
    assert not cache(home)[1].exists()


def test_unreadable_usage_is_unknown(env, tmp_path):
    e, repo, body, home = env
    bad = tmp_path / "badusage"
    # run as a python script: a reading printed, but exit 30
    bad.write_text("import sys\nprint('50.0 1790000000')\nsys.exit(30)\n")
    bad.chmod(0o755)
    run(e, repo, body, CODEX_USAGE_GATE=str(bad))
    j = json.loads(cache(home)[1].read_text())
    assert j["usage_before"] == j["usage_after"] == "unknown"


def test_unreadable_body_names_the_body(env, tmp_path):
    e, repo, _, home = env
    r = run(e, repo, tmp_path / "nope.md")
    assert r.returncode != 0
    assert "body file unreadable" in r.stderr and "Traceback" not in r.stderr
    assert not cache(home)[1].exists()


def test_node_that_cannot_start_is_recorded_and_stale_record_is_gone(env, tmp_path):
    e, repo, body, home = env
    out, rec = cache(home)
    rec.parent.mkdir(parents=True)
    rec.write_text('{"status": 0}')
    nonode = tmp_path / "nonode"  # git and the interpreter, no node
    nonode.mkdir()
    (nonode / "git").symlink_to(shutil.which("git"))
    r = run(e, repo, body, PATH=str(nonode))
    assert r.returncode == 0, r.stderr
    j = json.loads(rec.read_text())
    assert j["status"] == 127
    assert "node did not start" in out.read_text()
