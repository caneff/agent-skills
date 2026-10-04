#!/usr/bin/env python3
"""The merge check (#1401): did the worker dispose of every review finding?

    python3 implement/fix_check.py <ticket> [<branch, default implement-<ticket>>]

Run from any checkout of the repo; the review cache is keyed on the shared
.git's parent name, as `implement/SKILL.md` § Review writes it. The controller
passes `origin/implement-<ticket>`, the head the PR merges. It verifies,
mechanically, what the removed verification pass used to grade:

- `dispositions-<n>.jsonl` exists (empty when every reviewer found nothing: a
  missing file is not a clean review), every finding id in
  `findings-{standards,spec,correctness}-<n>.jsonl` and in the Codex pass's
  output has exactly one line in it, and every line names a finding. The file
  is read by `runfile.read_dispositions`, the one reader of the format;
- a `fixed` line's sha is a hex commit on the branch, past `origin`'s default
  branch;
- a `moved` line's ticket is open, and is not a ticket this PR closes (the
  merge would close it and lose the finding);
- a `disputed` line gives a reason;
- every review that ran left a sidecar beside its completion marker
  `findings-<axis>-<n>.done`, written after the sidecar was complete: an empty
  file is also what a reviewer that crashed leaves, and a truncated one is
  not told from a whole one without it (defect class 1);
- every file of the review is newer than the branch's first commit, so a
  leftover of an earlier dispatch of the same ticket is not read as this one.

A review the ledger records as skipped (`review_ledger.py append --type
<axis> --skip-reason`, the ablation) needs no sidecar; a Codex pass needs a
record, or a `codex-gate` ledger row saying why it did not run (size gate,
usage, kill switch). A Codex record that errored, or whose branch moved under
it, is a refused pass and its findings are not required, said in the output.
An output the parser cannot read is a refusal of this check, never an empty
pass.

Exit 0 and one line when every finding is disposed; 1 and one line per
problem; 2 on usage or an environment that cannot answer (git, `gh`, an
unreadable file).
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "docs", "research"))
sys.path.insert(0, os.path.join(HERE, "..", "burndown"))
import review_ledger  # noqa: E402
import runfile  # noqa: E402

AXES = ("standards", "spec", "correctness")
SHA = re.compile(r"[0-9a-f]{7,40}\Z")
CLOSES = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?) #(\d+)", re.IGNORECASE)


class Unanswerable(Exception):
    """The environment cannot answer (git, gh or the cache): exit 2, not a verdict."""


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


def skipped_types(reviews, n):
    """The review types the ledger records as not run for ticket `n` of this repo."""
    repo = review_ledger.fold_repo(os.path.basename(reviews))
    try:
        rows = review_ledger.read_ledger(review_ledger.DEFAULT_LEDGER)
    except FileNotFoundError:
        return set()
    except ValueError as exc:
        raise Unanswerable(str(exc))
    return {r["type"] for r in rows
            if r.get("repo") == repo and n in (r.get("tickets") or [r.get("ticket")])
            and r["status"]["fields"]["findings"]["status"] == "skipped"}


class Branch:
    """The branch under review: its commits past the default branch, their
    start time and the tickets they close."""

    def __init__(self, name):
        self.name = name
        self.base = git("symbolic-ref", "--short", "refs/remotes/origin/HEAD")
        self.commits = set(git("rev-list", f"{self.base}..{name}").split())
        log = git("log", f"{self.base}..{name}", "--format=%ct%n%B%n==end==").split("==end==")
        stamps = [int(chunk.split("\n", 1)[0]) for chunk in log if chunk.strip()]
        self.started = min(stamps) if stamps else None
        self.closes = {int(m.group(1)) for m in CLOSES.finditer("\n".join(log))}

    def fresh(self, path):
        """None when `path` was written after the branch began; else the problem."""
        if self.started is None or os.path.getmtime(path) >= self.started:
            return None
        return (f"{os.path.basename(path)} is older than the first commit of {self.name} — a leftover of "
                "an earlier dispatch of this ticket, not this review")


def axis_findings(reviews, n, branch, skipped, problems):
    ids = []
    for axis in AXES:
        name = f"findings-{axis}-{n}.jsonl"
        marker = f"findings-{axis}-{n}.done"
        path = os.path.join(reviews, name)
        lines = read_lines(path)
        if lines is None and axis in skipped:
            continue
        if lines is None:
            problems.append(f"{name} is missing — that reviewer never ran, and the ledger "
                            "records no skip for it")
            continue
        if not os.path.exists(os.path.join(reviews, marker)):
            problems.append(f"{name} has no completion marker {marker} — a reviewer that crashed or "
                            "was cut off leaves an empty or truncated sidecar too")
            continue
        for fresh in (branch.fresh(path), branch.fresh(os.path.join(reviews, marker))):
            if fresh:
                problems.append(fresh)
        for num, line in lines:
            obj = json_object(line)
            if obj is None or not isinstance(obj.get("id"), str) or not obj["id"].strip():
                problems.append(f"{name}:{num} is not a finding line with an id")
            else:
                ids.append(obj["id"])
    return ids


def codex_findings(reviews, n, branch, skipped, problems, notes):
    record = os.path.join(reviews, f"codex-adversarial-{n}-gate.json")
    out_name = f"codex-adversarial-{n}-gate.out"
    if not os.path.exists(record):
        if "codex-gate" not in skipped:
            problems.append(f"{os.path.basename(record)} is missing and the ledger has no codex-gate "
                            "row saying why the pass did not run (size gate, usage, kill switch)")
        return []
    try:
        with open(record) as fh:
            rec = json.load(fh)
    except (OSError, ValueError) as exc:
        problems.append(f"{os.path.basename(record)} is unreadable: {exc}")
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
            found, why = review_ledger.parse_codex_out(fh.read())
    except (OSError, UnicodeDecodeError) as exc:
        problems.append(f"{out_name} is unreadable: {exc}")
        return []
    for fresh in (branch.fresh(record), branch.fresh(os.path.join(reviews, out_name))):
        if fresh:
            problems.append(fresh)
    if found is None:
        problems.append(f"{out_name} cannot be read as findings: {why}")
        return []
    return [f"codex-gate-{k}" for k in range(1, len(found) + 1)]


def moved_state(ticket):
    done = subprocess.run(["gh", "issue", "view", str(ticket), "--json", "state", "--jq", ".state"],
                          capture_output=True, text=True)
    if done.returncode != 0:
        raise Unanswerable(f"`gh issue view {ticket}` failed: {done.stderr.strip() or 'no output'}")
    return done.stdout.strip()


def check_disposition(obj, n, branch):
    """The problem with one disposition line, or None."""
    fid, outcome = obj["id"], obj["outcome"]
    if outcome == "disputed" and not str(obj.get("reason", "")).strip():
        return f"{fid}: disputed without a reason"
    if outcome == "fixed":
        sha = str(obj.get("sha", ""))
        resolved = None
        if SHA.match(sha):
            done = subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}"],
                                  capture_output=True, text=True)
            resolved = done.stdout.strip() if done.returncode == 0 else None
        if resolved not in branch.commits:
            return (f"{fid}: fixed sha {sha or '(none)'} is not a hex commit on {branch.name} past "
                    f"{branch.base}")
    if outcome == "moved":
        ticket = obj.get("ticket")
        if not isinstance(ticket, int) or isinstance(ticket, bool):
            return f"{fid}: moved without a ticket number"
        if ticket == n or ticket in branch.closes:
            return f"{fid}: moved ticket #{ticket} is one this PR closes, so the merge would close it"
        state = moved_state(ticket)
        if state != "OPEN":
            return f"{fid}: moved ticket #{ticket} is {state}, not OPEN"
    return None


def check(n, branch_name):
    reviews = reviews_dir()
    branch = Branch(branch_name)
    skipped = skipped_types(reviews, n)
    problems, notes = [], []
    ids = axis_findings(reviews, n, branch, skipped, problems)
    ids += codex_findings(reviews, n, branch, skipped, problems, notes)
    for fid in sorted({i for i in ids if ids.count(i) > 1}):
        problems.append(f"{fid} is raised twice across the findings sidecars")
    sidecar = os.path.join(reviews, f"dispositions-{n}.jsonl")
    lines = []
    if not os.path.exists(sidecar):
        problems.append(f"dispositions-{n}.jsonl is missing — the worker writes it, "
                        "empty when every reviewer found nothing")
    else:
        if (fresh := branch.fresh(sidecar)):
            problems.append(fresh)
        try:
            lines = runfile.read_dispositions(sidecar)
        except runfile.RunFileError as exc:
            problems.append(str(exc))
            return problems, ""
    disposed = {obj["id"] for _, obj in lines}
    for _, obj in lines:
        if obj["id"] not in ids:
            problems.append(f"{obj['id']} is no finding of this ticket's review")
        elif (problem := check_disposition(obj, n, branch)):
            problems.append(problem)
    for fid in dict.fromkeys(ids):
        if fid not in disposed:
            problems.append(f"no disposition for {fid}")
    return problems, f"{len(set(ids))} findings, each disposed once" + "".join(f"; {x}" for x in notes)


def main(argv):
    if not argv or not argv[0].isdigit() or len(argv) > 2:
        print("usage: fix-check.sh <ticket number> [<branch, default implement-<ticket>>]", file=sys.stderr)
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
