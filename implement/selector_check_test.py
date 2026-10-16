"""`implement/selector_check.py`: `command` prints the repo's per-change
command (#1593), and at merge one `selector:` comment on the PR records the
suites the narrowed command selected, judging nothing (#1537, #1593).

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

    def comment(self, *extra, post=True, env=None):
        args = ["comment", "--root", self.root, "--state", self.state, *extra]
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


def test_the_comment_records_the_listing_and_judges_nothing(w):
    assert w.list().returncode == 0
    out = verdict(w.comment())
    assert out == ("selector: listed 2 suites from `bash tests/all.sh --changed origin/main --list`\n\n"
                   "```\nalpha/a.test.sh\nbeta/b.test.sh\n```")
    assert w.posted() == ["pr comment 42 --repo me/repo --body " + out.splitlines()[0]] + out.splitlines()[1:]
    for word in ("clean", "miss", "hit"):
        assert f"selector: {word}" not in out


def test_one_suite_is_said_in_the_singular(tmp_path):
    w = World(tmp_path, listing="alpha/a.test.sh\n")
    w.list()
    assert verdict(w.comment(post=False)).startswith("selector: listed 1 suite from ")


@pytest.mark.parametrize("listing, exit_code, why", [
    ("alpha/a.test.sh\n", 3, "exited 3"),
    ("", 0, "printed nothing"),
    ("   \n\n", 0, "printed nothing"),
])
def test_a_listing_that_failed_or_is_empty_is_not_checked_never_an_empty_selection(tmp_path, listing, exit_code, why):
    w = World(tmp_path, listing=listing, listing_exit=exit_code)
    w.list()
    out = verdict(w.comment())
    assert out.startswith("selector: not checked: "), out
    assert why in out
    assert not any("selector: listed" in c for c in w.posted())


def test_a_listing_command_that_is_missing_is_not_checked(tmp_path):
    w = World(tmp_path)
    os.remove(os.path.join(w.root, "tests", "all.sh"))
    w.list()
    out = verdict(w.comment())
    assert out.startswith("selector: not checked: ")
    assert "exited 127" in out


def test_a_listing_step_that_never_ran_is_not_checked(w):
    # No `list` call: the state file is absent, which is not an empty selection.
    out = verdict(w.comment())
    assert out.startswith("selector: not checked: ")
    assert "no listing record" in out


def test_a_repo_with_no_narrowed_line_gets_no_listing_and_no_comment(tmp_path):
    w = World(tmp_path, narrowed=False)
    r = w.list()
    assert r.returncode == 3
    assert not os.path.exists(w.state)
    r = w.comment()
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
    out = verdict(w.comment())
    assert out.startswith("selector: not checked: ")
    assert "names no command" in out


def test_a_failed_post_is_said_and_never_changes_the_script_status(w):
    """Evidence only: a gh outage exits 0, so no caller reads it as a reason
    to hold the merge."""
    w.list()
    r = w.comment(env={"GH_FAIL": "1"})
    assert r.returncode == 0
    assert "selector comment not posted: gh exploded" in r.stdout
    assert r.stdout.startswith("selector: listed 2 suites")


def test_suites_are_whole_lines_so_a_multi_word_command_is_one_suite(tmp_path):
    """The pilot runner labels a suite with its command line, so the listing
    is read one suite per line, never one per word."""
    w = World(tmp_path, listing="node examples/alpha/a.test.mjs\nuvx ruff check finders\n")
    w.list()
    out = verdict(w.comment(post=False))
    assert out.splitlines()[0].startswith("selector: listed 2 suites ")
    assert out.splitlines()[3:5] == ["node examples/alpha/a.test.mjs", "uvx ruff check finders"]


def test_a_state_file_that_is_not_json_is_unreadable_not_a_step_that_never_ran(w):
    with open(w.state, "w") as f:
        f.write("{not json")
    out = verdict(w.comment())
    assert out.startswith("selector: not checked: the listing record could not be read")
    assert "did not run" not in out


def test_list_removes_the_state_an_earlier_run_left_before_it_runs_anything(w):
    with open(w.state, "w") as f:
        json.dump({"command": "x", "status": 0, "listing": ["zeta/z.test.sh"], "error": None}, f)
    w.list(env={"PATH": "/nonexistent"})  # `sh` cannot start: the stale listing, which holds the suite, must be gone
    out = verdict(w.comment(post=False))
    assert out.startswith("selector: not checked: the listing command could not run")


def test_a_repo_with_no_line_leaves_no_state_even_when_an_earlier_run_wrote_one(tmp_path):
    w = World(tmp_path, narrowed=False)
    with open(w.state, "w") as f:
        f.write("{}")
    assert w.list().returncode == 3
    assert not os.path.exists(w.state)


# --- `command`: the repo's per-change command (#1593) ---


def resolve(tmp_path, agents):
    root = tmp_path / "repo"
    root.mkdir()
    if agents is not None:
        (root / "AGENTS.md").write_text(agents)
    return subprocess.run([sys.executable, SCRIPT, "command", "--root", str(root)], capture_output=True, text=True)


SEAM_ONLY = "## End-to-end seam\n\n- **Seam**: `npm test` — every suite\n- **Blind to**: the live editor\n"


def test_command_prints_the_narrowed_command_when_one_is_declared(tmp_path):
    r = resolve(tmp_path, declared(narrowed=True))
    assert (r.returncode, r.stdout, r.stderr) == (0, "bash tests/all.sh --changed origin/main\n", "")


def test_command_falls_back_to_the_seam_when_no_narrowed_line_is_declared(tmp_path):
    r = resolve(tmp_path, SEAM_ONLY)
    assert (r.returncode, r.stdout, r.stderr) == (0, "npm test\n", "")


@pytest.mark.parametrize("agents, why", [
    ("## End-to-end seam\n\n- **Blind to**: everything\n", "declares neither a `Narrowed` nor a `Seam` line"),
    ("# Notes\n\nno seam here\n", "has no `## End-to-end seam` section"),
    (None, "no AGENTS.md"),
    ("## End-to-end seam\n\n- **Seam**: `npm test`\n- **Narrowed**:\n", "the `Narrowed` line names no command"),
    ("## End-to-end seam\n\n- **Seam**: **\n", "the `Seam` line names no command"),
])
def test_command_exits_non_zero_naming_the_gap_and_prints_no_command(tmp_path, agents, why):
    r = resolve(tmp_path, agents)
    assert r.returncode == 1
    assert r.stdout == ""
    assert why in r.stderr


# --- `failing_suites`: the seam log's failed suites, which the backstop reads ---


def test_failing_suites_reads_whole_unindented_fail_lines_once_each(tmp_path):
    sys.path.insert(0, HERE)
    from selector_check import failing_suites
    log = tmp_path / "seam.log"
    log.write_text("PASS a/a.test.sh\n  FAIL b/b.test.sh\nFAIL node z/z.test.mjs\nFAIL c/c.test.sh\nFAIL node z/z.test.mjs\n")
    assert failing_suites(str(log)) == (["node z/z.test.mjs", "c/c.test.sh"], None)
    log.write_text("npm ci failed\n")
    assert failing_suites(str(log)) == ([], "the seam's log has no `FAIL <suite>` line")
    assert failing_suites(str(tmp_path / "nope.log"))[1].startswith("the seam's log could not be read")
