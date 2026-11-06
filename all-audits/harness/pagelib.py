#!/usr/bin/env python3
"""The one owner of the audit-report page shell (#613).

Every page the harness renders — the sweep index, the mutation sub-index, a
setup-failure page, landed — is the same document: doctype, a head linking
visual-teach's base spine plus the components it uses, and a `<main>` holding
kicker / h1 / lede / body. `page()` is that document and `copy_assets()` puts
the linked files where the relative hrefs point. Nothing else writes a
`<head>`, and nothing else copies assets.

Callers own escaping: `kicker`, `h1`, `lede` and `body` are inserted as HTML
so a caller can put markup in a heading. Escape untrusted text with
`html.escape` before passing it.
"""
import html
import json
import os
import shutil
import subprocess
import sys

VISUAL_TEACH_ASSETS = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "visual-teach", "assets")
)


def page(title, kicker, h1, lede, body, *, prefix="", extra_css=""):
    """The full HTML document, as a string.

    `prefix` is the relative path from the page to the folder holding
    `assets/` ("../" for a page one directory down); `extra_css` is the
    page's own `<style>` block, empty for a page that only needs the base.
    An empty `kicker`, `h1` or `lede` renders no element at all.
    """
    head = [
        "<!doctype html>\n<html lang=\"en\">\n<head>\n",
        '<meta charset="utf-8">\n',
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n',
        f"<title>{html.escape(title)}</title>\n",
        f'<link rel="stylesheet" href="{prefix}assets/base/base.css">\n',
        f'<link rel="stylesheet" href="{prefix}assets/components/callout/callout.css">\n',
        f'<script src="{prefix}assets/base/base.js"></script>\n',
    ]
    if extra_css:
        head.append(f"<style>\n{extra_css}\n</style>\n")
    head.append("</head>\n<body>\n<main>\n")
    if kicker:
        head.append(f'<p class="vt-kicker">{kicker}</p>\n')
    if h1:
        head.append(f"<h1>{h1}</h1>\n")
    if lede:
        head.append(f'<p class="vt-lede">{lede}</p>\n')
    return "".join(head) + body + "</main>\n</body>\n</html>\n"


def copy_assets(dest, components=("callout",)):
    """Copy the assets `page()` links into `dest/assets/`, replacing what is
    there. `dest` is the folder holding the page — an index over a collection
    with no reports still gets its own assets this way, rather than hoisting
    a sibling report's copy."""
    assets = os.path.join(dest, "assets")
    _replace_tree(os.path.join(VISUAL_TEACH_ASSETS, "base"), os.path.join(assets, "base"))
    for name in components:
        _replace_tree(
            os.path.join(VISUAL_TEACH_ASSETS, "components", name),
            os.path.join(assets, "components", name),
        )
    return assets


def _replace_tree(src, dest):
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copytree(src, dest)


# Polls until every `.vt-mermaid` holds an svg (mermaid renders async) or the
# budget runs out, then reports each block that is not a clean render. A block
# with no svg counts as failed: a bridge that never ran must not read as clean.
_MERMAID_JS = """(async () => {
  const blocks = [...document.querySelectorAll('.vt-mermaid')];
  const end = Date.now() + %d;
  while (Date.now() < end && blocks.some(b => !b.querySelector('svg'))) {
    await new Promise(r => setTimeout(r, 100));
  }
  return {total: blocks.length,
          failed: blocks.flatMap((b, i) =>
            !b.querySelector('svg') || b.textContent.includes('Syntax error') ? [i] : [])};
})()"""


def check_mermaid(report_path, *, timeout=20):
    """Render `report_path` headless and return `{"total": n, "failed": [i, ...]}`.

    `failed` holds the 0-based index of every `.vt-mermaid` block that shows
    Mermaid's "Syntax error" box or never rendered an svg. Mermaid fails at
    parse time in the browser, so only a render sees it (#1665). Raises if
    `shot-scraper` is missing or answers something unreadable: a check that
    could not run is not a clean report.
    """
    js = _MERMAID_JS % (timeout * 1000)
    proc = subprocess.run(["shot-scraper", "javascript", report_path, js],
                          capture_output=True, text=True, timeout=timeout + 60)
    if proc.returncode != 0:
        raise RuntimeError(f"shot-scraper failed ({proc.returncode}): {proc.stderr.strip()}")
    result = json.loads(proc.stdout)
    if not isinstance(result, dict) or set(result) != {"total", "failed"}:
        raise RuntimeError(f"unreadable shot-scraper answer: {proc.stdout[:200]!r}")
    return result


def main(argv):
    if len(argv) != 3 or argv[1] != "check-mermaid":
        print("usage: pagelib.py check-mermaid <report.html>", file=sys.stderr)
        return 2
    result = check_mermaid(argv[2])
    for i in result["failed"]:
        print(f"block {i + 1} of {result['total']}: Mermaid syntax error or not rendered")
    if not result["failed"]:
        print(f"{result['total']} mermaid blocks rendered clean")
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
