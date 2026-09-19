#!/usr/bin/env python3
"""The frontier of a ticket queue: `python3 burndown/frontier.py <owner/repo>
<label>` prints the open, unclaimed tickets split three ways —

    unblocked   <n> <title>
    blocked     <n> <title>  (blocked by #a, #b)
    unresolved  <n> <title>  (<why>)

Three sources, in order: the tracker's native dependencies where it has them
(`issue_dependencies_summary.blocked_by`, open blockers only, the live gate),
then the `## Blocked by` section grammar in the ticket body, then nothing —
and nothing is **unresolved**, never unblocked. Reads only.

Silence is the whole point. On #781 eight of twenty-one `ready-for-agent`
tickets carried no `## Blocked by` section at all, and reading a missing
section as "unblocked" dispatches a worker onto a ticket whose prerequisite
is still open — the cost is a whole build. The grammar this parses, and what
each answer means, are specified in `references/frontier.md`.
"""
import json
import re
import subprocess
import sys

# An ATX heading whose text is exactly "Blocked by", any level, any case —
# `##` is what `/to-tickets` emits and what the grammar specifies.
_HEADING = re.compile(r"^[ \t]*#{1,6}[ \t]+blocked by[ \t]*:?[ \t]*$",
                      re.IGNORECASE)
_ANY_HEADING = re.compile(r"^[ \t]*#{1,6}[ \t]+\S")
# A bare `#NNN`. The lookbehind keeps `owner/repo#7` and `abc#7` out: a
# cross-repo reference is outside the grammar, and reading its tail as a
# local number would gate a ticket on an unrelated issue.
_REFERENCE = re.compile(r"(?<![0-9A-Za-z_/#-])#(\d+)")
# "None", however it is dressed: `None`, `- None`, `None — can start
# immediately.` The stated way to say a ticket has no blockers.
_NONE = re.compile(r"^[-*\s]*none\b", re.IGNORECASE)

CLAIMED_LABEL = "in-progress"


def blocked_by_section(body):
    """The lines under the `## Blocked by` heading, up to the next heading of
    any level, or `None` when the body has no such heading at all. A ticket
    that never states the relationship is not a ticket that states it has no
    blockers."""
    lines = (body or "").splitlines()
    for i, line in enumerate(lines):
        if not _HEADING.match(line):
            continue
        section = []
        for rest in lines[i + 1:]:
            if _ANY_HEADING.match(rest):
                break
            section.append(rest)
        return "\n".join(section).strip()
    return None


def section_blockers(section):
    """`(references, why)` for one section's text: the `#NNN` numbers it
    names, or `None` references plus the reason when the section says
    nothing this grammar can read."""
    if not section:
        return None, "`## Blocked by` section is empty"
    references = [int(n) for n in _REFERENCE.findall(section)]
    if references:
        # dedup, keep the order they were written in
        return list(dict.fromkeys(references)), None
    if _NONE.match(section):
        return [], None
    return None, "`## Blocked by` section names no `#NNN` and does not say None"


def _is_claimed(issue):
    labels = {label.get("name") for label in issue.get("labels") or []}
    return bool(issue.get("assignees")) or CLAIMED_LABEL in labels


def _native(issue):
    """`True`/`False` for blocked, or `None` when the tracker holds no
    dependency edges for this ticket. `total_blocked_by` counts every
    blocker and `blocked_by` the open ones, so a zero total is silence."""
    summary = issue.get("issue_dependencies_summary")
    if not isinstance(summary, dict):
        return None
    if not (summary.get("total_blocked_by") or 0):
        return None
    return bool(summary.get("blocked_by") or 0)


def classify(issues, state_of):
    """`{unblocked, blocked, unresolved}` over GitHub issue objects.
    `state_of(number) -> "open" | "closed" | None` reads a blocker's state;
    `None` means it could not be read, which is unresolved rather than a
    guess. A claimed ticket, and anything that is really a PR, is in no
    bucket at all — it is off the frontier."""
    buckets = {"unblocked": [], "blocked": [], "unresolved": []}
    for issue in sorted(issues, key=lambda i: i.get("number") or 0):
        if issue.get("pull_request") or _is_claimed(issue):
            continue
        entry = {"number": issue.get("number"), "title": issue.get("title"),
                 "blockers": [], "why": ""}
        native = _native(issue)
        if native is not None:
            entry["why"] = "native dependencies"
            buckets["blocked" if native else "unblocked"].append(entry)
            continue
        section = blocked_by_section(issue.get("body"))
        if section is None:
            entry["why"] = "no native dependencies and no `## Blocked by` section"
            buckets["unresolved"].append(entry)
            continue
        references, why = section_blockers(section)
        if references is None:
            entry["why"] = why
            buckets["unresolved"].append(entry)
            continue
        entry["blockers"] = references
        states = [(n, state_of(n)) for n in references]
        unreadable = [n for n, state in states if state is None]
        if unreadable:
            entry["why"] = ("`## Blocked by` names "
                            + ", ".join(f"#{n}" for n in unreadable)
                            + ", whose state could not be read")
            buckets["unresolved"].append(entry)
            continue
        open_blockers = [n for n, state in states if state == "open"]
        if open_blockers:
            entry["blockers"] = open_blockers
            entry["why"] = "`## Blocked by` names an open ticket"
            buckets["blocked"].append(entry)
        else:
            entry["why"] = "`## Blocked by` names only closed tickets"
            buckets["unblocked"].append(entry)
    return buckets


def _gh_json(*args):
    out = subprocess.run(["gh", *args], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip() or f"gh {' '.join(args)} failed")
    return json.loads(out.stdout or "null")


def fetch_issues(repo, label):
    """Every open issue with `label`, from the REST endpoint — the GraphQL
    one `gh issue list` uses does not carry `issue_dependencies_summary`."""
    return _gh_json("api", "--paginate",
                    f"repos/{repo}/issues?state=open&per_page=100&labels={label}")


def fetch_state(repo, number):
    """`"open"` / `"closed"` for one issue, or `None` when it cannot be read
    — a number that names nothing in this repo is not a closed blocker."""
    try:
        return (_gh_json("api", f"repos/{repo}/issues/{number}") or {}).get("state")
    except (RuntimeError, ValueError):
        return None


def frontier(repo, label, fetch=fetch_issues, state_of=fetch_state):
    """`(repo, label) -> {unblocked, blocked, unresolved}`. Each blocker's
    state is read once however many tickets name it."""
    seen = {}

    def cached(number):
        if number not in seen:
            seen[number] = state_of(repo, number)
        return seen[number]

    return classify(fetch(repo, label), cached)


def render(buckets):
    lines = []
    for name in ("unblocked", "blocked", "unresolved"):
        for entry in buckets[name]:
            note = ""
            if name == "blocked" and entry["blockers"]:
                note = "  (blocked by " + ", ".join(
                    f"#{n}" for n in entry["blockers"]) + ")"
            elif name == "unresolved":
                note = f"  ({entry['why']})"
            lines.append(f"{name:<11} {entry['number']} {entry['title']}{note}")
    return "\n".join(lines)


def main(argv):
    if len(argv) != 3:
        print("usage: frontier.py <owner/repo> <label>", file=sys.stderr)
        return 2
    print(render(frontier(argv[1], argv[2])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
