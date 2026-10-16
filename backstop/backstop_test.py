"""Tests for `backstop` (#1594). Seam: the command line, `backstop.py --repo
<checkout> --jobs <k> --notify <cmd>`, run as a subprocess against a real git
repo with a bare origin whose `AGENTS.md` declares a fake seam (`sh seam.sh`,
told by `FAKE_SEAM` what to print and exit with), a fake `gh` (a JSON state
file) and a fake notifier that logs its arguments. `HOME` and the global git
config are the test's own. Each case is a night in, and the last-green record,
the filed tickets, the notifications and the exit code out.
"""
import json
import os
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
BACKSTOP = os.path.join(HERE, "backstop.py")

FAKE_GH = r'''#!/usr/bin/env python3
import json, os, sys
path = os.environ["FAKE_STATE"]
state = json.load(open(path))
args = sys.argv[1:]
def opt(name):
    return args[args.index(name) + 1] if name in args else None
if args[:2] == ["issue", os.environ.get("FAIL_VERB")]:
    sys.stderr.write("fake gh: injected failure\n"); sys.exit(1)
if args[:2] == ["api", "user"]:
    print(state["login"])
elif args[:2] == ["issue", "list"]:
    assert opt("--repo") == state["repo"], args
    print(json.dumps([dict(number=n, body=i["body"]) for n, i in enumerate(state["issues"], 1)
                      if i["state"] == "open" and opt("--label") in i["labels"]]))
elif args[:2] == ["issue", "create"]:
    assert opt("--repo") == state["repo"], args
    labels = [args[i + 1] for i, a in enumerate(args) if a == "--label"]
    state["issues"].append(dict(title=opt("--title"), body=open(opt("--body-file")).read(),
                                labels=labels, state="open"))
    json.dump(state, open(path, "w"))
    print(f"https://github.com/{state['repo']}/issues/{len(state['issues'])}")
else:
    sys.stderr.write("fake gh: unhandled %r\n" % args); sys.exit(2)
'''

# What the fake seam does is chosen per night by `FAKE_SEAM`.
FAKE_SEAM = r'''echo "jobs=${TESTS_JOBS:-unset}" >> "$JOBS_LOG"
case "$FAKE_SEAM" in
  green) echo "PASS a/a_test.py"; echo "PASS b/b.test.sh"; echo "2 suites passed" ;;
  red) echo "PASS a/a_test.py"; echo "FAIL b/b.test.sh"; echo "boom"; exit 1 ;;
  red2) echo "FAIL a/a_test.py"; echo "FAIL b/b.test.sh"; exit 1 ;;
  garbled) echo "Segmentation fault"; exit 1 ;;
  silent) ;;
  contradiction) echo "FAIL b/b.test.sh" ;;
esac
'''

FAKE_NOTIFY = '#!/bin/sh\nprintf "%s|%s\\n" "$1" "$2" >> "$NOTIFY_LOG"\n'

AGENTS = "# Repo\n\n## End-to-end seam\n\n- **Seam**: `{seam}`\n- **Blind to**: nothing\n"


def write(path, text, mode=None):
    with open(path, "w") as f:
        f.write(text)
    if mode:
        os.chmod(path, mode)


def read(path):
    with open(path) as f:
        return f.read()


class Sandbox:
    """A repo, a bare origin, the fakes on PATH and an isolated HOME."""

    def __init__(self, tmp_path):
        t = str(tmp_path)
        self.tmp = t
        self.home = os.path.join(t, "home")
        os.mkdir(self.home)
        write(os.path.join(self.home, ".gitconfig"), "[user]\n\tname = t\n\temail = t@example.test\n")
        self.env = {**os.environ, "HOME": self.home, "GIT_CONFIG_GLOBAL": os.path.join(self.home, ".gitconfig"),
                    "GIT_CONFIG_NOSYSTEM": "1"}
        self.bin = os.path.join(t, "bin")
        os.mkdir(self.bin)
        write(os.path.join(self.bin, "gh"), FAKE_GH, 0o755)
        self.notify = os.path.join(t, "notify")
        write(self.notify, FAKE_NOTIFY, 0o755)
        self.state_dir = os.path.join(t, "state")
        self.state_path = os.path.join(t, "gh.json")
        self.notify_log = os.path.join(t, "notify.log")
        self.jobs_log = os.path.join(t, "jobs.log")
        self.origin = os.path.join(t, "origin.git")
        self.repo = os.path.join(t, "repo")
        self.git(t, "init", "-q", "--bare", "-b", "main", self.origin)
        self.git(t, "clone", "-q", self.origin, self.repo)
        self.git(self.repo, "checkout", "-q", "-b", "main")
        self.commit("init", {"AGENTS.md": AGENTS.format(seam="sh seam.sh"), "seam.sh": FAKE_SEAM})
        self.git(self.repo, "remote", "set-head", "origin", "main")
        url = "https://github.com/me/repo.git"
        self.git(self.repo, "remote", "set-url", "origin", url)
        self.git(self.repo, "config", f"url.{self.origin}.insteadOf", url)
        self.save({"login": "me", "repo": "me/repo", "issues": []})

    def git(self, cwd, *args):
        return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                              env=self.env).stdout.strip()

    def commit(self, message, files):
        """One commit on main, pushed, as a squash merge lands; its sha."""
        for name, text in files.items():
            write(os.path.join(self.repo, name), text)
        self.git(self.repo, "add", ".")
        self.git(self.repo, "commit", "-qm", message)
        self.git(self.repo, "push", "-q", "origin", "HEAD:main")
        return self.git(self.repo, "rev-parse", "HEAD")

    def save(self, state):
        write(self.state_path, json.dumps(state))

    def gh_state(self):
        return json.loads(read(self.state_path))

    def run(self, seam, jobs="3", extra=None):
        env = {**self.env, "PATH": self.bin + os.pathsep + os.environ["PATH"], "FAKE_STATE": self.state_path,
               "FAKE_SEAM": seam, "NOTIFY_LOG": self.notify_log, "JOBS_LOG": self.jobs_log,
               "BACKSTOP_DIR": self.state_dir, **(extra or {})}
        args = ["python3", BACKSTOP, "--repo", self.repo, "--notify", self.notify]
        if jobs is not None:
            args += ["--jobs", jobs]
        return subprocess.run(args, capture_output=True, text=True, env=env, timeout=120)

    def last_green(self):
        path = os.path.join(self.state_dir, "last-green-me__repo")
        return read(path).strip() if os.path.exists(path) else None

    def notes(self):
        return read(self.notify_log).splitlines() if os.path.exists(self.notify_log) else []

    def tickets(self):
        return self.gh_state()["issues"]


@pytest.fixture
def sb(tmp_path):
    return Sandbox(tmp_path)


def test_green_advances_last_green_to_origin_tip(sb):
    first = sb.git(sb.repo, "rev-parse", "HEAD")
    assert sb.run("green").returncode == 0
    assert sb.last_green() == first
    tip = sb.commit("feature (#7)", {"f": "x\n"})
    out = sb.run("green")
    assert out.returncode == 0, out.stderr
    assert sb.last_green() == tip
    assert sb.tickets() == [] and sb.notes() == []


def test_job_count_is_the_stated_input_and_required(sb):
    assert sb.run("green", jobs="3").returncode == 0
    assert read(sb.jobs_log).split() == ["jobs=3"]
    out = sb.run("green", jobs=None)
    assert out.returncode != 0 and "--jobs" in out.stderr
    assert read(sb.jobs_log).split() == ["jobs=3"], "no seam runs without a stated job count"


def red_night(sb):
    """A green night, two merges, then a red one; the shas of the green tip
    and the two merges."""
    assert sb.run("green").returncode == 0
    green = sb.last_green()
    merges = [sb.commit("feature (#7)", {"f": "x\n"}), sb.commit("fix (#8)", {"g": "y\n"})]
    return green, merges


def test_red_files_one_ticket_naming_suites_and_merges_and_notifies(sb):
    green, merges = red_night(sb)
    out = sb.run("red")
    assert out.returncode == 1, out.stderr
    assert sb.last_green() == green, "a red night never advances the record"
    (ticket,) = sb.tickets()
    assert sorted(ticket["labels"]) == ["bug", "ready-for-agent"]
    body = ticket["body"]
    assert "b/b.test.sh" in body and "a/a_test.py" not in body
    assert "feature (#7)" in body and "fix (#8)" in body and "init" not in body
    assert merges[-1] in body and green in body
    (note,) = sb.notes()
    assert "red" in note and "me/repo" in note and "issues/1" in note


def test_repeat_red_on_open_backstop_ticket_files_nothing_new(sb):
    red_night(sb)
    assert sb.run("red").returncode == 1
    assert sb.run("red").returncode == 1
    assert len(sb.tickets()) == 1
    assert len(sb.notes()) == 2 and "#1" in sb.notes()[1] and "still red" in sb.notes()[1]


def test_red_with_a_new_failing_suite_files_again(sb):
    red_night(sb)
    assert sb.run("red").returncode == 1
    assert sb.run("red2").returncode == 1
    first, second = sb.tickets()
    assert "a/a_test.py" in second["body"] and "b/b.test.sh" in second["body"]


def test_closed_backstop_ticket_does_not_hold_a_new_one(sb):
    red_night(sb)
    assert sb.run("red").returncode == 1
    state = sb.gh_state()
    state["issues"][0]["state"] = "closed"
    sb.save(state)
    assert sb.run("red").returncode == 1
    assert len(sb.tickets()) == 2


def assert_inconclusive(sb, out, green, why):
    assert out.returncode == 2, out.stderr
    assert sb.last_green() == green, "an inconclusive night is never recorded green"
    assert sb.tickets() == []
    (note,) = sb.notes()
    assert "inconclusive" in note and why in note, note


@pytest.mark.parametrize("files, why", [
    ({"AGENTS.md": AGENTS.format(seam="sh missing-seam.sh")}, "names no `FAIL <suite>` line"),
    ({"AGENTS.md": "# Repo\n\n## End-to-end seam\n\n- **Blind to**: nothing\n"}, "declares no `Seam` command"),
    ({"AGENTS.md": "# Repo\n"}, "declares no `Seam` command"),
])
def test_seam_that_could_not_start_is_inconclusive(sb, files, why):
    assert sb.run("green").returncode == 0
    green = sb.last_green()
    sb.commit("break the seam (#9)", files)
    assert_inconclusive(sb, sb.run("green"), green, why)


@pytest.mark.parametrize("seam, why", [
    ("garbled", "names no `FAIL <suite>` line"),
    ("silent", "printed nothing"),
    ("contradiction", "exited 0 but its log names failing suites"),
])
def test_unreadable_result_is_inconclusive(sb, seam, why):
    assert sb.run("green").returncode == 0
    green = sb.last_green()
    sb.commit("feature (#7)", {"f": "x\n"})
    assert_inconclusive(sb, sb.run(seam), green, why)


def test_ticket_that_could_not_be_filed_is_notified_and_exits_3(sb):
    red_night(sb)
    out = sb.run("red", extra={"FAIL_VERB": "create"})
    assert out.returncode == 3
    assert sb.tickets() == []
    (note,) = sb.notes()
    assert "no ticket filed" in note and "b/b.test.sh" in note


def test_notifier_that_fails_exits_3(sb):
    red_night(sb)
    out = sb.run("red", extra={"NOTIFY_LOG": os.path.join(sb.tmp, "no-such-dir", "log")})
    assert out.returncode == 3 and "notification not sent" in out.stderr
    assert len(sb.tickets()) == 1
