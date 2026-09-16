#!/usr/bin/env python3
"""Tally the multi-axis-code-review reports under ~/.cache/agent-reviews (#854).

Two jobs, kept separate on purpose:
1. Mechanical (this file): find report files, parse their filenames, fold
   repo/round-kind aliases, join round-1 reports to their verify report, and
   join issues to their merged PR (via `gh`, matching a `Closes #N` keyword
   or, when that's absent — the common case in this dataset — the PR's
   `implement-<n>`/`issue-<n>` branch name). All of this is pure and
   unit-tested in tally_review_axes_test.py except the thin `gh` subprocess
   call itself.
2. Judgement (not here): reading each finding's prose and its disposition in
   the verify report / PR body to classify severity and outcome. That pass
   is done by hand (an agent reading, not a regex) and its results are
   folded into the JSON this script emits, then written up in
   docs/research/2026-09-16-review-axis-tally.md.

Usage:
    python3 tally_review_axes.py > inventory.json                  # live gh lookup
    python3 tally_review_axes.py --issue-to-pr map.json > inv.json # offline replay
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REVIEWS_ROOT = Path.home() / ".cache" / "agent-reviews"
ALL_AXES = ("standards", "spec", "correctness")
AXIS_ALTS = "|".join(ALL_AXES)

REPO_ALIASES = {
    "agent-skills": "skills",
}

# The `gh` repo each folded repo name lives in, for the merged-PR lookup.
GH_REPO_FOR = {
    "skills": "caneff/agent-skills",
    "sudokumaker-custom-constraints": "caneff/sudokumaker-custom-constraints",
    "twitch-rules-scroller": "caneff/twitch-rules-scroller",
}

# review-<axis>-<n>.md — a single round-1 axis report.
_ROUND1_RE = re.compile(rf"^review-({AXIS_ALTS})-(\d+)\.md$")
# review-verify-<n>.md / review-verification-<n>.md — one combined verify
# report covering all three axes (two names for the same round).
_COMBINED_VERIFY_RE = re.compile(r"^review-(?:verify|verification)-(\d+)\.md$")
# review-<axis>(-<axis>)*-<n>-verify.md — an axis-specific or multi-axis
# verify report: one axis (sudokumaker #368, skills #790's correctness
# pass) or two named axes in one file (skills #790's standards+spec pass).
# A single axis is just the zero-repetition case of this same pattern, so
# there is exactly one regex for both shapes.
_AXIS_VERIFY_RE = re.compile(
    rf"^review-((?:{AXIS_ALTS})(?:-(?:{AXIS_ALTS}))*)-(\d+)-verify\.md$"
)

_CLOSES_RE = re.compile(r"\b(?:closes?|fixe[sd]?|resolve[sd]?)\s*:?\s*#(\d+)", re.IGNORECASE)
_BRANCH_ISSUE_RE = re.compile(r"(?:implement|issue)-(\d+)\b")


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

    m = _AXIS_VERIFY_RE.match(filename)
    if m:
        axes = tuple(m.group(1).split("-"))
        return ReportInfo(kind="verify", axes=axes, issue=int(m.group(2)))

    return None


def fold_repo(repo_dir: str) -> str:
    """Fold known aliases (agent-skills is the same repo as skills, checked
    out under two directory names historically) onto one canonical name."""
    return REPO_ALIASES.get(repo_dir, repo_dir)


def find_report_files(root: Path = REVIEWS_ROOT) -> list[tuple[str, str]]:
    """Return (repo_dir, filename) pairs for every review-*.md file one
    level under `root`, skipping any scratch*-prefixed dir (not real
    reports). Raises FileNotFoundError if `root` doesn't exist, rather than
    silently reporting zero files."""
    if not root.is_dir():
        raise FileNotFoundError(f"reviews cache not found: {root}")

    out = []
    for path in sorted(root.rglob("review-*.md")):
        rel_parts = path.relative_to(root).parts
        if any(part.startswith("scratch") for part in rel_parts):
            continue
        if len(rel_parts) != 2:
            # our cache layout is exactly root/<repo>/review-*.md; anything
            # else (a stray file directly in root, or a deeper nesting) is
            # not a real report bucket.
            continue
        repo_dir = rel_parts[0]
        out.append((repo_dir, path.name))
    return out


def build_issue_index(reports: list[tuple[str, str]]) -> dict:
    """Group round-1 and verify reports by (folded repo, issue number).
    Raises ValueError if two reports claim the same round-1 axis for the
    same (repo, issue) — e.g. a same-named file under both `skills` and
    `agent-skills` — instead of silently letting one overwrite the other."""
    index: dict = {}
    round1_sources: dict = {}  # (repo, issue, axis) -> repo_dir, kept out of `index`
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
            axis = info.axes[0]
            source_key = (repo, info.issue, axis)
            existing = entry["round1"].get(axis)
            existing_source = round1_sources.get(source_key)
            if existing is not None and existing_source != repo_dir:
                raise ValueError(
                    f"conflicting round-1 {axis} reports for {repo}#{info.issue}: "
                    f"{existing_source}/{existing!r} vs {repo_dir}/{fname!r}"
                )
            entry["round1"][axis] = fname
            round1_sources[source_key] = repo_dir
        else:
            entry["verify"].append({"file": fname, "axes": list(info.axes)})
    return index


def normalize_issue_to_pr(raw: dict) -> dict[str, dict[int, list[int]]]:
    """`json.loads` always hands back string keys; this is the one place
    that turns them into the int keys the rest of the join uses."""
    return {
        repo: {int(issue): prs for issue, prs in issues.items()}
        for repo, issues in raw.items()
    }


def attach_prs(index: dict, issue_to_pr: dict[str, dict[int, list[int]]]) -> None:
    """Mutate `index` in place, setting entry["pr"] to the matched merged PR
    number for that repo/issue, or None if no merged PR was found.
    `issue_to_pr` must already be int-keyed (see normalize_issue_to_pr)."""
    for (repo, issue), entry in index.items():
        prs = issue_to_pr.get(repo, {}).get(issue)
        entry["pr"] = prs[0] if prs else None


def match_issue_to_prs(prs: list[dict], issues: set[int]) -> dict[int, list[int]]:
    """Match merged PRs to issue numbers by a `Closes #N`-shaped keyword in
    the body or title, falling back to an `implement-<n>`/`issue-<n>`
    branch name when neither has one (the common case in this dataset:
    `gh`'s closingIssuesReferences came back empty for nearly every PR here
    even where the body said "Closes #N")."""
    result: dict[int, list[int]] = {}
    for pr in prs:
        body = pr.get("body") or ""
        title = pr.get("title") or ""
        branch = pr.get("headRefName") or ""
        found = {int(n) for n in _CLOSES_RE.findall(body)}
        found |= {int(n) for n in _CLOSES_RE.findall(title)}
        bm = _BRANCH_ISSUE_RE.search(branch)
        if bm:
            found.add(int(bm.group(1)))
        for n in found & issues:
            result.setdefault(n, []).append(pr["number"])
    return result


def fetch_merged_prs(gh_repo: str) -> list[dict]:
    """Thin `gh` subprocess wrapper — not unit-tested, kept minimal so
    match_issue_to_prs (the actual matching logic) can be."""
    out = subprocess.run(
        [
            "gh", "pr", "list", "--repo", gh_repo, "--state", "merged",
            "--json", "number,body,title,headRefName", "--limit", "300",
        ],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


def build_issue_to_pr_live(index: dict) -> dict[str, dict[int, list[int]]]:
    """Build the {repo: {issue: [pr_numbers]}} map by calling `gh` once per
    repo present in `index`, over just that repo's issue numbers."""
    issues_by_repo: dict[str, set[int]] = {}
    for repo, issue in index:
        issues_by_repo.setdefault(repo, set()).add(issue)

    result: dict[str, dict[int, list[int]]] = {}
    for repo, issues in issues_by_repo.items():
        gh_repo = GH_REPO_FOR.get(repo)
        if gh_repo is None:
            result[repo] = {}
            continue
        prs = fetch_merged_prs(gh_repo)
        result[repo] = match_issue_to_prs(prs, issues)
    return result


def load_issue_to_pr_override(path: Path) -> dict[str, dict[int, list[int]]]:
    """Load a pre-built {repo: {issue: [pr_numbers]}} JSON file (for offline
    replay), raising a clear error instead of a bare traceback on bad JSON."""
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise ValueError(f"malformed JSON in {path}: {e}") from e
    return normalize_issue_to_pr(raw)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--issue-to-pr",
        type=Path,
        default=None,
        help="offline replay: a pre-built {repo: {issue: [pr_numbers]}} JSON file, "
             "instead of calling `gh` live",
    )
    args = parser.parse_args()

    try:
        reports = find_report_files()
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1)

    index = build_issue_index(reports)

    if args.issue_to_pr:
        try:
            issue_to_pr = load_issue_to_pr_override(args.issue_to_pr)
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            raise SystemExit(1)
    else:
        issue_to_pr = build_issue_to_pr_live(index)
    attach_prs(index, issue_to_pr)

    serializable = {f"{repo}#{issue}": entry for (repo, issue), entry in index.items()}
    print(json.dumps(serializable, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
