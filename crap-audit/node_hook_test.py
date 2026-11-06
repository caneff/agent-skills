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
        os.environ,
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


def test_capped_run_wraps_the_command_in_a_memory_capped_unit(tmp_path):
    bindir, log = _fake_systemd_run(tmp_path)
    env = dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}")
    r = subprocess.run(["bash", CAPPED, "6G", "--", "node", "--test", "a.test.mjs"],
                       env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    argv = log.read_text().split("\n")
    assert argv[:2] == ["--user", "--wait"]
    assert "MemoryMax=6G" in argv
    assert "MemorySwapMax=0" in argv
    assert argv[argv.index("node"):argv[:-1].index("a.test.mjs") + 1] == ["node", "--test", "a.test.mjs"]


def test_capped_run_refuses_a_missing_cap_or_command(tmp_path):
    r = subprocess.run(["bash", CAPPED, "6G"], capture_output=True, text=True)
    assert r.returncode != 0
    assert "usage" in r.stderr.lower()


def test_capped_run_fails_loud_when_systemd_run_is_absent(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    bash = shutil.which("bash")
    r = subprocess.run([bash, CAPPED, "6G", "--", "true"],
                       env={"PATH": str(empty)}, capture_output=True, text=True)
    assert r.returncode != 0
    assert "systemd-run" in r.stderr
