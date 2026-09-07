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
import os
import shutil

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
        f"<title>{title}</title>\n",
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
