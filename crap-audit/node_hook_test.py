"""Tests for the Node coverage preload hook and the memory-capped runner.

The hook is exercised for real under `node`, with a stub standing in for
`istanbul-lib-instrument` (CRAP_TOOLS/node_modules/...). The stub throws, like
Babel, when handed `import`/`export` source without `esModules: true`, so the
tests bind to the option the hook passes, not to Babel being installed.
"""
import glob
import json
import os
import shutil
import subprocess
import textwrap

import pytest

HERE = os.path.dirname(__file__)
MERGE = os.path.join(HERE, "merge-hits.cjs")
HOOK = os.path.join(HERE, "node-coverage-hook.cjs")
CAPPED = os.path.join(HERE, "capped-run.sh")

STUB = textwrap.dedent(
    """
    exports.createInstrumenter = (opts) => ({
      instrumentSync (src, file) {
        if (src.includes('FORCE_INSTRUMENT_ERROR')) throw new Error('boom from stub')
        if (/^\\s*(import|export)\\b/m.test(src) && !opts.esModules)
          throw new SyntaxError("'import' and 'export' may appear only with 'sourceType: \\"module\\"'")
        return `globalThis.__coverage__ = Object.assign(globalThis.__coverage__ || {}, { [${JSON.stringify(file)}]: { esModules: ${opts.esModules} } });\\n` + src
      }
    })
    """
)

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


@pytest.fixture
def project(tmp_path):
    tools = tmp_path / "tools"
    stub_dir = tools / "node_modules" / "istanbul-lib-instrument"
    stub_dir.mkdir(parents=True)
    (stub_dir / "index.js").write_text(STUB)
    root = tmp_path / "repo"
    root.mkdir()
    (root / "package.json").write_text('{"type": "module"}')
    hits = tmp_path / "hits"
    hits.mkdir()
    return {"tools": tools, "root": root, "hits": hits, "tmp": tmp_path}


def _run(project, sources, entry, extra_env=None):
    files = project["tmp"] / "files.txt"
    files.write_text("\n".join(sources) + "\n")
    env = dict(
        PATH=os.environ["PATH"],
        HOME=str(project["tmp"]),
        CRAP_TOOLS=str(project["tools"]),
        CRAP_ROOT=str(project["root"]),
        CRAP_FILES=str(files),
        CRAP_HITS=str(project["hits"]),
    )
    env.update(extra_env or {})
    return subprocess.run(
        ["node", "--require", HOOK, entry],
        cwd=project["root"], env=env, capture_output=True, text=True, timeout=60,
    )


def _dumps(project):
    return [json.load(open(p)) for p in glob.glob(str(project["hits"] / "*.json"))]


@needs_node
def test_es_module_saved_as_dot_js_is_instrumented_as_a_module(project):
    root = project["root"]
    (root / "app.js").write_text("export const add = (a, b) => a + b\n")
    (root / "main.mjs").write_text("import { add } from './app.js'\nconsole.log(add(1, 2))\n")
    r = _run(project, ["app.js", "main.mjs"], str(root / "main.mjs"))
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "3"
    merged = {k: v for d in _dumps(project) for k, v in d.items()}
    assert merged[str(root / "app.js")]["esModules"] is True


@needs_node
def test_instrument_error_fails_loud_naming_the_file(project):
    root = project["root"]
    (root / "bad.mjs").write_text("// FORCE_INSTRUMENT_ERROR\nconsole.log('ran')\n")
    r = _run(project, ["bad.mjs"], str(root / "bad.mjs"))
    assert r.returncode != 0
    assert "ran" not in r.stdout
    assert "bad.mjs" in r.stderr
    assert "boom from stub" in r.stderr


@needs_node
def test_file_outside_the_source_list_is_not_instrumented(project):
    root = project["root"]
    (root / "app.js").write_text("export const x = 1\n")
    (root / "other.mjs").write_text("console.log('plain')\n")
    r = _run(project, ["app.js"], str(root / "other.mjs"))
    assert r.returncode == 0, r.stderr
    assert _dumps(project) == []


def _fake_systemd_run(tmp_path):
    """A systemd-run on PATH that records its argv, one per line, then exits 0."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    log = tmp_path / "argv.log"
    exe = bindir / "systemd-run"
    exe.write_text(f'#!/bin/sh\nfor a in "$@"; do printf "%s\\n" "$a" >> {log}; done\n')
    exe.chmod(0o755)
    return bindir, log


def _minimal_env(path, **extra):
    keep = {k: os.environ[k] for k in ("XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS") if k in os.environ}
    return dict(PATH=path, HOME=os.environ["HOME"], **keep, **extra)


def _real_user_systemd():
    if shutil.which("systemd-run") is None:
        return False
    r = subprocess.run(["systemd-run", "--user", "--wait", "--pipe", "true"], capture_output=True)
    return r.returncode == 0


def test_capped_run_wraps_the_command_in_a_memory_capped_unit(tmp_path):
    bindir, log = _fake_systemd_run(tmp_path)
    env = _minimal_env(f"{bindir}:{os.environ['PATH']}")
    r = subprocess.run(["bash", CAPPED, "6G", "--", "node", "--test", "a.test.mjs"],
                       env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    argv = log.read_text().splitlines()
    assert argv[:2] == ["--user", "--wait"]
    assert "MemoryMax=6G" in argv
    assert "MemorySwapMax=0" in argv
    assert argv[-3:] == ["node", "--test", "a.test.mjs"]


def test_capped_run_names_the_hook_variables_for_the_unit(tmp_path):
    bindir, log = _fake_systemd_run(tmp_path)
    env = _minimal_env(f"{bindir}:{os.environ['PATH']}",
                       NODE_OPTIONS="--require /x.cjs", CRAP_HITS="/h", UNRELATED="no")
    r = subprocess.run(["bash", CAPPED, "6G", "--", "true"], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    argv = log.read_text().splitlines()
    for name in ("NODE_OPTIONS", "CRAP_HITS", "PATH", "HOME"):
        assert argv[argv.index(f"{name}") - 1] == "-E"
    assert "UNRELATED" not in argv


@pytest.mark.skipif(not _real_user_systemd(), reason="no working systemd --user")
def test_capped_run_delivers_the_hook_variables_into_the_real_unit(tmp_path):
    """The unit starts in the user manager's environment; without passthrough the
    preload never loads and a suite passes uninstrumented."""
    env = _minimal_env(os.environ["PATH"], NODE_OPTIONS="--no-warnings", CRAP_HITS="/some/hits")
    r = subprocess.run(
        ["bash", CAPPED, "1G", "--", "sh", "-c", 'echo "$NODE_OPTIONS|$CRAP_HITS"'],
        env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert "--no-warnings|/some/hits" in r.stdout


def test_capped_run_refuses_a_missing_cap_command_or_separator(tmp_path):
    bindir, log = _fake_systemd_run(tmp_path)
    env = _minimal_env(f"{bindir}:{os.environ['PATH']}")
    for args in (["6G"], ["6G", "true"], ["6G", "x", "true"]):
        r = subprocess.run(["bash", CAPPED, *args], env=env, capture_output=True, text=True)
        assert r.returncode != 0, args
        assert "usage" in r.stderr.lower()
    assert not log.exists(), "systemd-run was started despite a refused call"


def test_capped_run_fails_loud_without_running_when_systemd_run_is_absent(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    ran = tmp_path / "ran"
    r = subprocess.run([shutil.which("bash"), CAPPED, "6G", "--", "touch", str(ran)],
                       env={"PATH": str(empty), "HOME": str(tmp_path)}, capture_output=True, text=True)
    assert r.returncode != 0
    assert "systemd-run" in r.stderr
    assert not ran.exists(), "the command ran uncapped"


@needs_node
@pytest.mark.parametrize("missing", ["CRAP_TOOLS", "CRAP_ROOT", "CRAP_FILES", "CRAP_HITS"])
def test_hook_names_a_missing_variable(project, missing):
    (project["root"] / "a.mjs").write_text("console.log('ran')\n")
    files = project["tmp"] / "files.txt"
    files.write_text("a.mjs\n")
    env = dict(PATH=os.environ["PATH"], HOME=str(project["tmp"]), CRAP_TOOLS=str(project["tools"]),
               CRAP_ROOT=str(project["root"]), CRAP_FILES=str(files), CRAP_HITS=str(project["hits"]))
    del env[missing]
    r = subprocess.run(["node", "--require", HOOK, str(project["root"] / "a.mjs")],
                       env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode != 0
    assert missing in r.stderr
    assert "ran" not in r.stdout


@needs_node
def test_hook_refuses_a_file_list_naming_a_missing_file(project):
    (project["root"] / "a.mjs").write_text("console.log('ran')\n")
    r = _run(project, ["a.mjs", "nope.js"], str(project["root"] / "a.mjs"))
    assert r.returncode != 0
    assert "nope.js" in r.stderr


@needs_node
def test_hook_matches_through_a_symlinked_root_and_a_crlf_list(project):
    real = project["root"]
    (real / "app.js").write_text("export const x = 1\n")
    (real / "main.mjs").write_text("import './app.js'\n")
    link = project["tmp"] / "link"
    link.symlink_to(real)
    r = _run(project, ["app.js\r"], str(real / "main.mjs"), {"CRAP_ROOT": str(link)})
    assert r.returncode == 0, r.stderr
    assert any(str(real / "app.js") in d for d in _dumps(project))


def _merge(hits):
    return subprocess.run(["node", MERGE, str(hits)], capture_output=True, text=True, timeout=60)


@needs_node
def test_merge_sums_counters_across_processes(tmp_path):
    def cov(n):
        return {"/r/a.js": {"s": {"0": n, "1": 0}, "f": {"0": n}, "b": {"0": [n, 0]}}}
    (tmp_path / "1.json").write_text(json.dumps(cov(2)))
    (tmp_path / "2.json").write_text(json.dumps(cov(3)))
    r = _merge(tmp_path)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout)["/r/a.js"]
    assert got == {"s": {"0": 5, "1": 0}, "f": {"0": 5}, "b": {"0": [5, 0]}}


@needs_node
def test_merge_fails_loud_on_an_empty_hits_dir(tmp_path):
    r = _merge(tmp_path)
    assert r.returncode != 0
    assert "no coverage dumps" in r.stderr
    assert r.stdout == ""
