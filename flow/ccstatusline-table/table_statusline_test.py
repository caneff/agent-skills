"""table-statusline.py: pure helpers in-process, `main` as a process.

Seam: the script's command line (session JSON on stdin, a temp transcript,
a temp git repo, a temp `$HOME`); the rendered table is the observable.
Replaces the old `--selftest` mode (#1753).
"""
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
LINE = HERE / "table-statusline.py"

spec = importlib.util.spec_from_file_location("table_statusline", LINE)
ts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ts)


def plain(s):
    return ts.ANSI.sub("", s)


def cells(out):
    """The rendered table's data row, split into its stripped cell texts."""
    return [c.strip() for c in out.splitlines()[1].strip("│").split("│")]


def frame_top(color):
    """The escape a frame of `color` opens its top border with."""
    return ts.paint("╭", color).removesuffix("\x1b[0m")


@pytest.fixture(autouse=True)
def isolated_git(tmp_path, monkeypatch):
    """No live gitconfig or exported GIT_* reaches a test's git
    (CODING_STANDARDS.md rule 2)."""
    for k in [k for k in os.environ if k.startswith("GIT_")]:
        monkeypatch.delenv(k)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


# --- pure helpers (the old --selftest cases) --------------------------------

def test_dwidth_counts_emoji_as_two():
    assert ts.dwidth("🏰 idle") == 7
    assert ts.dwidth("abc") == 3
    assert ts.dwidth("main") == 4


def test_dwidth_zero_width_marks():
    assert ts.dwidth("a‍b") == 2  # ZWJ
    assert ts.dwidth("é") == 1  # combining acute


def test_table_rows_have_equal_visible_width():
    out = ts.table([[("a", ts.FG), ("bb", ts.FG)], [("ccc", ts.FG), ("d", ts.FG)]], ts.GREEN)
    lines = out.splitlines()
    assert {ts.dwidth(plain(line)) for line in lines} == {ts.dwidth(plain(lines[0]))}
    assert "╭" in lines[0] and "┬" in lines[0]
    assert "├" in lines[2] and "╰" in lines[-1]


def test_table_pads_short_rows():
    out = ts.table([[("a", ts.FG), ("b", ts.FG)], [("c", ts.FG)]], ts.GREEN)
    assert len({ts.dwidth(plain(line)) for line in out.splitlines()}) == 1


@pytest.mark.parametrize(
    "tokens,color",
    [
        (0, ts.PURPLE),
        (139_000, ts.GREEN),
        (140_000, ts.YELLOW),
        (179_000, ts.YELLOW),
        (180_000, ts.RED),
        (250_000, ts.RED),
    ],
)
def test_frame_color(tokens, color):
    assert ts.frame_color(tokens) == color


def test_parse_usage_fields():
    assert ts.parse_usage_fields("42%\t2d3h30m\t12%\t3h10m") == ("42%", "2d3h30m", "12%", "3h10m")
    assert ts.parse_usage_fields("\t\t12%\t3h10m") == ("", "", "12%", "3h10m")
    assert ts.parse_usage_fields("") == ("", "", "", "")


# --- context_tokens ---------------------------------------------------------

def _usage_line(i, c, w):
    return json.dumps({"message": {"usage": {
        "input_tokens": i, "cache_read_input_tokens": c, "cache_creation_input_tokens": w}}})


def test_context_tokens_takes_latest_usage(tmp_path):
    t = tmp_path / "t.jsonl"
    t.write_text("\n".join([
        _usage_line(1, 2, 3),
        "not json",
        json.dumps({"message": {}}),
        _usage_line(100, 2000, 30000),
    ]))
    assert ts.context_tokens(str(t)) == 32100


def test_context_tokens_missing_or_empty_path(tmp_path):
    assert ts.context_tokens("") == 0
    assert ts.context_tokens(str(tmp_path / "absent.jsonl")) == 0


def test_context_tokens_no_usage_lines(tmp_path):
    t = tmp_path / "t.jsonl"
    t.write_text('{"type":"user"}\n')
    assert ts.context_tokens(str(t)) == 0


def test_context_tokens_unreadable_transcript_is_none(tmp_path):
    # a directory exists but cannot be read as a transcript: None, which is
    # not the 0 of a new session
    assert ts.context_tokens(str(tmp_path)) is None


def test_context_tokens_skips_torn_and_odd_lines(tmp_path):
    t = tmp_path / "t.jsonl"
    t.write_text("\n".join(['{"message": {"usa', "[1]", '{"message": "x"}', _usage_line(5, 0, 0)]))
    assert ts.context_tokens(str(t)) == 5


def test_context_tokens_skips_a_non_numeric_count(tmp_path):
    t = tmp_path / "t.jsonl"
    t.write_text("\n".join([_usage_line(7, 0, 0), _usage_line(None, 5, 0)]))
    assert ts.context_tokens(str(t)) == 7


def test_context_tokens_unsearchable_parent_is_none(tmp_path):
    if os.geteuid() == 0:
        pytest.skip("root searches any directory")
    locked = tmp_path / "locked"
    locked.mkdir()
    (locked / "t.jsonl").write_text(_usage_line(5, 0, 0))
    locked.chmod(0)
    try:
        assert ts.context_tokens(str(locked / "t.jsonl")) is None
    finally:
        locked.chmod(0o755)


def test_frame_color_unreadable_is_not_the_new_session_color():
    assert ts.frame_color(None) not in (ts.PURPLE, ts.GREEN, ts.YELLOW, ts.RED)


# --- git --------------------------------------------------------------------

def _git(cwd, *args):
    subprocess.run(
        ["git", "-C", str(cwd), "-c", "user.email=t@example.com", "-c", "user.name=t", *args],
        check=True, capture_output=True,
    )


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "proj"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    (r / "f.txt").write_text("a\nb\n")
    _git(r, "add", ".")
    _git(r, "commit", "-q", "-m", "init")
    return r


def test_git_not_a_repo(tmp_path):
    assert ts.git(str(tmp_path)) == ("", "", "")


def test_git_clean_repo(repo):
    branch, changes, root = ts.git(str(repo))
    assert branch == "⎇ main"
    assert changes == "+0,-0"
    assert Path(root).resolve() == repo.resolve()


def test_git_counts_insertions_and_deletions(repo):
    (repo / "f.txt").write_text("a\nx\ny\nz\n")  # +3 -1
    _, changes, _ = ts.git(str(repo))
    assert changes == "+3,-1"


def test_git_detached_head_shows_short_sha(repo):
    _git(repo, "checkout", "-q", "--detach")
    branch, _, _ = ts.git(str(repo))
    assert re.fullmatch(r"⎇ [0-9a-f]{4,}", branch)


def test_git_linked_worktree_reports_main_root(repo, tmp_path):
    wt = tmp_path / "linked"
    _git(repo, "worktree", "add", "-q", "-b", "side", str(wt))
    branch, _, root = ts.git(str(wt))
    assert branch == "⎇ side"
    assert Path(root).resolve() == repo.resolve()


def test_git_missing_binary_is_blank(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path))
    assert ts.git(str(tmp_path)) == ("", "", "")


def test_git_non_utf8_output_is_decoded_leniently(repo):
    _git(repo, "config", "core.quotePath", "false")
    (repo / "caf\xe9.txt".encode("latin-1").decode("utf-8", "surrogateescape")).write_text("x\n")
    _git(repo, "add", ".")
    _, changes, _ = ts.git(str(repo))
    assert changes == "+1,-0"


def test_git_does_not_swallow_programming_errors(monkeypatch, tmp_path):
    monkeypatch.setattr(ts.subprocess, "run", raise_type_error)
    with pytest.raises(TypeError):
        ts.git(str(tmp_path))


# --- main, as a process -----------------------------------------------------

@pytest.fixture
def env(tmp_path):
    """Temp HOME/CODEX_HOME and a `codex` that fails, so no helper reaches
    the network."""
    stub = tmp_path / "bin"
    stub.mkdir()
    codex = stub / "codex"
    codex.write_text("#!/bin/sh\nexit 1\n")
    codex.chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    return {
        "HOME": str(home),
        "CODEX_HOME": str(home / ".codex"),
        "PATH": f"{stub}:{os.environ['PATH']}",
        "GIT_CONFIG_GLOBAL": os.environ["GIT_CONFIG_GLOBAL"],
        "GIT_CONFIG_NOSYSTEM": "1",
    }


def render_raw(env, stdin_text, cwd):
    """The script as a process: its painted stdout, once it exited 0."""
    p = subprocess.run([sys.executable, str(LINE)], input=stdin_text, env=env,
                       capture_output=True, text=True, cwd=cwd)
    assert p.returncode == 0, p.stderr
    return p.stdout


def render(env, session, cwd):
    return plain(render_raw(env, json.dumps(session), cwd))


def test_main_renders_cells(env, repo, tmp_path):
    t = tmp_path / "t.jsonl"
    t.write_text(_usage_line(1000, 40000, 1500) + "\n")  # 42.5k
    (repo / "f.txt").write_text("a\nb\nc\n")
    now = time.time()
    session = {
        "model": {"display_name": "Opus 4.8"},
        "workspace": {"current_dir": str(repo)},
        "transcript_path": str(t),
        "effort": {"level": "medium"},
        "rate_limits": {
            "five_hour": {"used_percentage": 12.9, "resets_at": now + 3 * 3600 + 630},
            "seven_day": {"used_percentage": 42.1, "resets_at": now + 2 * 86400 + 3 * 3600 + 1830},
        },
    }
    out = render(env, session, repo)
    assert cells(out) == ["O 4.8 (M)", "proj", "Ctx 42.5k", "42% 2d · 12% 3h", "⎇ main +1,-0"]
    assert out.splitlines()[0].startswith("╭") and out.splitlines()[-1].startswith("╰")


def test_main_usage_cell_absent_without_rate_limits(env, repo):
    out = render(env, {"model": {"display_name": "Opus 4.8"}, "cwd": str(repo)}, repo)
    assert cells(out)[:3] == ["O 4.8", "proj", "Ctx —"]
    assert not any("%" in c for c in cells(out))


def test_main_usage_cell_single_window(env, repo):
    session = {"cwd": str(repo), "rate_limits": {
        "five_hour": {"used_percentage": 7, "resets_at": time.time() + 90 * 60}}}
    out = render(env, session, repo)
    assert "7% 1h" in out


def test_main_frame_color_follows_context(env, repo, tmp_path):
    t = tmp_path / "t.jsonl"
    t.write_text(_usage_line(190_000, 0, 0) + "\n")
    out = render_raw(env, json.dumps({"cwd": str(repo), "transcript_path": str(t)}), repo)
    assert out.startswith(frame_top(ts.RED))


def test_main_garbage_stdin_still_renders(env, tmp_path):
    assert "Ctx —" in plain(render_raw(env, "not json", tmp_path))


def test_main_does_not_swallow_a_stdin_programming_error(monkeypatch, capsys, env):
    monkeypatch.setattr(ts.json, "loads", raise_type_error)
    with pytest.raises(TypeError):
        run_main(monkeypatch, capsys, env, {})


def test_main_codex_cell_from_fresh_cache(env, repo):
    cache = Path(env["CODEX_HOME"])
    cache.mkdir()
    now = time.time()
    (cache / "usage-cache.json").write_text(json.dumps({
        "fetchedAt": now,
        "primary": {"usedPercent": 12.0, "resetsAt": now + 3 * 86400 + 60},
        "secondary": None,
    }))
    out = render(env, {"cwd": str(repo)}, repo)
    assert "Cdx 12% 3d" in out


def test_main_graft_line_when_wired(env, repo):
    helper = repo / ".claude" / "helpers"
    helper.mkdir(parents=True)
    (helper / "graft-statusline.cjs").write_text("console.log('graft 12 nodes')\n")
    out = render(env, {"workspace": {"current_dir": str(repo), "project_dir": str(repo)}}, repo)
    assert out.splitlines()[-1] == "graft 12 nodes"


# --- main, in-process (so coverage sees `main` and its nested cells) --------

def run_main(monkeypatch, capsys, env, session, raw=None):
    import io

    for k, v in env.items():
        monkeypatch.setenv(k, v)
    payload = (raw if raw is not None else json.dumps(session)).encode()
    monkeypatch.setattr(sys, "stdin", type("S", (), {"buffer": io.BytesIO(payload)})())
    ts.main()
    return plain(capsys.readouterr().out)


def test_main_in_process_full_row(monkeypatch, capsys, env, repo, tmp_path):
    t = tmp_path / "t.jsonl"
    t.write_text(_usage_line(500, 20000, 0) + "\n")
    now = time.time()
    session = {
        "model": {"display_name": "Sonnet 5.5"},
        "workspace": {"current_dir": str(repo)},
        "transcript_path": str(t),
        "rate_limits": {"seven_day": {"used_percentage": 50, "resets_at": now + 86400 + 1830}},
    }
    out = run_main(monkeypatch, capsys, env, session)
    assert cells(out) == ["S 5.5", "proj", "Ctx 20.5k", "50% 1d", "⎇ main +0,-0"]


def test_main_in_process_empty_stdin(monkeypatch, capsys, env, tmp_path):
    monkeypatch.chdir(tmp_path)
    out = run_main(monkeypatch, capsys, env, None, raw="")
    assert "Ctx —" in out


def test_main_unreadable_transcript_has_its_own_marker(env, repo, tmp_path):
    session = {"cwd": str(repo), "transcript_path": str(tmp_path)}  # a directory
    out = render_raw(env, json.dumps(session), repo)
    assert "Ctx ?" in plain(out)
    assert "Ctx —" not in plain(out)
    assert out.startswith(frame_top(ts.ORANGE))  # not the purple "no data yet" frame


def test_main_new_session_keeps_no_data_marker(env, repo):
    out = render_raw(env, json.dumps({"cwd": str(repo)}), repo)
    assert "Ctx —" in plain(out)
    assert out.startswith(frame_top(ts.PURPLE))


def test_usage_cell_does_not_swallow_programming_errors(monkeypatch, capsys, env, repo):
    real = ts.subprocess.run

    def run(cmd, *a, **k):
        if str(cmd[0]).endswith("usage-segment.sh"):
            raise TypeError("bug")
        return real(cmd, *a, **k)

    monkeypatch.setattr(ts.subprocess, "run", run)
    with pytest.raises(TypeError):
        run_main(monkeypatch, capsys, env, {"cwd": str(repo)})


def test_failed_helper_load_is_logged(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(ts, "CFG", tmp_path)  # no claude-usage.py here
    ts.write_usage_cache({})
    assert "claude-usage" in capsys.readouterr().err


def test_helper_load_ok_is_silent(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    ts.write_usage_cache({})
    assert capsys.readouterr().err == ""


def raise_type_error(*a, **k):
    raise TypeError("bug")


def test_run_does_not_swallow_programming_errors(monkeypatch):
    monkeypatch.setattr(ts.subprocess, "run", raise_type_error)
    with pytest.raises(TypeError):
        ts.run(["x"], b"")
