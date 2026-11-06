"""Structure test for the create-lmd-page flow (#1662): the SKILL.md prose that the spec's
acceptance criteria name, the checks SKILL.md runs around the driver, and the scripts it
calls (extractor `solution`, board_png with Pillow and the renderer faked).

Runs nothing from ~/src/sudokupad-art or ~/src/twitch-rules-scroller. Blind to: whether a
model follows the prose, the `lmd_archive` command itself (sudokupad-art #261, #262, #287),
the rig's stream gate and stream-browser launch, the driver (lmd_driver_test.py), and a
real render or a real OBS.
"""
import json
import re
import subprocess
import sys
import types
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SKILL = (HERE / "SKILL.md").read_text()
FLAT = " ".join(SKILL.split())  # prose wraps; assert on the sentence, not the line break
sys.path.insert(0, str(HERE))
import board_png  # noqa: E402
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


# ---- board_png, with Pillow and sudokupad-art's renderer faked ----

class FakeImage:
    """The slice of a PIL image fit() touches; records what fit() asked of it."""
    LANCZOS = "lanczos"

    def __init__(self, size, log):
        self.width, self.height = self.size = size
        self.log = log

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def load(self):
        pass

    def copy(self):
        return self

    def thumbnail(self, box, method):
        self.log.append(("thumbnail", box, method))
        self.size = (1, 1)

    def save(self, path):
        self.log.append(("save", str(path)))


def fake_pil(monkeypatch, size):
    log = []
    image = types.SimpleNamespace(open=lambda png: FakeImage(size, log), LANCZOS=FakeImage.LANCZOS)
    monkeypatch.setitem(sys.modules, "PIL", types.SimpleNamespace(Image=image))
    return log


def test_fit_shrinks_a_board_over_800_in_place(monkeypatch):
    log = fake_pil(monkeypatch, (1536, 1200))
    assert board_png.fit("b.png") == (1, 1)
    assert log == [("thumbnail", (800, 800), "lanczos"), ("save", "b.png")]


@pytest.mark.parametrize("size", [(600, 600), (800, 800), (800, 300)])
def test_fit_leaves_a_board_inside_800_alone(monkeypatch, size):
    log = fake_pil(monkeypatch, size)
    assert board_png.fit("b.png") == size
    assert log == []


@pytest.fixture
def renderer(monkeypatch):
    """sudokupad-art's codec and render_real, faked; `shot` is what screenshot() does."""
    calls = types.SimpleNamespace(shots=None, shot=lambda out: out.write_bytes(b"png"))

    def screenshot(shots, grid):
        calls.shots, calls.grid = shots, grid
        calls.shot(shots[0][1])

    monkeypatch.setitem(sys.modules, "codec", types.SimpleNamespace(load=lambda link: ("puzzle", link),
                                                                     dump_scl=lambda p: f"scl of {p[1]}"))
    monkeypatch.setitem(sys.modules, "render_real", types.SimpleNamespace(
        scl_file=lambda png: Path(png).with_suffix(".scl.txt"), screenshot=screenshot))
    monkeypatch.setattr(sys, "path", list(sys.path))  # render() prepends ART; keep it from leaking
    return calls


def test_render_draws_the_link_with_its_grid_and_returns_the_fitted_size(renderer, monkeypatch, tmp_path):
    monkeypatch.setattr(board_png, "fit", lambda png: (700, 650))
    out = tmp_path / "work" / "board.png"
    assert board_png.render("https://sudokupad.app/x", out) == (700, 650)
    assert renderer.shots == [(out.with_suffix(".scl.txt"), out)] and renderer.grid is True
    assert out.with_suffix(".scl.txt").read_text() == "scl of https://sudokupad.app/x"
    assert out.read_bytes() == b"png"


def test_render_deletes_the_png_when_the_renderer_fails_after_writing_it(renderer, tmp_path):
    def half_done(out):
        out.write_bytes(b"partial")
        raise RuntimeError("renderer died")
    renderer.shot = half_done
    out = tmp_path / "board.png"
    with pytest.raises(RuntimeError, match="renderer died"):
        board_png.render("x", out)
    assert not out.exists()


def test_render_deletes_the_png_when_the_fit_fails(renderer, monkeypatch, tmp_path):
    monkeypatch.setattr(board_png, "fit", lambda png: (_ for _ in ()).throw(OSError("bad png")))
    out = tmp_path / "board.png"
    with pytest.raises(OSError, match="bad png"):
        board_png.render("x", out)
    assert not out.exists()


# ---- the driver.json checks around the driver call ----

def output_command(marker):
    """The one SKILL.md command line containing `marker`, as a shell command."""
    lines = [l.strip() for l in section("Output").splitlines() if marker in l and l.strip().startswith("cd ")]
    assert len(lines) == 1, (marker, lines)
    return lines[0]


def run_in(work, command):
    command = command.replace("cd ~/lmd-pages/work/<slug>", f"cd {work}", 1)
    assert command.startswith(f"cd {work} "), command
    return subprocess.run(["bash", "-c", command], capture_output=True, text=True)


def post_with_a_fake_driver(work):
    """The Post command with the driver replaced by one that writes a fresh puzzle."""
    command, n = re.subn(r"node\.exe .*> driver\.json$", """echo '{"puzzle_id": "999"}' > driver.json""",
                         output_command("lmd_driver.mjs"))
    assert n == 1
    return run_in(work, command)


def test_post_refuses_when_driver_json_holds_an_earlier_puzzle(tmp_path):
    earlier = '{"image_id": "5", "puzzle_id": "12345", "puzzle_url": "u", "html": "h"}\n'
    (tmp_path / "driver.json").write_text(earlier)
    r = post_with_a_fake_driver(tmp_path)
    assert r.returncode != 0 and "already holds puzzle 12345" in r.stderr, r.stderr
    assert (tmp_path / "driver.json").read_text() == earlier


@pytest.mark.parametrize("submitted, clicked", [(True, ", Create clicked"), (False, "")])
def test_post_refuses_after_an_earlier_failure_past_the_upload(tmp_path, submitted, clicked):
    earlier = json.dumps({"failed": "no puzzle id", "image_id": "0100XY", "submitted": submitted}) + "\n"
    (tmp_path / "driver.json").write_text(earlier)
    r = post_with_a_fake_driver(tmp_path)
    assert r.returncode != 0, r
    assert f"failed after uploading image 0100XY{clicked}: no puzzle id" in r.stderr, r.stderr
    assert (tmp_path / "driver.json").read_text() == earlier


@pytest.mark.parametrize("earlier", [None, ""])
def test_post_runs_the_driver_with_no_earlier_output(tmp_path, earlier):
    if earlier is not None:
        (tmp_path / "driver.json").write_text(earlier)
    r = post_with_a_fake_driver(tmp_path)
    assert r.returncode == 0, r.stderr
    assert json.loads((tmp_path / "driver.json").read_text()) == {"puzzle_id": "999"}


def check_driver_output(work, text):
    (work / "driver.json").write_text(text)
    return run_in(work, output_command('"puzzle_url"'))


def test_driver_output_check_passes_a_whole_output_and_prints_the_id(tmp_path):
    r = check_driver_output(tmp_path, '{"image_id": "5", "puzzle_id": "12345", "puzzle_url": "u", "html": "h"}\n')
    assert r.returncode == 0 and r.stdout.strip() == "12345", r


@pytest.mark.parametrize("text, missing", [
    ("", "puzzle_id, puzzle_url, html"),
    ('{"puzzle_id": "1", "html": "h"}', "puzzle_url"),
    ('{"puzzle_id": "", "puzzle_url": "u", "html": "h"}', "puzzle_id"),
    ('{"puzzle_id": "1", "puzzle_url": "u", "html": null}', "html"),
])
def test_driver_output_check_fails_on_a_missing_or_empty_key(tmp_path, text, missing):
    r = check_driver_output(tmp_path, text)
    assert r.returncode != 0 and r.stderr.strip() == f"driver.json lacks {missing}", r.stderr


def test_driver_checks_bracket_the_driver_call_in_order():
    out = section("Output")
    post, check, page = out.index("lmd_driver.mjs)"), out.index('"puzzle_url","html"'), out.index("**Write the page file.**")
    assert post < check < page < out.index("**Archive**")


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
    cmd = "layout/install-preflight.mjs obs\n"
    assert out.count(cmd) == 1, "the gate command must appear exactly once, as its own line"
    gate_at, driver_at = out.index(cmd), out.index("lmd_driver.mjs")
    assert gate_at < driver_at
    assert "Before any driver call" in out


def test_stream_browser_is_probed_and_launched_after_the_gate_and_before_the_driver():
    out = section("Output")
    gate = out.index("install-preflight.mjs obs")
    probe = out.index("127.0.0.1:9334/json/version")
    launch = out.index("Start-Process")
    driver = out.index("lmd_driver.mjs)")
    assert gate < probe < launch < driver
    launch_line = out[launch:out.index("\n", launch)]
    assert "--remote-debugging-port=9334" in launch_line and "stream-profile" in launch_line
    assert "Any `chrome-stream.exe` line is a refusal" in " ".join(out.split())


def test_driver_runs_through_windows_node():
    assert "node.exe" in section("Output")


def test_image_step_names_render_real_and_the_800_limit():
    out = " ".join(section("Output").split())
    assert "board_png.py" in out and "render_real.js" in out and "800×800" in out
    assert "stays 420 (two-column) or 600 (one-column)" in out
    assert "if either side is over 800, stop" not in out, "board_png.fit guarantees it; the check cannot fire"


def test_aktivieren_is_left_to_chris_and_hand_off_is_the_puzzle_link():
    assert 'Chris reviews the page and clicks "Aktivieren" himself' in FLAT
    out = section("Output")
    hand_off = out[out.index("**Hand-off.**"):]
    assert "puzzle_url" in hand_off and "puzzle page link" in hand_off


def test_archive_waits_for_chris_to_activate_after_the_hand_off():
    # Chris's ruling on #1662 (A1 = a): LMD hides an inactive puzzle from the anonymous
    # fetch lmd_archive makes, so the one archive call runs only once he says he activated it.
    out = section("Output")
    hand_off, archive = out.index("**Hand-off.**"), out.index("**Archive**")
    assert hand_off < archive
    wait = " ".join(out[hand_off:archive].split())
    assert 'say once he has clicked "Aktivieren"' in wait and "Wait for that answer" in wait


def test_failure_stops_the_skill_and_is_reported_with_output():
    assert "A failure stops the skill" in FLAT
    assert "reported to the user with the command's output" in FLAT
    assert "no fallback to the manual flow" in FLAT
    assert "never say the puzzle is posted or archived after a failure" in FLAT
    assert "the report also names the page file it wrote, `~/lmd-pages/work/<slug>/page.html`" in FLAT


def test_the_failure_rule_is_stated_once():
    for phrase in ("reported to the user with the command's output", "report its output and stop"):
        assert FLAT.count(phrase) <= 1, phrase


def test_a_null_title_is_asked_for_right_after_the_link():
    inputs = " ".join(section("Inputs").split("###")[0].split())
    link, title, notes = inputs.index("**SudokuPad link**"), inputs.index("**title**"), inputs.index("**Notes**")
    assert link < title < notes
    assert "`title` is `null`" in inputs and "one message of its own" in inputs


def test_solution_code_and_tag_confirmation_flow():
    assert "plain readout" in SKILL
    assert "Sudoku_JaNein" in SKILL and "`Ja`" in SKILL
    assert "**Labels**" in SKILL and "**Free tags**" in SKILL
    assert "in **one** message" in FLAT


def test_driver_values_point_at_the_drivers_header_instead_of_restating_it():
    out = " ".join(section("Output").split())
    assert "with the keys and types the header of `lmd_driver.mjs` lists" in out
    header = (HERE / "lmd_driver.mjs").read_text().split("\nimport ")[0]
    assert "// values.json" in header
    for key in ("slug", "title", "code", "difficulty", "sudoku", "labels", "freetags", "codedescr_en"):
        assert f'"{key}"' in header, key
    assert '"freetags", "codedescr_en"' not in SKILL, "SKILL.md restates the values.json keys"
    assert "()<>~+-*=" not in SKILL, "SKILL.md restates LMD's allowed code characters"
