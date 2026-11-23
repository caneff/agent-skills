#!/usr/bin/env python3
"""Print a solve guide's HTML page to PDF with `shot-scraper pdf`, which
drives Playwright's installed Chromium.

    print_pdf.py <guide.html> <out.pdf>

A guide of a published puzzle is a solution path, never committed anywhere
(sudoku-kit AGENTS.md), so a destination inside any git work tree is refused.
Only git's own "not a git repository" answer counts as outside; any other git
failure is refused too, and git runs with the caller's GIT_* variables
cleared, so none of them can point it away from the destination. The PDF is
written under a temporary name beside the destination and renamed into place
only once it starts with `%PDF-`, so a reader never opens a half file and a
failed print leaves an earlier file there alone. Prints the PDF's path.

Exit codes: 0 printed; 1 shot-scraper ran but left no PDF; 2 refused (the
page is missing, the destination is inside a git work tree or git could not
say, or shot-scraper is not on PATH).
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

USAGE = "usage: print_pdf.py <guide.html> <out.pdf>"


class Refused(Exception):
    """Nothing was printed: an input or the environment rules it out."""


class Failed(Exception):
    """The printer ran and left no PDF."""


def work_tree(path):
    """The git work tree holding `path` (or its nearest existing parent), or
    None when git says it is not in one. Any other git failure is Refused."""
    probe = path
    while not probe.exists():
        probe = probe.parent
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    r = subprocess.run(["git", "-C", str(probe), "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True, env=env)
    if r.returncode == 0:
        return r.stdout.strip()
    if "not a git repository" in r.stderr:
        return None
    raise Refused(f"git could not say whether {probe} is in a work tree: "
                  f"{r.stderr.strip()}")


def print_pdf(html, out):
    html, out = Path(html).resolve(), Path(out).resolve()
    if not html.is_file():
        raise Refused(f"no page at {html}")
    tree = work_tree(out.parent)
    if tree:
        raise Refused(f"{out} is inside the git work tree {tree}: a solve "
                      "guide is never committed; name a destination outside "
                      "every repo")
    binary = shutil.which("shot-scraper")
    if binary is None:
        raise Refused("shot-scraper is not on PATH: "
                      "`uv tool install shot-scraper && shot-scraper install`")
    out.parent.mkdir(parents=True, exist_ok=True)
    part = out.with_name(f".{out.name}.partial")
    part.unlink(missing_ok=True)
    r = subprocess.run([binary, "pdf", str(html), "-o", str(part),
                        "--format", "a4", "--print-background", "--silent"],
                       capture_output=True, text=True, timeout=120)
    if not part.is_file() or not part.read_bytes().startswith(b"%PDF-"):
        part.unlink(missing_ok=True)
        raise Failed(f"shot-scraper exited {r.returncode} and left no PDF: "
                     f"{r.stderr.strip()[-400:]}")
    part.replace(out)
    return out


def main():
    if len(sys.argv) != 3:
        print(USAGE, file=sys.stderr)
        return 2
    try:
        print(print_pdf(*sys.argv[1:]))
    except Refused as e:
        print(f"print_pdf: {e}", file=sys.stderr)
        return 2
    except Failed as e:
        print(f"print_pdf: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
