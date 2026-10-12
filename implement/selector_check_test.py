"""`implement/selector_check.py` (#1537): after a merge's full seam run, one
`selector:` comment on the PR saying whether the repo's narrowed command would
have selected what the full seam failed on.

Seam: the real script as a subprocess against a throwaway repo whose
`AGENTS.md` declares a `Narrowed` line, a fake `tests/all.sh` standing in for
the narrowed runner and a fake `gh` on PATH that records each `pr comment`.
Every `not checked` case asserts the reason it names, so a refusal for some
other cause does not pass for the one under test (`AGENTS.md` § Recurring
defect classes, class 3).
"""
import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "selector_check.py")

FAKE_GH = """#!/bin/sh
[ -n "$GH_FAIL" ] && { echo "gh exploded" >&2; exit 1; }
printf '%s\\n' "$*" >> "$GH_LOG"
"""


def declared(narrowed=True):
    lines = ["## End-to-end seam", "", "- **Seam**: `bash tests/all.sh`", "- **Blind to**: the live editor"]
    if narrowed:
        lines.append("- **Narrowed**: `bash tests/all.sh --changed origin/main` over the changed suites")
    return "\n".join(lines) + "\n"


class World:
    def __init__(self, tmp_path, narrowed=True, listing="alpha/a.test.sh\nbeta/b.test.sh\n", listing_exit=0):
        self.tmp = str(tmp_path)
        self.root = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(self.root, "tests"))
        with open(os.path.join(self.root, "AGENTS.md"), "w") as f:
            f.write(declared(narrowed))
        # The runner's `--list` prints `LISTING` (a file) and exits `LISTING_EXIT`; the run itself is unused here.
        self.write("tests/all.sh", '#!/bin/sh\ncase "$*" in *--list*) cat "$LISTING"; exit "${LISTING_EXIT:-0}";; esac\nexit 9\n')
        os.chmod(os.path.join(self.root, "tests", "all.sh"), 0o755)
        self.listing_file = os.path.join(self.tmp, "listing.txt")
        with open(self.listing_file, "w") as f:
            f.write(listing)
        self.bin = os.path.join(self.tmp, "bin")
        os.mkdir(self.bin)
        gh = os.path.join(self.bin, "gh")
        with open(gh, "w") as f:
            f.write(FAKE_GH)
        os.chmod(gh, 0o755)
        self.gh_log = os.path.join(self.tmp, "gh.log")
        self.state = os.path.join(self.tmp, "state.json")
        self.seam_log = os.path.join(self.tmp, "seam.log")
        self.env = {**os.environ, "PATH": self.bin + os.pathsep + os.environ["PATH"], "GH_LOG": self.gh_log,
                    "LISTING": self.listing_file, "LISTING_EXIT": str(listing_exit)}

    def write(self, rel, text):
        with open(os.path.join(self.root, rel), "w") as f:
            f.write(text)

    def script(self, *args, env=None):
        return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True,
                              env={**self.env, **(env or {})}, cwd=self.tmp)

    def list(self, *extra, env=None):
        return self.script("list", "--root", self.root, "--state", self.state, *extra, env=env)

    def comment(self, seam_exit, log="", *extra, post=True, env=None):
        with open(self.seam_log, "w") as f:
            f.write(log)
        args = ["comment", "--root", self.root, "--state", self.state, "--seam-exit", str(seam_exit),
                "--seam-log", self.seam_log, *extra]
        if post:
            args += ["--pr", "42", "--repo", "me/repo"]
        return self.script(*args, env=env)

    def posted(self):
        if not os.path.exists(self.gh_log):
            return []
        with open(self.gh_log) as f:
            return f.read().splitlines()


@pytest.fixture
def w(tmp_path):
    return World(tmp_path)


def verdict(r):
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def test_a_green_seam_posts_clean(w):
    assert w.list().returncode == 0
    assert verdict(w.comment(0, "7 of 7 suites passed\n")) == "selector: clean"
    assert w.posted() == ["pr comment 42 --repo me/repo --body selector: clean"]


def test_a_red_seam_whose_failing_suite_is_outside_the_listing_is_a_miss(w):
    w.list()
    assert verdict(w.comment(1, "ok alpha/a.test.sh\nFAIL zeta/z.test.sh\n")) == "selector: miss zeta/z.test.sh"
    assert w.posted() == ["pr comment 42 --repo me/repo --body selector: miss zeta/z.test.sh"]


def test_a_red_seam_whose_failing_suite_is_inside_the_listing_is_a_hit(w):
    w.list()
    assert verdict(w.comment(1, "FAIL beta/b.test.sh\n")) == "selector: hit beta/b.test.sh"


def test_one_failing_suite_outside_the_listing_makes_the_whole_run_a_miss(w):
    w.list()
    assert verdict(w.comment(1, "FAIL beta/b.test.sh\nFAIL zeta/z.test.sh\n")) == "selector: miss zeta/z.test.sh"


def test_an_indented_fail_line_a_passing_suite_reprints_is_not_a_failure(w):
    w.list()
    assert verdict(w.comment(1, "  FAIL zeta/z.test.sh\nFAIL beta/b.test.sh\n")) == "selector: hit beta/b.test.sh"


@pytest.mark.parametrize("listing, exit_code, why", [
    ("alpha/a.test.sh\n", 3, "exited 3"),
    ("", 0, "printed nothing"),
    ("   \n\n", 0, "printed nothing"),
])
def test_a_listing_that_failed_or_is_empty_is_not_checked_and_never_clean(tmp_path, listing, exit_code, why):
    w = World(tmp_path, listing=listing, listing_exit=exit_code)
    w.list()
    for seam_exit, log in ((0, ""), (1, "FAIL zeta/z.test.sh\n")):
        out = verdict(w.comment(seam_exit, log))
        assert out.startswith("selector: not checked: "), out
        assert why in out
    assert not any(c.endswith("selector: clean") for c in w.posted())


def test_a_listing_command_that_is_missing_is_not_checked(tmp_path):
    w = World(tmp_path)
    os.remove(os.path.join(w.root, "tests", "all.sh"))
    w.list()
    out = verdict(w.comment(0))
    assert out.startswith("selector: not checked: ")
    assert "exited 127" in out


def test_a_listing_step_that_never_ran_is_not_checked(w):
    # No `list` call: the state file is absent, which is not an empty selection.
    out = verdict(w.comment(0))
    assert out.startswith("selector: not checked: ")
    assert "no listing record" in out


def test_a_red_seam_log_with_no_fail_line_is_not_checked(w):
    w.list()
    out = verdict(w.comment(1, "npm ci failed\n"))
    assert out == "selector: not checked: the seam's log has no `FAIL <suite>` line"


def test_a_seam_log_that_cannot_be_read_is_not_checked(w):
    w.list()
    r = w.script("comment", "--root", w.root, "--state", w.state, "--seam-exit", "1",
                 "--seam-log", os.path.join(w.tmp, "nope.log"))
    assert verdict(r).startswith("selector: not checked: the seam's log could not be read")


def test_a_seam_exit_that_is_not_a_number_is_not_checked(w):
    w.list()
    r = w.comment("", "FAIL zeta/z.test.sh\n")
    assert verdict(r) == "selector: not checked: the seam's exit status was not recorded"


def test_a_repo_with_no_narrowed_line_gets_no_listing_and_no_comment(tmp_path):
    w = World(tmp_path, narrowed=False)
    r = w.list()
    assert r.returncode == 3
    assert not os.path.exists(w.state)
    r = w.comment(1, "FAIL zeta/z.test.sh\n")
    assert r.returncode == 0 and r.stdout == ""
    assert w.posted() == []


def test_a_narrowed_line_in_a_fence_is_an_example_not_a_declaration(tmp_path):
    w = World(tmp_path, narrowed=False)
    w.write("AGENTS.md", "## End-to-end seam\n\n```\n- **Narrowed**: `bash tests/all.sh --changed origin/main`\n```\n")
    assert w.list().returncode == 3


def test_a_narrowed_line_with_no_command_is_not_checked_not_silent(tmp_path):
    w = World(tmp_path, narrowed=False)
    w.write("AGENTS.md", "## End-to-end seam\n\n- **Narrowed**:\n")
    assert w.list().returncode == 0
    out = verdict(w.comment(0))
    assert out.startswith("selector: not checked: ")
    assert "names no command" in out


def test_the_comment_never_changes_the_script_status(w):
    """Evidence only: a miss, a hit and a failed post all exit 0, so no caller
    reads the verdict, or a gh outage, as a reason to hold the merge."""
    w.list()
    assert w.comment(1, "FAIL zeta/z.test.sh\n").returncode == 0
    assert w.comment(1, "FAIL beta/b.test.sh\n").returncode == 0
    r = w.comment(1, "FAIL zeta/z.test.sh\n", env={"GH_FAIL": "1"})
    assert r.returncode == 0
    assert "selector comment not posted: " in r.stdout
    assert "selector: miss zeta/z.test.sh" in r.stdout


def test_suites_are_whole_lines_so_a_multi_word_command_is_not_matched_by_its_first_word(tmp_path):
    """The pilot runner labels a suite with its command line and prints
    `FAIL <that line>`; reading the first word turned every miss into a hit."""
    w = World(tmp_path, listing="node examples/alpha/a.test.mjs\nuvx ruff check finders\n")
    w.list()
    assert verdict(w.comment(1, "FAIL node examples/zeta/z.test.mjs\n")) == "selector: miss node examples/zeta/z.test.mjs"
    assert verdict(w.comment(1, "FAIL uvx ruff check finders\n")) == "selector: hit uvx ruff check finders"


def test_a_state_file_that_is_not_json_is_unreadable_not_a_step_that_never_ran(w):
    with open(w.state, "w") as f:
        f.write("{not json")
    out = verdict(w.comment(0))
    assert out.startswith("selector: not checked: the listing record could not be read")
    assert "did not run" not in out


def test_list_removes_the_state_an_earlier_run_left_before_it_runs_anything(w):
    with open(w.state, "w") as f:
        json.dump({"command": "x", "status": 0, "listing": ["zeta/z.test.sh"], "error": None}, f)
    w.list(env={"PATH": "/nonexistent"})  # `sh` cannot start: the stale listing, which holds the suite, must be gone
    out = verdict(w.comment(1, "FAIL zeta/z.test.sh\n"))
    assert out.startswith("selector: not checked: the listing command could not run")


def test_a_repo_with_no_line_leaves_no_state_even_when_an_earlier_run_wrote_one(tmp_path):
    w = World(tmp_path, narrowed=False)
    with open(w.state, "w") as f:
        f.write("{}")
    assert w.list().returncode == 3
    assert not os.path.exists(w.state)
