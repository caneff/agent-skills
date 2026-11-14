"""Structure test for the create-lmd-page flow (#1662): the checks SKILL.md runs around the
driver, the template's `<p>` measure, and the scripts it calls (extractor `solution`, board_png with Pillow and the renderer faked).

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
sys.path.insert(0, str(HERE))
import board_png  # noqa: E402
import extract_puzzle  # noqa: E402


def section(name):
    m = re.search(rf"^## {name}\n(.*?)(?=^## |\Z)", SKILL, re.S | re.M)
    assert m, f"SKILL.md has no '## {name}' section"
    return m.group(1)


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
    """The slice of a PIL image fit() touches. `thumbnail` shrinks in place keeping the aspect
    ratio, as Pillow's does; `saved` records the size each save wrote, by path."""
    LANCZOS = "lanczos"

    def __init__(self, size, saved):
        self.width, self.height = self.size = size
        self.saved = saved

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def load(self):
        pass

    def copy(self):
        return self

    def thumbnail(self, box, method):
        scale = min(box[0] / self.width, box[1] / self.height, 1)
        self.size = (max(1, round(self.width * scale)), max(1, round(self.height * scale)))

    def save(self, path):
        self.saved[str(path)] = self.size


def fake_pil(monkeypatch, size):
    saved = {}
    image = types.SimpleNamespace(open=lambda png: FakeImage(size, saved), LANCZOS=FakeImage.LANCZOS)
    monkeypatch.setitem(sys.modules, "PIL", types.SimpleNamespace(Image=image))
    return saved


def test_fit_shrinks_a_board_over_800_in_place(monkeypatch):
    saved = fake_pil(monkeypatch, (1536, 1200))
    size = board_png.fit("b.png")
    assert saved == {"b.png": size}
    assert max(size) <= 800 and abs(size[0] / size[1] - 1536 / 1200) < 0.01


@pytest.mark.parametrize("size", [(600, 600), (800, 800), (800, 300)])
def test_fit_leaves_a_board_inside_800_alone(monkeypatch, size):
    saved = fake_pil(monkeypatch, size)
    assert board_png.fit("b.png") == size
    assert saved == {}


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


@pytest.mark.parametrize("link, grid", [
    ("https://sudokupad.app/x", True),
    ("https://sudokupad.app/x?setting-nogrid=true", False),
    ("https://sudokupad.app/x?setting-nogrid=1", False),
    ("https://sudokupad.app/x?setting-nogrid=false", True),
])
def test_the_grid_follows_the_links_nogrid_setting(renderer, monkeypatch, tmp_path, link, grid):
    # Check-In's ?setting-nogrid=true link rendered with SudokuPad's grid over its frame (#1659's closing check).
    monkeypatch.setattr(board_png, "fit", lambda png: (1, 1))
    board_png.render(link, tmp_path / "board.png")
    assert renderer.grid is grid


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


@pytest.mark.parametrize("image_id, image", [("0100XY", "image 0100XY"), (None, "an uploaded image whose id was not read")])
@pytest.mark.parametrize("submitted, clicked", [(True, ", Create clicked"), (False, "")])
def test_post_refuses_after_an_earlier_failure_past_the_upload(tmp_path, image_id, image, submitted, clicked):
    earlier = json.dumps({"failed": "no puzzle id", "uploaded": image_id is None, "image_id": image_id,
                          "submitted": submitted}) + "\n"
    (tmp_path / "driver.json").write_text(earlier)
    r = post_with_a_fake_driver(tmp_path)
    assert r.returncode != 0, r
    assert f"an earlier run failed with {image} on LMD{clicked}: no puzzle id" in r.stderr, r.stderr
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


# ---- LMD's base.css caps `p, li` at 35em (#1712) ----

TEMPLATE = (HERE / "reference" / "template.md").read_text()


def test_every_template_p_uncaps_lmds_35em_measure():
    emitted = re.sub(r"<!--.*?-->", "", TEMPLATE, flags=re.S)  # comments mention <p> in prose
    tags = re.findall(r"<p\b[^>]*>", emitted)
    assert tags, "template.md emits no <p>; the check below would pass for nothing"
    bare = [t for t in tags if "max-width: none" not in t]
    assert not bare, f"<p> without max-width: none: {bare}"


# ---- § Edit a live page (#1720) ----

def test_edit_section_runs_the_stream_gate_before_the_driver():
    edit = " ".join(section("Edit a live page").split())
    assert edit.index("stream gate") < edit.index("lmd_driver.mjs")
    assert "Output steps 3 and 4" in edit
    assert "--edit <id>" in edit and "--template" in edit


def test_edit_section_never_activates_and_reuses_the_one_archive_call():
    raw = section("Edit a live page")
    edit = " ".join(raw.split())
    assert 'never clicks "Aktivieren"' in edit
    assert "§ Archive's command" in edit and "--lmd <id>" in edit
    assert not [l for l in raw.splitlines() if "lmd_archive.py" in l]  # the one archive call stays in § Archive


def test_edit_section_states_that_a_failure_stops_it():
    assert "The failure rule above applies" in " ".join(section("Edit a live page").split())
