#!/usr/bin/env python3
"""Bordered ASCII-table statusline for Claude Code.

Reads the session JSON on stdin (the same blob ccstatusline segments get) and
draws a real box-drawing grid: two data rows sharing one set of column
dividers, so the ``│`` lines up top-to-bottom like a table.

Data comes from the JSON directly (model, session, git) plus the existing
segment helper scripts, which each read the same JSON on stdin and print one
value. We fan the raw stdin bytes out to each.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

ANSI = re.compile(r"\x1b\[[0-9;]*m")

# Dracula palette
PURPLE, CYAN, GREEN, PINK = "BD93F9", "8BE9FD", "50FA7B", "FF79C6"
ORANGE, YELLOW, GRAY, FG = "FFB86C", "F1FA8C", "6272A4", "F8F8F2"
RED = "FF5555"


def paint(text: str, hex_: str) -> str:
    r, g, b = (int(hex_[i : i + 2], 16) for i in (0, 2, 4))
    return f"\x1b[38;2;{r};{g};{b}m{text}\x1b[0m"

CFG = Path(__file__).resolve().parent / "helpers"


def run(cmd: list[str], stdin: bytes, cwd: str | None = None) -> str:
    """Run a helper, feed it the session JSON, return its trimmed stdout."""
    try:
        out = subprocess.run(
            cmd, input=stdin, capture_output=True, timeout=1.5, cwd=cwd
        ).stdout
        return ANSI.sub("", out.decode("utf-8", "replace")).strip()
    except Exception:
        return ""


def dwidth(s: str) -> int:
    """Terminal cell width, counting emoji / CJK as 2 and zero-widths as 0."""
    w = 0
    for ch in s:
        o = ord(ch)
        if ch in "️‍" or unicodedata.combining(ch):
            continue  # variation selector, ZWJ, combining mark
        if (
            0x1F300 <= o <= 0x1FAFF
            or 0x2600 <= o <= 0x27BF
            or 0x2B00 <= o <= 0x2BFF
            or 0x1F1E6 <= o <= 0x1F1FF
            or unicodedata.east_asian_width(ch) in ("W", "F")
        ):
            w += 2
        else:
            w += 1
    return w


def pad(s: str, width: int) -> str:
    return s + " " * max(0, width - dwidth(s))


def parse_usage_fields(line: str) -> tuple[str, str, str, str]:
    """Split `usage-segment.sh all`'s tab-separated line into its 4 fields.

    Pads with blanks on the right so a trailing empty field (dropped by a
    plain ``.split`` when nothing follows the last tab) still comes back as
    "", matching the single-field modes' "blank when absent" contract.
    """
    weekly, wreset, session, breset = (line.split("\t") + [""] * 4)[:4]
    return weekly, wreset, session, breset


def git(cwd: str) -> tuple[str, str, str]:
    """Return (branch-cell, changes-cell, main-repo-root) for the repo at cwd.

    The root is the *main* worktree's directory even when cwd is a linked
    worktree (``.claude/worktrees/...``), so the path cell shows the repo, not
    the worktree. git-common-dir points at the main repo's ``.git`` from any
    worktree; its parent is that main root. Falls back to ``--show-toplevel``
    (the blind-test toast's convention). All blank if cwd is not a git repo.
    """
    def g(args: list[str]) -> str:
        try:
            return subprocess.run(
                ["git", "-C", cwd, *args],
                capture_output=True,
                timeout=1.0,
                text=True,
            ).stdout.strip()
        except Exception:
            return ""

    if not g(["rev-parse", "--git-dir"]):
        return "", "", ""
    branch = g(["symbolic-ref", "--short", "HEAD"]) or g(["rev-parse", "--short", "HEAD"])
    ins = dele = 0
    for line in g(["diff", "HEAD", "--numstat"]).splitlines():
        a, d, *_ = (line.split("\t") + ["", ""])[:3]
        ins += int(a) if a.isdigit() else 0
        dele += int(d) if d.isdigit() else 0
    common = g(["rev-parse", "--path-format=absolute", "--git-common-dir"])
    root = str(Path(common).parent) if common else g(["rev-parse", "--show-toplevel"])
    return (f"⎇ {branch}" if branch else ""), f"+{ins},-{dele}", root


def context_tokens(transcript: str) -> int:
    """Latest context size (tokens) from the transcript's most recent usage."""
    p = Path(transcript) if transcript else None
    if not p or not p.exists():
        return 0
    total = 0
    try:
        for line in p.read_text("utf-8", "replace").splitlines():
            try:
                u = json.loads(line).get("message", {}).get("usage")
            except Exception:
                continue
            if u:
                total = (
                    u.get("input_tokens", 0)
                    + u.get("cache_read_input_tokens", 0)
                    + u.get("cache_creation_input_tokens", 0)
                )
    except Exception:
        return 0
    return total


def frame_color(tokens: int) -> str:
    """Green → yellow (≥140k) → red (≥180k) by absolute context size."""
    if tokens <= 0:
        return PURPLE  # no data yet
    if tokens >= 180_000:
        return RED
    if tokens >= 140_000:
        return YELLOW
    return GREEN


def table(rows: list[list[tuple[str, str]]], frame: str) -> str:
    """Render equal-column (text, color) rows as a colored box-drawing grid.

    Rounded corners; frame color signals context fill; each cell painted in its
    own color. Widths are measured on the raw text, so the color codes never
    shift the borders.
    """
    cols = max(len(r) for r in rows)
    rows = [r + [("", FG)] * (cols - len(r)) for r in rows]
    w = [max(dwidth(r[c][0]) for r in rows) for c in range(cols)]
    seg = ["─" * (x + 2) for x in w]
    bar = paint("│", frame)
    top = paint("╭" + "┬".join(seg) + "╮", frame)
    mid = paint("├" + "┼".join(seg) + "┤", frame)
    bot = paint("╰" + "┴".join(seg) + "╯", frame)
    body = [
        bar + bar.join(f" {paint(pad(t, w[c]), col)} " for c, (t, col) in enumerate(r)) + bar
        for r in rows
    ]
    lines = [top]
    for i, b in enumerate(body):
        lines.append(b)
        lines.append(mid if i < len(body) - 1 else bot)
    return "\n".join(lines)


def main() -> None:
    raw = sys.stdin.buffer.read()
    try:
        data = json.loads(raw or b"{}")
    except Exception:
        data = {}

    model = (data.get("model") or {}).get("display_name", "")
    cwd = (data.get("workspace") or {}).get("current_dir") or data.get("cwd") or "."
    transcript = data.get("transcript_path", "")

    branch, changes, root = git(cwd)
    tokens = context_tokens(transcript)
    frame = frame_color(tokens)

    # Two windows, "percent reset" each (reset = leading unit), 7d then 5h:
    # "94% 2d · 6% 3h".
    def lead(reset: str) -> str:
        m = re.match(r"\d+[dhm]", reset)
        return m.group() if m else reset

    def win(pct: str, reset: str) -> str:
        return " ".join(x for x in (pct, lead(reset)) if x)

    def model_cell() -> str:
        # "Opus 4.8" -> "O 4.8"; keep the effort suffix, e.g. "O 4.8 (M)"
        effort = run(["python3", str(CFG / "effort-abbrev.py")], raw)
        ver = re.search(r"\d[\d.]*", model)
        short = (f"{model[:1]} {ver.group()}") if model and ver else model
        return f"{short} {effort}".strip()

    def usage_cell() -> str:
        # One spawn for all four fields (not `run()`: its `.strip()` would eat
        # a leading/trailing empty field's tab along with it).
        try:
            out = subprocess.run(
                [str(CFG / "usage-segment.sh"), "all"],
                input=raw,
                capture_output=True,
                timeout=1.5,
            ).stdout
            line = ANSI.sub("", out.decode("utf-8", "replace")).rstrip("\n")
        except Exception:
            line = ""
        weekly, wreset, session, breset = parse_usage_fields(line)
        return " · ".join(x for x in (win(weekly, wreset), win(session, breset)) if x)

    def codex_cell() -> str:
        # Codex's own quota, labelled because the unlabelled percentages next
        # to it are Claude's. Blank — and so dropped — until Codex has run.
        got = run(["python3", str(CFG / "codex-usage.py")], raw)
        return f"Cdx {got}" if got else ""

    cells = [
        (PURPLE, model_cell),
        # Project name only, matching the blind-test toast's `Path(cwd).name`
        # convention; fed the main root so a linked worktree collapses to the
        # project name too, not the worktree's.
        (CYAN, lambda: Path(root or cwd).name),
        (ORANGE, lambda: f"Ctx {tokens / 1000:.1f}k" if tokens else "Ctx —"),
        (PINK, usage_cell),
        (YELLOW, codex_cell),
        (GREEN, lambda: f"{branch} {changes}".strip()),
    ]
    row = [(text, color) for color, build in cells if (text := build())]
    row = row or [(model, PURPLE)]

    print(table([row], frame))

    # ponytail: graft's own statusline (graph size / stale count) as one extra
    # line under the table, only in repos where `graft init` wired it.
    proj = (data.get("workspace") or {}).get("project_dir") or cwd
    graft = Path(proj) / ".claude" / "helpers" / "graft-statusline.cjs"
    if graft.exists():
        line = run(["node", str(graft)], raw, cwd=proj)
        if line:
            print(line)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        assert dwidth("🏰 idle") == 7, dwidth("🏰 idle")  # emoji=2, space, idle=4
        assert dwidth("abc") == 3
        assert dwidth("main") == 4
        out = table([[("a", FG), ("bb", FG)], [("ccc", FG), ("d", FG)]], GREEN)
        # strip color to check the frame aligns on visible width
        widths = {dwidth(ANSI.sub("", l)) for l in out.splitlines()}
        assert len(widths) == 1, f"rows not equal width: {widths}"
        assert "╭" in out and "┬" in out.splitlines()[0]
        assert frame_color(0) == PURPLE
        assert frame_color(139_000) == GREEN
        assert frame_color(140_000) == YELLOW
        assert frame_color(179_000) == YELLOW
        assert frame_color(180_000) == RED
        assert frame_color(250_000) == RED  # over 200k: stays red
        assert parse_usage_fields("42%\t2d3h30m\t12%\t3h10m") == (
            "42%", "2d3h30m", "12%", "3h10m",
        )
        assert parse_usage_fields("\t\t12%\t3h10m") == ("", "", "12%", "3h10m")
        assert parse_usage_fields("") == ("", "", "", "")
        print("ok")
    else:
        main()
