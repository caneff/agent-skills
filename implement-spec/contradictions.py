#!/usr/bin/env python3
"""The exploration pass's contradiction check: which of a spec's decisions
reach Chris.

The check compares the spec's stated decisions against the code. Run without
the spec's **own ticket list**, it flags a decision the code has not caught up
with yet as CONTRADICTED — which on #781's spec run happened twice on #366,
both times describing exactly the gap #367, a slice of that same spec, existed
to close. That is the spec correctly describing a future state, and every spec
with a prefactor slice generates it, into the one channel that reaches Chris.

So a decision the code does not implement, where a ticket of this spec builds
it, is **not yet built**: a line in the exploration summary. Only "the code
does this, **differently**" escalates.

The grammar, the three verdicts and the evidence:
`references/exploration.md`.
"""
import collections
import json
import sys

# One decision's verdict. `escalates` is the only bit the controller acts on;
# `line` is what the exploration summary carries either way.
Result = collections.namedtuple("Result", "id verdict escalates line")

# What the exploration pass found in the code for one decision. Three answers
# and no fourth: a reader that guesses at a spelling it does not know is a
# reader that can call a contradiction "not yet built".
FOUND = ("absent", "differs", "matches")


class SpecError(Exception):
    """The check could not be run on what it was handed. Fatal: a malformed
    decision silently classified is the failure this check exists to stop."""


def check(decisions, tickets):
    """Verdicts for one exploration pass's decisions, in the order given.

    `decisions` are the spec's stated decisions as the exploration pass found
    them — `id`, `decision`, `found` (one of FOUND), `built_by` (the ticket of
    this spec that builds it, or None). `tickets` is this spec's own ticket
    list, which is what separates "not yet built" from a real contradiction.
    """
    numbers = set(_ticket_numbers(tickets))
    return [_verdict(_validated(d, numbers)) for d in decisions]


def _ticket_numbers(tickets):
    for entry in tickets:
        try:
            yield int(str(entry).lstrip("#"))
        except (TypeError, ValueError):
            raise SpecError(f"not a ticket number: {entry!r}")


def _validated(decision, numbers):
    if not isinstance(decision, dict):
        raise SpecError(f"not a decision: {decision!r}")
    for key in ("id", "decision", "found"):
        if not str(decision.get(key) or "").strip():
            raise SpecError(f"decision is missing {key}: {decision!r}")
    if decision["found"] not in FOUND:
        raise SpecError(
            f"{decision['id']}: found is {decision['found']!r}, "
            f"not one of {', '.join(FOUND)}")
    built_by = decision.get("built_by")
    if built_by is not None:
        try:
            built_by = int(str(built_by).lstrip("#"))
        except (TypeError, ValueError):
            raise SpecError(f"{decision['id']}: not a ticket number: {built_by!r}")
        # A defence citing a ticket outside this spec is not a defence: the
        # whole rule is that *this spec* closes the gap before it ships. Fail
        # closed rather than quietly escalate or quietly excuse it.
        if built_by not in numbers:
            raise SpecError(
                f"{decision['id']}: built_by names #{built_by}, "
                "which is not a ticket of this spec")
    return {**decision, "built_by": built_by}


def _verdict(decision):
    name, what = decision["id"], decision["decision"]
    found, built_by = decision["found"], decision["built_by"]
    evidence = str(decision.get("evidence") or "").strip()
    trailer = f" — {evidence}" if evidence else ""
    if found == "differs":
        # The one verdict that reaches Chris. The code does this, and it does
        # it another way than the spec decided.
        return Result(name, "contradicted", True,
                      f"{name} CONTRADICTED: {what}{trailer}")
    if found == "matches":
        return Result(name, "consistent", False,
                      f"{name} consistent: {what}")
    if built_by is not None:
        return Result(name, "not-yet-built", False,
                      f"{name} not yet built, #{built_by} builds it: {what}{trailer}")
    # Absent, and no slice of this spec builds it. Not drift — the code has
    # never heard of this decision — so it stays a summary line (#897) and the
    # controller reads it as a slicing gap, not as a ruling to make.
    return Result(name, "unbuilt", False,
                  f"{name} unbuilt, no ticket of this spec builds it: {what}{trailer}")


def render(results):
    """The exploration summary: every decision one line, escalations last so
    the controller's eye lands on what it must carry to Chris."""
    lines = [r.line for r in results if not r.escalates]
    lines += [r.line for r in results if r.escalates]
    escalating = sum(1 for r in results if r.escalates)
    noun = "contradiction" if escalating == 1 else "contradictions"
    lines.append(f"{len(results)} decisions checked, {escalating} {noun} for Chris")
    return "\n".join(lines)


def main(argv):
    if len(argv) != 2:
        print("usage: contradictions.py <exploration.json>", file=sys.stderr)
        return 2
    try:
        with open(argv[1]) as fh:
            payload = json.load(fh)
        if not isinstance(payload, dict):
            raise SpecError("the exploration file is not a JSON object")
        print(render(check(payload.get("decisions") or [],
                           payload.get("tickets") or [])))
    except (OSError, ValueError, SpecError) as exc:
        print(f"contradictions.py: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
