"""`codex-gate-run.py` launches the Codex adversarial gate and writes its record.

Seam: the command line, against a fake plugin tree under a temporary `$HOME`
(its `installed_plugins.json` and a fake `codex-companion.mjs` run by a fake
`node`), a fake usage gate named by `CODEX_USAGE_GATE`, and a real git repo.
Asserts on the `.out` and `.json` files the run leaves in the review cache.
"""
import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "codex-gate-run.py")

FAKE_NODE = """#!/bin/sh
# argv: <companion> adversarial-review --wait --base <ref> -- <focus text>
echo "args: $*"
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
    g("config", "user.email", "t@example.com")
    g("config", "user.name", "t")
    g("commit", "--allow-empty", "-qm", "init")
    body = tmp_path / "body.md"
    body.write_text('ticket "quoted" $(not run) `x`\n')
    e = {**os.environ, "HOME": str(home), "PATH": f"{bindir}:{os.environ['PATH']}",
         "CODEX_USAGE_GATE": str(usage), "FAKE_USAGE_FILE": str(tmp_path / "n")}
    e.pop("FAKE_COMMIT", None)
    e.pop("FAKE_STATUS", None)
    return e, repo, body, home


def run(env, repo, body, *extra, **over):
    e = {**env, **over}
    r = subprocess.run([sys.executable, SCRIPT, "--repo", "r", "--ticket", "7",
                        "--body-file", str(body), "--base", "HEAD", *extra],
                       cwd=repo, env=e, capture_output=True, text=True)
    return r


def cache(home):
    d = home / ".cache" / "agent-reviews" / "r"
    return (d / "codex-adversarial-7-gate.out", d / "codex-adversarial-7-gate.json")


def test_clean_run_writes_out_and_record(env):
    e, repo, body, home = env
    r = run(e, repo, body)
    assert r.returncode == 0, r.stderr
    out, rec = cache(home)
    text = out.read_text()
    assert "adversarial-review --wait --base HEAD --" in text
    assert 'ticket "quoted" $(not run) `x`' in text  # body passed as one literal arg
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
    assert "args:" in out.read_text()
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
    assert "codex@openai-codex" in r.stderr
    assert not cache(home)[1].exists()


def test_unreadable_usage_is_unknown(env, tmp_path):
    e, repo, body, home = env
    bad = tmp_path / "badusage"
    bad.write_text("#!/bin/sh\nexit 30\n")
    bad.chmod(0o755)
    run(e, repo, body, CODEX_USAGE_GATE=str(bad))
    j = json.loads(cache(home)[1].read_text())
    assert j["usage_before"] == j["usage_after"] == "unknown"
