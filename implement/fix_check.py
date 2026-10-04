#!/usr/bin/env python3
"""The merge check (#1401): did the worker dispose of every review finding?

    python3 implement/fix_check.py <ticket> [<branch, default implement-<ticket>>]

Run from any checkout of the repo; the review cache is keyed on the shared
.git's parent name, as `implement/SKILL.md` § Review writes it. It verifies,
mechanically, what the removed verification pass used to grade:

- `dispositions-<n>.jsonl` exists (empty when every reviewer found nothing:
  a missing file is not a clean review), every finding id in
  `findings-{standards,spec,correctness}-<n>.jsonl` and in the Codex pass's
  output has exactly one line in it, and every line names a finding;
- a `fixed` line's sha is a commit on the branch, past `origin`'s default
  branch;
- a `moved` line's ticket is open;
- a `disputed` line gives a reason;
- an empty findings sidecar is accepted only beside its reviewer's completion
  marker `findings-<axis>-<n>.done`, since an empty file is also what a
  reviewer that crashed leaves behind (defect class 1).

A Codex pass is optional (size gate, usage, kill switch): no record means it
did not run. A record that errored, or whose branch moved under it, is a
refused pass and its findings are not required, said in the output. An output
the parser cannot read is a refusal of this check, never an empty pass.

Exit 0 and one line when every finding is disposed; 1 and one line per
problem; 2 on usage or an environment that cannot answer.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "docs", "research"))
from review_ledger import parse_codex_out  # noqa: E402

AXES = ("standards", "spec", "correctness")
OUTCOMES = ("fixed", "moved", "disputed")


class Unanswerable(Exception):
    """The environment cannot answer (git or the cache): exit 2, not a verdict."""


def git(*args):
    done = subprocess.run(["git", *args], capture_output=True, text=True)
    if done.returncode != 0:
        raise Unanswerable(f"`git {' '.join(args)}` failed: {done.stderr.strip()}")
    return done.stdout.strip()


def reviews_dir():
    common = git("rev-parse", "--path-format=absolute", "--git-common-dir")
    return os.path.join(os.path.expanduser("~"), ".cache", "agent-reviews",
                        os.path.basename(os.path.dirname(common)))


def read_lines(path):
    """The non-blank lines of a file, or None when it is absent."""
    try:
        with open(path) as fh:
            return [(n, line) for n, line in enumerate(fh.read().splitlines(), 1) if line.strip()]
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as exc:
        raise Unanswerable(f"{path} is unreadable: {exc}")


def json_object(line):
    try:
        obj = json.loads(line)
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def axis_findings(reviews, n, problems):
    ids = []
    for axis in AXES:
        name = f"findings-{axis}-{n}.jsonl"
        lines = read_lines(os.path.join(reviews, name))
        if lines is None:
            problems.append(f"{name} is missing — that reviewer never ran")
            continue
        if not lines:
            marker = f"findings-{axis}-{n}.done"
            if not os.path.exists(os.path.join(reviews, marker)):
                problems.append(f"{name} is empty and has no completion marker {marker} — "
                                "an empty sidecar is also what a crashed reviewer leaves")
            continue
        for num, line in lines:
            obj = json_object(line)
            if obj is None or not isinstance(obj.get("id"), str) or not obj["id"].strip():
                problems.append(f"{name}:{num} is not a finding line with an id")
            else:
                ids.append(obj["id"])
    return ids


def codex_findings(reviews, n, problems, notes):
    record = os.path.join(reviews, f"codex-adversarial-{n}-gate.json")
    if not os.path.exists(record):
        return []
    out_name = f"codex-adversarial-{n}-gate.out"
    try:
        with open(record) as fh:
            rec = json.load(fh)
    except (OSError, ValueError) as exc:
        problems.append(f"codex-adversarial-{n}-gate.json is unreadable: {exc}")
        return []
    if not isinstance(rec, dict) or rec.get("status") != 0:
        notes.append(f"codex pass refused (status {rec.get('status') if isinstance(rec, dict) else '?'}), "
                     "its findings are not required")
        return []
    if rec.get("launch_sha") != rec.get("completion_sha"):
        notes.append("codex pass refused (the branch moved while it read), its findings are not required")
        return []
    try:
        with open(os.path.join(reviews, out_name)) as fh:
            found, why = parse_codex_out(fh.read())
    except (OSError, UnicodeDecodeError) as exc:
        problems.append(f"{out_name} is unreadable: {exc}")
        return []
    if found is None:
        problems.append(f"{out_name} cannot be read as findings: {why}")
        return []
    return [f"codex-gate-{k}" for k in range(1, len(found) + 1)]


def pr_commits(branch):
    default = git("symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    return default, set(git("rev-list", f"{default}..{branch}").split())


def moved_state(ticket):
    done = subprocess.run(["gh", "issue", "view", str(ticket), "--json", "state", "--jq", ".state"],
                          capture_output=True, text=True)
    return done.stdout.strip() if done.returncode == 0 else None


def check_disposition(obj, branch, base, commits):
    """The problem with one disposition line, or None."""
    fid, outcome = obj["id"], obj.get("outcome")
    if outcome not in OUTCOMES:
        return f"{fid}: outcome '{outcome}' is not one of {', '.join(OUTCOMES)}"
    if outcome == "disputed" and not str(obj.get("reason", "")).strip():
        return f"{fid}: disputed without a reason"
    if outcome == "fixed":
        sha = str(obj.get("sha", ""))
        done = subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}"],
                              capture_output=True, text=True)
        if not sha or done.returncode != 0 or done.stdout.strip() not in commits:
            return f"{fid}: fixed sha {sha or '(none)'} is not a commit on {branch} past {base}"
    if outcome == "moved":
        ticket = obj.get("ticket")
        if not isinstance(ticket, int) or isinstance(ticket, bool):
            return f"{fid}: moved without a ticket number"
        state = moved_state(ticket)
        if state != "OPEN":
            return f"{fid}: moved ticket #{ticket} is {state or 'unreadable (gh failed)'}, not OPEN"
    return None


def check(n, branch):
    reviews = reviews_dir()
    problems, notes = [], []
    ids = axis_findings(reviews, n, problems) + codex_findings(reviews, n, problems, notes)
    for fid in {i for i in ids if ids.count(i) > 1}:
        problems.append(f"{fid} is raised twice across the findings sidecars")
    disposed = {}
    lines = read_lines(os.path.join(reviews, f"dispositions-{n}.jsonl"))
    base = commits = None
    if lines is None:
        problems.append(f"dispositions-{n}.jsonl is missing — the worker writes it, "
                        "empty when every reviewer found nothing")
    for num, line in lines or []:
        obj = json_object(line)
        if obj is None or not isinstance(obj.get("id"), str):
            problems.append(f"dispositions-{n}.jsonl:{num} is not a disposition line with an id")
            continue
        disposed.setdefault(obj["id"], []).append(obj)
        if obj["id"] not in ids:
            problems.append(f"{obj['id']} is no finding of this ticket's review")
        elif len(disposed[obj["id"]]) == 1:
            if base is None:
                base, commits = pr_commits(branch)
            problem = check_disposition(obj, branch, base, commits)
            if problem:
                problems.append(problem)
    for fid in dict.fromkeys(ids):
        if fid not in disposed:
            problems.append(f"no disposition for {fid}")
    for fid, objs in disposed.items():
        if len(objs) > 1:
            problems.append(f"{fid} has {len(objs)} dispositions, one allowed")
    return problems, f"{len(set(ids))} findings, each disposed once" + "".join(f"; {x}" for x in notes)


def main(argv):
    if not argv or not argv[0].isdigit() or len(argv) > 2:
        print("usage: verification-check.sh <ticket number> [<branch, default implement-<ticket>>]", file=sys.stderr)
        return 2
    n = int(argv[0])
    try:
        problems, summary = check(n, argv[1] if len(argv) > 1 else f"implement-{n}")
    except Unanswerable as exc:
        print(f"fix check: {exc}", file=sys.stderr)
        return 2
    if problems:
        print("\n".join(f"fix check: {p}" for p in problems))
        return 1
    print(f"fix check: {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
