#!/usr/bin/env python3
"""Count auto-mode denials per settings-edit window (#1538).

Reads every `~/.claude/projects/**/*.jsonl` transcript, subagents included,
and counts three denial kinds against tool calls:

- classifier: a `tool_result` with `is_error` whose text carries `auto mode
  classifier`; its reason is the bracketed name after `Reason:`
- unavailable: the classifier gave no verdict (timeout or error). Not a
  denial and not in the classifier count; the 2026-10-06 note counted these
- hook: an error carrying `PreToolUse:`; its reason is the hook script's name
- reject: an error carrying `The user doesn't want to proceed`

Events are bucketed into windows cut at each settings edit in `EDITS`
(commit author time of `flow/claude/settings.json`), so each window is the
state of the settings between two edits. A tool_use id seen in two files
counts once; unparseable and undated lines are counted and reported.

Usage:
    python3 count_automode_denials.py [--root DIR] [--settings FILE]
        [--edit ISO=LABEL ...] [--json]

`--edit` adds an edit to `EDITS`. Coverage (first and last event, bad lines)
is part of the output: a window outside it is not measured.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

UNLABELLED = "(no bracketed reason)"
DEFAULT_ROOT = Path.home() / ".claude" / "projects"
DEFAULT_SETTINGS = Path(__file__).resolve().parents[2] / "flow" / "claude" / "settings.json"

_REASON_RE = re.compile(r"Reason: \[([^\]]+)\]")
_HOOK_RE = re.compile(r"PreToolUse:\S* hook error: \[([^\]]+)\]")
DETAIL_CHARS = 300
PROBE_PREFIX = "probe:"
_REJECT = "The user doesn't want to proceed"
_CLASSIFIER = "auto mode classifier"
_NO_VERDICT_RE = re.compile(r"auto mode classifier gave no verdict \(([^)]+)\)")


@dataclass(frozen=True)
class Edit:
    at: datetime
    label: str


def _utc(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc)


# Author times of the commits that changed what the classifier read from
# `flow/claude/settings.json` (autoMode), plus 5376d708, a permissions edit
# that sits four minutes before b7908905. Edit batches: 10-04 995e036, 6b7ee99,
# 7665b61 and 14d6328 (within eight minutes, one edit); 10-06 2c050fb; 10-09
# fa30798; 10-09 5376d70 + b790890 (cut at the earlier); 10-11 423ecc8.
# Not edits here, and so folded into the window they fall in: five settings
# commits later on 10-04 (ef02c8e, 97807bf, 4edea84, 96ceb59, 29956f9: hooks,
# a resolve-controller allow, the `uv run:*` widening and an ask list), which
# make W1 a mixed state, and 77beeed (10-09, the DISPLAY env var).
EDITS = [
    Edit(_utc("2026-10-04T15:14:37-04:00"), "10-04 batch: reversibility line, ILD, LMD, soft_deny trim"),
    Edit(_utc("2026-10-06T11:01:32-04:00"), "10-06 read-only git allow"),
    Edit(_utc("2026-10-09T10:58:15-04:00"), "10-09 twitch rig entry"),
    Edit(_utc("2026-10-09T13:04:30-04:00"), "10-09 git commit allow, wider self-modification"),
    Edit(_utc("2026-10-11T13:08:21-04:00"), "10-11 ledger rewrite, run-output reads"),
]


@dataclass(frozen=True)
class Denial:
    at: datetime
    kind: str  # classifier | unavailable | hook | reject
    reason: str
    tool: str
    detail: str


@dataclass
class Transcripts:
    calls: list[datetime] = field(default_factory=list)
    denials: list[Denial] = field(default_factory=list)
    files: int = 0
    bad_lines: int = 0
    undated: int = 0
    duplicates: int = 0
    probe_hooks: int = 0
    first: datetime | None = None
    last: datetime | None = None


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(b.get("text", "") for b in content if isinstance(b, dict))
    return ""


def _detail(inp) -> str:
    if not isinstance(inp, dict):
        return ""
    for key in ("command", "file_path", "path", "skill", "pattern", "url"):
        if isinstance(inp.get(key), str):
            return " ".join(inp[key].split())[:DETAIL_CHARS]
    return " ".join(json.dumps(inp, sort_keys=True).split())[:DETAIL_CHARS]


def _classify(text: str):
    """The denial kind and reason a tool_result's error text carries, or None."""
    m = _NO_VERDICT_RE.search(text)
    if m:
        return "unavailable", m.group(1)
    if _CLASSIFIER in text:
        m = _REASON_RE.search(text)
        return "classifier", m.group(1) if m else UNLABELLED
    if "PreToolUse:" in text:
        m = _HOOK_RE.search(text)
        if not m:
            return "hook", "(unnamed hook)"
        hook = m.group(1).split()[-1]
        return "hook", PROBE_PREFIX + hook if hook.startswith("/tmp/") else Path(hook).name
    if _REJECT in text:
        return "reject", "user"
    return None


def read_transcripts(root: Path) -> Transcripts:
    out = Transcripts()
    uses: dict[str, tuple[str, str]] = {}
    seen_result: set[str] = set()
    pending: list[tuple[datetime, str, str]] = []  # (at, tool_use_id, error text)

    def note(at: datetime) -> None:
        out.first = at if out.first is None or at < out.first else out.first
        out.last = at if out.last is None or at > out.last else out.last

    for path in sorted(Path(root).rglob("*.jsonl")):
        out.files += 1
        with open(path, errors="replace") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    out.bad_lines += 1
                    continue
                msg = obj.get("message") if isinstance(obj, dict) else None
                content = msg.get("content") if isinstance(msg, dict) else None
                if not isinstance(content, list):
                    continue
                blocks = [b for b in content if isinstance(b, dict)
                          and b.get("type") in ("tool_use", "tool_result")]
                if not blocks:
                    continue
                try:
                    at = _utc(obj["timestamp"])
                except (KeyError, TypeError, ValueError):
                    out.undated += 1
                    continue
                note(at)
                for b in blocks:
                    if b["type"] == "tool_use":
                        tid = b.get("id")
                        if tid and tid in uses:
                            out.duplicates += 1
                            continue
                        if tid:
                            uses[tid] = (b.get("name", "?"), _detail(b.get("input")))
                        out.calls.append(at)
                    elif b.get("is_error"):
                        tid = b.get("tool_use_id")
                        if tid and tid in seen_result:
                            out.duplicates += 1
                            continue
                        if tid:
                            seen_result.add(tid)
                        pending.append((at, tid, _text(b.get("content"))))

    for at, tid, text in pending:
        got = _classify(text)
        if got is None:
            continue
        if got[0] == "hook" and got[1].startswith(PROBE_PREFIX):
            out.probe_hooks += 1  # a /tmp probe hook, not a configured one
            continue
        tool, detail = uses.get(tid, ("?", ""))
        out.denials.append(Denial(at, got[0], got[1], tool, detail))
    out.denials.sort(key=lambda d: d.at)
    return out


def rate_per_1k(n: int, calls: int) -> float | None:
    """Events per 1,000 calls; None, not 0, when there were no calls."""
    return round(1000 * n / calls, 1) if calls else None


@dataclass
class Window:
    label: str
    start: datetime | None
    end: datetime | None
    calls: int = 0
    classifier: int = 0
    unavailable: int = 0
    hook: int = 0
    reject: int = 0
    reasons: Counter = field(default_factory=Counter)
    hooks: Counter = field(default_factory=Counter)
    samples: dict = field(default_factory=dict)

    @property
    def per_1k(self) -> float | None:
        return rate_per_1k(self.classifier, self.calls)


def windows(edits: list[Edit]) -> list[Window]:
    edits = sorted(edits, key=lambda e: e.at)
    ws = [Window("baseline", None, edits[0].at)]
    for i, e in enumerate(edits):
        end = edits[i + 1].at if i + 1 < len(edits) else None
        ws.append(Window(e.label, e.at, end))
    return ws


def window_of(at: datetime, ws: list[Window]) -> Window:
    for w in ws:
        if (w.start is None or at >= w.start) and (w.end is None or at < w.end):
            return w
    raise ValueError(f"no window holds {at}")


def tally(tr: Transcripts, edits: list[Edit]) -> list[Window]:
    ws = windows(edits)
    for at in tr.calls:
        window_of(at, ws).calls += 1
    for d in tr.denials:
        w = window_of(d.at, ws)
        setattr(w, d.kind, getattr(w, d.kind) + 1)
        if d.kind == "classifier":
            w.reasons[d.reason] += 1
            w.samples.setdefault(d.reason, []).append(d)
        elif d.kind == "hook":
            w.hooks[d.reason] += 1
    return ws


def daily(tr: Transcripts, tz=None) -> dict[str, dict[str, int]]:
    days: dict[str, Counter] = {}
    for at in tr.calls:
        days.setdefault(at.astimezone(tz).strftime("%Y-%m-%d"), Counter())["calls"] += 1
    for d in tr.denials:
        days.setdefault(d.at.astimezone(tz).strftime("%Y-%m-%d"), Counter())[d.kind] += 1
    keys = ("calls", "classifier", "hook", "reject", "unavailable")
    return {k: {f: days[k][f] for f in keys} for k in sorted(days)}


def missing_days(tr: Transcripts, tz=None) -> list[str]:
    """Days between the first and last event with no tool call: a gap in the
    transcripts on disk, not a day with zero denials."""
    if tr.first is None or tr.last is None:
        return []
    have = {at.astimezone(tz).date() for at in tr.calls}
    day, end = tr.first.astimezone(tz).date(), tr.last.astimezone(tz).date()
    out = []
    while day <= end:
        if day not in have:
            out.append(day.isoformat())
        day += timedelta(days=1)
    return out


def soft_deny_names(settings: Path) -> set[str]:
    """The rule names in autoMode.soft_deny. Refuses a missing or empty list
    and any rule (other than `$defaults`) without the ` [named` marker the
    name is read before: that rule would otherwise be labelled built-in."""
    rules = json.load(open(settings)).get("autoMode", {}).get("soft_deny")
    if not isinstance(rules, list) or not rules:
        raise ValueError(f"{settings}: autoMode.soft_deny is missing or empty")
    names = set()
    for r in rules:
        if r == "$defaults":
            continue
        if not isinstance(r, str) or " [named" not in r:
            raise ValueError(f"{settings}: soft_deny rule has no ' [named' marker: {str(r)[:60]!r}")
        names.add(r.split(" [named", 1)[0].strip())
    if not names:
        raise ValueError(f"{settings}: autoMode.soft_deny names no rule")
    return names


def _day(at: datetime | None, tz=None) -> str:
    return at.astimezone(tz).strftime("%m-%d %H:%M") if at else "—"


def _coverage(tr: Transcripts, tz=None) -> list[str]:
    gaps = missing_days(tr, tz)
    return [
        "## Coverage\n",
        f"- {tr.files} transcript files, {len(tr.calls)} tool calls, "
        f"{len(tr.denials)} denials, {tr.duplicates} duplicate ids dropped.",
        f"- First event {_day(tr.first, tz)}, last {_day(tr.last, tz)}.",
        "- No transcripts for: " + (", ".join(g[5:] for g in gaps) or "no day") +
        " (a gap on disk, not zero denials).",
        f"- {tr.bad_lines} unparseable lines, {tr.undated} undated tool blocks "
        f"and {tr.probe_hooks} hook errors from /tmp probe hooks were not counted.\n",
    ]


def _windows_table(ws: list[Window], tz=None) -> list[str]:
    L = ["## Windows\n",
         "| W | Window | From | To | Calls | Classifier | /1k | No verdict | Hook | Reject |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for i, w in enumerate(ws):
        rate = "n/a" if w.per_1k is None else f"{w.per_1k}"
        L.append(f"| W{i} | {w.label} | {_day(w.start, tz)} | {_day(w.end, tz)} | {w.calls} | "
                 f"{w.classifier} | {rate} | {w.unavailable} | {w.hook} | {w.reject} |")
    return L


def _counter_table(title: str, ws: list[Window], attr: str, source=None) -> list[str]:
    names = sorted({k for w in ws for k in getattr(w, attr)},
                   key=lambda k: -sum(getattr(w, attr)[k] for w in ws))
    head = "| Reason | Source |" if source else "| Hook |"
    L = [f"\n## {title}\n",
         head + " " + " | ".join(f"W{i}" for i in range(len(ws))) + " |",
         "|---|" + ("---|" if source else "") + "---|" * len(ws)]
    for k in names:
        cells = " | ".join(str(getattr(w, attr)[k]) for w in ws)
        L.append(f"| {k} | " + (f"{source(k)} | " if source else "") + cells + " |")
    return L


def _daily_table(tr: Transcripts, tz=None) -> list[str]:
    L = ["\n## Per day\n",
         "| Day | Calls | Classifier | /1k | No verdict | Hook | Reject |",
         "|---|---|---|---|---|---|---|"]
    for day, v in daily(tr, tz).items():
        rate = rate_per_1k(v["classifier"], v["calls"])
        L.append(f"| {day} | {v['calls']} | {v['classifier']} | "
                 f"{'n/a' if rate is None else rate} | {v['unavailable']} | "
                 f"{v['hook']} | {v['reject']} |")
    return L


def _denied_calls(ws: list[Window]) -> list[str]:
    L = ["\n## Denied calls, every window after the baseline\n"]
    n = len(L)
    for i, w in enumerate(ws[1:], 1):
        for r in sorted(w.samples, key=lambda r: -len(w.samples[r])):
            for d in w.samples[r]:
                L.append(f"- W{i} {_day(d.at)} {r}: {d.tool} `{d.detail}`")
    return L if len(L) > n else L + ["- none"]


def render(tr: Transcripts, ws: list[Window], soft_deny: set[str], tz=None) -> str:
    def source(r: str) -> str:
        return "—" if r == UNLABELLED else "soft_deny" if r in soft_deny else "built-in"
    L = (_coverage(tr, tz) + _windows_table(ws, tz)
         + _counter_table("Classifier reasons per window", ws, "reasons", source)
         + _counter_table("Hook blocks per window", ws, "hooks")
         + _daily_table(tr, tz) + _denied_calls(ws))
    return "\n".join(L) + "\n"


def as_json(tr: Transcripts, ws: list[Window]) -> dict:
    return {
        "coverage": {"files": tr.files, "calls": len(tr.calls), "denials": len(tr.denials),
                     "duplicates": tr.duplicates, "bad_lines": tr.bad_lines,
                     "undated": tr.undated, "probe_hooks": tr.probe_hooks,
                     "first": tr.first and tr.first.isoformat(),
                     "last": tr.last and tr.last.isoformat(),
                     "days_without_transcripts": missing_days(tr)},
        "windows": [{"label": w.label, "start": w.start and w.start.isoformat(),
                     "end": w.end and w.end.isoformat(), "calls": w.calls,
                     "classifier": w.classifier, "unavailable": w.unavailable,
                     "hook": w.hook, "reject": w.reject,
                     "reasons": dict(w.reasons), "hooks": dict(w.hooks)} for w in ws],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    ap.add_argument("--settings", type=Path, default=DEFAULT_SETTINGS)
    ap.add_argument("--edit", action="append", default=[], metavar="ISO=LABEL")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if not args.root.is_dir():
        print(f"error: transcript root {args.root} is not a directory", file=sys.stderr)
        return 2
    try:
        soft_deny = soft_deny_names(args.settings)
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    edits = list(EDITS)
    for spec in args.edit:
        iso, _, label = spec.partition("=")
        edits.append(Edit(_utc(iso), label or iso))
    tr = read_transcripts(args.root)
    if not tr.calls:
        print(f"error: no tool calls found under {args.root}", file=sys.stderr)
        return 2
    ws = tally(tr, edits)
    if args.json:
        json.dump(as_json(tr, ws), sys.stdout, indent=1)
        print()
    else:
        print(render(tr, ws, soft_deny), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
