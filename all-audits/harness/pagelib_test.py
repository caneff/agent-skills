"""Tests for the shared page shell (#613). Two seams: the document `page()`
returns, and the assets `copy_assets()` puts on disk in a tmp dir."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import pagelib  # noqa: E402


def test_page_carries_the_head_links_and_the_given_content():
    doc = pagelib.page(
        title="All-audits index",
        kicker="All-audits sweep",
        h1="myrepo",
        lede="Everything is fine.",
        body="<h2>Reports</h2>\n",
    )
    assert doc.startswith("<!doctype html>")
    assert "<title>All-audits index</title>" in doc
    assert '<link rel="stylesheet" href="assets/base/base.css">' in doc
    assert '<link rel="stylesheet" href="assets/components/callout/callout.css">' in doc
    assert '<script src="assets/base/base.js"></script>' in doc
    assert '<p class="vt-kicker">All-audits sweep</p>' in doc
    assert "<h1>myrepo</h1>" in doc
    assert '<p class="vt-lede">Everything is fine.</p>' in doc
    assert "<h2>Reports</h2>" in doc
    assert doc.rstrip().endswith("</html>")


def test_prefix_reaches_assets_from_a_subdirectory_and_extra_css_lands():
    doc = pagelib.page("Mutation sub-index", "", "", "", "<p>x</p>",
                       prefix="../", extra_css="main { --vt-measure: 1080px; }")
    assert '<link rel="stylesheet" href="../assets/base/base.css">' in doc
    assert '<script src="../assets/base/base.js"></script>' in doc
    assert "<style>\nmain { --vt-measure: 1080px; }\n</style>" in doc
    assert "vt-kicker" not in doc, "an empty kicker renders no element"
    assert "vt-lede" not in doc, "an empty lede renders no element"


def test_copy_assets_delivers_base_and_the_named_components_idempotently(tmp_path):
    for _ in range(2):
        pagelib.copy_assets(str(tmp_path))
        assert (tmp_path / "assets" / "base" / "base.css").is_file()
        assert (tmp_path / "assets" / "base" / "base.js").is_file()
        assert (tmp_path / "assets" / "components" / "callout" / "callout.css").is_file()
        assert not (tmp_path / "assets" / "assets").is_dir(), "assets/assets nesting"
        assert not (tmp_path / "assets" / "base" / "base").is_dir(), "base/base nesting"


def test_copy_assets_takes_the_component_list(tmp_path):
    pagelib.copy_assets(str(tmp_path), components=("callout", "chip"))
    assert (tmp_path / "assets" / "components" / "chip" / "chip.css").is_file()
