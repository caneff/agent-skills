#!/usr/bin/env -S uv run --with lzstring --quiet python
"""Pull title/author/rules from a SudokuPad link or id.

Usage: extract_puzzle.py <sudokupad-url-or-id>
Prints JSON {title, author, rules, solution, layout} to stdout. `solution` is
the puzzle's embedded solution string (row-major digits, as SudokuPad stores
it), or null when the puzzle carries none. Exits non-zero if fetch/decode fails.

The API returns an lz-string(base64) blob prefixed with a format tag ("scl").
Two payload shapes exist: SudokuMaker exports are valid JSON with the fields
under "metadata"; legacy SudokuPad blobs are a JS object literal (unquoted keys,
`t`/`f` bools) — not strict JSON — so those we string-slice instead of parsing.
"""
import json, re, sys, urllib.request


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
    """
    IMG_H, CPL, LINE, GAP, CHROME = 450, 52, 21, 14, 70
    h = CHROME
    for para in filter(str.strip, rules_text.split("\n\n")):
        body = para.split(": ", 1)[1] if ": " in para[:30] else para
        h += LINE * (1 + max(1, -(-len(body) // CPL))) + GAP
    return "one" if h > IMG_H else "two"


def parse_blob(data):
    """{title, author, rules, solution} from a decompressed blob.

    `solution` is None when absent or empty.
    """
    try:  # SudokuMaker: valid JSON, fields under "metadata"
        m = json.loads(data)["metadata"]
        out = {k: m.get(k) for k in ("title", "author", "rules", "solution")}
    except (ValueError, KeyError, TypeError):  # legacy SudokuPad JS-literal blob
        out = {"title": field(data, "t"), "author": field(data, "author"),
               "rules": field(data, "rules"), "solution": field(data, "solution")}
    out["solution"] = out["solution"] or None
    return out


def main():
    import lzstring
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
    out = parse_blob(data)
    if not out["rules"]:
        sys.exit("no rules field found in puzzle data")
    out["layout"] = layout_hint(out["rules"])
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
