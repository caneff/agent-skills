#!/usr/bin/env python3
"""Phase timings for one build ticket, read out of its worktree's main-line
Claude transcript: `python3 burndown/phases.py <worktree-path|ticket-number>...`
prints one line per phase per ticket:

    <identifier> <phase> <start-iso|-> <duration-seconds|->

plus one `waiting_on_controller` line totalling the gaps from an outgoing
SendMessage to the next incoming cross-session message.

Reads only, like cost.py beside it. A worktree with no matching transcript,
or a phase never reached, prints `-` for that phase rather than dying —
partial evidence beats none (#826).
"""
import json
import os
import re
import sys
from datetime import datetime

from cost import project_dir_name

PHASES = ("dispatch", "build", "review_round_1", "verification", "pr_open",
          "report")


def _parse_ts(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def load_mainline_entries(root):
    """Every top-level `*.jsonl` file directly in a project dir, merged and
    time-sorted. Subagent transcripts sit one level down, under
    `<session>/subagents/`, and `os.listdir` here never descends into them."""
    entries = []
    if not os.path.isdir(root):
        return entries
    for name in sorted(os.listdir(root)):
        if not name.endswith(".jsonl"):
            continue
        path = os.path.join(root, name)
        if not os.path.isfile(path):
            continue
        with open(path, errors="replace") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue  # a half-written last line is not a failure
                if isinstance(entry, dict) and entry.get("timestamp"):
                    entries.append(entry)
    entries.sort(key=lambda e: e["timestamp"])
    return entries


def _tool_uses(entries):
    """(timestamp, tool_name, input, tool_use_id) for every assistant
    tool call on the main line, in transcript order."""
    out = []
    for e in entries:
        if e.get("type") != "assistant" or e.get("isSidechain"):
            continue
        for c in e.get("message", {}).get("content", []) or []:
            if isinstance(c, dict) and c.get("type") == "tool_use":
                out.append((e["timestamp"], c.get("name"), c.get("input") or {},
                             c.get("id")))
    return out


def _agent_completion_times(root):
    """tool_use_id -> the real finish time of a background Agent spawn.

    The mainline `tool_result` on an `Agent` tool call only acknowledges
    the async launch, seconds after the call — the subagent's own work
    keeps running and the mainline session goes on to other things while
    it does. The real finish time is the last timestamp in that
    subagent's own transcript, `<session>/subagents/agent-*.jsonl`, whose
    sibling `.meta.json` carries the `toolUseId` linking it back here."""
    out = {}
    if not os.path.isdir(root):
        return out
    for dirpath, _, filenames in os.walk(root):
        if os.path.basename(dirpath) != "subagents":
            continue
        for name in filenames:
            if not name.endswith(".meta.json"):
                continue
            meta_path = os.path.join(dirpath, name)
            try:
                with open(meta_path, errors="replace") as f:
                    meta = json.load(f)
            except ValueError:
                continue
            tool_use_id = meta.get("toolUseId")
            if not tool_use_id:
                continue
            jsonl_path = meta_path[: -len(".meta.json")] + ".jsonl"
            last_ts = None
            if os.path.isfile(jsonl_path):
                with open(jsonl_path, errors="replace") as f:
                    for line in f:
                        try:
                            e = json.loads(line)
                        except ValueError:
                            continue
                        ts = e.get("timestamp") if isinstance(e, dict) else None
                        if ts and (last_ts is None or ts > last_ts):
                            last_ts = ts
            if last_ts:
                out[tool_use_id] = last_ts
    return out


def _tool_result_times(entries):
    """tool_use_id -> earliest timestamp its tool_result completed at."""
    out = {}
    for e in entries:
        if e.get("type") != "user":
            continue
        content = e.get("message", {}).get("content")
        if not isinstance(content, list):
            continue
        for c in content:
            if isinstance(c, dict) and c.get("type") == "tool_result":
                tid = c.get("tool_use_id")
                if tid is not None and (tid not in out or e["timestamp"] < out[tid]):
                    out[tid] = e["timestamp"]
    return out


def _is_incoming_cross_session(entry):
    if entry.get("type") != "user":
        return False
    content = entry.get("message", {}).get("content")
    text = content if isinstance(content, str) else json.dumps(content)
    return "cross-session-message" in text


def compute_phases(entries, agent_completions=None):
    """{phase: (start_iso, duration_seconds)} plus `waiting_on_controller`
    (start is always None for that one — it's a total, not a point). A
    phase this transcript never reached maps to (None, None).

    `agent_completions` is the `tool_use_id -> finish timestamp` map from
    `_agent_completion_times` — the review-phase spans need it because an
    Agent call's own mainline `tool_result` is only the async-launch ack."""
    agent_completions = agent_completions or {}
    result = {p: (None, None) for p in PHASES}
    result["waiting_on_controller"] = (None, 0.0)
    if not entries:
        return result

    result["dispatch"] = (entries[0]["timestamp"], None)

    tool_uses = _tool_uses(entries)
    result_times = _tool_result_times(entries)

    build_uses = [t for t in tool_uses if t[1] in ("Edit", "Write")]
    if build_uses:
        result["build"] = (min(t[0] for t in build_uses), None)

    def is_diff_reviewer(t):
        return t[1] == "Agent" and t[2].get("subagent_type") == "diff-reviewer"

    def is_axis_skill(t):
        return t[1] == "Skill" and t[2].get("skill") == "multi-axis-code-review"

    def is_verification(t):
        blob = (str(t[2].get("description", "")) + " " +
                str(t[2].get("prompt", ""))).lower()
        return "verif" in blob

    round1 = [t for t in tool_uses
              if is_axis_skill(t) or (is_diff_reviewer(t) and not is_verification(t))]
    round2 = [t for t in tool_uses if is_diff_reviewer(t) and is_verification(t)]

    def span(group):
        starts = [t[0] for t in group]
        ends = [agent_completions[t[3]] for t in group
                if t[1] == "Agent" and t[3] in agent_completions]
        if not starts:
            return (None, None)
        start = min(starts)
        if not ends:
            return (start, None)
        end = max(ends)
        return (start, (_parse_ts(end) - _parse_ts(start)).total_seconds())

    result["review_round_1"] = span(round1)
    result["verification"] = span(round2)

    pr_creates = [t for t in tool_uses
                  if t[1] == "Bash" and "gh pr create" in (t[2].get("command") or "")]
    if pr_creates:
        t = min(pr_creates, key=lambda x: x[0])
        end = result_times.get(t[3])
        dur = (_parse_ts(end) - _parse_ts(t[0])).total_seconds() if end else None
        result["pr_open"] = (t[0], dur)

    reports = [t for t in tool_uses
               if t[1] == "SendMessage" and "pr up" in str(t[2].get("message", "")).lower()]
    if reports:
        t = min(reports, key=lambda x: x[0])
        end = result_times.get(t[3])
        dur = (_parse_ts(end) - _parse_ts(t[0])).total_seconds() if end else None
        result["report"] = (t[0], dur)

    outgoing = sorted(t[0] for t in tool_uses if t[1] == "SendMessage")
    incoming = sorted(e["timestamp"] for e in entries if _is_incoming_cross_session(e))
    events = sorted([(ts, "OUT") for ts in outgoing] + [(ts, "IN") for ts in incoming])
    waiting = 0.0
    pending = None
    for ts, kind in events:
        if kind == "OUT":
            if pending is None:
                pending = ts
        elif pending is not None:
            waiting += (_parse_ts(ts) - _parse_ts(pending)).total_seconds()
            pending = None
    result["waiting_on_controller"] = (None, waiting)

    return result


def resolve_worktrees(arg, projects_root):
    """A path arg is used as-is. A bare ticket number is resolved by
    scanning `projects_root` for project dirs ending in `-implement-<n>` —
    every worker's projects dir is named after its worktree path, and
    `implement-dispatch` always names the worktree `implement-<n>`."""
    if re.fullmatch(r"\d+", arg):
        suffix = f"-implement-{arg}"
        if not os.path.isdir(projects_root):
            return []
        matches = [d for d in sorted(os.listdir(projects_root)) if d.endswith(suffix)]
        return [(arg, m) for m in matches]
    return [(arg, project_dir_name(os.path.abspath(arg)))]


def _fmt(value):
    return "-" if value is None else str(value)


def main(argv):
    if len(argv) < 2:
        print("usage: phases.py <worktree-path|ticket-number>...", file=sys.stderr)
        return 2
    projects_root = os.environ.get("BURNDOWN_PROJECTS_DIR") or os.path.expanduser(
        "~/.claude/projects")
    for arg in argv[1:]:
        matches = resolve_worktrees(arg, projects_root)
        if not matches:
            print(f"{arg} - - -", file=sys.stderr)
            continue
        for identifier, project_dir in matches:
            root = os.path.join(projects_root, project_dir)
            entries = load_mainline_entries(root)
            agent_completions = _agent_completion_times(root)
            phases = compute_phases(entries, agent_completions)
            for phase in PHASES:
                start, duration = phases[phase]
                print(f"{identifier} {phase} {_fmt(start)} {_fmt(duration)}")
            print(f"{identifier} waiting_on_controller - {phases['waiting_on_controller'][1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
