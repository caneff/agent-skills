"""End-to-end test for spec #1731: the statusline, skills-safe-update,
visual-teach and wizard sweep.

Each slice's public entry, driven the way a render or a seam run reaches it:

- the built-in self-test modes are gone and each script's cases are a suite
  `tests/all.sh --list` selects (ADR 0007; #1753, #1755);
- the statusline, run as a process, paints a new session's purple "Ctx —",
  an unreadable transcript's orange "Ctx ?", and a read transcript's size,
  and says on stderr when its claude-usage helper cannot load (#1753, #1754);
- effort-abbrev renders the effort cell from the session JSON (#1753);
- visual-teach's code component exports one object to `module.exports` and
  `window.vtCode` (#1756);
- the wizard's one `ask` stores what is typed, `--secret` or not (#1756).

What a green run does NOT cover (the seam is blind to it):
- the statusline inside a live Claude Code session: whether the harness
  paints these frames as the escapes say, and whether anyone sees the
  helper-load line on stderr;
- visual-teach's CSS in a browser: the shared selectors are read by a
  browser, which no suite runs;
- the wizard at a human's terminal emulator (`wizard/template_tty_test.py`
  drives a pseudo-terminal, which is as close as the seam gets).
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUSLINE = ROOT / "flow/ccstatusline-table"
SELF_TEST_SCRIPTS = {
    "flow/ccstatusline-table/table-statusline.py": "--selftest",
    "flow/ccstatusline-table/helpers/codex-usage.py": "--selftest",
    "flow/ccstatusline-table/helpers/usage-segment.sh": "--selftest",
    "skills-safe-update/scripts/upstream.py": "--selfcheck",
}
ESC = "\x1b[38;2;{};{};{}m╭"
PURPLE, ORANGE, GREEN = ESC.format(189, 147, 249), ESC.format(255, 184, 108), ESC.format(80, 250, 123)


def _env(tmp_path):
    """A temp HOME and a failing `codex`, so no helper reads Chris's caches
    or reaches the network; no GIT_* from the caller."""
    stub = tmp_path / "bin"
    stub.mkdir(exist_ok=True)
    (stub / "codex").write_text("#!/bin/sh\nexit 1\n")
    (stub / "codex").chmod(0o755)
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return {"HOME": str(home), "CODEX_HOME": str(home / ".codex"),
            "PATH": f"{stub}:{os.environ['PATH']}", "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": str(tmp_path / "gitconfig")}


def _statusline(tmp_path, session, script=STATUSLINE / "table-statusline.py"):
    p = subprocess.run([sys.executable, str(script)], input=json.dumps(session),
                       env=_env(tmp_path), cwd=tmp_path, capture_output=True,
                       text=True, timeout=30)
    assert p.returncode == 0, p.stderr
    return p


def test_self_test_modes_are_gone_and_their_cases_are_selected_suites():
    listed = subprocess.run(["bash", "tests/all.sh", "--list"], cwd=ROOT,
                            capture_output=True, text=True, timeout=120,
                            env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")})
    assert listed.returncode == 0, listed.stderr
    suites = set(listed.stdout.split())
    for rel, flag in SELF_TEST_SCRIPTS.items():
        assert flag not in (ROOT / rel).read_text(encoding="utf-8"), rel
        beside = {p.relative_to(ROOT).as_posix() for p in (ROOT / rel).parent.iterdir()
                  if p.name.endswith(("_test.py", ".test.sh"))}
        assert suites & beside, f"tests/all.sh --list selects no suite beside {rel}"


def test_statusline_frames_tell_new_unreadable_and_read_sessions_apart(tmp_path):
    new = _statusline(tmp_path, {}).stdout
    assert new.startswith(PURPLE) and "Ctx —" in new

    unreadable = _statusline(tmp_path, {"transcript_path": str(tmp_path)}).stdout
    assert unreadable.startswith(ORANGE) and "Ctx ?" in unreadable

    t = tmp_path / "t.jsonl"
    t.write_text(json.dumps({"message": {"usage": {
        "input_tokens": 500, "cache_read_input_tokens": 20000,
        "cache_creation_input_tokens": 0}}}) + "\n")
    read = _statusline(tmp_path, {"transcript_path": str(t)}).stdout
    assert read.startswith(GREEN) and "Ctx 20.5k" in read


def test_statusline_reports_a_helper_it_cannot_load(tmp_path):
    lone = tmp_path / "lone"
    lone.mkdir()
    shutil.copy(STATUSLINE / "table-statusline.py", lone)  # no helpers/ beside it
    p = _statusline(tmp_path, {}, script=lone / "table-statusline.py")
    assert "claude-usage cache not written" in p.stderr


def test_effort_cell_from_the_session_json(tmp_path):
    p = subprocess.run([sys.executable, str(STATUSLINE / "helpers/effort-abbrev.py")],
                       input=json.dumps({"effort": {"level": "xhigh"}}),
                       env=_env(tmp_path), capture_output=True, text=True, timeout=30)
    assert p.stdout == "(XH)"


def test_code_component_exports_one_object_to_both_hosts():
    js = """
const fs = require("fs"), vm = require("vm");
const src = fs.readFileSync(process.argv[1], "utf8");
const mod = { exports: {} }, win = {};
vm.runInNewContext(src, { module: mod, console: { warn() {} } });
vm.runInNewContext(src, { window: win, console: { warn() {} } });
console.log(JSON.stringify([Object.keys(mod.exports).sort(), Object.keys(win.vtCode || {}).sort()]));
"""
    p = subprocess.run(["node", "-e", js, str(ROOT / "visual-teach/assets/components/code/code.js")],
                       capture_output=True, text=True, timeout=30)
    assert p.returncode == 0, p.stderr
    node_keys, window_keys = json.loads(p.stdout)
    assert node_keys and node_keys == window_keys


def test_wizard_ask_stores_typed_input_secret_or_not(tmp_path):
    lib = tmp_path / "lib.sh"
    lib.write_text((ROOT / "wizard/template.sh").read_text().split("\n# STAGES", 1)[0] + "\n")
    for args in (["KEY_VAL", "Prompt:"], ["--secret", "KEY_VAL", "Prompt:"]):
        p = subprocess.run(["bash", "-c", 'source ./lib.sh; ask "$@"; printf "%s" "$KEY_VAL"', "_", *args],
                           input="typed\n", cwd=tmp_path, capture_output=True, text=True, timeout=30,
                           env={"PATH": os.environ["PATH"], "ENV_FILE": str(tmp_path / ".env")})
        assert p.stdout.endswith("typed"), (args, p.stdout, p.stderr)
