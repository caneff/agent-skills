"""Structure test for the create-lmd-page flow (#1662): the SKILL.md prose that the spec's
acceptance criteria name, plus the three scripts it calls (extractor `solution`, the PNG fit,
the stream gate).

Blind to: whether a model follows the prose, the `lmd_archive` command itself (sudokupad-art
#261, #262, #287), the driver (lmd_driver_test.py), and a real render or a real OBS.
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = (HERE / "SKILL.md").read_text()
FLAT = " ".join(SKILL.split())  # prose wraps; assert on the sentence, not the line break
sys.path.insert(0, str(HERE))
import extract_puzzle  # noqa: E402


def section(name):
    m = re.search(rf"^## {name}\n(.*?)(?=^## |\Z)", SKILL, re.S | re.M)
    assert m, f"SKILL.md has no '## {name}' section"
    return m.group(1)


def archive_commands():
    return [l for l in SKILL.splitlines() if "lmd_archive" in l and " archive " in l]


# ---- the extractor's `solution` ----

def test_extractor_outputs_solution_from_a_sudokumaker_blob():
    blob = json.dumps({"metadata": {"title": "T", "author": "A", "rules": "R", "solution": "123456789"}})
    assert extract_puzzle.parse_blob(blob)["solution"] == "123456789"


def test_extractor_solution_is_null_without_one():
    no_key = json.dumps({"metadata": {"title": "T", "rules": "R"}})
    empty = json.dumps({"metadata": {"title": "T", "rules": "R", "solution": ""}})
    legacy = "{t:'T',rules:'R'}"
    for blob in (no_key, empty, legacy):
        assert extract_puzzle.parse_blob(blob)["solution"] is None, blob


def test_extractor_solution_from_a_legacy_blob():
    assert extract_puzzle.parse_blob("{t:'T',rules:'R',solution:'4321'}")["solution"] == "4321"


# ---- the PNG fit ----

def test_board_png_fit_shrinks_to_inside_800_and_leaves_small_alone():
    """Pillow is sudokupad-art's dependency, not this repo's: the helper runs under that project, as SKILL.md says."""
    code = """
import sys, tempfile
from pathlib import Path
from PIL import Image
sys.path.insert(0, %r)
import board_png
with tempfile.TemporaryDirectory() as d:
    big, small = Path(d, "big.png"), Path(d, "small.png")
    Image.new("RGB", (1536, 1200), "red").save(big)
    Image.new("RGB", (600, 600), "red").save(small)
    print(board_png.fit(big), Image.open(big).size, board_png.fit(small))
""" % str(HERE)
    out = subprocess.run(["uv", "run", "--project", str(Path.home() / "src/sudokupad-art"), "python", "-c", code],
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "(800, 625) (800, 625) (600, 600)"


# ---- the stream gate ----

def gate(status=None, error=None):
    js = """
import { gate } from %r;
const status = %s, error = %s;
const withObs = async (run) => { if (error) throw error; return run(); };
const r = await gate(withObs, async () => status);
console.log(JSON.stringify(r));
""" % ((HERE / "stream_gate.mjs").as_uri(), json.dumps(status),
       "Object.assign(new Error('x'), %s)" % json.dumps(error) if error is not None else "null")
    out = subprocess.run(["node", "--input-type=module", "-e", js], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)["ok"]


def test_gate_passes_only_when_idle_or_obs_not_running():
    assert gate({"streaming": False, "recording": False}) is True
    assert gate(error={"unreachable": True}) is True


def test_gate_refuses_streaming_recording_and_an_unreadable_status():
    assert gate({"streaming": True, "recording": False}) is False
    assert gate({"streaming": False, "recording": True}) is False
    assert gate(error={}) is False


# ---- SKILL.md ----

def test_exactly_one_archive_call_with_slug_and_lmd():
    cmds = archive_commands()
    assert len(cmds) == 1, cmds
    assert "--slug" in cmds[0] and "--lmd" in cmds[0]
    assert "--archive ~/src/lmd-archive" in cmds[0] and "~/src/sudokupad-art" in cmds[0]


def test_link_is_the_page_link_verbatim():
    assert "exactly as the page uses" in section("Archive")


def test_no_ask_for_the_lmd_id():
    assert "Ask the user for the puzzle's LMD id" not in SKILL
    assert "Image id" not in section("Inputs").split("###")[0].split("Order:")[1]


def test_inputs_are_asked_one_per_message_in_order():
    inputs = section("Inputs").split("###")[0]
    assert "each in its own message" in inputs
    order = [inputs.index(k) for k in ("**SudokuPad link**", "**Notes**", "**Solution code description**", "**Difficulty**")]
    assert order == sorted(order)


def test_stream_gate_runs_before_the_driver_call():
    out = section("Output")
    gate_at, driver_at = out.index("stream_gate.mjs"), out.index("lmd_driver.mjs")
    assert gate_at < driver_at
    assert "Before any driver call" in out


def test_driver_runs_through_windows_node():
    assert "node.exe" in section("Output")


def test_image_step_names_render_real_and_the_800_limit():
    out = " ".join(section("Output").split())
    assert "board_png.py" in out and "render_real.js" in out and "800×800" in out
    assert "stays 420 (two-column) or 600 (one-column)" in out


def test_aktivieren_is_left_to_chris_and_hand_off_is_the_puzzle_link():
    assert 'Chris reviews the page and clicks "Aktivieren" himself' in FLAT
    out = section("Output")
    hand_off = out[out.index("**Hand-off.**"):]
    assert "puzzle_url" in hand_off and "puzzle page link" in hand_off


def test_failure_stops_the_skill_and_is_reported_with_output():
    assert "A failure stops the skill" in FLAT
    assert "reported to the user with the command's output" in FLAT
    assert "no fallback to the manual flow" in FLAT
    assert "never say the puzzle is posted or archived after a failure" in FLAT


def test_solution_code_and_tag_confirmation_flow():
    assert "plain readout" in SKILL
    assert "Sudoku_JaNein" in SKILL and "`Ja`" in SKILL
    assert "**Labels**" in SKILL and "**Free tags**" in SKILL
    assert "in **one** message" in FLAT


def test_driver_values_match_the_drivers_contract():
    for key in ("slug", "title", "code", "difficulty", "sudoku", "labels", "freetags", "codedescr_en"):
        assert f'"{key}"' in SKILL, key
