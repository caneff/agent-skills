"""Structure test for the create-lmd-page closing step (#1288): the archive
step exists, passes --slug on every call, asks for the LMD id, allows a skip
naming the backfill fallback, and reports a failed archive.

Blind to: whether a model follows the prose, and the `lmd_archive` command
itself (tested in sudokupad-art#261, #262, #287).
"""
import re
from pathlib import Path

SKILL = (Path(__file__).resolve().parent / "SKILL.md").read_text()


def closing_step():
    m = re.search(r"^## Archive\n(.*?)(?=^## |\Z)", SKILL, re.S | re.M)
    assert m, "SKILL.md has no '## Archive' section"
    return m.group(1)


def archive_commands(text):
    return [line for line in text.splitlines() if "lmd_archive" in line and " archive " in line]



def test_runs_after_clipboard_step():
    assert SKILL.index("## Output") < SKILL.index("## Archive")


def test_first_call_passes_link_and_slug():
    cmds = [c for c in archive_commands(closing_step()) if "--lmd" not in c]
    assert len(cmds) == 1, cmds
    assert "--slug" in cmds[0]
    assert "<sudokupad-link>" in cmds[0]


def test_rerun_passes_lmd_and_slug():
    cmds = [c for c in archive_commands(closing_step()) if "--lmd" in c]
    assert len(cmds) == 1, cmds
    assert "--slug" in cmds[0]


def test_uses_absolute_repo_path_and_archive_clone():
    for c in archive_commands(closing_step()):
        assert "~/src/sudokupad-art" in c
        assert "--archive ~/src/lmd-archive" in c


def test_link_is_the_page_link_verbatim():
    assert "exactly as the page uses" in closing_step()


def test_asks_for_the_lmd_id():
    assert "Ask the user for the puzzle's LMD id" in closing_step()


def test_output_steps_hand_off_to_archive():
    out = SKILL[SKILL.index("## Output"):SKILL.index("## Archive")]
    assert re.search(r"(?m)^4\. Archive the puzzle: run § Archive", out)


def test_skip_names_backfill_fallback():
    t = closing_step()
    assert "backfill" in t
    assert "may skip the id" in t
    assert "match the puzzle by its SudokuPad link" in t


def test_failure_is_reported_not_swallowed():
    t = closing_step()
    assert "A non-zero exit, or any `FAILED` line on stderr, is reported to the user" in t
    assert "never say the puzzle is archived after one" in t
