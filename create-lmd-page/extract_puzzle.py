#!/usr/bin/env -S uv run --with lzstring --quiet python
"""Pull title/author/rules from a SudokuPad link or id.

Usage: extract_puzzle.py <sudokupad-url-or-id>
Prints JSON {title, author, rules} to stdout. Exits non-zero if fetch/decode fails.

The API returns an lz-string(base64) blob prefixed with a format tag ("scl").
Two payload shapes exist: SudokuMaker exports are valid JSON with the fields
under "metadata"; legacy SudokuPad blobs are a JS object literal (unquoted keys,
`t`/`f` bools) — not strict JSON — so those we string-slice instead of parsing.
ponytail: JSON first, slice as fallback; the slice missed on SudokuMaker's metadata.rules.
"""
import json, re, sys, urllib.request
import lzstring


def puzzle_id(arg):
    m = re.search(r"sudokupad\.app/(?:puzzle/)?([^/?#]+)", arg)
    return m.group(1) if m else arg.split("?")[0].strip("/")


def field(blob, key):
    # value is single-quoted, may contain \' escapes; read until the unescaped '
    i = blob.find(key + ":'")
    if i < 0:
        return None
    i += len(key) + 2
    esc = {"n": "\n", "t": "\t", "r": "\r", "'": "'", "\\": "\\"}
    out = []
    while i < len(blob):
        c = blob[i]
        if c == "\\":
            nxt = blob[i + 1]
            out.append(esc.get(nxt, nxt)); i += 2; continue
        if c == "'":
            break
        out.append(c); i += 1
    return "".join(out)


def layout_hint(rules_text):
    """"two" columns unless the Rules card would stand taller than the image.

    Estimates the card's rendered height (~320px-wide column, ~52 chars/line,
    21px lines, a bold title line per rule) against a ~450px image block. Taller
    rules -> "one" column (rules fall below the image at full width).
    ponytail: crude px estimate, not a real layout engine; nudge the constants if the flip lands wrong.
    """
    IMG_H, CPL, LINE, GAP, CHROME = 450, 52, 21, 14, 70
    h = CHROME
    for para in filter(str.strip, rules_text.split("\n\n")):
        body = para.split(": ", 1)[1] if ": " in para[:30] else para
        h += LINE * (1 + max(1, -(-len(body) // CPL))) + GAP
    return "one" if h > IMG_H else "two"


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: extract_puzzle.py <sudokupad-url-or-id>")
    pid = puzzle_id(sys.argv[1])
    url = f"https://sudokupad.app/api/puzzle/{pid}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=20).read().decode().strip()
    body = re.sub(r"^scl", "", raw)
    data = lzstring.LZString().decompressFromBase64(body)
    if not data:
        sys.exit("decompress failed (unexpected blob format)")
    try:  # SudokuMaker: valid JSON, fields under "metadata"
        m = json.loads(data)["metadata"]
        out = {k: m.get(k) for k in ("title", "author", "rules")}
    except (ValueError, KeyError, TypeError):  # legacy SudokuPad JS-literal blob
        out = {"title": field(data, "t"), "author": field(data, "author"),
               "rules": field(data, "rules")}
    if not out["rules"]:
        sys.exit("no rules field found in puzzle data")
    out["layout"] = layout_hint(out["rules"])
    print(json.dumps(out, indent=2, ensure_ascii=False))


def _selfcheck():
    assert field("t:'it\\'s here',x:'y'", "t") == "it's here", "escaped quote mid-value"
    assert field("t:'plain',x:'y'", "t") == "plain", "plain value stops at closing quote"
    short = "Normal sudoku rules apply.\n\nHit Counts: short clue.\n\nHit Lines: short clue."
    long = "\n\n".join(f"Rule {i}: " + "word " * 60 for i in range(5))
    assert layout_hint(short) == "two", "short rules should stay two-column"
    assert layout_hint(long) == "one", "long rules should drop to one column"
    print("ok")


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--selfcheck":
        _selfcheck()
    else:
        main()
