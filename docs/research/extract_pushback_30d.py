#!/usr/bin/env python3
"""Extract candidate Claude Code user-pushback events from a calendar 30-day window.

The fixed seed is recorded here and in the output metadata so a >600-session
sample is reproducible and does not privilege the latest week.
"""

from __future__ import annotations

import argparse
import json
import random
import re
from collections import Counter
from datetime import datetime, time, timedelta
from pathlib import Path


SEED = 20260912
PROJECTS = Path.home() / ".claude" / "projects"
SYSTEM_WRAPPERS = ("<system-reminder>", "<local-command-stdout>")
INJECTED_PREFIXES = (
    "<task-notification>",
    "<teammate-message",
    "<command-message>",
    "another claude session sent a message",
    "base directory for this skill:",
    "this session is being continued from a previous conversation",
    "you are working inside orca",
    "- # buildable",
    "- # task open one pull request",
)
PUSHBACK = re.compile(
    r"(?:^\s*(?:no|nope|nah|stop|wait|wrong|actually|but|don't|do not|never)\b|"
    r"\b(?:i (?:already |just )?(?:said|told|asked)|as i said|like i said|"
    r"i told you|you keep|you ignored|you missed|you forgot|"
    r"this (?:is|still) (?:wrong|not)|that(?:'s| is) (?:wrong|not)|"
    r"makes no sense|\b(?:still|again|instead|rather than)\b|"
    r"why (?:do|are|did|can(?:not|'t)|would) you\b|"
    r"fuck(?:ing)?|stupid|ridiculous|unacceptable|useless|goddamn|wtf)\b)",
    re.IGNORECASE,
)


def text_content(content: object) -> str | None:
    if isinstance(content, str):
        return content.strip() or None
    if isinstance(content, list):
        parts = [
            block["text"].strip()
            for block in content
            if isinstance(block, dict)
            and block.get("type") == "text"
            and isinstance(block.get("text"), str)
            and block["text"].strip()
        ]
        return "\n".join(parts) or None
    return None


def is_plumbing(text: str) -> bool:
    stripped = text.lstrip()
    lowered = stripped.lower()
    return any(lowered.startswith(tag) for tag in SYSTEM_WRAPPERS + INJECTED_PREFIXES)


def has_all_caps(text: str) -> bool:
    letters = [char for char in text if char.isalpha()]
    return len(letters) >= 6 and sum(char.isupper() for char in letters) / len(letters) >= 0.72


def tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{3,}", text.lower()))


def is_restatement(text: str, earlier_messages: list[str]) -> bool:
    current = tokens(text)
    if len(current) < 5:
        return False
    for earlier in earlier_messages[-5:]:
        previous = tokens(earlier)
        overlap = len(current & previous) / len(current | previous) if previous else 0
        if overlap >= 0.72:
            return True
    return False


def candidate(text: str, earlier_messages: list[str]) -> list[str]:
    reasons: list[str] = []
    if PUSHBACK.search(text):
        reasons.append("pushback-language")
    if has_all_caps(text):
        reasons.append("all-caps")
    if is_restatement(text, earlier_messages):
        reasons.append("near-repeat")
    return reasons


def session_events(path: Path) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    previous_assistant: dict[str, object] | None = None
    user_history: list[str] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            message = record.get("message")
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            text = text_content(message.get("content"))
            if not text or is_plumbing(text):
                continue
            if role == "assistant":
                previous_assistant = {"line": line_number, "text": text}
            elif role == "user":
                reasons = candidate(text, user_history)
                # A user correction cannot target an assistant that has not
                # spoken yet; this also removes initial skill and worker briefs.
                if reasons and previous_assistant is not None:
                    events.append(
                        {
                            "session_file": str(path),
                            "session_mtime": datetime.fromtimestamp(
                                path.stat().st_mtime
                            ).astimezone().isoformat(),
                            "transcript_line": line_number,
                            "user_message": text,
                            "assistant_before": previous_assistant,
                            "candidate_reasons": reasons,
                        }
                    )
                user_history.append(text)
    return events


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--now", help="ISO timestamp, for a reproducible window")
    args = parser.parse_args()
    now = datetime.fromisoformat(args.now) if args.now else datetime.now().astimezone()
    if now.tzinfo is None:
        now = now.astimezone()
    local_today = now.date()
    start = datetime.combine(local_today - timedelta(days=29), time.min, tzinfo=now.tzinfo)
    end = now
    sessions = [
        path
        for path in PROJECTS.rglob("*.jsonl")
        if start.timestamp() <= path.stat().st_mtime <= end.timestamp()
    ]
    sessions.sort()
    sampled = len(sessions) > 600
    selected = sorted(random.Random(SEED).sample(sessions, 600)) if sampled else sessions
    events = [event for path in selected for event in session_events(path)]
    mtimes = [datetime.fromtimestamp(path.stat().st_mtime, tz=now.tzinfo).isoformat() for path in selected]
    result = {
        "method": {
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "seed": SEED,
            "session_count_in_window": len(sessions),
            "sampled": sampled,
            "selected_session_count": len(selected),
            "selected_mtime_min": min(mtimes, default=None),
            "selected_mtime_max": max(mtimes, default=None),
            "candidate_event_count": len(events),
            "candidate_session_count": len({event["session_file"] for event in events}),
            "candidate_reason_counts": dict(Counter(reason for event in events for reason in event["candidate_reasons"])),
        },
        "events": events,
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
