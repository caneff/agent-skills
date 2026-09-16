#!/usr/bin/env python3
"""Tally the multi-axis-code-review reports under ~/.cache/agent-reviews (#854).

Two jobs, kept separate on purpose:
1. Mechanical (this file): find report files, parse their filenames, fold
   repo/round-kind aliases, and join round-1 reports to their verify report
   and merged PR by issue number. All of this is pure and unit-tested in
   tally_review_axes_test.py.
2. Judgement (not here): reading each finding's prose and its disposition in
   the verify report / PR body to classify severity and outcome. That pass
   is done by hand (an agent reading, not a regex) and its results are
   folded into the JSON this script's `--inventory` mode emits, then written
   up in docs/research/2026-09-16-review-axis-tally.md.

Usage:
    python3 tally_review_axes.py --inventory > inventory.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

REVIEWS_ROOT = Path.home() / ".cache" / "agent-reviews"
ALL_AXES = ("standards", "spec", "correctness")
AXIS_ALTS = "|".join(ALL_AXES)

REPO_ALIASES = {
    "agent-skills": "skills",
}

# review-<axis>-<n>.md — a single round-1 axis report.
_ROUND1_RE = re.compile(rf"^review-({AXIS_ALTS})-(\d+)\.md$")
# review-verify-<n>.md / review-verification-<n>.md — one combined verify
# report covering all three axes (two names for the same round).
_COMBINED_VERIFY_RE = re.compile(r"^review-(?:verify|verification)-(\d+)\.md$")
# review-<axis>-<n>-verify.md — an axis-specific verify report (seen for
# sudokumaker #368 and skills #790's correctness pass).
_AXIS_VERIFY_RE = re.compile(rf"^review-({AXIS_ALTS})-(\d+)-verify\.md$")
# review-standards-spec-<n>-verify.md — the #790 anomaly: one verify report
# covering exactly two named axes.
_MULTI_AXIS_VERIFY_RE = re.compile(
    rf"^review-((?:{AXIS_ALTS})(?:-(?:{AXIS_ALTS}))*)-(\d+)-verify\.md$"
)


@dataclass(frozen=True)
class ReportInfo:
    kind: str  # "round1" | "verify"
    axes: tuple[str, ...]
    issue: int


def parse_report_filename(filename: str) -> ReportInfo | None:
    """Parse one review-*.md basename. Returns None for anything that isn't
    a round-1 or verify report in a shape we recognize (diffs, logs, the
    non-`review-`-prefixed stray files, etc.)."""
    m = _ROUND1_RE.match(filename)
    if m:
        return ReportInfo(kind="round1", axes=(m.group(1),), issue=int(m.group(2)))

    m = _COMBINED_VERIFY_RE.match(filename)
    if m:
        return ReportInfo(kind="verify", axes=ALL_AXES, issue=int(m.group(1)))

    m = _MULTI_AXIS_VERIFY_RE.match(filename)
    if m:
        axes = tuple(m.group(1).split("-"))
        return ReportInfo(kind="verify", axes=axes, issue=int(m.group(2)))

    m = _AXIS_VERIFY_RE.match(filename)
    if m:
        return ReportInfo(kind="verify", axes=(m.group(1),), issue=int(m.group(2)))

    return None


def fold_repo(repo_dir: str) -> str:
    """Fold known aliases (agent-skills is the same repo as skills, checked
    out under two directory names historically) onto one canonical name."""
    return REPO_ALIASES.get(repo_dir, repo_dir)


def find_report_files(root: Path = REVIEWS_ROOT) -> list[tuple[str, str]]:
    """Walk the reviews cache and return (repo_dir, filename) pairs for every
    review-*.md file, skipping any scratch* path (not real reports)."""
    out = []
    for dirpath, _dirnames, filenames in os.walk(root):
        if "scratch" in Path(dirpath).relative_to(root).parts:
            continue
        repo_dir = Path(dirpath).name
        for fname in filenames:
            if fname.startswith("review-") and fname.endswith(".md"):
                out.append((repo_dir, fname))
    return out


def build_issue_index(reports: list[tuple[str, str]]) -> dict:
    """Group round-1 and verify reports by (folded repo, issue number)."""
    index: dict = {}
    for repo_dir, fname in reports:
        info = parse_report_filename(fname)
        if info is None:
            continue
        repo = fold_repo(repo_dir)
        key = (repo, info.issue)
        entry = index.setdefault(
            key, {"round1": {}, "verify": [], "pr": None, "repo_dir": repo_dir}
        )
        if info.kind == "round1":
            entry["round1"][info.axes[0]] = fname
        else:
            entry["verify"].append({"file": fname, "axes": list(info.axes)})
    return index


def attach_prs(index: dict, issue_to_pr: dict[str, dict]) -> None:
    """Mutate `index` in place, setting entry["pr"] to the matched merged PR
    number for that repo/issue, or None if no merged PR was found."""
    for (repo, issue), entry in index.items():
        prs = issue_to_pr.get(repo, {}).get(issue) or issue_to_pr.get(repo, {}).get(
            str(issue)
        )
        entry["pr"] = prs[0] if prs else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--issue-to-pr",
        type=Path,
        default=None,
        help="path to a JSON file of {repo: {issue: [pr_numbers]}} (see docs/research/2026-09-16-review-axis-tally.md for how it was built)",
    )
    parser.add_argument("--inventory", action="store_true", help="print the joined index as JSON")
    args = parser.parse_args()

    reports = find_report_files()
    index = build_issue_index(reports)
    if args.issue_to_pr:
        raw = json.loads(args.issue_to_pr.read_text())
        issue_to_pr = {repo: v.get("issue_to_pr", v) for repo, v in raw.items()}
        attach_prs(index, issue_to_pr)

    if args.inventory:
        serializable = {f"{repo}#{issue}": entry for (repo, issue), entry in index.items()}
        print(json.dumps(serializable, indent=2, sort_keys=True))
    else:
        print(f"{len(reports)} report files, {len(index)} distinct (repo, issue) pairs")


if __name__ == "__main__":
    main()
