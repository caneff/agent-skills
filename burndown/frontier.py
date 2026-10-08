#!/usr/bin/env python3
"""The frontier of a ticket queue: `python3 burndown/frontier.py <owner/repo>
<label>` prints the open, unclaimed, dispatchable tickets split five ways —

    unblocked   <n> <title>
    blocked     <n> <title>  (blocked by #a, #b)
    unresolved  <n> <title>  (<why>)
    spec        <n> <title>  (a spec parent: dispatch with ... --spec <n> ...)
    slice       <n> <title>  (a slice of spec #<p>: hand off with ... --spec <p> ...)

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
_HEADING = re.compile(r"^ {0,3}#{1,6}[ \t]+blocked by[ \t]*:?[ \t]*$",
                      re.IGNORECASE)
_ANY_HEADING = re.compile(r"^ {0,3}#{1,6}[ \t]+\S")
# The inline forms the tree also writes: `Blocked by: #7, #8` at the top of a
# /wayfinder child (docs/agents/issue-tracker.md), and `**Blocked by:** ...`
# in to-tickets' local ticket template. Anchored at the line start and
# allowing no `#` before the words, so a heading is never read as one of
# these and prose that merely says "blocked by #7" mid-sentence is not a
# declaration. All three allow at most three spaces of indent: four or more
# is an indented code block in CommonMark, a quotation and not a declaration.
_INLINE = re.compile(r"^ {0,3}(?![ \t])[*_]{0,2}[ \t]*blocked by[ \t]*:?[ \t]*[*_]{0,2}[ \t]*:?[ \t]*(.*)$",
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
#
# CommonMark recognises a fence marker only at up to three spaces of
# indentation; four spaces or a tab is indented code, not a fence (#999). A
# marker past that bound is quotation like any other indented line, and
# `visible()`'s own `_QUOTED` bound below already knows to drop it — this
# bound has to agree with that one, or a quoted fence with no matching
# closer swallows every real line after it, declaration included.
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*$")
_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})")

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

# A slice is the other half of that verb (#1242). The spec parent need not
# carry the queried label — burn-2026-09-27's carried `spec` alone — so the
# parent never reaches this reader as a candidate, and its slices would read
# as ordinary unblocked tickets and be built one by one. The slice is found
# from its side: its parent, by the sub-issue endpoint or a `Part of #<n>`
# line, carries `spec`. `/to-tickets` writes it under a `## Parent` heading
# as `Part of [Spec: ...](https://github.com/<o>/<r>/issues/<n>).` (#1282), and
# a bare `#<n>` under that heading is the same declaration.
_PART_OF = re.compile(r"^ {0,3}Part of\b(?:\s+#(\d+)\b)?", re.IGNORECASE)
_PARENT_HEADING = re.compile(r"^ {0,3}#{1,6}[ \t]+parent[ \t]*$", re.IGNORECASE)
_LINK = re.compile(r"\[[^\]]*\]\([^)]*\)|https?://\S+")  # text and URL: not a bare #<n>
_ISSUE_LINK = r"https://github\.com/{repo}/issues/(\d+)\b"
# Any repo's issue, as a URL or `owner/repo#<n>`: on a `Part of` line that
# names none in this repo, it is a declaration this reader cannot resolve.
_ANY_ISSUE = re.compile(r"https://github\.com/[^/\s]+/[^/\s]+/issues/\d+|[\w.-]+/[\w.-]+#\d+")


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


AMBIGUOUS = object()  # `blocked_by_section`'s answer to two declarations


# An indented code block or a blockquote line is quotation, whatever it
# says: four or more spaces or a tab of indent, or a `>` within three.
_QUOTED = re.compile(r"^(?: {4}|\t| {0,3}>)")


def visible(lines):
    """`unfenced` minus indented code and blockquote lines: what this ticket
    says in its own voice. One test for declaration detection and for the
    lines a section collects, so a quotation cannot be dropped from the one
    and still feed the other."""
    return [(i, line) for i, line in unfenced(lines) if not _QUOTED.match(line)]


# `- **Directive**: <value>` — a key in optional emphasis, then a colon. The
# colon may sit inside the emphasis (`**Directive:**`): that closing run is
# consumed whatever follows it, since the key's own emphasis is balanced and
# `**Directive:**`#include <path>`` is a valid line. A colon after the
# emphasis (`**Directive**:`) keeps a bold value's markers, `**Directive**:**x**`
# reading as the value `**x**`. One grammar for `closure.py` and
# `implement-spec/closing_ticket.py` (#928, #1000): two copies drifted once.
_KEY = re.compile(
    r"^[ \t]*[-*+][ \t]*(?:"
    r"[*_]{1,2}(?P<inside>[A-Za-z][A-Za-z -]*?)[ \t]*:[*_]{1,2}"
    r"|[*_]{0,2}(?P<outside>[A-Za-z][A-Za-z -]*?)[*_]{0,2}[ \t]*:"
    r")[ \t]*(?P<value>.*?)[ \t]*$")


def key_line(line):
    """`(key, value)` for a `- **Key**: value` line, the key stripped and
    lowercased and the value stripped, or `None` when the line is no key."""
    match = _KEY.match(line)
    if not match:
        return None
    key = match.group("inside") or match.group("outside")
    return key.strip().lower(), match.group("value").strip()


def blocked_by_section(body):
    """What the ticket states about its blockers, or `None` when it states
    nothing at all — a ticket that never mentions the relationship is not a
    ticket that says it has none. `AMBIGUOUS` when it states it more than
    once: which one is the ticket's own cannot be told from the text, and a
    quotation of another ticket's declaration reads the same as the real one.

    Three written forms, the section listed first as the canonical one
    `/to-tickets` emits: the lines under a `## Blocked by` heading up to the
    next heading of any level, or the rest of an inline `Blocked by:` /
    `**Blocked by:**` line in the preamble. Every visible occurrence of
    either form is one declaration."""
    lines = visible((body or "").splitlines())
    answers = []
    for pos, (_, line) in enumerate(lines):
        if not _HEADING.match(line):
            continue
        section = []
        for _, rest in lines[pos + 1:]:
            if _ANY_HEADING.match(rest):
                break
            section.append(rest)
        answers.append("\n".join(section).strip())
    for _, line in lines:
        if _ANY_HEADING.match(line):
            break  # the preamble ends at the first heading
        inline = _INLINE.match(line)
        if inline:
            answers.append(inline.group(1).strip())
    if len(answers) > 1:
        return AMBIGUOUS
    return answers[0] if answers else None


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


def _handoff(number):
    """The one verb a spec run is dispatched by, for a spec parent's own
    entry and for each of its slices'."""
    return f"`implement-dispatch --spec {number} --slots <k>`"


def _is_clear(name, stated):
    """Whether a ticket's own blocking state leaves it free to be handed off
    by a verb: unblocked, or silent. `blocked` outranks the verb, and a
    stated declaration this reader could not resolve is not silence."""
    return name == "unblocked" or (name == "unresolved" and not stated)


# The buckets `classify` fills, in the order `render` prints them.
BUCKETS = ("unblocked", "blocked", "unresolved", "spec", "slice")


def classify(issues, state_of, parent_of, landed_of=None, native_blockers_of=None):
    """`{unblocked, blocked, unresolved, spec, slice}` over GitHub issue
    objects. `state_of(number) -> "open" | "closed" | None` reads a blocker's
    state; `None` means it could not be read, which is unresolved rather than
    a guess. `parent_of(ticket) -> issue | None` reads the ticket's parent
    issue, `None` being a ticket with no parent; it raises `FrontierError`
    for a parent that could not be read, which is unresolved too. A claimed
    ticket, a ticket carrying a non-dispatchable label, and anything that is
    really a PR, is in no bucket at all — each is off the frontier by its own
    nature, not by a blocking relationship.

    `landed_of(number) -> bool` says an open blocker's PR merged into its
    spec's integration branch (#1466): that blocker is met, because the slice
    stays open until the integration PR closes it. `native_blockers_of(ticket)
    -> [number]` lists a ticket's open native blockers so each can be asked
    the same; it raises `FrontierError` when it cannot. Both default to "no
    blocker has landed", so a reader that supplies neither blocks as before."""
    buckets = {name: [] for name in BUCKETS}
    landed_of = landed_of or (lambda number: False)

    def native_still_blocked(issue):
        """Whether a natively blocked ticket still has an open blocker that
        has not landed. A list that cannot be read stays blocked: an unknown
        blocker is not a met one."""
        if native_blockers_of is None:
            return True
        try:
            open_numbers = native_blockers_of(issue)
        except FrontierError:
            return True
        return not open_numbers or not all(landed_of(n) for n in open_numbers)

    def rank(issue, entry):
        """`(bucket, stated)` from this ticket's blocking state alone.
        `stated` is whether the ticket said anything about blockers at all,
        not whether it said it was blocked: silence and an unreadable
        declaration are both `unresolved`, and the spec override below is
        the one caller that has to tell them apart."""
        native = _native(issue)
        if native is not None:
            entry["why"] = "native dependencies"
            if native and not native_still_blocked(issue):
                entry["why"] = "native dependencies, all landed on a spec branch"
                native = False
            return ("blocked" if native else "unblocked"), True
        section = blocked_by_section(issue.get("body"))
        if section is None:
            entry["why"] = "no native dependencies and no `Blocked by` of any form"
            return "unresolved", False
        if section is AMBIGUOUS:
            entry["why"] = ("the ticket's `Blocked by` is declared more than "
                            "once, so which one is its own is ambiguous")
            return "unresolved", True
        references, why = section_blockers(section)
        if references is None:
            entry["why"] = why
            return "unresolved", True
        entry["blockers"] = references
        states = [(n, state_of(n)) for n in references]
        unreadable = [n for n, state in states if state is None]
        if unreadable:
            entry["why"] = ("`Blocked by` names "
                            + ", ".join(f"#{n}" for n in unreadable)
                            + ", whose state could not be read")
            return "unresolved", True
        open_blockers = [n for n, state in states
                         if state == "open" and not landed_of(n)]
        if open_blockers:
            entry["blockers"] = open_blockers
            entry["why"] = "`Blocked by` names an open ticket"
            return "blocked", True
        entry["why"] = "`Blocked by` names only closed or landed tickets"
        return "unblocked", True

    for issue in sorted(issues, key=lambda i: i.get("number") or 0):
        if (issue.get("pull_request") or _is_claimed(issue)
                or _is_non_dispatchable(issue)):
            continue
        entry = {"number": issue.get("number"), "title": issue.get("title"),
                 "blockers": [], "why": ""}
        name, stated = rank(issue, entry)
        if SPEC_LABEL in _labels(issue) and _is_clear(name, stated):
            # The prerequisites are checked *first*, so `blocked` outranks
            # `spec` on one entry: both are true claims, but only `spec`
            # carries a dispatch verb, and a controller copies lines like
            # that — onto a whole nested run over blocked work.
            #
            # An unreadable declaration stays `unresolved` for the same
            # reason. Silence is the case ruled into `spec`; a stated
            # prerequisite this reader could not resolve is not silence,
            # and an unknown prerequisite is not a met one.
            entry["blockers"] = []
            entry["why"] = ("a spec parent: dispatch with "
                            + _handoff(entry["number"]))
            name = "spec"
        elif _is_clear(name, stated):
            # Same ordering as above: a blocked slice stays `blocked`, since
            # only `slice` carries a verb to copy. Silence is ruled in for
            # the reason it is for `spec` — the spec run orders its own
            # slices — and a parent that cannot be read is not "no parent".
            try:
                parent = parent_of(issue)
            except FrontierError as exc:
                # A silent ticket keeps its own reason: that one a human fixes.
                own = f"{entry['why']}; " if name == "unresolved" else ""
                entry["why"] = f"{own}its parent could not be read ({exc})"
                name = "unresolved"
            else:
                if parent and SPEC_LABEL in _labels(parent):
                    entry["blockers"] = []
                    entry["why"] = (
                        f"a slice of spec #{parent['number']}: hand off with "
                        + _handoff(parent["number"])
                        + ", never as its own ticket")
                    name = "slice"
        buckets[name].append(entry)
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


_SPEC_BRANCH = re.compile(r"^spec-\d+$")


def fetch_landed(repo, number, run=gh_json):
    """Whether ticket `number`'s PR merged into a `spec-<p>` integration
    branch (#1466, ruling (a)). The slice's branch is `implement-<n>`, so the
    merged PRs from that head name their base. A lookup that fails is `False`:
    an unknown landing keeps the ticket blocked, never frees it. A clump's
    non-lowest ticket has no branch of its own and reads as not landed."""
    try:
        prs = run(["pr", "list", "--repo", repo, "--head", f"implement-{int(number)}",
                   "--state", "merged", "--json", "baseRefName", "--limit", "20"])
    except (FrontierError, OSError):
        return False
    return any(_SPEC_BRANCH.match(str((pr or {}).get("baseRefName") or ""))
               for pr in prs or [])


def fetch_native_blockers(repo, ticket, run=gh_json):
    """The numbers of `ticket`'s open native blockers. Raises `FrontierError`
    when the list cannot be read."""
    answer = run(["api", f"repos/{quote(repo, safe='/')}/issues/"
                  f"{int(ticket['number'])}/dependencies/blocked_by"])
    if not isinstance(answer, list):
        raise FrontierError("the dependencies endpoint answered with no list")
    return [b["number"] for b in answer if b.get("state") == "open"]


def fetch_parent(repo, ticket, run=gh_json):
    """The parent issue of `ticket`, `None` when it has none. The sub-issue
    endpoint first; a 404 there means no sub-issue link, and the body's
    parent line (`_parent_number`) is the fallback the tree writes where
    sub-issues are not enabled. Any other failure raises `FrontierError`: a
    call that did not answer is not an answer of "no parent"."""
    base = f"repos/{quote(repo, safe='/')}/issues"
    try:
        answer = run(["api", f"{base}/{int(ticket['number'])}/parent"])
        if not isinstance(answer, dict) or "number" not in answer:
            raise FrontierError("the parent endpoint answered with no issue")
        return answer
    except FrontierError as exc:
        # gh's own status marker, not a bare "404": a failed call's message
        # can carry the request URL, and a ticket #1404 would match it.
        if "(HTTP 404)" not in str(exc):
            raise
    parent = _parent_number(ticket.get("body") or "", repo)
    return None if parent is None else run(["api", f"{base}/{parent}"])


def _parent_number(body, repo):
    """The parent issue number a ticket body declares in this repo, or `None`:
    a `Part of #<n>` line, a `Part of [..](<this repo's issue URL>)` line, or
    the first `#<n>` / this repo's issue URL under a `## Parent` heading.

    A `## Parent` section that names no such issue — empty, prose, another
    repo's link — raises `FrontierError`: a declaration this reader cannot
    resolve is not "no parent" (#1406). `None` under it, as `Blocked by`
    says it, is no parent. A `Part of` line outside the heading that names
    another repo's issue and none in this one raises too; a `Part of` line
    naming no issue at all is prose.

    `flow/lane/src/bin/implement_dispatch.rs` `body_names_parent` reads the
    same grammar to ask only whether a parent is declared; a change to one
    is a change to both.
    """
    link = re.compile(_ISSUE_LINK.format(repo=re.escape(repo)), re.IGNORECASE)
    in_parent = False
    unread = None  # the `## Parent` section's text while it names nothing
    foreign = None  # a `Part of` line naming only another repo's issue
    for _, line in visible(body.splitlines()):
        part = _PART_OF.match(line)
        if part and part.group(1):
            return int(part.group(1))
        if _ANY_HEADING.match(line):
            in_parent = bool(_PARENT_HEADING.match(line))
            if in_parent and unread is None:
                unread = ""
            continue
        found = link.search(line)
        if found and (part or in_parent):
            return int(found.group(1))
        if part and not in_parent and foreign is None and _ANY_ISSUE.search(line):
            foreign = line.strip()
        if in_parent:
            ref = _REFERENCE.search(_LINK.sub("", line))
            if ref:
                return int(ref.group(1))
            unread += line.strip() + " "
    if unread is not None and not _NONE.match(unread):
        raise FrontierError(f"`## Parent` names no issue in {repo}"
                            + (f": {unread.strip()[:80]}" if unread.strip() else ""))
    if foreign is not None:
        raise FrontierError(f"`Part of` names no issue in {repo}: {foreign[:80]}")
    return None


def frontier(repo, label, fetch=fetch_issues, state_of=fetch_state,
             parent_of=fetch_parent, run=gh_json, landed_of=fetch_landed,
             native_blockers_of=fetch_native_blockers):
    """`(repo, label) -> {unblocked, blocked, unresolved, spec, slice}`. Each
    blocker's state is read once however many tickets name it, and so is
    each parent issue a `Part of` line names: slices of one spec share it.
    The `/parent` call itself is one per ticket, which no cache shortens."""
    seen, answers = {}, {}

    def cached(number):
        if number not in seen:
            seen[number] = state_of(repo, number)
        return seen[number]

    def read_once(args):  # a failed call raises and is not kept
        if tuple(args) not in answers:
            answers[tuple(args)] = run(args)
        return answers[tuple(args)]

    landings = {}

    def landed(number):
        if number not in landings:
            landings[number] = landed_of(repo, number)
        return landings[number]

    return classify(fetch(repo, label), cached,
                    lambda ticket: parent_of(repo, ticket, run=read_once),
                    landed,
                    lambda ticket: native_blockers_of(repo, ticket))


def render(buckets):
    lines = []
    for name in BUCKETS:
        for entry in buckets[name]:
            note = ""
            if name == "blocked":
                if entry["blockers"]:
                    note = "  (blocked by " + ", ".join(
                        f"#{n}" for n in entry["blockers"]) + ")"
            elif name != "unblocked":
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
