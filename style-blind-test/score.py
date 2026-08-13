#!/usr/bin/env python3
"""Batch reveal: score blind guesses against ground truth (issue #298).

The ONLY place truth is revealed. tally() is pure -- it takes already
-assembled per-session records and returns stats, never touching disk or
assignment(). main() does all the I/O: parse the log, recompute truth via
assignment(), count transcript turns, then hand tally() clean records.
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean

from assignment import STYLES, assignment

DEFAULT_LOG_PATH = Path.home() / ".claude" / "style-blind-test" / "log.jsonl"
DEFAULT_PROJECTS_DIR = Path.home() / ".claude" / "projects"

CONFIDENCE_TIERS = ("low", "med", "high")
QUALIFYING_TURNS = 15


def count_assistant_turns(session_id: str, projects_dir: Path = DEFAULT_PROJECTS_DIR) -> int:
    # Counts assistant *message events* as a proxy for turns -- a turn with
    # N tool calls yields N assistant lines. Coarse but deliberate.
    projects_dir = Path(projects_dir)
    for path in projects_dir.glob(f"*/{session_id}.jsonl"):
        if "subagents" in path.relative_to(projects_dir).parts:
            continue
        count = 0
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            if json.loads(line).get("type") == "assistant":
                count += 1
        return count
    return 0


def _hit_rate(records):
    if not records:
        return None
    hits = sum(1 for r in records if r["guess"] == r["truth"])
    return hits / len(records)


def tally(records: list[dict]) -> dict:
    guessed = [r for r in records if r["guess"] is not None]
    nondefault_guessed = [r for r in guessed if r["truth"] != "default"]
    qualifying = [r for r in records if r["turns"] >= QUALIFYING_TURNS]

    by_confidence = {}
    for tier in CONFIDENCE_TIERS:
        by_confidence[tier] = _hit_rate([r for r in guessed if r["confidence"] == tier])

    def mean_strength(hook_on):
        strengths = [
            r["strength"] for r in qualifying
            if r["hook_on"] == hook_on and r["strength"] is not None
        ]
        return mean(strengths) if strengths else None

    return {
        "n_guesses": len(guessed),
        "raw_hit_rate": _hit_rate(guessed),
        "raw_baseline": 1 / len(STYLES),
        "nondefault_hit_rate": _hit_rate(nondefault_guessed),
        "by_confidence": by_confidence,
        "n_qualifying": len(qualifying),
        "hook_on_mean_strength": mean_strength(True),
        "hook_off_mean_strength": mean_strength(False),
    }


def _load_sessions(log_path: Path) -> dict:
    sessions = defaultdict(dict)
    if not Path(log_path).exists():
        return sessions
    for line in Path(log_path).read_text().splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        session = sessions[record["session_id"]]
        if record["kind"] == "guess":
            session["guess"] = record["style"]
            session["confidence"] = record["confidence"]
        elif record["kind"] == "strength":
            session["strength"] = record["strength"]
            session["faded"] = record["faded"]
    return sessions


def build_records(log_path: Path, projects_dir: Path) -> list[dict]:
    sessions = _load_sessions(log_path)
    records = []
    for session_id, logged in sessions.items():
        truth, hook_on = assignment(session_id)
        records.append({
            "session_id": session_id,
            "truth": truth,
            "hook_on": hook_on,
            "guess": logged.get("guess"),
            "confidence": logged.get("confidence"),
            "strength": logged.get("strength"),
            "faded": logged.get("faded"),
            "turns": count_assistant_turns(session_id, projects_dir),
        })
    return records


def _fmt(rate):
    return "n/a" if rate is None else f"{rate:.2%}" if rate <= 1 else f"{rate:.2f}"


def print_report(stats: dict) -> None:
    print(f"n_guesses: {stats['n_guesses']}")
    print(f"raw_hit_rate: {_fmt(stats['raw_hit_rate'])} (baseline {stats['raw_baseline']:.2%})")
    print(f"nondefault_hit_rate: {_fmt(stats['nondefault_hit_rate'])}")
    for tier in CONFIDENCE_TIERS:
        print(f"  {tier}: {_fmt(stats['by_confidence'][tier])}")
    print(f"n_qualifying (turns >= {QUALIFYING_TURNS}): {stats['n_qualifying']}")
    print(f"hook_on_mean_strength: {_fmt(stats['hook_on_mean_strength'])}")
    print(f"hook_off_mean_strength: {_fmt(stats['hook_off_mean_strength'])}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="score")
    parser.add_argument("--log-path", type=Path, default=DEFAULT_LOG_PATH)
    parser.add_argument("--projects-dir", type=Path, default=DEFAULT_PROJECTS_DIR)
    args = parser.parse_args(argv)

    records = build_records(args.log_path, args.projects_dir)
    print_report(tally(records))


if __name__ == "__main__":
    main()
