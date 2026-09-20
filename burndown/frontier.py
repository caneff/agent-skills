#!/usr/bin/env python3
"""The frontier of a ticket queue: `python3 burndown/frontier.py <owner/repo>
<label>` prints the open, unclaimed, dispatchable tickets split three ways —

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
from urllib.parse import quote

# An ATX heading whose text is exactly "Blocked by", any level, any case —
# `##` is what `/to-tickets` emits and what the grammar specifies.
_HEADING = re.compile(r"^[ \t]*#{1,6}[ \t]+blocked by[ \t]*:?[ \t]*$",
                      re.IGNORECASE)
_ANY_HEADING = re.compile(r"^[ \t]*#{1,6}[ \t]+\S")
# The inline forms the tree also writes: `Blocked by: #7, #8` at the top of a
# /wayfinder child (docs/agents/issue-tracker.md), and `**Blocked by:** ...`
# in to-tickets' local ticket template. Anchored at the line start and
# allowing no `#` before the words, so a heading is never read as one of
# these and prose that merely says "blocked by #7" mid-sentence is not a
# declaration.
_INLINE = re.compile(r"^[ \t]*[*_]{0,2}[ \t]*blocked by[ \t]*:?[ \t]*[*_]{0,2}[ \t]*:?[ \t]*(.*)$",
                     re.IGNORECASE)
# A bare `#NNN`. The lookbehind keeps `owner/repo#7` and `abc#7` out: a
# cross-repo reference is outside the grammar, and reading its tail as a
# local number would gate a ticket on an unrelated issue.
_REFERENCE = re.compile(r"(?<![0-9A-Za-z_/#-])#(\d+)")
# "None", however it is dressed: `None`, `- None`, `None — can start
# immediately.` The stated way to say a ticket has no blockers.
_NONE = re.compile(r"^[-*\s]*none\b", re.IGNORECASE)

# A fenced region — ``` or ~~~ — is quoted material, never a declaration.
# `to-tickets/SKILL.md` ships a fenced issue template containing a
# `## Blocked by` heading, and a ticket quoting the grammar carries one too;
# reading either as this ticket's own answer dispatches a worker on an
# example. The whole run is captured, not three characters, because
# CommonMark closes a fence only on the same character with a run at least
# as long: a ```` fence is exactly what quotes content that itself contains
# ```, and reading that inner line as the closer hands the rest of the
# quotation back to the reader as live document.
_FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,})[ \t]*$")
_FENCE_OPEN = re.compile(r"^[ \t]*(`{3,}|~{3,})")

CLAIMED_LABEL = "in-progress"

# Labels that put a ticket off the frontier by its own nature rather than by
# a blocking relationship. `implement-dispatch` refuses each of them on the
# label alone (`flow/lane/src/bin/implement_dispatch.rs`), so a ticket
# carrying one is not work this reader may offer, however its blockers read.
# `needs-info` waits on grilling; reporting it as `unresolved` says "a human
# must determine this ticket's blocking state", which is the wrong question
# about it and costs a controller a decision it cannot act on.
# `in-progress` is refused too, and is handled as a claim instead: an
# assignee says the same thing without a label.
NON_DISPATCHABLE_LABELS = frozenset({"needs-info"})

# A spec parent is neither of those things. `implement-dispatch` refuses it
# in plain mode while naming the route that does take it — a nested run,
# `--spec <n> --slots <k>` (#897) — so it is dispatchable work in a
# different mode. Dropping it hides real work from the only reader that
# surfaces it, and calling it `unresolved` says a human must determine its
# blocking state when what it needs is a different verb. Both would be a
# lie about what the entry is, so it gets its own bucket (#910).
SPEC_LABEL = "spec"


class FrontierError(Exception):
    """The tracker could not be read. One stderr line, never a traceback:
    this reader's whole point is that an answer it cannot get has a name."""



def unfenced(lines):
    """Every line outside a fenced code block, as `(index, line)`."""
    fence = None
    for i, line in enumerate(lines):
        if fence is None:
            opener = _FENCE_OPEN.match(line)
            if opener:
                fence = opener.group(1)  # an opener may carry an info string
                continue
            yield i, line
            continue
        closer = _FENCE.match(line)  # a closer may not, per CommonMark
        if closer:
            run = closer.group(1)
            if run[0] == fence[0] and len(run) >= len(fence):
                fence = None


def blocked_by_section(body):
    """What the ticket states about its blockers, or `None` when it states
    nothing at all — a ticket that never mentions the relationship is not a
    ticket that says it has none.

    Three written forms, the section first because it is the one
    `/to-tickets` emits: the lines under a `## Blocked by` heading up to the
    next heading of any level, or the rest of an inline `Blocked by:` /
    `**Blocked by:**` line."""
    visible = list(unfenced((body or "").splitlines()))
    for pos, (_, line) in enumerate(visible):
        if not _HEADING.match(line):
            continue
        section = []
        for _, rest in visible[pos + 1:]:
            if _ANY_HEADING.match(rest):
                break
            section.append(rest)
        return "\n".join(section).strip()
    for _, line in visible:
        if _ANY_HEADING.match(line):
            break  # the preamble ends at the first heading
        inline = _INLINE.match(line)
        if inline:
            return inline.group(1).strip()
    return None


def section_blockers(section):
    """`(references, why)` for one section's text: the `#NNN` numbers it
    names, or `None` references plus the reason when the section says
    nothing this grammar can read."""
    if not section:
        return None, "the ticket's `Blocked by` states nothing"
    references = [int(n) for n in _REFERENCE.findall(section)]
    if references:
        # dedup, keep the order they were written in
        return list(dict.fromkeys(references)), None
    if _NONE.match(section):
        return [], None
    return None, "`Blocked by` names no `#NNN` and does not say None"


def _labels(issue):
    return {label.get("name") for label in issue.get("labels") or []}


def _is_claimed(issue):
    return bool(issue.get("assignees")) or CLAIMED_LABEL in _labels(issue)


def _is_non_dispatchable(issue):
    """A ticket no run may dispatch whatever its blockers say, because a
    label puts it out of reach. Read before any bucket is decided: the
    question a bucket answers does not apply to it."""
    return bool(_labels(issue) & NON_DISPATCHABLE_LABELS)


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
    guess. A claimed ticket, a ticket carrying a non-dispatchable label,
    and anything that is really a PR, is in no bucket at all — each is off
    the frontier by its own nature, not by a blocking relationship."""
    buckets = {"unblocked": [], "blocked": [], "unresolved": [], "spec": []}
    for issue in sorted(issues, key=lambda i: i.get("number") or 0):
        if (issue.get("pull_request") or _is_claimed(issue)
                or _is_non_dispatchable(issue)):
            continue
        entry = {"number": issue.get("number"), "title": issue.get("title"),
                 "blockers": [], "why": ""}
        if SPEC_LABEL in _labels(issue):
            # Before the sources, because none of them asks the question a
            # spec parent answers: it is dispatched by verb, not by state.
            entry["why"] = ("a spec parent: dispatch with `implement-dispatch"
                            f" --spec {entry['number']} --slots <k>`")
            buckets["spec"].append(entry)
            continue
        native = _native(issue)
        if native is not None:
            entry["why"] = "native dependencies"
            buckets["blocked" if native else "unblocked"].append(entry)
            continue
        section = blocked_by_section(issue.get("body"))
        if section is None:
            entry["why"] = "no native dependencies and no `Blocked by` of any form"
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
            entry["why"] = ("`Blocked by` names "
                            + ", ".join(f"#{n}" for n in unreadable)
                            + ", whose state could not be read")
            buckets["unresolved"].append(entry)
            continue
        open_blockers = [n for n, state in states if state == "open"]
        if open_blockers:
            entry["blockers"] = open_blockers
            entry["why"] = "`Blocked by` names an open ticket"
            buckets["blocked"].append(entry)
        else:
            entry["why"] = "`Blocked by` names only closed tickets"
            buckets["unblocked"].append(entry)
    return buckets


def gh_json(args):
    """`gh <args>` parsed as JSON. Raises `FrontierError` on anything that
    stops it answering — the caller decides whether that is fatal."""
    try:
        out = subprocess.run(["gh", *args], capture_output=True, text=True)
    except OSError as exc:  # gh not installed, not executable, ...
        raise FrontierError(f"gh: {exc}") from exc
    if out.returncode != 0:
        raise FrontierError(out.stderr.strip() or f"gh {' '.join(args)} failed")
    try:
        return json.loads(out.stdout or "null")
    except ValueError as exc:
        raise FrontierError(f"gh {' '.join(args)}: unreadable JSON") from exc


def fetch_issues(repo, label, run=gh_json):
    """Every open issue with `label`, from the REST endpoint — the GraphQL
    one `gh issue list` uses does not carry `issue_dependencies_summary`.

    The label and repo are percent-encoded into the path: a `#` in a raw URL
    is a fragment marker `gh` drops, which answers a broader queue with exit
    0 — the wrong queue reported as a good one — and a space hangs the
    request. An empty answer is an empty queue, not `None`.

    `--slurp` wraps the pages in an outer array, which this flattens. Without
    it `gh` merges array pages itself (measured on 2.95.0), but that is
    behaviour its own help does not promise — and a queue past one page is
    exactly where a burn needs the reader to work."""
    path = (f"repos/{quote(repo, safe='/')}/issues"
            f"?state=open&per_page=100&labels={quote(label, safe='')}")
    pages = run(["api", "--paginate", "--slurp", path]) or []
    issues = []
    for page in pages:
        if not isinstance(page, list):
            raise FrontierError("gh answered with something other than pages of issues")
        issues.extend(page)
    return issues


def fetch_state(repo, number, run=gh_json):
    """`"open"` / `"closed"` for one issue, or `None` when it cannot be read
    — a number that names nothing in this repo is not a closed blocker, and
    neither is one whose lookup failed."""
    try:
        answer = run(["api", f"repos/{quote(repo, safe='/')}/issues/{int(number)}"])
    except (FrontierError, OSError):
        return None
    return (answer or {}).get("state")


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
    for name in ("unblocked", "blocked", "unresolved", "spec"):
        for entry in buckets[name]:
            note = ""
            if name == "blocked" and entry["blockers"]:
                note = "  (blocked by " + ", ".join(
                    f"#{n}" for n in entry["blockers"]) + ")"
            elif name in ("unresolved", "spec"):
                note = f"  ({entry['why']})"
            lines.append(f"{name:<11} {entry['number']} {entry['title']}{note}")
    return "\n".join(lines)


def main(argv):
    if len(argv) != 3:
        print("usage: frontier.py <owner/repo> <label>", file=sys.stderr)
        return 2
    try:
        buckets = frontier(argv[1], argv[2])
    except FrontierError as exc:
        print(f"frontier.py: {exc}", file=sys.stderr)
        return 1
    print(render(buckets))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
