#!/usr/bin/env python3
"""Side-channel capture CLI for blind-test subject guesses (issue #296).

Records the test subject's blind guess (which style is active) and their
felt strength-of-guess to an append-only JSONL log that the MODEL NEVER
READS -- this module never imports or calls anything model-related, it is
a pure local file append. The scorer (#298) reads the log later and
recomputes ground truth via assignment(session_id).

Schema (one JSON object per line, pinned -- #298 depends on it exactly):
  guess:    {"kind": "guess", "session_id", "style", "confidence", "ts"}
  strength: {"kind": "strength", "session_id", "strength", "faded", "ts"}
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from assignment import STYLES

DEFAULT_LOG_PATH = Path.home() / ".claude" / "style-blind-test" / "log.jsonl"

CONFIDENCE_TIERS = ("low", "med", "high")

YES_VALUES = {"yes", "y", "true"}
NO_VALUES = {"no", "n", "false"}


def record_guess(session_id: str, style: str, confidence: str, ts: str) -> dict:
    if style not in STYLES:
        raise ValueError(f"invalid style {style!r}, must be one of {STYLES}")
    if confidence not in CONFIDENCE_TIERS:
        raise ValueError(
            f"invalid confidence {confidence!r}, must be one of {CONFIDENCE_TIERS}"
        )
    return {
        "kind": "guess",
        "session_id": session_id,
        "style": style,
        "confidence": confidence,
        "ts": ts,
    }


def record_strength(session_id: str, strength: int, faded: bool, ts: str) -> dict:
    if not isinstance(strength, int) or isinstance(strength, bool) or not 1 <= strength <= 5:
        raise ValueError(f"invalid strength {strength!r}, must be an int 1-5")
    return {
        "kind": "strength",
        "session_id": session_id,
        "strength": strength,
        "faded": bool(faded),
        "ts": ts,
    }


def append(record: dict, log_path: Path = DEFAULT_LOG_PATH) -> None:
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as f:
        f.write(json.dumps(record) + "\n")


def _parse_faded(value: str) -> bool:
    lowered = value.lower()
    if lowered in YES_VALUES:
        return True
    if lowered in NO_VALUES:
        return False
    raise ValueError(f"invalid faded value {value!r}, expected yes/no/y/n/true/false")


def _resolve_session_id(cli_value: str | None) -> str:
    # #298 recomputes truth via assignment(session_id), so this value must
    # equal the session_id the SessionStart hook received on stdin --
    # i.e. CLAUDE_CODE_SESSION_ID must match the Claude Code session's own
    # id. Proving that equality end-to-end is wiring ticket #299's job.
    session_id = cli_value or os.environ.get("CLAUDE_CODE_SESSION_ID")
    if not session_id:
        raise ValueError(
            "no session id: set CLAUDE_CODE_SESSION_ID or pass --session-id"
        )
    return session_id


def main(argv: list[str] | None = None) -> None:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--session-id")
    common.add_argument("--log-path", type=Path, default=DEFAULT_LOG_PATH)

    parser = argparse.ArgumentParser(prog="capture", parents=[common])
    subparsers = parser.add_subparsers(dest="command", required=True)

    guess_parser = subparsers.add_parser("guess", parents=[common])
    guess_parser.add_argument("style")
    guess_parser.add_argument("confidence")

    strength_parser = subparsers.add_parser("strength", parents=[common])
    strength_parser.add_argument("strength", type=int)
    strength_parser.add_argument("faded")

    args = parser.parse_args(argv)

    try:
        session_id = _resolve_session_id(args.session_id)
        ts = datetime.now(timezone.utc).isoformat()
        if args.command == "guess":
            record = record_guess(session_id, args.style, args.confidence, ts)
        else:
            record = record_strength(session_id, args.strength, _parse_faded(args.faded), ts)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1)

    append(record, args.log_path)


if __name__ == "__main__":
    main()
