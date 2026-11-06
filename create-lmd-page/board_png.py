"""Render a SudokuPad link's board to a PNG that fits inside 800x800 (the LMD image box).

Usage (Pillow and the renderer's deps come from the sudokupad-art project):
    uv run --project ~/src/sudokupad-art python ~/.agents/skills/create-lmd-page/board_png.py "<sudokupad-link>" <out.png>

Loads the puzzle (a short id, any link), saves its scl beside <out.png>, has sudokupad-art's
`render_real.js` draw it (with SudokuPad's grid unless the link sets `setting-nogrid`), then shrinks
the PNG in place when either side is over 800 px. A smaller board is left alone. Any failure exits non-zero with the error and leaves no PNG.
"""
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

LIMIT = 800
ART = Path.home() / "src" / "sudokupad-art"


def fit(png):
    """Shrink `png` in place, keeping its aspect ratio, until both sides are <= LIMIT. Returns (w, h)."""
    from PIL import Image
    with Image.open(png) as im:
        im.load()
        if im.width <= LIMIT and im.height <= LIMIT:
            return im.size
        small = im.copy()
    small.thumbnail((LIMIT, LIMIT), Image.LANCZOS)
    small.save(png)
    return small.size


def keeps_grid(link):
    """False when the link turns SudokuPad's grid off (`?setting-nogrid=true` or `=1`). render_real honours
    a link's own setting only on its link path, and this renders the saved scl, so the link's must be passed."""
    values = parse_qs(urlsplit(link).query).get("setting-nogrid", [])
    return not any(v.lower() in ("true", "1") for v in values)


def render(link, out):
    sys.path.insert(0, str(ART))
    import codec
    import render_real
    out = Path(out)
    scl = render_real.scl_file(out)
    scl.parent.mkdir(parents=True, exist_ok=True)
    scl.write_text(codec.dump_scl(codec.load(link)))
    try:
        render_real.screenshot([(scl, out)], grid=keeps_grid(link))
        return fit(out)
    except BaseException:
        out.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    w, h = render(sys.argv[1], sys.argv[2])
    print(f"wrote {sys.argv[2]} ({w}x{h})")
