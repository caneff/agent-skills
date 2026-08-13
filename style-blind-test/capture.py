#!/usr/bin/env python3
"""Side-channel capture CLI for blind-test subject guesses (issue #296).

Records the test subject's blind guess (which style is active) and their
felt strength-of-guess to an append-only JSONL log that the MODEL NEVER
READS -- this module never imports or calls anything model-related, it is
a pure local file append. The scorer (#298) reads the log later and
recomputes ground truth via assignment(session_id).

Schema (one JSON object per line, pinned -- #298 depends on it exactly):
  guess:    {"kind": "guess", "session_id", "style", "confidence", "turn", "ts"}
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


def record_guess(
    session_id: str, style: str, confidence: str, ts: str, turn: int | None = None
) -> dict:
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
        "turn": turn,
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


STYLE_CHOICES = {str(i + 1): style for i, style in enumerate(STYLES)}
CONFIDENCE_CHOICES = dict(zip("lmh", CONFIDENCE_TIERS))

NAMES = {
    "clarity-and-grace": "Clarity and Grace",
    "orwell-ste": "Orwell STE",
    "plain-speak": "Plain Speak",
    "default": "default",
}

DESCRIPTIONS = {
    "clarity-and-grace": "Clear prose with range — character-as-subject, active verbs, varied rhythm (Williams' Style).",
    "orwell-ste": "Clear and direct — Orwell's six rules + Simplified Technical English; short sentences, one term per concept.",
    "plain-speak": "Plain-language default — standard terms OK, invented jargon and needless abbreviations banned.",
    "default": "No injected style — Claude's normal voice.",
}


def parse_style_choice(raw: str) -> str:
    style = STYLE_CHOICES.get(raw.strip())
    if style is None:
        raise ValueError(f"invalid style choice {raw!r}, expected 1-{len(STYLES)}")
    return style


def parse_confidence_choice(raw: str) -> str:
    confidence = CONFIDENCE_CHOICES.get(raw.strip().lower())
    if confidence is None:
        raise ValueError(f"invalid confidence choice {raw!r}, expected l/m/h")
    return confidence


def _current_turn(session_id: str, state_dir: Path | None = None) -> int | None:
    # The turn a guess is logged on = the Stop reminder's per-session counter
    # (issue #316), so a guess records where in the session it landed and drift
    # can be tracked. None when the reminder hook isn't active / no counter yet.
    from stop_reminder import DEFAULT_STATE_DIR, _read_state

    state_dir = state_dir or DEFAULT_STATE_DIR
    count, _ = _read_state(Path(state_dir) / session_id)
    return count or None


def run_guess_wizard(
    input_func=input,
    session_id: str | None = None,
    log_path: Path = DEFAULT_LOG_PATH,
    turn: int | None = None,
    turn_state_dir: Path | None = None,
) -> dict:
    session_id = _resolve_session_id(session_id)
    print(f"Recording guess for session {session_id}")
    for i, style_slug in enumerate(STYLES):
        print(f"  {i + 1}. {NAMES[style_slug]} — {DESCRIPTIONS[style_slug]}")
    style = parse_style_choice(input_func(f"which style is active? [1-{len(STYLES)}] "))
    confidence = parse_confidence_choice(
        input_func("how confident are you in that guess? [l/m/h]  (low / medium / high) ")
    )
    if turn is None:
        turn = _current_turn(session_id, turn_state_dir)
    record = record_guess(
        session_id, style, confidence, datetime.now(timezone.utc).isoformat(), turn=turn
    )
    append(record, log_path)
    return record


def run_strength_wizard(
    input_func=input,
    session_id: str | None = None,
    log_path: Path = DEFAULT_LOG_PATH,
) -> dict:
    session_id = _resolve_session_id(session_id)
    raw_strength = input_func(
        "how strong was the voice this session? [1-5]  (1 = barely there, 5 = unmistakable) "
    )
    try:
        strength = int(raw_strength.strip())
    except ValueError:
        raise ValueError(f"invalid strength {raw_strength!r}, must be an int 1-5")
    faded = _parse_faded(input_func("did the voice fade as the session went on? [y/n] "))
    record = record_strength(
        session_id, strength, faded, datetime.now(timezone.utc).isoformat()
    )
    append(record, log_path)
    return record


def _active_session(turns_dir: Path | None = None) -> str | None:
    # The Stop reminder writes turns/<session_id> every turn, so the newest
    # file there names the session in play (issue #318). Lets `gs` run in a
    # side terminal -- which never inherits CLAUDE_CODE_SESSION_ID -- with no
    # id passed. None when the dir is absent/empty (reminder hook not active).
    # ponytail: newest-mtime wins; picks wrong under two concurrent sessions,
    # exact for solo use. Pass --session-id to override.
    from stop_reminder import DEFAULT_STATE_DIR

    turns_dir = Path(turns_dir or DEFAULT_STATE_DIR)
    if not turns_dir.is_dir():
        return None
    files = [p for p in turns_dir.iterdir() if p.is_file()]
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime).name


def _resolve_session_id(cli_value: str | None, turns_dir: Path | None = None) -> str:
    # #298 recomputes truth via assignment(session_id), so this value must
    # equal the session_id the SessionStart hook received on stdin --
    # i.e. CLAUDE_CODE_SESSION_ID must match the Claude Code session's own
    # id. Proving that equality end-to-end is wiring ticket #299's job.
    session_id = (
        cli_value
        or os.environ.get("CLAUDE_CODE_SESSION_ID")
        or _active_session(turns_dir)
    )
    if not session_id:
        raise ValueError(
            "no session id: pass --session-id, set CLAUDE_CODE_SESSION_ID, "
            "or run with the reminder hook active so a session is detectable"
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
    guess_parser.add_argument("--turn", type=int, default=None)

    strength_parser = subparsers.add_parser("strength", parents=[common])
    strength_parser.add_argument("strength", type=int)
    strength_parser.add_argument("faded")

    subparsers.add_parser("gs", parents=[common])
    subparsers.add_parser("fin", parents=[common])

    args = parser.parse_args(argv)

    if args.command in ("gs", "fin"):
        try:
            if args.command == "gs":
                run_guess_wizard(session_id=args.session_id, log_path=args.log_path)
            else:
                run_strength_wizard(session_id=args.session_id, log_path=args.log_path)
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            raise SystemExit(1)
        return

    try:
        session_id = _resolve_session_id(args.session_id)
        ts = datetime.now(timezone.utc).isoformat()
        if args.command == "guess":
            record = record_guess(session_id, args.style, args.confidence, ts, turn=args.turn)
        else:
            record = record_strength(session_id, args.strength, _parse_faded(args.faded), ts)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1)

    append(record, args.log_path)


if __name__ == "__main__":
    main()
