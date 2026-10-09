"""The merge check (#1401): `fix-check.sh <n>` verifies mechanically
that every review finding of ticket <n> has exactly one disposition, that a
`fixed` sha is a commit on the PR branch, that a `moved` ticket is open, and
that an empty findings sidecar carries its reviewer's completion marker.

Seam: the real script, run from a linked worktree of a throwaway repo whose
`origin` is a bare clone, with a fake `gh` on PATH and the review cache under
a fake HOME. Every refusal case also asserts the message names its cause, so
a refusal for another reason (a missing file, a failed setup) does not pass
for the one under test (`AGENTS.md` § Recurring defect classes, class 3).

Each case builds its own throwaway world under pytest's temp dir.
"""
import json
import os
import shutil
import subprocess
import time

import pytest

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
    """One repo, one branch (`implement-5` unless named) with commits past main, and the
    review cache keyed on `ticket`."""

    def __init__(self, tmp, author_date=None, ticket=5, branch="implement-5"):
        self.n = ticket
        self.tmp = str(tmp)
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
        self.git(self.primary, "worktree", "add", "-q", "-b", branch, self.work)
        self.base_sha = self.git(self.primary, "rev-parse", "HEAD")
        self.fix_sha = self.commit(self.work, "fix")
        # A second commit, so the branch's history is read across commits: one of them closes #6.
        self.commit(self.work, "more", "more\n\nCloses #6")
        self.reviews = os.path.join(self.home, ".cache", "agent-reviews", "skills-repo")
        os.makedirs(self.reviews)
        self.tickets = {}
        self.prs = []
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
        not in it fails, as an unreachable gh does), and a `gh pr list` that prints self.prs, one
        `<number> <base>` line per open PR, or fails when self.prs is None."""
        table = "\n".join(f"{n}) echo {s};;" for n, s in self.tickets.items())
        prs = ("echo 'gh: no network' >&2; exit 1" if self.prs is None
               else "".join(f"echo '{number} {base}'; " for number, base in self.prs) + "exit 0")
        with open(os.path.join(self.bin, "gh"), "w") as fh:
            fh.write(f'#!/usr/bin/env bash\nif [ "$1 $2" = "pr list" ]; then {prs}; fi\n'
                     f'case "$3" in\n{table}\n*) echo "no such issue" >&2; exit 1;;\nesac\n')
        os.chmod(os.path.join(self.bin, "gh"), 0o755)

    def put(self, name, text):
        with open(os.path.join(self.reviews, name), "w") as fh:
            fh.write(text)

    def findings(self, **by_axis):
        """Write the three sidecars (axis -> ids), each beside its completion marker."""
        for axis in ("standards", "spec", "correctness"):
            ids = by_axis.get(axis, [])
            self.put(f"findings-{axis}-{self.n}.jsonl",
                     "".join(json.dumps({"id": i, "axis": axis, "severity": "hard", "file": "f", "title": "t",
                                         **({"rating": "CONFIRMED"} if axis == "correctness" else {})}) + "\n"
                             for i in ids))
            self.put(f"findings-{axis}-{self.n}.done", "")

    def ledger_skip(self, rtype, ticket=None):
        """A ledger row saying review `rtype` did not run for `ticket` (what `append --skip-reason` writes)."""
        ticket = self.n if ticket is None else ticket
        row = {"repo": "skills-repo", "ticket": ticket, "tickets": [ticket], "type": rtype,
               "status": {"fields": {"findings": {"status": "skipped", "reason": "test"}}}}
        path = os.path.join(self.home, ".cache", "agent-reviews", "ledger.jsonl")
        with open(path, "a") as fh:
            fh.write(json.dumps(row) + "\n")

    def dispositions(self, *lines):
        self.put(f"dispositions-{self.n}.jsonl", "".join(json.dumps(line) + "\n" for line in lines))

    def codex(self, status=0, launch=None, completion=None, out=CODEX_OUT):
        sha = self.git(self.work, "rev-parse", "HEAD")
        self.put(f"codex-adversarial-{self.n}-gate.json", json.dumps({
            "ticket": self.n, "phase": "gate", "status": status,
            "launch_sha": launch or sha, "completion_sha": completion or sha}))
        self.put(f"codex-adversarial-{self.n}-gate.out", out)

    def run(self, cwd=None, *args):
        done = subprocess.run(["bash", CHECK, str(self.n), *args], cwd=cwd or self.work, env=self.env,
                              capture_output=True, text=True)
        return done.returncode, done.stdout + done.stderr


def fixed(fid, sha):
    return {"id": fid, "outcome": "fixed", "sha": sha}


def disputed(fid, reason="r"):
    return {"id": fid, "outcome": "disputed", "reason": reason}


def assert_fix_check(world, want_code, needle, cwd=None, *args):
    """Run the check and assert its exit code and that its output names the cause."""
    code, out = world.run(cwd, *args)
    assert code == want_code and needle in out, f"want exit {want_code} + {needle!r}, got {code}: {out}"


def age(world, names, seconds_ago):
    old = time.time() - seconds_ago
    for name in names:
        os.utime(os.path.join(world.reviews, name), (old, old))


@pytest.fixture
def make_world(tmp_path_factory):
    def make(**kwargs):
        return World(tmp_path_factory.mktemp("world"), **kwargs)
    return make


@pytest.fixture
def world(make_world):
    return make_world()


@pytest.fixture
def reviewed(world):
    """Standards S1 and spec P1 found; the cache otherwise empty of dispositions."""
    world.findings(standards=["S1"], spec=["P1"])
    return world


@pytest.fixture
def clean(world):
    """Three empty sidecars with their markers, and an empty dispositions sidecar."""
    world.findings()
    world.dispositions()
    return world


@pytest.fixture
def rebased(make_world):
    """#1419: a rebase after the review wave moves every committer date past the sidecars, and
    the sidecars must still read as this dispatch's: the branch is dated by author time."""
    w = make_world(author_date=time.time() - 3600)
    w.findings(standards=["S1"])
    written = time.time() - 1800  # after the commits were authored, before the rebase
    for name in os.listdir(w.reviews):
        os.utime(os.path.join(w.reviews, name), (written, written))
    w.commit(w.primary, "moved-on")
    w.git(w.primary, "push", "-q", "origin", "main")
    w.git(w.work, "fetch", "-q", "origin")
    w.git(w.work, "rebase", "-q", "origin/main")
    committed = int(w.git(w.work, "log", "origin/main..HEAD", "--format=%ct", "-1"))
    assert committed > written, "setup: the rebase did not move the committer date past the sidecars"
    new_fix = w.git(w.work, "log", "origin/main..HEAD", "--format=%H", "--grep=^fix$")
    w.dispositions(fixed("S1", new_fix))
    os.utime(os.path.join(w.reviews, "dispositions-5.jsonl"), (written + 60, written + 60))
    return w


def test_a_rebase_after_the_review_wave_leaves_the_sidecars_fresh(rebased):
    assert_fix_check(rebased, 0, "1 findings")


def test_sidecars_older_than_the_branchs_authored_commits_are_still_an_earlier_dispatchs(rebased):
    age(rebased, ("findings-standards-5.jsonl", "findings-standards-5.done"), 10 * 86400)
    assert_fix_check(rebased, 1, "findings-standards-5.jsonl is older than the first commit")


# #1459: a slice of a spec run is reviewed once on its integration branch, so its own
# branch runs no wave. The skip is read from the base dispatch recorded, never from the
# missing dispositions file (defect class 1).

def test_a_base_recorded_for_another_ticket_excuses_nothing(world):
    world.git(world.primary, "config", "branch.implement-6.base", "spec-3")
    assert_fix_check(world, 1, "dispositions-5.jsonl is missing")


def test_a_recorded_base_that_is_no_spec_p_keeps_the_review_check(world):
    world.git(world.primary, "config", "branch.implement-6.base", "spec-3")
    world.git(world.primary, "config", "branch.implement-5.base", "main")
    assert_fix_check(world, 1, "dispositions-5.jsonl is missing")


def test_a_recorded_spec_3_with_no_origin_spec_3_is_no_live_slice_a_stale_or_hand_set_key(world):
    world.git(world.primary, "config", "branch.implement-5.base", "spec-3")
    assert_fix_check(world, 1, "origin/spec-3 does not exist")


@pytest.fixture
def slice_world(world):
    world.git(world.primary, "config", "branch.implement-5.base", "spec-3")
    world.git(world.primary, "push", "-q", "origin", "main:spec-3")
    world.git(world.primary, "fetch", "-q", "origin")
    return world


def test_a_slice_of_spec_3_needs_no_review_sidecars_and_no_dispositions(slice_world):
    assert_fix_check(slice_world, 0, "slice of spec-3, no review wave")


def test_before_its_pr_exists_the_slice_says_its_base_is_checked_at_the_merge(slice_world):
    assert_fix_check(slice_world, 0, "no open PR from implement-5 yet")


# #1460's S4: fix-check passes a slice with no review, so a slice PR opened against main
# would land there unreviewed; the base GitHub holds is read, not the one dispatch meant.
def test_a_slice_pr_into_its_spec_3_passes(slice_world):
    slice_world.prs = [(40, "spec-3")]
    slice_world.write_gh()
    assert_fix_check(slice_world, 0, "PR #40 into spec-3")


def test_a_slice_pr_opened_against_main_is_refused_before_the_merge(slice_world):
    slice_world.prs = [(40, "main")]
    slice_world.write_gh()
    assert_fix_check(slice_world, 1, "PR #40 from implement-5 targets main, not spec-3")


def test_a_gh_that_cannot_list_the_slices_pr_is_the_environments_exit_2(slice_world):
    slice_world.prs = None
    slice_world.write_gh()
    assert_fix_check(slice_world, 2, "gh: no network")


def test_a_recorded_base_git_cannot_read_is_the_environments_exit_2_never_an_ordinary_ticket(slice_world):
    real_git = shutil.which("git", path=os.environ["PATH"])
    with open(os.path.join(slice_world.bin, "git"), "w") as fh:
        fh.write('#!/usr/bin/env bash\n'
                 'if [ "$1 $2" = "config --get" ]; then echo "bad config line 9" >&2; exit 3; fi\n'
                 f'exec {real_git} "$@"\n')
    os.chmod(os.path.join(slice_world.bin, "git"), 0o755)
    assert_fix_check(slice_world, 2, "bad config line 9")


def test_a_slice_head_that_was_never_pushed_is_still_no_pr_head(slice_world):
    assert_fix_check(slice_world, 2, "origin/implement-5", slice_world.primary, "origin/implement-5")


def test_the_controllers_origin_implement_5_reads_the_same_recorded_base(slice_world):
    slice_world.git(slice_world.work, "push", "-q", "origin", "implement-5")
    assert_fix_check(slice_world, 0, "slice of spec-3", slice_world.primary, "origin/implement-5")


# #1461: the spec is reviewed once on its integration branch `spec-<p>`, and the merge check
# is keyed on the spec number: one disposition per finding of that review, every `fixed` sha
# on `spec-<p>` past main. The branch holds a landed slice that closes #4, as a slice's squash
# merge into `spec-3` does.
@pytest.fixture
def spec_world(make_world):
    w = make_world(ticket=3, branch="spec-3")
    w.commit(w.work, "slice-4", "slice 4 (#40)\n\nCloses #4")
    w.git(w.work, "push", "-q", "origin", "spec-3")
    w.git(w.primary, "fetch", "-q", "origin")
    w.findings(standards=["S1"], spec=["P1"])
    return w


def test_a_spec_review_with_an_undisposed_finding_is_refused_keyed_on_the_spec_number(spec_world):
    spec_world.dispositions(fixed("S1", spec_world.fix_sha))
    assert_fix_check(spec_world, 1, "no disposition for P1", spec_world.primary, "origin/spec-3")


def test_a_fixed_sha_that_is_no_commit_on_spec_3_is_refused(spec_world):
    w = spec_world
    w.git(w.primary, "checkout", "-q", "-b", "elsewhere")
    stray = w.commit(w.primary, "stray")
    w.git(w.primary, "checkout", "-q", "main")
    w.dispositions(fixed("S1", stray), disputed("P1"))
    assert_fix_check(w, 1, f"S1: fixed sha {stray} is not a hex commit on origin/spec-3", w.primary, "origin/spec-3")


def test_a_finding_moved_onto_a_slice_the_integration_pr_closes_is_refused(spec_world):
    w = spec_world
    w.dispositions(fixed("S1", w.fix_sha), {"id": "P1", "outcome": "moved", "ticket": 4})
    assert_fix_check(w, 1, "P1: moved ticket #4 is one this PR closes", w.primary, "origin/spec-3")


def test_a_spec_review_with_every_finding_disposed_passes_on_origin_spec_3(spec_world):
    w = spec_world
    w.dispositions(fixed("S1", w.fix_sha), disputed("P1"))
    assert_fix_check(w, 0, "2 findings, each disposed once", w.primary, "origin/spec-3")


def test_nothing_in_the_cache_the_reviewers_never_ran(world):
    assert_fix_check(world, 1, "findings-standards-5.jsonl is missing")


def test_no_findings_and_no_dispositions_sidecar_a_missing_file_is_not_a_clean_review(world):
    world.findings()
    assert_fix_check(world, 1, "dispositions-5.jsonl is missing")


def test_findings_and_no_dispositions_sidecar(reviewed):
    assert_fix_check(reviewed, 1, "dispositions-5.jsonl is missing")


def test_every_finding_disposed_once_passes(reviewed):
    reviewed.dispositions(fixed("S1", reviewed.fix_sha),
                          disputed("P1", "the ticket asks for it"))
    assert_fix_check(reviewed, 0, "2 findings")


@pytest.mark.parametrize("name, lines, code, needle", [
    ("one finding with no disposition",
     lambda w: [fixed("S1", w.fix_sha)], 1, "no disposition for P1"),
    ("one finding disposed twice",
     lambda w: [fixed("S1", w.fix_sha), fixed("S1", w.fix_sha), disputed("P1")],
     1, "repeats finding id 'S1'"),
    ("a disposition for no finding",
     lambda w: [fixed("S1", w.fix_sha), disputed("P1"), fixed("X9", w.fix_sha)],
     1, "X9 is no finding"),
    ("a fixed sha already on main is not a fix on the branch",
     lambda w: [fixed("S1", w.base_sha), disputed("P1")], 1, "S1: fixed sha"),
    ("a fixed sha that is no commit here",
     lambda w: [fixed("S1", "0" * 40), disputed("P1")], 1, "S1: fixed sha"),
    ("a symbolic fixed sha is refused: it means another commit from another checkout",
     lambda w: [fixed("S1", "HEAD"), disputed("P1")], 1, "S1: fixed sha HEAD"),
    ("an abbreviated fixed sha resolves",
     lambda w: [fixed("S1", w.fix_sha[:9]), disputed("P1")], 0, "2 findings"),
    ("a finding moved onto the ticket this PR closes would be lost at the merge",
     lambda w: [fixed("S1", w.fix_sha), {"id": "P1", "outcome": "moved", "ticket": 5}],
     1, "P1: moved ticket #5 is one this PR closes"),
    ("a finding moved onto a ticket a later commit of the branch closes",
     lambda w: [fixed("S1", w.fix_sha), {"id": "P1", "outcome": "moved", "ticket": 6}],
     1, "P1: moved ticket #6 is one this PR closes"),
    ("a moved line without an integer ticket",
     lambda w: [fixed("S1", w.fix_sha), {"id": "P1", "outcome": "moved", "ticket": "77"}],
     1, "P1: moved without a ticket number"),
    ("the removed outcome leftover",
     lambda w: [fixed("S1", w.fix_sha), {"id": "P1", "outcome": "leftover"}],
     1, "its outcome is 'leftover'"),
    ("the removed outcome filed",
     lambda w: [fixed("S1", w.fix_sha), {"id": "P1", "outcome": "filed"}],
     1, "its outcome is 'filed'"),
    ("the removed outcome handed-back",
     lambda w: [fixed("S1", w.fix_sha), {"id": "P1", "outcome": "handed-back"}],
     1, "its outcome is 'handed-back'"),
    ("standards and spec findings need no rating",
     lambda w: [fixed("S1", w.fix_sha), disputed("P1")], 0, "2 findings"),
    ("disputed with no reason",
     lambda w: [fixed("S1", w.fix_sha), disputed("P1", "  ")], 1, "P1: disputed without a reason"),
], ids=lambda v: v if isinstance(v, str) and " " in v else None)
def test_dispositions_of_standards_and_spec_findings(reviewed, name, lines, code, needle):
    reviewed.dispositions(*lines(reviewed))
    assert_fix_check(reviewed, code, needle)


def test_a_moved_ticket_that_is_open_passes(reviewed):
    reviewed.dispositions(fixed("S1", reviewed.fix_sha), {"id": "P1", "outcome": "moved", "ticket": 77})
    reviewed.tickets = {77: "OPEN"}
    reviewed.write_gh()
    assert_fix_check(reviewed, 0, "2 findings")


def test_a_moved_ticket_that_is_closed(reviewed):
    reviewed.dispositions(fixed("S1", reviewed.fix_sha), {"id": "P1", "outcome": "moved", "ticket": 77})
    reviewed.tickets = {77: "CLOSED"}
    reviewed.write_gh()
    assert_fix_check(reviewed, 1, "P1: moved ticket #77 is CLOSED")


def test_a_gh_that_cannot_answer_is_the_environments_exit_2_not_a_refusal_the_worker_fixes(reviewed):
    reviewed.dispositions(fixed("S1", reviewed.fix_sha), {"id": "P1", "outcome": "moved", "ticket": 77})
    reviewed.tickets = {}
    reviewed.write_gh()
    assert_fix_check(reviewed, 2, "`gh issue view 77` failed")


# #1230: a correctness finding carries its CONFIRMED/PLAUSIBLE rating in the sidecar.
@pytest.fixture
def correctness(world):
    world.findings(correctness=["C1"])
    world.dispositions(disputed("C1"))
    return world


def test_a_correctness_finding_with_a_rating_passes(correctness):
    assert_fix_check(correctness, 0, "1 findings")


def test_a_correctness_finding_with_no_rating_is_refused(correctness):
    correctness.put("findings-correctness-5.jsonl", json.dumps(
        {"id": "C1", "axis": "correctness", "severity": "hard", "file": "f", "title": "t"}) + "\n")
    assert_fix_check(correctness, 1, "findings-correctness-5.jsonl:1 has no rating")


def test_a_correctness_rating_outside_confirmed_plausible_is_refused_by_naming_the_wrong_value(correctness):
    correctness.put("findings-correctness-5.jsonl", json.dumps(
        {"id": "C1", "axis": "correctness", "severity": "hard", "rating": "LIKELY",
         "file": "f", "title": "t"}) + "\n")
    assert_fix_check(correctness, 1, "rating 'LIKELY' is not CONFIRMED or PLAUSIBLE")


def test_three_empty_sidecars_with_their_markers_need_no_dispositions(clean):
    assert_fix_check(clean, 0, "0 findings")


def test_an_empty_sidecar_without_its_marker_is_a_reviewer_that_may_have_crashed(clean):
    os.remove(os.path.join(clean.reviews, "findings-spec-5.done"))
    assert_fix_check(clean, 1, "findings-spec-5.jsonl has no completion marker")


def test_a_non_empty_sidecar_without_its_marker_may_be_truncated_refused_too(world):
    world.findings(spec=["P1"])
    os.remove(os.path.join(world.reviews, "findings-spec-5.done"))
    world.dispositions(disputed("P1"))
    assert_fix_check(world, 1, "findings-spec-5.jsonl has no completion marker")


def test_a_sidecar_older_than_the_branch_is_a_leftover_of_an_earlier_dispatch(world):
    world.findings(spec=["P1"])
    world.dispositions(disputed("P1"))
    age(world, ("findings-spec-5.jsonl", "findings-spec-5.done"), 10 * 86400)
    assert_fix_check(world, 1, "findings-spec-5.jsonl is older than the first commit")


def test_a_stale_dispositions_sidecar_is_refused_the_same_way(clean):
    age(clean, ("dispositions-5.jsonl",), 10 * 86400)
    assert_fix_check(clean, 1, "dispositions-5.jsonl is older than the first commit")


def test_a_malformed_sidecar_line_is_not_skipped(clean):
    clean.put("findings-spec-5.jsonl", '{"id": "P1"')
    assert_fix_check(clean, 1, "findings-spec-5.jsonl:1")


# The ablation: a review the ledger records as skipped needs no sidecar.
@pytest.fixture
def no_standards(clean):
    for name in ("findings-standards-5.jsonl", "findings-standards-5.done"):
        os.remove(os.path.join(clean.reviews, name))
    return clean


def test_a_standards_axis_the_ledger_does_not_record_as_skipped_needs_its_sidecar(no_standards):
    assert_fix_check(no_standards, 1, "records no skip for it")


def test_a_skip_recorded_for_another_ticket_excuses_nothing(no_standards):
    no_standards.ledger_skip("standards", ticket=6)
    assert_fix_check(no_standards, 1, "records no skip for it")


def test_a_standards_axis_the_ledger_records_as_skipped_the_ablation_passes_with_no_sidecar(no_standards):
    no_standards.ledger_skip("standards")
    assert_fix_check(no_standards, 0, "0 findings")


# Codex: its findings are `codex-gate-<k>`, the id `review_ledger.py` harvests under.
def test_a_codex_finding_with_no_disposition(clean):
    clean.codex()
    clean.dispositions(fixed("codex-gate-1", clean.fix_sha))
    assert_fix_check(clean, 1, "no disposition for codex-gate-2")


def test_both_codex_findings_disposed(clean):
    clean.codex()
    clean.dispositions(fixed("codex-gate-1", clean.fix_sha), disputed("codex-gate-2"))
    assert_fix_check(clean, 0, "2 findings")


def test_a_codex_run_that_errored_is_a_skipped_pass_named(clean):
    clean.codex(status=1)
    assert_fix_check(clean, 0, "codex pass refused")


def test_a_codex_run_the_branch_moved_under_is_refused_the_same_way(clean):
    clean.codex(launch="a" * 40)
    assert_fix_check(clean, 0, "codex pass refused")


def test_a_codex_output_the_parser_cannot_read_is_not_a_clean_pass(clean):
    clean.codex(out="garbage\n")
    assert_fix_check(clean, 1, "codex-adversarial-5-gate.out")


def test_an_unreadable_codex_record_is_refused_not_read_as_no_pass(clean):
    clean.codex(out="garbage\n")
    clean.put("codex-adversarial-5-gate.json", "{not json")
    assert_fix_check(clean, 1, "codex-adversarial-5-gate.json is unreadable")


def test_a_codex_run_with_no_findings_needs_no_dispositions(clean):
    clean.codex(out="No material findings\n")
    assert_fix_check(clean, 0, "0 findings")


def test_no_codex_record_and_no_ledger_row_saying_why_the_pass_neither_ran_nor_was_skipped_on_record(clean):
    ledger = os.path.join(clean.home, ".cache", "agent-reviews", "ledger.jsonl")
    os.rename(ledger, ledger + ".off")
    assert_fix_check(clean, 1, "no codex-gate row")


# From the primary checkout, as the controller runs it: the branch is named, never HEAD.
@pytest.fixture
def s1_world(world):
    world.findings(standards=["S1"])
    world.dispositions(fixed("S1", world.fix_sha))
    return world


def test_the_primary_checkout_resolves_the_branch_not_its_own_head(s1_world):
    code, out = s1_world.run(s1_world.primary)
    assert code == 0, f"got {code}: {out}"


def test_a_branch_that_was_never_pushed_is_no_pr_head_the_environment_cannot_answer(s1_world):
    assert_fix_check(s1_world, 2, "origin/implement-5", s1_world.primary, "origin/implement-5")


def test_the_pushed_head_named_as_the_controller_names_it_passes(s1_world):
    s1_world.git(s1_world.work, "push", "-q", "origin", "implement-5")
    code, out = s1_world.run(s1_world.primary, "origin/implement-5")
    assert code == 0, f"got {code}: {out}"


def test_no_ticket_number_is_a_usage_error(world):
    done = subprocess.run(["bash", CHECK], cwd=world.work, env=world.env, capture_output=True, text=True)
    assert done.returncode == 2 and "usage" in done.stderr, f"got {done.returncode}: {done.stderr}"
