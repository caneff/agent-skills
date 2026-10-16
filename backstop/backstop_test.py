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
if " ".join(args[:2]) in state.get("raw", {}):
    print(state["raw"][" ".join(args[:2])])
elif args[:2] == ["api", "user"]:
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
elif args[:2] == ["run", "list"]:
    if os.environ.get("FAIL_RUN_LIST"):
        sys.stderr.write("fake gh: run list failed\n"); sys.exit(1)
    assert opt("--repo") == state["repo"] and opt("--event") == "schedule", args
    runs = [r for r in state.get("runs", []) if r["headBranch"] == opt("--branch")
            and (not opt("--workflow") or r["workflow"] == opt("--workflow"))
            and (not opt("--status") or r["status"] == opt("--status"))]
    print(json.dumps(runs[::-1][:int(opt("--limit"))]))
elif args[:2] == ["run", "view"]:
    assert "--log-failed" in args and opt("--repo") == state["repo"], args
    log = state.get("logs", {}).get(args[2])
    if log is None:
        sys.stderr.write("fake gh: no log\n"); sys.exit(1)
    print(log)
elif args[:2] == ["pr", "view"]:
    assert opt("--repo") == state["repo"] and opt("--json") == "comments", args
    if args[2] in state.get("pr_errors", []):
        sys.stderr.write("fake gh: pr view failed\n"); sys.exit(1)
    print(json.dumps({"comments": [{"body": b} for b in state.get("prs", {}).get(args[2], [])]}))
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
    os.makedirs(os.path.dirname(path), exist_ok=True)
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

    def run(self, seam, jobs="3", extra=None, flags=(), script=BACKSTOP):
        env = {**self.env, "PATH": self.bin + os.pathsep + os.environ["PATH"], "FAKE_STATE": self.state_path,
               "FAKE_SEAM": seam, "NOTIFY_LOG": self.notify_log, "JOBS_LOG": self.jobs_log,
               "BACKSTOP_DIR": self.state_dir, **(extra or {})}
        args = ["python3", script, "--repo", self.repo, "--notify", self.notify, *flags]
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

    def misses(self):
        path = os.path.join(self.state_dir, "selector-verdicts-me__repo.jsonl")
        rows = [json.loads(x) for x in read(path).splitlines()] if os.path.exists(path) else []
        return [r["suite"] for r in rows if r["verdict"] == "miss"]

    def set(self, **fields):
        state = self.gh_state()
        state.update(fields)
        self.save(state)


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
    ({"AGENTS.md": "# Repo\n\n## End-to-end seam\n\n- **Blind to**: nothing\n"}, "declares no `Seam` line"),
    ({"AGENTS.md": "# Repo\n"}, "has no `## End-to-end seam` section"),
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


def listed(*suites):
    """A merge's `selector:` comment as `selector_check.py comment` posts it."""
    noun = "suite" if len(suites) == 1 else "suites"
    return (f"selector: listed {len(suites)} {noun} from `bash tests/all.sh --changed origin/main --list`"
            "\n\n```\n" + "\n".join(suites) + "\n```")


def verdict_lines(body):
    """The failing-suite lines of a ticket body."""
    section = body.split("## Failing suites", 1)[1].split("##", 1)[0]
    return [x for x in section.splitlines() if x.startswith("- ")]


def test_suite_in_a_merged_listing_is_a_hit(sb):
    red_night(sb)
    sb.set(prs={"7": [listed("a/a_test.py")], "8": ["selector: not checked: x", listed("b/b.test.sh")]})
    assert sb.run("red").returncode == 1
    (ticket,) = sb.tickets()
    assert verdict_lines(ticket["body"]) == ["- `b/b.test.sh`: hit, selected by #8"]
    assert sb.misses() == []


def test_suite_in_no_merged_listing_is_a_miss_and_counted(sb):
    red_night(sb)
    sb.set(prs={"7": [listed("a/a_test.py")], "8": [listed("c/c_test.py", "a/a_test.py")]})
    out = sb.run("red")
    assert out.returncode == 1, out.stderr
    (ticket,) = sb.tickets()
    assert verdict_lines(ticket["body"]) == ["- `b/b.test.sh`: miss, selected by none of #7, #8"]
    assert sb.misses() == ["b/b.test.sh"]
    assert "1 selector miss on record" in sb.notes()[0]


def test_repeat_red_night_counts_its_miss_once(sb):
    red_night(sb)
    sb.set(prs={"7": [listed("a/a_test.py")], "8": [listed("a/a_test.py")]})
    assert sb.run("red").returncode == 1
    assert sb.run("red").returncode == 1
    assert sb.misses() == ["b/b.test.sh"]


@pytest.mark.parametrize("prs, why", [
    ({"7": [listed("a/a_test.py")]}, "#8 has no `selector:` listing"),
    ({"7": [listed("a/a_test.py")], "8": ["selector: clean"]}, "#8 has no `selector:` listing"),
    ({"7": [listed("a/a_test.py")], "8": [listed("b/b.test.sh"), "selector: not checked: gone"]},
     "#8 has no `selector:` listing"),
])
def test_a_merge_with_no_readable_listing_makes_an_absent_suite_unknown(sb, prs, why):
    red_night(sb)
    sb.set(prs=prs)
    assert sb.run("red").returncode == 1
    (ticket,) = sb.tickets()
    (line,) = verdict_lines(ticket["body"])
    assert line.startswith("- `b/b.test.sh`: unknown") and why in line, line
    assert sb.misses() == []


def test_unreadable_pr_comments_make_the_suite_unknown(sb):
    red_night(sb)
    sb.set(prs={"7": [listed("a/a_test.py")]}, pr_errors=["8"])
    assert sb.run("red").returncode == 1
    (line,) = verdict_lines(sb.tickets()[0]["body"])
    assert line.startswith("- `b/b.test.sh`: unknown") and "#8" in line, line


def test_no_green_on_record_makes_every_suite_unknown(sb):
    sb.commit("feature (#7)", {"f": "x\n"})
    sb.set(prs={"7": [listed("a/a_test.py")]})
    assert sb.run("red").returncode == 1
    (line,) = verdict_lines(sb.tickets()[0]["body"])
    assert line.startswith("- `b/b.test.sh`: unknown") and "no green run on record" in line, line


def test_silent_seam_after_npm_ci_output_is_inconclusive(sb):
    """`npm ci` writes to the same log before the seam runs; its output is not
    the seam's, so a seam that exits 0 and prints nothing stays inconclusive."""
    assert sb.run("green").returncode == 0
    green = sb.last_green()
    write(os.path.join(sb.bin, "npm"), "#!/bin/sh\necho 'added 3 packages in 1s'\n", 0o755)
    sb.commit("lock (#9)", {"package-lock.json": "{}\n"})
    assert_inconclusive(sb, sb.run("silent"), green, "printed nothing")


def test_repo_owned_by_someone_else_is_refused_before_anything_runs(sb):
    sb.set(login="someone-else")
    out = sb.run("red")
    assert out.returncode == 2, out.stderr
    assert sb.tickets() == [] and sb.last_green() is None
    assert not os.path.exists(sb.jobs_log), "no seam runs on a repo the caller does not own"
    (note,) = sb.notes()
    assert "inconclusive" in note and "is not owned by someone-else" in note, note
    assert "seam could not start" not in note, note


def test_missing_origin_head_is_reported_as_itself(sb):
    sb.git(sb.repo, "remote", "set-head", "origin", "-d")
    out = sb.run("green")
    assert out.returncode == 2, out.stderr
    (note,) = sb.notes()
    assert "origin/HEAD" in note and "seam could not start" not in note, note


def test_an_unexpected_crash_is_an_inconclusive_night_not_a_red_one(sb):
    """A malformed `gh issue list` row (no `number`) raises in the red path."""
    red_night(sb)
    green = sb.last_green()
    sb.set(raw={"issue list": json.dumps([{"body": '<!-- backstop suites: ["b/b.test.sh"] -->'}])})
    out = sb.run("red")
    assert out.returncode == 2, out.stderr
    assert sb.last_green() == green and sb.tickets() == []
    (note,) = sb.notes()
    assert "inconclusive" in note and "KeyError" in note, note


def test_a_backstop_that_cannot_import_its_neighbours_is_inconclusive(sb):
    """A copy of backstop.py with no drain/ beside it: the import fails."""
    lone = os.path.join(sb.tmp, "lone", "backstop", "backstop.py")
    write(lone, read(BACKSTOP))
    out = sb.run("green", script=lone)
    assert out.returncode == 2, out.stderr
    assert sb.last_green() is None and not os.path.exists(sb.jobs_log)
    (note,) = sb.notes()
    assert "inconclusive" in note and "could not import" in note, note


def test_direct_commits_do_not_make_a_suite_unknown_and_are_listed(sb):
    """A commit naming no PR is the non-code lane (Gate 2): it ran no
    narrowed command and owes no listing."""
    green, merges = red_night(sb)
    direct = sb.commit("friction: a note", {"n.md": "x\n"})
    sb.set(prs={"7": [listed("a/a_test.py")], "8": [listed("a/a_test.py")]})
    assert sb.run("red").returncode == 1
    (ticket,) = sb.tickets()
    assert verdict_lines(ticket["body"]) == ["- `b/b.test.sh`: miss, selected by none of #7, #8"]
    direct_section = ticket["body"].split("## Direct commits", 1)[1].split("##", 1)[0]
    assert direct in direct_section and "friction: a note" in direct_section
    assert merges[0] not in direct_section
    assert sb.misses() == ["b/b.test.sh"]


def test_only_direct_commits_since_green_make_the_suite_unknown(sb):
    assert sb.run("green").returncode == 0
    sb.commit("friction: a note", {"n.md": "x\n"})
    assert sb.run("red").returncode == 1
    (line,) = verdict_lines(sb.tickets()[0]["body"])
    assert line.startswith("- `b/b.test.sh`: unknown") and "no PR merge" in line, line
    assert sb.misses() == []


# A repo with CI: the caller names its full-gate workflow with `--workflow`.
WORKFLOW = "on:\n  pull_request:\n  schedule:\n    - cron: '17 3 * * *'\njobs: {}\n"
GATE = ("--workflow", "ci.yml")


def gh_log(*lines):
    """`gh run view --log-failed` output: job, step and timestamp before each line."""
    return "\n".join(f"check\tGate (check)\t2026-10-16T03:20:0{i}.1234567Z {x}" for i, x in enumerate(lines))


def ci_run(sb, sha, conclusion, run_id=None, age_hours=2, status="completed", branch="main", workflow="ci.yml"):
    import datetime
    created = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=age_hours)
    runs = sb.gh_state().get("runs", [])
    runs.append(dict(databaseId=run_id or len(runs) + 100, status=status, conclusion=conclusion, headSha=sha,
                     headBranch=branch, workflow=workflow, createdAt=created.strftime("%Y-%m-%dT%H:%M:%SZ"),
                     url=f"https://github.com/me/repo/actions/runs/{run_id or len(runs) + 100}"))
    sb.set(runs=runs)
    return runs[-1]["databaseId"]


@pytest.fixture
def ci(sb):
    """A sandbox whose repo has CI; the sha the workflow landed at."""
    sb.ci_sha = sb.commit("add CI (#5)", {".github/workflows/ci.yml": WORKFLOW})
    return sb


def test_ci_repo_green_comes_from_its_scheduled_run_and_no_seam_runs(ci):
    ci_run(ci, ci.ci_sha, "success")
    later = ci.commit("feature (#7)", {"f": "x\n"})
    out = ci.run("red", flags=GATE)  # the local seam would go red; it must not run
    assert out.returncode == 0, out.stderr
    assert ci.last_green() == ci.ci_sha, "the record is the sha the scheduled run read, not the tip"
    assert later != ci.ci_sha
    assert not os.path.exists(ci.jobs_log), "no local seam runs for a CI repo"


def test_a_scheduled_workflow_without_the_flag_runs_the_seam_locally(ci):
    ci_run(ci, ci.ci_sha, "success")
    out = ci.run("green")
    assert out.returncode == 0, out.stderr
    assert read(ci.jobs_log).split() == ["jobs=3"], "no named workflow: the seam runs here"


def test_an_unrelated_scheduled_success_cannot_certify_the_gate(ci):
    run_id = ci_run(ci, ci.ci_sha, "failure")
    ci.set(logs={str(run_id): gh_log("FAIL b/b.test.sh")})
    ci_run(ci, ci.ci_sha, "success", workflow="stale.yml")
    out = ci.run("green", flags=GATE)
    assert out.returncode == 1, out.stderr
    assert ci.last_green() is None


def test_ci_repo_red_names_the_runs_failed_suites_with_verdicts(ci):
    ci_run(ci, ci.ci_sha, "success")
    assert ci.run("green", flags=GATE).returncode == 0
    m7 = ci.commit("feature (#7)", {"f": "x\n"})
    ci.commit("fix (#8)", {"g": "y\n"})
    run_id = ci_run(ci, m7, "failure")
    ci.set(logs={str(run_id): gh_log("PASS a/a_test.py", "FAIL b/b.test.sh", "  FAIL nested/child",
                                     "FAIL c/c_test.py")},
           prs={"7": [listed("c/c_test.py")]})
    out = ci.run("green", flags=GATE)
    assert out.returncode == 1, out.stderr
    assert ci.last_green() == ci.ci_sha
    (ticket,) = ci.tickets()
    assert verdict_lines(ticket["body"]) == ["- `b/b.test.sh`: miss, selected by none of #7",
                                             "- `c/c_test.py`: hit, selected by #7"]
    assert "fix (#8)" not in ticket["body"], "the merges are those up to the run's sha, not the tip"
    assert f"actions/runs/{run_id}" in ticket["body"]
    assert not os.path.exists(ci.jobs_log)
    assert ci.misses() == ["b/b.test.sh"]


def test_a_red_run_already_reported_is_not_reported_again(ci):
    """The ticket is closed and no newer run exists: the same red run read on
    a later night files nothing and counts no second miss."""
    ci_run(ci, ci.ci_sha, "success")
    assert ci.run("green", flags=GATE).returncode == 0
    m7 = ci.commit("feature (#7)", {"f": "x\n"})
    run_id = ci_run(ci, m7, "failure")
    ci.set(logs={str(run_id): gh_log("FAIL b/b.test.sh")}, prs={"7": [listed("a/a_test.py")]})
    assert ci.run("green", flags=GATE).returncode == 1
    state = ci.gh_state()
    state["issues"][0]["state"] = "closed"
    ci.save(state)
    out = ci.run("green", flags=GATE)
    assert out.returncode == 2, out.stderr
    assert len(ci.tickets()) == 1 and ci.misses() == ["b/b.test.sh"]
    assert "already reported" in ci.notes()[-1], ci.notes()


@pytest.mark.parametrize("setup, why", [
    (lambda sb: None, "no scheduled run"),
    (lambda sb: ci_run(sb, sb.ci_sha, "success", branch="other"), "no scheduled run"),
    (lambda sb: ci_run(sb, sb.ci_sha, None, status="in_progress"), "is `in_progress`"),
    (lambda sb: (ci_run(sb, sb.ci_sha, "success", age_hours=25), ci_run(sb, sb.ci_sha, None, status="queued")),
     "is `queued`"),
    (lambda sb: ci_run(sb, sb.ci_sha, "success", age_hours=30), "is from"),
    (lambda sb: ci_run(sb, sb.ci_sha, "cancelled"), "concluded `cancelled`"),
    (lambda sb: ci_run(sb, sb.ci_sha, "failure"), "its failed log could not be read"),
    (lambda sb: sb.set(logs={str(ci_run(sb, sb.ci_sha, "failure")): gh_log("Segmentation fault")}),
     "names no `FAIL <suite>` line"),
    (lambda sb: ci_run(sb, "0" * 40, "success"), "is not on"),
])
def test_ci_repo_missing_or_unreadable_scheduled_run_is_inconclusive(ci, setup, why):
    setup(ci)
    out = ci.run("green", flags=GATE)
    assert out.returncode == 2, out.stderr
    assert ci.last_green() is None, "an inconclusive night is never recorded green"
    assert ci.tickets() == [] and not os.path.exists(ci.jobs_log)
    (note,) = ci.notes()
    assert "inconclusive" in note and why in note, note


def test_ci_run_list_that_fails_is_inconclusive(ci):
    ci_run(ci, ci.ci_sha, "success")
    out = ci.run("green", flags=GATE, extra={"FAIL_RUN_LIST": "1"})
    assert out.returncode == 2 and ci.last_green() is None
    (note,) = ci.notes()
    assert "inconclusive" in note and "run list" in note, note
