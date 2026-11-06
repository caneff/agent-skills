"""Render a SudokuPad link's board to a PNG that fits inside 800x800 (the LMD image box).

Usage (Pillow and the renderer's deps come from the sudokupad-art project):
    uv run --project ~/src/sudokupad-art python ~/.agents/skills/create-lmd-page/board_png.py "<sudokupad-link>" <out.png>

Loads the puzzle (a short id, any link), saves its scl beside <out.png>, has sudokupad-art's
`render_real.js` draw it, then shrinks the PNG in place when either side is over 800 px. A smaller
board is left alone. Any failure exits non-zero with the error and leaves no PNG.
"""
import sys
from pathlib import Path

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


def render(link, out):
    sys.path.insert(0, str(ART))
    import codec
    import render_real
    out = Path(out)
    scl = render_real.scl_file(out)
    scl.parent.mkdir(parents=True, exist_ok=True)
    scl.write_text(codec.dump_scl(codec.load(link)))
    try:
        render_real.screenshot([(scl, out)], grid=True)
        return fit(out)
    except BaseException:
        out.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    w, h = render(sys.argv[1], sys.argv[2])
    print(f"wrote {sys.argv[2]} ({w}x{h})")
