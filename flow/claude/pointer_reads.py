#!/usr/bin/env python3
"""Pointer-doc read count (#1413): do sessions read the docs under
flow/claude/ when they run the commands those docs are for?

    pointer_reads.py count --end <iso> [--start <iso>] [--projects <dir>]
    pointer_reads.py recount [--today <iso>] [--root <repo>] [--projects <dir>]
    pointer_reads.py install-cron

`count` prints the two tables of
docs/research/2026-10-04-claude-md-pointer-reads.md for a window ending at
--end (default start: 14 days before). It is the 2026-10-04 grep, made
replayable: a transcript is in the window when its mtime or any top-level
`timestamp` falls in it, and only its lines up to --end are searched. With
--end 2026-10-04T17:52:01Z it reproduces that note's first table, and with
17:54:33Z its second (the two were run two minutes apart).

`recount` is the one-shot cron job Chris ruled on 2026-10-04 (option a). It
asks `gh` for #1413's closedAt and exits silently while the ticket is open or
until 14 days after it closed. On or after that day it counts the 14 days
after closedAt, appends the dated result to the note in a throwaway worktree
of origin/main, commits and pushes it, and removes its own crontab line. A
closedAt it cannot read is an error, never a quiet "not yet". `install-cron`
adds that crontab line once.

Pure grep: no model call.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

TICKET = 1413
REPO = "caneff/agent-skills"
NOTE = "docs/research/2026-10-04-claude-md-pointer-reads.md"
WINDOW = timedelta(days=14)
CRON_TAG = "# pointer-reads-recount-1413"
ROOT = Path(__file__).resolve().parents[2]


def cron_line() -> str:
    # The primary checkout, never this file's own worktree, which merge-cleanup
    # deletes. Absolute paths throughout: cron runs with PATH=/usr/bin:/bin.
    common = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--path-format=absolute",
                             "--git-common-dir"], capture_output=True, text=True, check=True).stdout
    primary = Path(common.strip()).parent
    return (f"17 9 * * * PATH={Path.home()}/.local/bin:/usr/bin:/bin python3 "
            f"{primary}/flow/claude/pointer_reads.py recount "
            f">> {Path.home()}/.cache/pointer-reads-recount.log 2>&1  {CRON_TAG}")

# (doc, trigger regex, skills that already carry the procedure): the
# 2026-10-04 note's rows, in its order.
DOCS = [
    ("OPERATIONS", "gh pr merge|implement-dispatch|merge-cleanup", "burndown|implement"),
    ("WORKFLOW", "gh issue create|gh issue edit",
     "burndown|implement|file-ticket|to-tickets|to-spec|wayfinder|grilling"),
    ("VISUAL-INSPECTION", "shot-scraper|zed ", "computer-use|visual-teach|prototype"),
    ("SHELL-SAFETY", "pkill|kill -|kill [0-9]", "diagnosing-bugs"),
]


def iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def stamp(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def transcript(path: Path, start: datetime, end: datetime) -> str | None:
    """The text of `path` up to `end`, or None when it is not in the window."""
    kept, last, inside = [], None, False
    with open(path, errors="replace") as f:
        for raw in f:
            try:
                ts = json.loads(raw).get("timestamp")
            except (ValueError, AttributeError):
                ts = None
            if isinstance(ts, str):
                try:
                    last = iso(ts)
                except ValueError:
                    pass
            if last is not None and last > end:
                break
            if last is not None and last > start:
                inside = True
            kept.append(raw)
    # A line appended without a timestamp still moves the mtime, and the
    # original `find -mtime -14` counted that file.
    mtime = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    if start < mtime <= end:
        inside = True
    return "".join(kept) if inside else None


def sessions(projects: Path, start: datetime, end: datetime) -> list[str]:
    out = []
    for path in sorted(projects.rglob("*.jsonl")):
        if "subagents" in path.relative_to(projects).parts:
            continue
        text = transcript(path, start, end)
        if text is not None:
            out.append(text)
    return out


def tables(projects: Path, start: datetime, end: datetime) -> str:
    texts = sessions(projects, start, end)
    raw = ["| Doc | Trigger regex | Triggered | Read |", "|---|---|---|---|"]
    covered = ["| Doc | Triggered | Not covered by a skill | Of those, read the doc |",
               "|---|---|---|---|"]
    for doc, trigger, skills in DOCS:
        trig = re.compile(r'"command":"[^"]*(' + trigger + ")")
        read = re.compile(r'"(file_path|command)":"[^"]*flow/claude/' + doc + r"\.md")
        skill = re.compile(r'Base directory for this skill: [^"]*/(' + skills + r")\b")
        hit = [t for t in texts if trig.search(t)]
        bare = [t for t in hit if not skill.search(t)]
        n_read = sum(1 for t in hit if read.search(t))
        cell = trigger.replace("|", "\\|")  # a bare | would end the table cell
        raw.append(f"| {doc} | `{cell}` | {len(hit)} | {n_read} |")
        covered.append(f"| {doc} | {len(hit)} | {len(bare)} | {sum(1 for t in bare if read.search(t))} |")
    return "\n".join([f"Window: {stamp(start)} to {stamp(end)}. Sessions in the window: {len(texts)}.",
                      "", *raw, "", *covered, ""])


def closed_at() -> datetime | None:
    """#1413's closedAt; None while it is open. Raises on anything unreadable."""
    p = subprocess.run(["gh", "issue", "view", str(TICKET), "--repo", REPO, "--json", "state,closedAt"],
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"gh could not read closedAt for #{TICKET}: {p.stderr.strip()}")
    try:
        data = json.loads(p.stdout)
        state, when = data["state"], data["closedAt"]
    except (ValueError, KeyError, TypeError) as e:
        raise RuntimeError(f"gh returned no readable closedAt for #{TICKET}: {e!r}: {p.stdout[:200]}")
    if state == "OPEN":
        return None
    if not when:
        raise RuntimeError(f"#{TICKET} is {state} but gh returned no closedAt")
    return iso(when)


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True,
                          text=True).stdout


def crontab_without_tag() -> None:
    p = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    lines = p.stdout.splitlines(keepends=True) if p.returncode == 0 else []
    subprocess.run(["crontab", "-"], input="".join(l for l in lines if CRON_TAG not in l),
                   text=True, check=True)


def recount(today: datetime, root: Path, projects: Path) -> int:
    try:
        closed = closed_at()
    except RuntimeError as e:
        print(f"pointer_reads recount: {e}", file=sys.stderr)
        return 1
    if closed is None or today < closed + WINDOW:
        return 0
    end = closed + WINDOW
    heading = f"## Re-count {end:%Y-%m-%d}"
    body = (f"\n{heading}: 14 days after #{TICKET} closed\n\n"
            f"Same space and regexes as above, over the 14 days after #{TICKET} closed at "
            f"{stamp(closed)}; written by `flow/claude/pointer_reads.py recount` from cron.\n\n"
            + tables(projects, closed, end))
    git("fetch", "-q", "origin", "main", cwd=root)
    tree = Path(tempfile.mkdtemp(prefix="pointer-reads-")) / "tree"
    git("worktree", "add", "-q", "--detach", str(tree), "origin/main", cwd=root)
    try:
        note = tree / NOTE
        if heading not in note.read_text():
            with open(note, "a") as f:
                f.write(body)
            git("commit", "-q", "-m", f"research: pointer-doc re-count 14 days after #{TICKET}",
                "--", NOTE, cwd=tree)
            git("push", "-q", "origin", "HEAD:main", cwd=tree)
            print(f"appended {heading} to {NOTE} and pushed")
    finally:
        git("worktree", "remove", "--force", str(tree), cwd=root)
    crontab_without_tag()
    print("removed the crontab line")
    return 0


def install_cron() -> int:
    p = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    current = p.stdout if p.returncode == 0 else ""
    if CRON_TAG in current:
        return 0
    if current and not current.endswith("\n"):
        current += "\n"
    line = cron_line()
    subprocess.run(["crontab", "-"], input=current + line + "\n", text=True, check=True)
    print(line)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("count")
    c.add_argument("--end", type=iso, required=True)
    c.add_argument("--start", type=iso)
    c.add_argument("--projects", type=Path, default=Path.home() / ".claude" / "projects")
    r = sub.add_parser("recount")
    r.add_argument("--today", type=iso, default=datetime.now(timezone.utc))
    r.add_argument("--root", type=Path, default=ROOT)
    r.add_argument("--projects", type=Path, default=Path.home() / ".claude" / "projects")
    sub.add_parser("install-cron")
    a = ap.parse_args()
    if a.cmd == "count":
        print(tables(a.projects, a.start or a.end - WINDOW, a.end), end="")
        return 0
    if a.cmd == "recount":
        return recount(a.today, a.root, a.projects)
    return install_cron()


if __name__ == "__main__":
    sys.exit(main())
