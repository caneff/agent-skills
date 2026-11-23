"""print_pdf.py at its command line: shot-scraper prints a real page; a
printer that leaves no PDF, and a git that cannot answer, are caught.

Blind to: the page's layout, and whether the skill's prose calls the script.
"""
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "print_pdf.py"


def run(*args):
    return run_with(None, *args)


def page(tmp_path):
    html = tmp_path / "guide.html"
    html.write_text("<!doctype html><html><body><h1>Key idea 1</h1></body></html>")
    return html


def test_prints_a_pdf_outside_any_repo(tmp_path):
    out = tmp_path / "out" / "guide.pdf"
    r = run(page(tmp_path), out)
    assert r.returncode == 0, r.stderr
    assert out.read_bytes().startswith(b"%PDF-")
    assert r.stdout.strip() == str(out)
    assert sorted(p.name for p in out.parent.iterdir()) == ["guide.pdf"]


def test_refuses_a_destination_inside_a_git_work_tree(tmp_path):
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    out = repo / "sub" / "guide.pdf"
    r = run(page(tmp_path), out)
    assert r.returncode == 2
    assert "inside the git work tree" in r.stderr
    assert not out.exists()


def test_refuses_a_missing_page(tmp_path):
    out = tmp_path / "guide.pdf"
    r = run(tmp_path / "nope.html", out)
    assert r.returncode == 2
    assert "nope.html" in r.stderr
    assert not out.exists()


def fake_tool(tmp_path, name, script):
    """A directory holding an executable `name` running `script`, for PATH."""
    bin_dir = tmp_path / f"fake-{name}"
    bin_dir.mkdir()
    (bin_dir / name).write_text("#!/bin/sh\n" + script)
    (bin_dir / name).chmod(0o755)
    return bin_dir


def run_with(path_dir, *args, env=None):
    env = {**os.environ, **(env or {})}
    if path_dir:
        env["PATH"] = f"{path_dir}:{env['PATH']}"
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)],
                          capture_output=True, text=True, env=env, timeout=120)


NOT_A_PDF = 'while [ "$#" -gt 0 ]; do [ "$1" = -o ] && echo "<html>" > "$2"; shift; done\n'


def test_a_printer_that_leaves_no_pdf_fails_and_publishes_nothing(tmp_path):
    out = tmp_path / "out" / "guide.pdf"
    r = run_with(fake_tool(tmp_path, "shot-scraper", NOT_A_PDF), page(tmp_path), out)
    assert r.returncode == 1
    assert "left no PDF" in r.stderr
    assert list(out.parent.iterdir()) == []


def test_a_git_that_fails_for_another_reason_refuses_rather_than_printing(tmp_path):
    git = fake_tool(tmp_path, "git",
                    'echo "fatal: detected dubious ownership in repository" >&2\nexit 128\n')
    out = tmp_path / "out" / "guide.pdf"
    r = run_with(git, page(tmp_path), out)
    assert r.returncode == 2
    assert "dubious ownership" in r.stderr
    assert not out.exists()


def test_git_environment_variables_do_not_hide_the_repo(tmp_path):
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    out = repo / "guide.pdf"
    r = run_with(None, page(tmp_path), out, env={"GIT_DIR": str(tmp_path / "nonexistent")})
    assert r.returncode == 2
    assert "inside the git work tree" in r.stderr
    assert not out.exists()


def test_a_failed_print_leaves_an_earlier_file_at_the_destination_alone(tmp_path):
    out = tmp_path / "guide.pdf"
    out.write_bytes(b"%PDF-1.4 earlier round")
    r = run_with(fake_tool(tmp_path, "shot-scraper", NOT_A_PDF), page(tmp_path), out)
    assert r.returncode == 1
    assert out.read_bytes() == b"%PDF-1.4 earlier round"
