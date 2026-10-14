#!/usr/bin/env python3
"""Render one review axis's brief (#1216).

    render-brief.py --axis standards|spec|correctness --repo <name> --worktree <path>
                    --ticket <n> --base <fixed point> --diff <capture> --diff-command <cmd>
                    (--commit "<sha subject>")... [--spec <path or pointer> | --no-spec]
                    [--ruling <text>]... [--choice <text>]... [--claim "<id>: <text>"]...
                    [--round <K> [--first-id <series><ordinal>]...]
                    [--workers <k>] [--ceiling <seconds>] [--test-command <cmd>] [--capture-stat <line>]

Writes the whole prompt for a `diff-reviewer` of that axis to
`~/.cache/agent-reviews/<repo>/brief-<ticket>-<axis>[-<n>].md` (#1548) and prints
one line naming that path: the dispatch prompt, sent to `Agent` unedited. The
file is created exclusively, so a second wave of the same ticket and axis takes
`-2`, `-3`, never another wave's file. `<repo>` goes through the ledger's
`fold_repo` (#1527), the one key every cache file uses. About sixty hand-
composed briefs drifted from one skeleton; this is the skeleton, so the parts
that drifted have one home each:

- the axis brief is `briefs/<axis>.md`, read here, never retyped;
- the standards sources are listed from the worktree, not asserted (#1329), and
  `docs/agents/defect-classes.md` is named only when it exists there, the three
  shapes printed inline when it does not;
- a ruling goes under "Settled decisions"; a worker's own choice goes under its
  own heading, flagged, never as settled; a claim (a disposition the worker
  states, a check the worker ran) goes under "Claims to check" and only there,
  and that heading is absent when there are no claims. The renderer writes no
  outcome of its own, since a verdict written into a brief is the verdict that
  comes back (#1400);
- one report filename per axis and ticket, `review-<axis>-<n>.md`, and the
  sidecar and marker names beside it. `--round K` (K >= 2, #1549) gives all three
  and the brief file the `-rK` suffix `review_ledger.py` reads, adds `--round K`
  to the ledger line, and gives the reviewer the id each series starts from
  (SKILL.md § Running a second round). An earlier round whose sidecar or
  marker is missing, or holds a line with no id, is refused, never read as
  "start at 1"; `--first-id S12 --first-id OE3` states every series then;
- the worker count and wall-clock ceiling any test run is held to, and that a
  reviewer spawns no nested subagent (#1400).

Exit 0 and the dispatch line on stdout; 2 on a bad input, with nothing written
and nothing on stdout: a missing or empty diff capture, a worktree that is not
a directory, an unknown axis, a claim with no finding id, a round below 1, a
round K >= 2 whose earlier round is missing or unreadable and not covered by
`--first-id`.
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import review_ledger  # noqa: E402  (fold_repo and REVIEWS_ROOT: the one cache key)

AXES = ("standards", "spec", "correctness")
STANDARDS_FILES = ("CODING_STANDARDS.md", "CONTRIBUTING.md", "AGENTS.md", "GLOSSARY.md")
DEFECT_CLASSES = "docs/agents/defect-classes.md"
SIDECAR = {
    "standards": '{"id": "S<n>" or "OE<n>", "axis": "standards", "severity": "hard" or "judgement", "file": "<path>", "title": "<short title>"}',
    "spec": '{"id": "P<n>", "axis": "spec", "severity": "hard" or "judgement", "file": "<path>", "title": "<short title>"}',
    "correctness": '{"id": "C<n>", "axis": "correctness", "severity": "hard" or "judgement", "rating": "CONFIRMED" or "PLAUSIBLE", "file": "<path>", "title": "<short title>"}',
}


ID_RE = re.compile(r"^(?:r\d+-)?([A-Z]+)(\d+)$")
SERIES = {"standards": ("S", "OE"), "spec": ("P",), "correctness": ("C",)}


class BadInput(Exception):
    pass


def read_diff(path):
    try:
        with open(path, "rb") as fh:
            lines = fh.read().count(b"\n")
    except OSError as exc:
        raise BadInput(f"diff capture {path} cannot be read: {exc}")
    if lines == 0:
        raise BadInput(f"diff capture {path} is empty")
    return lines


def check_claims(claims):
    for claim in claims:
        head, sep, body = claim.partition(":")
        if not sep or not head.strip() or " " in head.strip() or not body.strip():
            raise BadInput(f"claim '{claim}' is not '<finding id>: <text>'")


def sidecar_name(axis, ticket, rnd, ext="jsonl"):
    return f"findings-{axis}-{ticket}" + (f"-r{rnd}" if rnd > 1 else "") + f".{ext}"


def next_ids(directory, axis, ticket, rnd, first_id):
    """{series: first ordinal} for round `rnd`: one past the highest id any earlier round's
    sidecar holds. `first_id` ({series: ordinal}) states a series outright; a series it
    leaves out is refused when an earlier round cannot be read."""
    top, unread = {}, []
    for earlier in range(1, rnd):
        path = directory / sidecar_name(axis, ticket, earlier)
        marker = directory / sidecar_name(axis, ticket, earlier, "done")
        try:
            text = path.read_text()
        except OSError:
            unread.append(f"{path.name} cannot be read")
            continue
        if not marker.exists():
            unread.append(f"{marker.name} is missing, so {path.name} may be truncated")
        for line in filter(str.strip, text.splitlines()):
            m = re.search(r'"id":\s*"([^"]+)"', line)
            idm = ID_RE.match(m.group(1)) if m else None
            if not idm:
                unread.append(f"{path.name} holds a line with no readable id")
                break
            top[idm.group(1)] = max(top.get(idm.group(1), 0), int(idm.group(2)))
    stated = {s: k for s, k in first_id.items() if s in SERIES[axis]}
    open_series = [s for s in SERIES[axis] if s not in first_id]
    if unread and open_series:
        raise BadInput(f"round {rnd} continues earlier rounds' ids in {directory}, and {'; '.join(unread)}; "
                       f"pass --first-id for {', '.join(open_series)} (e.g. "
                       f"{' '.join(f'--first-id {s}<n>' for s in open_series)})")
    return {s: stated.get(s, top.get(s, 0) + 1) for s in SERIES[axis]}


def bullets(items, empty):
    return "\n".join(f"- {i}" for i in items) if items else empty


def render(a):
    if not os.path.isdir(a.worktree):
        raise BadInput(f"worktree {a.worktree} is not a directory")
    if a.round < 1:
        raise BadInput(f"round {a.round}: a round is at least 1")
    first_id = {}
    for spec in a.first_id:
        m = re.fullmatch(r"([A-Z]+)([1-9]\d*)", spec)
        if not m or m.group(1) not in SERIES[a.axis] or a.round == 1:
            raise BadInput(f"--first-id {spec!r} is not <series><ordinal> of the {a.axis} axis "
                           f"({', '.join(SERIES[a.axis])}) in a round of 2 or more")
        first_id[m.group(1)] = int(m.group(2))
    check_claims(a.claim)
    claims = a.claim
    if a.spec and a.no_spec:
        raise BadInput("both --spec and --no-spec were given")
    if a.axis != "standards" and not (a.spec or a.no_spec):
        raise BadInput(f"the {a.axis} axis needs --spec <path or pointer> or --no-spec")
    lines = read_diff(a.diff)
    with open(os.path.join(HERE, "briefs", f"{a.axis}.md")) as fh:
        brief = fh.read().strip()
    present = [f for f in STANDARDS_FILES + (DEFECT_CLASSES,) if os.path.exists(os.path.join(a.worktree, f))]
    if DEFECT_CLASSES in present:
        classes = (f"`{DEFECT_CLASSES}` exists in this worktree: read it by name — the three shapes this "
                   "repo keeps shipping, with every instance.")
    else:
        with open(os.path.join(HERE, "briefs", "defect-shapes.md")) as fh:
            shapes = fh.read().split("\n")
        classes = (f"`{DEFECT_CLASSES}` does not exist in this worktree. Check these three shapes:\n"
                   + "\n".join(f"{n}. {s}" for n, s in enumerate(filter(None, shapes), 1)))
    spec = "no spec available" if a.no_spec else a.spec
    out_dir = f"~/.cache/agent-reviews/{a.repo}"  # a.repo is folded in main
    n, axis, rnd = a.ticket, a.axis, a.round
    suffix = f"-r{rnd}" if rnd > 1 else ""
    ids = next_ids(review_ledger.REVIEWS_ROOT / a.repo, axis, n, rnd, first_id) if rnd > 1 else None
    inputs = [
        f"- Worktree: {a.worktree}",
        f"- Fixed point: {a.base}",
        f"- Diff capture: {a.diff} ({lines} lines) — read it to the end.",
        f"- Produced by: `{a.diff_command}` — the fallback when the capture is missing or empty; say so if you use it.",
        *([f"- Capture stat: {a.capture_stat}"] if a.capture_stat else []),
        "- Commits: " + ("; ".join(a.commit) if a.commit else "none given"),
    ]
    if axis != "standards":
        inputs.append(f"- Spec: {spec}" if spec else "- Spec: not given")
    if axis == "correctness" and a.test_command:
        inputs.append(f"- Test command: `{a.test_command}`")
    parts = [
        f"# {axis.capitalize()} review of #{n} in {a.repo}" + (f" (round {rnd})" if rnd > 1 else ""),
        f"You review this one axis only: {axis}. Another reviewer holds each other axis.",
        "## Inputs",
        "\n".join(inputs),
    ]
    parts += [
        "## Standards sources (listed from the worktree)",
        bullets(present, "- none of " + ", ".join(STANDARDS_FILES) + " exists here"),
        "## Defect classes",
        classes,
        "## Settled decisions (ruled by Chris or the controller)",
        "Never re-raise one; a diff that contradicts one is a finding.",
        bullets(a.ruling, "Settled decisions: none."),
    ]
    if a.choice:
        parts += ["## Worker's own choices — flag if you disagree (not settled)",
                  "The worker made these itself; nobody ruled on them. Flag any you disagree with and judge them like any other code.",
                  bullets(a.choice, "")]
    if claims:
        parts += ["## Claims to check (the worker's account, not a result)",
                  "Verify each against the code and re-run any check yourself; the verdict is yours, "
                  "and nothing here is settled.",
                  bullets(claims, "")]
    id_lines = []
    if ids:
        first = ", ".join(f"{s}{k}" for s, k in ids.items())
        id_lines = [f"- This is round {rnd}. Finding ids continue the earlier rounds' on this "
                    f"ticket: number yours from {first} (each series from its own number), "
                    "never restart at 1."]
    parts += [
        "## Brief",
        brief,
        "## Output",
        "\n".join([
            f"- Full report: `{out_dir}/review-{axis}-{n}{suffix}.md`",
            f"- Findings sidecar: `{out_dir}/{sidecar_name(axis, n, rnd)}`, one line per finding: `{SIDECAR[axis]}`. "
            "Empty file when you found nothing.",
            *id_lines,
            f"- Then the empty completion marker `{out_dir}/{sidecar_name(axis, n, rnd, 'done')}`, last, once the sidecar is complete.",
            f"- Then `python3 ~/.agents/skills/multi-axis-code-review/review_ledger.py append --repo {a.repo} "
            f"--ticket {n} --type {axis}" + (f" --round {rnd}" if rnd > 1 else "") + "`."]),
        "## Limits",
        "\n".join([
            "- You do your own reading and running and spawn no nested subagent: a nested agent reports to the "
            "top-level session, not to you, and its work is lost. A task too large for one agent is reported as such and stopped.",
            f"- Any solve, build or test run uses at most {a.workers} worker{'s' if a.workers != 1 else ''} and "
            f"finishes inside {a.ceiling} seconds of wall clock."]
            + ([f"- Run the witness check with `--slots {a.workers}`: it picks its own concurrency otherwise."]
               if axis == "correctness" else [])),
    ]
    return "\n\n".join(p for p in parts if p) + "\n"


def write_brief(text, repo, ticket, axis, rnd=1):
    """Write `text` to a ticket-numbered file of `repo`'s (folded) review cache directory that no
    earlier wave holds, and return its path. `O_EXCL` is the never-overwrite: a taken name moves on to `-2`, `-3`."""
    directory = review_ledger.REVIEWS_ROOT / repo
    directory.mkdir(parents=True, exist_ok=True)
    # SKILL.md allows a branch name for `--ticket`; a `/` in it must not name a directory.
    stem, k = f"brief-{re.sub(r'[^A-Za-z0-9._-]', '-', ticket)}-{axis}" + (f"-r{rnd}" if rnd > 1 else ""), 1
    while True:
        path = directory / (f"{stem}.md" if k == 1 else f"{stem}-{k}.md")
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            k += 1
            continue
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
        return path


def main(argv):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--axis", required=True, choices=AXES)
    p.add_argument("--repo", required=True)
    p.add_argument("--worktree", required=True)
    p.add_argument("--ticket", required=True)
    p.add_argument("--base", required=True)
    p.add_argument("--diff", required=True)
    p.add_argument("--diff-command", required=True)
    p.add_argument("--commit", action="append", default=[])
    p.add_argument("--spec")
    p.add_argument("--no-spec", action="store_true")
    p.add_argument("--ruling", action="append", default=[])
    p.add_argument("--choice", action="append", default=[])
    p.add_argument("--claim", action="append", default=[])
    p.add_argument("--round", type=int, default=1)
    p.add_argument("--first-id", action="append", default=[])
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--ceiling", type=int, default=600)
    p.add_argument("--test-command")
    p.add_argument("--capture-stat")
    a = p.parse_args(argv)
    a.repo = review_ledger.fold_repo(a.repo)  # once: every path and the ledger line below read it folded
    try:
        path = write_brief(render(a), a.repo, a.ticket, a.axis, a.round)
    except BadInput as exc:
        print(f"render-brief: {exc}", file=sys.stderr)
        return 2
    # `review_ledger.attribute` reads "round K" from the first 120 characters of this line.
    lead = f"Round {a.round}: " if a.round > 1 else ""
    print(f"{lead}Read {path} and carry out the {a.axis} review of #{a.ticket} it describes: that file is your whole brief.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
