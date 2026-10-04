#!/usr/bin/env python3
"""The merge check (#1401): `fix-check.sh <n>` verifies mechanically
that every review finding of ticket <n> has exactly one disposition, that a
`fixed` sha is a commit on the PR branch, that a `moved` ticket is open, and
that an empty findings sidecar carries its reviewer's completion marker.

Seam: the real script, run from a linked worktree of a throwaway repo whose
`origin` is a bare clone, with a fake `gh` on PATH and the review cache under
a fake HOME. Every refusal case also asserts the message names its cause, so
a refusal for another reason (a missing file, a failed setup) does not pass
for the one under test (`AGENTS.md` § Recurring defect classes, class 3).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CHECK = os.path.join(HERE, "fix-check.sh")
IDENT = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
         "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}

CODEX_OUT = """Findings:
- [high] First codex finding (a.py:1)
- [low] Second codex finding (b.py:2)

Next steps:
- fix
"""


class World:
    """One repo, one branch `implement-5` with one commit past main."""

    def __init__(self, author_date=None):
        self.tmp = tempfile.mkdtemp(prefix="fix-check-")
        self.home = os.path.join(self.tmp, "home")
        self.bin = os.path.join(self.tmp, "bin")
        os.makedirs(self.bin)
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env = {**env, **IDENT, "HOME": self.home,
                    "PATH": self.bin + os.pathsep + os.environ["PATH"]}
        if author_date is not None:  # commits are authored then; a rebase still stamps its committer date now
            self.env["GIT_AUTHOR_DATE"] = f"{int(author_date)} +0000"
        origin = os.path.join(self.tmp, "origin.git")
        self.git(self.tmp, "init", "-q", "--bare", "-b", "main", origin)
        self.primary = os.path.join(self.tmp, "skills-repo")
        self.git(self.tmp, "clone", "-q", origin, self.primary)
        self.commit(self.primary, "base")
        self.git(self.primary, "push", "-q", "origin", "main")
        self.git(self.primary, "remote", "set-head", "origin", "main")
        self.work = os.path.join(self.tmp, "wt")
        self.git(self.primary, "worktree", "add", "-q", "-b", "implement-5", self.work)
        self.base_sha = self.git(self.primary, "rev-parse", "HEAD")
        self.fix_sha = self.commit(self.work, "fix")
        # A second commit, so the branch's history is read across commits: one of them closes #6.
        self.commit(self.work, "more", "more\n\nCloses #6")
        self.reviews = os.path.join(self.home, ".cache", "agent-reviews", "skills-repo")
        os.makedirs(self.reviews)
        self.tickets = {}
        self.write_gh()
        self.ledger_skip("codex-gate")  # no Codex record unless a case writes one

    def git(self, cwd, *args):
        done = subprocess.run(["git", *args], cwd=cwd, env=self.env, capture_output=True, text=True)
        assert done.returncode == 0, (args, done.stderr)
        return done.stdout.strip()

    def commit(self, cwd, name, message=None):
        with open(os.path.join(cwd, name), "w") as fh:
            fh.write(name)
        self.git(cwd, "add", name)
        self.git(cwd, "commit", "-q", "-m", message or name)
        return self.git(cwd, "rev-parse", "HEAD")

    def write_gh(self):
        """A `gh issue view <n> --json state --jq .state` that answers from self.tickets (a ticket
        not in it fails, as an unreachable gh does)."""
        table = "\n".join(f"{n}) echo {s};;" for n, s in self.tickets.items())
        with open(os.path.join(self.bin, "gh"), "w") as fh:
            fh.write(f'#!/usr/bin/env bash\ncase "$3" in\n{table}\n*) echo "no such issue" >&2; exit 1;;\nesac\n')
        os.chmod(os.path.join(self.bin, "gh"), 0o755)

    def put(self, name, text):
        with open(os.path.join(self.reviews, name), "w") as fh:
            fh.write(text)

    def findings(self, **by_axis):
        """Write the three sidecars (axis -> ids), each beside its completion marker."""
        for axis in ("standards", "spec", "correctness"):
            ids = by_axis.get(axis, [])
            self.put(f"findings-{axis}-5.jsonl",
                     "".join(json.dumps({"id": i, "axis": axis, "severity": "hard", "file": "f", "title": "t",
                                         **({"rating": "CONFIRMED"} if axis == "correctness" else {})}) + "\n"
                             for i in ids))
            self.put(f"findings-{axis}-5.done", "")

    def ledger_skip(self, rtype, ticket=5):
        """A ledger row saying review `rtype` did not run for `ticket` (what `append --skip-reason` writes)."""
        row = {"repo": "skills-repo", "ticket": ticket, "tickets": [ticket], "type": rtype,
               "status": {"fields": {"findings": {"status": "skipped", "reason": "test"}}}}
        path = os.path.join(self.home, ".cache", "agent-reviews", "ledger.jsonl")
        with open(path, "a") as fh:
            fh.write(json.dumps(row) + "\n")

    def dispositions(self, *lines):
        self.put("dispositions-5.jsonl", "".join(json.dumps(line) + "\n" for line in lines))

    def codex(self, status=0, launch=None, completion=None, out=CODEX_OUT):
        sha = self.git(self.work, "rev-parse", "HEAD")
        self.put("codex-adversarial-5-gate.json", json.dumps({
            "ticket": 5, "phase": "gate", "status": status,
            "launch_sha": launch or sha, "completion_sha": completion or sha}))
        self.put("codex-adversarial-5-gate.out", out)

    def run(self, cwd=None, *args):
        done = subprocess.run(["bash", CHECK, "5", *args], cwd=cwd or self.work, env=self.env,
                              capture_output=True, text=True)
        return done.returncode, done.stdout + done.stderr

    def close(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


def fixed(fid, sha):
    return {"id": fid, "outcome": "fixed", "sha": sha}


FAILS = []


def case(name, world, want_code, needle):
    code, out = world.run()
    if code != want_code or needle not in out:
        FAILS.append(f"FAIL: {name} — want exit {want_code} + {needle!r}, got {code}: {out}")
    else:
        print(f"PASS: {name}")


def rebased_after_review():
    """#1419: a rebase after the review wave moves every committer date past the sidecars, and
    the sidecars must still read as this dispatch's: the branch is dated by author time."""
    w = World(author_date=time.time() - 3600)
    try:
        w.findings(standards=["S1"])
        written = time.time() - 1800  # after the commits were authored, before the rebase
        for name in os.listdir(w.reviews):
            os.utime(os.path.join(w.reviews, name), (written, written))
        w.commit(w.primary, "moved-on")
        w.git(w.primary, "push", "-q", "origin", "main")
        w.git(w.work, "fetch", "-q", "origin")
        w.git(w.work, "rebase", "-q", "origin/main")
        committed = int(w.git(w.work, "log", "origin/main..HEAD", "--format=%ct", "-1"))
        if committed <= written:
            FAILS.append("FAIL: setup — the rebase did not move the committer date past the sidecars")
            return
        new_fix = w.git(w.work, "log", "origin/main..HEAD", "--format=%H", "--grep=^fix$")
        w.dispositions(fixed("S1", new_fix))
        os.utime(os.path.join(w.reviews, "dispositions-5.jsonl"), (written + 60, written + 60))
        case("a rebase after the review wave leaves the sidecars fresh", w, 0, "1 findings")
        old = time.time() - 10 * 86400
        for name in ("findings-standards-5.jsonl", "findings-standards-5.done"):
            os.utime(os.path.join(w.reviews, name), (old, old))
        case("sidecars older than the branch's authored commits are still an earlier dispatch's", w, 1,
             "findings-standards-5.jsonl is older than the first commit")
    finally:
        w.close()


def main():
    rebased_after_review()
    w = World()
    try:
        case("nothing in the cache: the reviewers never ran", w, 1, "findings-standards-5.jsonl is missing")

        w.findings()
        case("no findings and no dispositions sidecar: a missing file is not a clean review", w, 1,
             "dispositions-5.jsonl is missing")

        w.findings(standards=["S1"], spec=["P1"])
        case("findings and no dispositions sidecar", w, 1, "dispositions-5.jsonl is missing")

        w.dispositions(fixed("S1", w.fix_sha), {"id": "P1", "outcome": "disputed", "reason": "the ticket asks for it"})
        case("every finding disposed once passes", w, 0, "2 findings")

        w.dispositions(fixed("S1", w.fix_sha))
        case("one finding with no disposition", w, 1, "no disposition for P1")

        w.dispositions(fixed("S1", w.fix_sha), fixed("S1", w.fix_sha),
                       {"id": "P1", "outcome": "disputed", "reason": "r"})
        case("one finding disposed twice", w, 1, "repeats finding id 'S1'")

        w.dispositions(fixed("S1", w.fix_sha), {"id": "P1", "outcome": "disputed", "reason": "r"}, fixed("X9", w.fix_sha))
        case("a disposition for no finding", w, 1, "X9 is no finding")

        w.dispositions(fixed("S1", w.base_sha), {"id": "P1", "outcome": "disputed", "reason": "r"})
        case("a fixed sha already on main is not a fix on the branch", w, 1, "S1: fixed sha")

        w.dispositions(fixed("S1", "0" * 40), {"id": "P1", "outcome": "disputed", "reason": "r"})
        case("a fixed sha that is no commit here", w, 1, "S1: fixed sha")

        w.dispositions(fixed("S1", "HEAD"), {"id": "P1", "outcome": "disputed", "reason": "r"})
        case("a symbolic fixed sha is refused: it means another commit from another checkout", w, 1,
             "S1: fixed sha HEAD")

        w.dispositions(fixed("S1", w.fix_sha[:9]), {"id": "P1", "outcome": "disputed", "reason": "r"})
        case("an abbreviated fixed sha resolves", w, 0, "2 findings")

        w.dispositions(fixed("S1", w.fix_sha), {"id": "P1", "outcome": "moved", "ticket": 77})
        w.tickets = {77: "OPEN"}
        w.write_gh()
        case("a moved ticket that is open passes", w, 0, "2 findings")
        w.tickets = {77: "CLOSED"}
        w.write_gh()
        case("a moved ticket that is closed", w, 1, "P1: moved ticket #77 is CLOSED")
        w.tickets = {}
        w.write_gh()
        case("a gh that cannot answer is the environment's, exit 2, not a refusal the worker fixes", w, 2,
             "`gh issue view 77` failed")
        w.dispositions(fixed("S1", w.fix_sha), {"id": "P1", "outcome": "moved", "ticket": 5})
        case("a finding moved onto the ticket this PR closes would be lost at the merge", w, 1,
             "P1: moved ticket #5 is one this PR closes")
        w.dispositions(fixed("S1", w.fix_sha), {"id": "P1", "outcome": "moved", "ticket": 6})
        case("a finding moved onto a ticket a later commit of the branch closes", w, 1,
             "P1: moved ticket #6 is one this PR closes")
        w.dispositions(fixed("S1", w.fix_sha), {"id": "P1", "outcome": "moved", "ticket": "77"})
        case("a moved line without an integer ticket", w, 1, "P1: moved without a ticket number")

        for outcome in ("leftover", "filed", "handed-back"):
            w.dispositions(fixed("S1", w.fix_sha), {"id": "P1", "outcome": outcome})
            case(f"the removed outcome {outcome}", w, 1, f"its outcome is '{outcome}'")
        # #1230: a correctness finding carries its CONFIRMED/PLAUSIBLE rating in the sidecar.
        w.findings(correctness=["C1"])
        w.dispositions({"id": "C1", "outcome": "disputed", "reason": "r"})
        case("a correctness finding with a rating passes", w, 0, "1 findings")
        w.put("findings-correctness-5.jsonl", json.dumps({"id": "C1", "axis": "correctness", "severity": "hard",
                                                         "file": "f", "title": "t"}) + "\n")
        case("a correctness finding with no rating is refused", w, 1, "findings-correctness-5.jsonl:1 has no rating")
        w.put("findings-correctness-5.jsonl", json.dumps({"id": "C1", "axis": "correctness", "severity": "hard",
                                                         "rating": "LIKELY", "file": "f", "title": "t"}) + "\n")
        case("a correctness rating outside CONFIRMED/PLAUSIBLE is refused", w, 1, "has no rating")
        w.findings(standards=["S1"], spec=["P1"])
        w.dispositions(fixed("S1", w.fix_sha), {"id": "P1", "outcome": "disputed", "reason": "r"})
        case("standards and spec findings need no rating", w, 0, "2 findings")
        w.dispositions(fixed("S1", w.fix_sha), {"id": "P1", "outcome": "disputed", "reason": "  "})
        case("disputed with no reason", w, 1, "P1: disputed without a reason")

        w.findings()
        w.dispositions()
        case("three empty sidecars with their markers need no dispositions", w, 0, "0 findings")
        os.remove(os.path.join(w.reviews, "findings-spec-5.done"))
        case("an empty sidecar without its marker is a reviewer that may have crashed", w, 1,
             "findings-spec-5.jsonl has no completion marker")
        w.findings(spec=["P1"])
        os.remove(os.path.join(w.reviews, "findings-spec-5.done"))
        w.dispositions({"id": "P1", "outcome": "disputed", "reason": "r"})
        case("a non-empty sidecar without its marker may be truncated: refused too", w, 1,
             "findings-spec-5.jsonl has no completion marker")
        w.findings(spec=["P1"])
        old = time.time() - 10 * 86400
        for name in ("findings-spec-5.jsonl", "findings-spec-5.done"):
            os.utime(os.path.join(w.reviews, name), (old, old))
        case("a sidecar older than the branch is a leftover of an earlier dispatch", w, 1,
             "findings-spec-5.jsonl is older than the first commit")
        w.findings()
        w.dispositions()
        old = time.time() - 10 * 86400
        os.utime(os.path.join(w.reviews, "dispositions-5.jsonl"), (old, old))
        case("a stale dispositions sidecar is refused the same way", w, 1,
             "dispositions-5.jsonl is older than the first commit")
        w.dispositions()
        w.put("findings-spec-5.jsonl", '{"id": "P1"')
        case("a malformed sidecar line is not skipped", w, 1, "findings-spec-5.jsonl:1")
        w.findings()

        # The ablation: a review the ledger records as skipped needs no sidecar.
        for name in ("findings-standards-5.jsonl", "findings-standards-5.done"):
            os.remove(os.path.join(w.reviews, name))
        case("a standards axis the ledger does not record as skipped needs its sidecar", w, 1,
             "records no skip for it")
        w.ledger_skip("standards", ticket=6)
        case("a skip recorded for another ticket excuses nothing", w, 1, "records no skip for it")
        w.ledger_skip("standards")
        case("a standards axis the ledger records as skipped (the ablation) passes with no sidecar", w, 0,
             "0 findings")
        w.findings()

        # Codex: its findings are `codex-gate-<k>`, the id `review_ledger.py` harvests under.
        w.codex()
        w.dispositions(fixed("codex-gate-1", w.fix_sha))
        case("a codex finding with no disposition", w, 1, "no disposition for codex-gate-2")
        w.dispositions(fixed("codex-gate-1", w.fix_sha), {"id": "codex-gate-2", "outcome": "disputed", "reason": "r"})
        case("both codex findings disposed", w, 0, "2 findings")
        w.codex(status=1)
        w.dispositions()
        case("a codex run that errored is a skipped pass, named", w, 0, "codex pass refused")
        w.codex(launch="a" * 40)
        case("a codex run the branch moved under is refused the same way", w, 0, "codex pass refused")
        w.codex(out="garbage\n")
        case("a codex output the parser cannot read is not a clean pass", w, 1, "codex-adversarial-5-gate.out")
        w.put("codex-adversarial-5-gate.json", "{not json")
        case("an unreadable codex record is refused, not read as no pass", w, 1,
             "codex-adversarial-5-gate.json is unreadable")
        w.codex(out="No material findings\n")
        case("a codex run with no findings needs no dispositions", w, 0, "0 findings")
        os.remove(os.path.join(w.reviews, "codex-adversarial-5-gate.json"))
        ledger = os.path.join(w.home, ".cache", "agent-reviews", "ledger.jsonl")
        os.rename(ledger, ledger + ".off")
        case("no codex record and no ledger row saying why: the pass neither ran nor was skipped on record", w, 1,
             "no codex-gate row")
        os.rename(ledger + ".off", ledger)

        # From the primary checkout, as the controller runs it: the branch is named, never HEAD.
        w.findings(standards=["S1"])
        w.dispositions(fixed("S1", w.fix_sha))
        code, out = w.run(w.primary)
        if code != 0:
            FAILS.append(f"FAIL: the primary checkout resolves the branch, not its own HEAD — got {code}: {out}")
        else:
            print("PASS: the primary checkout resolves the branch, not its own HEAD")
        code, out = w.run(w.primary, "origin/implement-5")
        if code != 2 or "origin/implement-5" not in out:
            FAILS.append(f"FAIL: a branch that was never pushed is no PR head — want exit 2 naming it, got {code}: {out}")
        else:
            print("PASS: a branch that was never pushed is no PR head: the environment cannot answer")
        w.git(w.work, "push", "-q", "origin", "implement-5")
        w.dispositions(fixed("S1", w.fix_sha))
        code, out = w.run(w.primary, "origin/implement-5")
        if code != 0:
            FAILS.append(f"FAIL: the pushed head, named as the controller names it, passes — got {code}: {out}")
        else:
            print("PASS: the pushed head, named as the controller names it, passes")

        done = subprocess.run(["bash", CHECK], cwd=w.work, env=w.env, capture_output=True, text=True)
        if done.returncode != 2 or "usage" not in done.stderr:
            FAILS.append(f"FAIL: no ticket number is a usage error — got {done.returncode}: {done.stderr}")
        else:
            print("PASS: no ticket number is a usage error")
    finally:
        w.close()
    if FAILS:
        print("\n".join(FAILS))
        sys.exit(1)
    print("ALL PASS")


if __name__ == "__main__":
    main()
