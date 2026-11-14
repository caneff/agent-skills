"""End-to-end test for spec #1735 (review ledger and briefs, 2026-11-13 sweep).

The spec moved the review-cache key into `multi-axis-code-review/review_cache.py` and
refactored the ledger's worst functions and render-brief's `render`, with every output kept
byte-identical. This drives the shipped scripts as subprocesses, from a linked worktree
(`implement-9`) of a throwaway repo named `agent-skills`, with HOME in a temp dir:

  1. Every importer of the key names one directory for that checkout,
     `<HOME>/.cache/agent-reviews/skills`: `review_ledger.py cache-dir`, counts'
     `default_reviews_dir`, fix-check's `reviews_dir`, codex-audit's `repo_name` under
     `REVIEWS_ROOT`, and the directory render-brief writes its brief into (#1774).
  2. fanout-brief and render-brief load without the ledger (#1774).
  3. render-brief's three axis briefs are byte-identical to what the renderer wrote before
     the split (#1777): `review_cache_e2e_golden/` was written by render-brief at 84c70295,
     with the temp directory masked as `<TMP>`.
  4. The ledger report over every row family is byte-identical to the pre-refactor ledger's
     (#1775, #1776): `docs/research/review_ledger_golden/families.*`, also written at
     84c70295. The harvest-fixture pin beside it covers the harvest path.

Seam: `bash tests/all.sh`, which runs this file.

Blind to: anything a human reads rather than a test asserts: whether a model follows a
skill's prose, whether a present `SKILL.md` instruction is also unambiguous, and the harness
behaviours around them (a hook denying a step, a worker spinning on no-op tool calls, a pane
closing before a question is answered, #925). For this spec in particular, a green run does
not show the refactored functions are under complexity 30 (no complexity tool runs here),
that a reviewer reading a brief behaves as before, or that output stays identical for a row
shape or brief flag the fixtures do not carry.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MACR = ROOT / "multi-axis-code-review"
GOLDEN = Path(__file__).resolve().parent / "review_cache_e2e_golden"
LEDGER_GOLDEN = ROOT / "docs" / "research" / "review_ledger_golden"
FLAGS = ["--base", "origin/main", "--diff-command", "git diff origin/main...HEAD", "--commit", "abc1234 a commit",
         "--spec", "#9", "--ruling", "a ruling", "--choice", "a choice", "--claim", "R1: a claim",
         "--test-command", "bash tests/all.sh", "--capture-stat", "captured: 1 file"]


@pytest.fixture
def box(tmp_path):
    env = {"HOME": str(tmp_path / "home"), "PATH": "/usr/bin:/bin",
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
    (tmp_path / "home").mkdir()
    repo, wt = tmp_path / "agent-skills", tmp_path / "wt"
    for args in (["init", "-q", str(repo)], ["-C", str(repo), "commit", "-q", "--allow-empty", "-m", "x"],
                 ["-C", str(repo), "worktree", "add", "-q", "-b", "implement-9", str(wt)]):
        subprocess.run(["git", *args], env=env, check=True, capture_output=True)
    (tmp_path / "d.patch").write_text("diff --git a/x b/x\n+y\n")
    return tmp_path, wt, env


def run(cwd, env, *argv):
    done = subprocess.run([sys.executable, *map(str, argv)], cwd=cwd, env=env, capture_output=True, text=True)
    assert done.returncode == 0, (argv, done.stderr)
    return done.stdout.strip()


def python(cwd, env, code):
    return run(cwd, env, "-c", f"import sys; sys.path[:0] = {[str(ROOT / d) for d in ('implement', 'implement-spec', 'multi-axis-code-review')]}\n{code}")


def render(tmp, wt, env, axis):
    return run(wt, env, MACR / "render-brief.py", "--axis", axis, "--repo", "agent-skills", "--worktree", wt,
               "--ticket", "9", "--diff", tmp / "d.patch", *FLAGS)


def test_every_importer_of_the_key_names_one_directory(box):
    tmp, wt, env = box
    want = str(tmp / "home" / ".cache" / "agent-reviews" / "skills")
    load_codex_audit = ("import importlib.util; s = importlib.util.spec_from_file_location('ca', "
                        f"{str(ROOT / 'implement' / 'codex-audit.py')!r}); m = importlib.util.module_from_spec(s); "
                        "s.loader.exec_module(m)")
    got = {
        "cache-dir": run(wt, env, MACR / "review_ledger.py", "cache-dir"),
        "counts": python(wt, env, "import counts, runfile; print(counts.default_reviews_dir(runfile.checkout_top('.')))"),
        "fix-check": python(wt, env, "import fix_check; print(fix_check.reviews_dir())"),
        "codex-audit": python(wt, env, f"{load_codex_audit}; print(m.REVIEWS_ROOT / m.repo_name())"),
        "render-brief": os.path.dirname(render(tmp, wt, env, "standards").split()[1]),
    }
    assert got == dict.fromkeys(got, want)


@pytest.mark.parametrize("script", ["implement/fanout-brief.py", "multi-axis-code-review/render-brief.py"])
def test_the_brief_renderers_load_without_the_ledger(box, script):
    tmp, wt, env = box
    code = ("import importlib.util; s = importlib.util.spec_from_file_location('m', "
            f"{str(ROOT / script)!r}); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); "
            "print('review_ledger' in sys.modules, 'review_cache' in sys.modules)")
    assert python(wt, env, code) == "False True"


@pytest.mark.parametrize("axis", ["standards", "spec", "correctness"])
def test_each_axis_brief_is_byte_identical_to_the_renderer_before_the_split(box, axis):
    tmp, wt, env = box
    written = Path(render(tmp, wt, env, axis).split()[1])
    assert written.read_text().replace(str(tmp), "<TMP>") == (GOLDEN / f"brief-9-{axis}.md").read_text()


def test_the_report_over_every_row_family_is_byte_identical_to_the_ledger_before_the_refactor(box):
    tmp, wt, env = box
    ledger = LEDGER_GOLDEN / "families.jsonl"
    for args, golden in ((["--format", "md"], "families.md"), (["--format", "json"], "families.json"),
                         (["--prices", LEDGER_GOLDEN / "prices.json", "--split", "none"], "families-priced.md")):
        out = run(tmp, env, MACR / "review_ledger.py", "report", "--ledger", ledger, *args)
        assert out + "\n" == (LEDGER_GOLDEN / golden).read_text(), golden
