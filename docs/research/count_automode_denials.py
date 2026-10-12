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
_REJECT = "The user doesn't want to proceed"
_CLASSIFIER = "auto mode classifier"
_NO_VERDICT_RE = re.compile(r"auto mode classifier gave no verdict \(([^)]+)\)")


@dataclass(frozen=True)
class Edit:
    at: datetime
    label: str


def _utc(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc)


# Short sha of each edit: 10-04 batch 995e036 6b7ee99 7665b61 14d6328;
# 10-06 2c050fb; 10-09 twitch fa30798; 10-09 5376d70 + b790890; 10-11 423ecc8.
# Author times of the commits that changed what the classifier or the hooks
# read from `flow/claude/settings.json` since the 2026-10-06 note. Commits
# 995e0364, 6b7ee99d, 7665b619 and 14d6328b landed within eight minutes and are
# one edit. 5376d708 (permissions) and b7908905 (self-modification blanket)
# are four minutes apart and are one edit, cut at the earlier.
EDITS = [
    Edit(_utc("2026-10-04T15:14:37-04:00"), "10-04 batch: reversibility line, ILD, LMD, soft_deny trim"),
    Edit(_utc("2026-10-06T11:01:32-04:00"), "10-06 read-only git allow"),
    Edit(_utc("2026-10-09T10:58:15-04:00"), "10-09 twitch rig entry"),
    Edit(_utc("2026-10-09T13:04:30-04:00"), "10-09 git commit allow, wider self-modification"),
    Edit(_utc("2026-10-11T13:08:21-04:00"), "10-11 ledger rewrite, run-output reads"),
]


@dataclass(frozen=True)
class Call:
    at: datetime
    tool: str


@dataclass(frozen=True)
class Denial:
    at: datetime
    kind: str  # classifier | unavailable | hook | reject
    reason: str
    tool: str
    detail: str


@dataclass
class Transcripts:
    calls: list[Call] = field(default_factory=list)
    denials: list[Denial] = field(default_factory=list)
    files: int = 0
    bad_lines: int = 0
    undated: int = 0
    duplicates: int = 0
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
            return " ".join(inp[key].split())[:160]
    return " ".join(json.dumps(inp, sort_keys=True).split())[:160]


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
        return "hook", Path(m.group(1)).name if m else "(unnamed hook)"
    if _REJECT in text:
        return "reject", "user"
    return None


def read_transcripts(root: Path) -> Transcripts:
    out = Transcripts()
    uses: dict[str, tuple[str, str]] = {}
    seen_use: set[str] = set()
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
                        tid = b.get("id", "")
                        if tid in seen_use:
                            out.duplicates += 1
                            continue
                        seen_use.add(tid)
                        uses[tid] = (b.get("name", "?"), _detail(b.get("input")))
                        out.calls.append(Call(at, b.get("name", "?")))
                    elif b.get("is_error"):
                        tid = b.get("tool_use_id", "")
                        if tid in seen_result:
                            out.duplicates += 1
                            continue
                        seen_result.add(tid)
                        pending.append((at, tid, _text(b.get("content"))))

    for at, tid, text in pending:
        got = _classify(text)
        if got is None:
            continue
        tool, detail = uses.get(tid, ("?", ""))
        out.denials.append(Denial(at, got[0], got[1], tool, detail))
    out.denials.sort(key=lambda d: d.at)
    return out


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
        return round(1000 * self.classifier / self.calls, 1) if self.calls else None


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
    for call in tr.calls:
        window_of(call.at, ws).calls += 1
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
    for call in tr.calls:
        days.setdefault(call.at.astimezone(tz).strftime("%Y-%m-%d"), Counter())["calls"] += 1
    for d in tr.denials:
        days.setdefault(d.at.astimezone(tz).strftime("%Y-%m-%d"), Counter())[d.kind] += 1
    keys = ("calls", "classifier", "hook", "reject", "unavailable")
    return {k: {f: days[k][f] for f in keys} for k in sorted(days)}


def missing_days(tr: Transcripts, tz=None) -> list[str]:
    """Days between the first and last event with no tool call: a gap in the
    transcripts on disk, not a day with zero denials."""
    if tr.first is None or tr.last is None:
        return []
    have = {c.at.astimezone(tz).date() for c in tr.calls}
    day, end = tr.first.astimezone(tz).date(), tr.last.astimezone(tz).date()
    out = []
    while day <= end:
        if day not in have:
            out.append(day.isoformat())
        day += timedelta(days=1)
    return out


def soft_deny_names(settings: Path) -> set[str]:
    rules = json.load(open(settings)).get("autoMode", {}).get("soft_deny")
    if not isinstance(rules, list) or not rules:
        raise ValueError(f"{settings}: autoMode.soft_deny is missing or empty")
    return {r.split(" [named", 1)[0].strip() for r in rules
            if isinstance(r, str) and " [named" in r}


def _day(at: datetime | None) -> str:
    return at.astimezone().strftime("%m-%d %H:%M") if at else "—"


def render(tr: Transcripts, ws: list[Window], soft_deny: set[str]) -> str:
    L: list[str] = []
    L.append("## Coverage\n")
    L.append(f"- {tr.files} transcript files, {len(tr.calls)} tool calls, "
             f"{len(tr.denials)} denials, {tr.duplicates} duplicate ids dropped.")
    L.append(f"- First event {_day(tr.first)}, last {_day(tr.last)} (local time).")
    gaps = missing_days(tr)
    L.append("- No transcripts for: " + (", ".join(g[5:] for g in gaps) or "no day") +
             " (a gap on disk, not zero denials).")
    L.append(f"- {tr.bad_lines} unparseable lines and {tr.undated} undated tool "
             "blocks were not counted.\n")
    L.append("## Windows\n")
    L.append("| W | Window | From | To | Calls | Classifier | /1k | No verdict | Hook | Reject |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for i, w in enumerate(ws):
        rate = "n/a" if w.per_1k is None else f"{w.per_1k}"
        L.append(f"| W{i} | {w.label} | {_day(w.start)} | {_day(w.end)} | {w.calls} | "
                 f"{w.classifier} | {rate} | {w.unavailable} | {w.hook} | {w.reject} |")
    L.append("\n## Classifier reasons per window\n")
    names = sorted({r for w in ws for r in w.reasons},
                   key=lambda r: -sum(w.reasons[r] for w in ws))
    L.append("| Reason | Source | " + " | ".join(f"W{i}" for i in range(len(ws))) + " |")
    L.append("|---|---|" + "---|" * len(ws))
    for r in names:
        src = ("—" if r == UNLABELLED
               else "soft_deny" if r in soft_deny else "built-in")
        L.append(f"| {r} | {src} | " + " | ".join(str(w.reasons[r]) for w in ws) + " |")
    L.append("")
    L.append("## Hook blocks per window\n")
    hooks = sorted({h for w in ws for h in w.hooks})
    L.append("| Hook | " + " | ".join(f"W{i}" for i in range(len(ws))) + " |")
    L.append("|---|" + "---|" * len(ws))
    for h in hooks:
        L.append(f"| {h} | " + " | ".join(str(w.hooks[h]) for w in ws) + " |")
    L.append("\n## Per day (local time)\n")
    L.append("| Day | Calls | Classifier | /1k | No verdict | Hook | Reject |")
    L.append("|---|---|---|---|---|---|---|")
    for day, v in daily(tr).items():
        rate = f"{round(1000 * v['classifier'] / v['calls'], 1)}" if v["calls"] else "n/a"
        L.append(f"| {day} | {v['calls']} | {v['classifier']} | {rate} | "
                 f"{v['unavailable']} | {v['hook']} | {v['reject']} |")
    L.append("\n## Latest window: denied calls\n")
    last = ws[-1]
    for r in sorted(last.samples, key=lambda r: -len(last.samples[r])):
        for d in last.samples[r][:5]:
            L.append(f"- {r}: {d.tool} `{d.detail}`")
    if not last.samples:
        L.append("- none")
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    ap.add_argument("--settings", type=Path, default=DEFAULT_SETTINGS)
    ap.add_argument("--edit", action="append", default=[], metavar="ISO=LABEL")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    edits = list(EDITS)
    for spec in args.edit:
        iso, _, label = spec.partition("=")
        edits.append(Edit(_utc(iso), label or iso))
    tr = read_transcripts(args.root)
    ws = tally(tr, edits)
    if args.json:
        json.dump([{"label": w.label, "start": w.start and w.start.isoformat(),
                    "end": w.end and w.end.isoformat(), "calls": w.calls,
                    "classifier": w.classifier, "unavailable": w.unavailable, "hook": w.hook, "reject": w.reject,
                    "reasons": dict(w.reasons), "hooks": dict(w.hooks)} for w in ws],
                  sys.stdout, indent=1)
        print()
    else:
        print(render(tr, ws, soft_deny_names(args.settings)), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
