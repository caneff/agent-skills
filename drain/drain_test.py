"""Tests for `drain` (#1403, #1415). Seam: the command line, `drain.py [--once]
[--max n] [--bundle-max k] [--anchor n] [--repo path]`, run as a subprocess
against a real git repo with a bare origin, a fake `gh` (a JSON state file), a
stub `claude` that answers the bundle chooser, a stub `implement-dispatch` that
claims the bundle and builds as the worker would (commit, push, PR), a stub
`herdr` that reports the worker's status, and a stub `merge-cleanup`. Each case
is a queue in, labels / merges / summary out. `HOME` and the global git config
are the test's own, so no case reads the real ones. A last group tests the wait
on a worker in-process, since a three-hour clock has no command-line witness,
and one `excerpt` case, since the fake `gh` cannot offer a natively unblocked empty ticket.
"""
import json
import os
import select
import subprocess
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
DRAIN = os.path.join(HERE, "drain.py")
sys.path.insert(0, HERE)

FAKE_GH = r'''#!/usr/bin/env python3
import json, os, re, sys
path = os.environ["FAKE_STATE"]
state = json.load(open(path))
args = sys.argv[1:]
def save():
    json.dump(state, open(path, "w"))
def out(value):
    print(json.dumps(value))
def opt(name):
    return args[args.index(name) + 1] if name in args else None
def names(issue):
    return [dict(name=x) for x in issue["labels"]]
if args[:2] == ["issue", os.environ.get("FAIL_VERB")] or (
        args[:2] == ["issue", "view"] and args[2] in os.environ.get("FAIL_VIEW", "").split()):
    sys.stderr.write("fake gh: injected failure\n"); sys.exit(1)
if args[:2] == ["api", "user"]:
    print(state["login"])
elif args[0] == "api":
    url = args[-1]
    m = re.search(r"/issues/(\d+)(/parent)?$", url)
    if "--paginate" in args:
        label = re.search(r"labels=([^&]+)", url).group(1)
        issues = [dict(number=int(n), title=i["title"], body=i["body"], state="open", labels=names(i),
                       assignees=[dict(login=a) for a in i.get("assignees", [])])
                  for n, i in state["issues"].items()
                  if (i["state"] == "open" or n in os.environ.get("STALE_LISTING", "").split())
                  and (label in i["labels"] or (label == "in-progress" and n in os.environ.get("STALE_LABELS", "").split()))]
        for t in os.environ.get("TAKE_AFTER_PICK", "").split() if label == "ready-for-agent" else []:
            if "ready-for-agent" in state["issues"][t]["labels"]:
                state["issues"][t]["labels"].remove("ready-for-agent")
                state["issues"][t]["labels"].append("in-progress")
                save()
        out([issues])
    elif m and m.group(2):
        parent = state["issues"][m.group(1)].get("parent")
        if parent is None:
            sys.stderr.write("gh: Not Found (HTTP 404)\n"); sys.exit(1)
        out(dict(number=parent, repository_url="https://api.github.com/repos/" + re.search(r"repos/([^/]+/[^/]+)/issues", url).group(1), state=state["issues"][str(parent)]["state"], labels=names(state["issues"][str(parent)])))
    elif m:
        out({"state": state["issues"][m.group(1)]["state"]})
elif args[:2] == ["issue", "edit"]:
    issue = state["issues"][args[2]]
    for i, a in enumerate(args):
        v = args[i + 1] if i + 1 < len(args) else None
        if a == "--add-label" and v not in issue["labels"]:
            issue["labels"].append(v)
        if a == "--remove-label" and v in issue["labels"]:
            issue["labels"].remove(v)
        if a == "--add-assignee":
            issue.setdefault("assignees", []).append("me")
        if a == "--remove-assignee" and "me" in issue.get("assignees", []):
            issue["assignees"].remove("me")
    save()
elif args[:2] == ["issue", "comment"]:
    state.setdefault("comments", []).append([args[2], opt("--body")])
    save()
elif args[:2] == ["issue", "view"]:
    issue = state["issues"][args[2]]
    if args[2] in os.environ.get("STALE_VIEW", "").split() and opt("--json") == "state,labels,comments":
        # resumable()'s reread, the one read GitHub has not caught up on
        issue = dict(issue, state="open", labels=issue["labels"] + ["in-progress"])
    out({"state": issue["state"], "labels": names(issue), "title": issue["title"], "body": issue["body"],
         "comments": [dict(body=b) for n, b in state.get("comments", []) if n == args[2]]})
elif args[:2] == ["pr", "list"]:
    pr = state["prs"].get(opt("--head"))
    out([dict(number=pr["number"], url=pr["url"])] if pr and not pr.get("merged") else [])
elif args[:2] == ["pr", "view"]:
    pr = next(p for b, p in state["prs"].items() if args[2] in (b, str(p["number"])))
    out({"isDraft": pr["draft"], "mergeStateStatus": pr["status"],
         "headRefOid": pr["head"], "url": pr["url"], "number": pr["number"],
         "closingIssuesReferences": [dict(number=n) for n in pr["closes"]],
         "mergeCommit": {"oid": "m" + pr["head"]}})
elif args[:2] == ["pr", "merge"]:
    branch = next(b for b, p in state["prs"].items() if str(p["number"]) == args[2])
    pr = state["prs"][branch]
    assert opt("--match-head-commit") == pr["head"], "head moved"
    pr["merged"] = True
    for n in pr["closes"]:
        state["issues"][str(n)]["state"] = "closed"
    state.setdefault("merged", []).append([pr["closes"], pr["head"]])
    save()
else:
    sys.stderr.write("fake gh: unhandled %r\n" % args); sys.exit(2)
'''

# The bundle chooser: one `claude -p` turn. Answers `drain bundle:` with the
# anchor and the tickets in TAKE. Knobs: CHOOSER_FAIL (exit 1), CHOOSER_SAY (the
# whole answer, verbatim), CHOOSER_SLEEP.
STUB_CLAUDE = r"""#!/usr/bin/env python3
import json, os, re, sys, time
prompt = sys.argv[sys.argv.index("-p") + 1]
env = os.environ
anchor = re.search(r"#(\d+) is the anchor", prompt).group(1)
with open(env["CHOOSER_LOG"], "a") as f:
    f.write(json.dumps({"n": anchor, "prompt": prompt, "argv": sys.argv[1:]}) + "\n")
if env.get("CHOOSER_SLEEP"):
    time.sleep(30)
if env.get("CHOOSER_FAIL"):
    sys.exit(1)
print(env.get("CHOOSER_SAY") or "thinking...\ndrain bundle: " + " ".join([anchor] + env.get("TAKE", "").split()))
"""

# Acts as `implement-dispatch` and then as the worker it starts: claims every
# ticket named, makes the worktree and branch (refusing, like the real one, when
# either exists), then builds and opens the PR. Knobs: FAIL_TICKETS (the lead
# ticket gets a worker that never opens a PR), LIGHT (it lands directly: tickets
# closed, no PR), DISPATCH_REFUSE, DRAFT_TICKETS, STATUS (merge state),
# NO_ANCHOR / UNCLOSED (what the PR's closing keywords leave out), EXTRA_CLOSE
# (tickets the PR closes that were never in the bundle), RESET_TO_OLD (build on
# the commit before main's tip), SPEC_SLICES (what a `--spec` dispatch's run
# claims and its PR closes beside the spec).
STUB_DISPATCH = r"""#!/usr/bin/env python3
import json, os, subprocess, sys
env, argv = os.environ, sys.argv[1:]
repo = argv[argv.index("--repo") + 1]
spec = "--spec" in argv
if spec:  # a spec run: the spec itself, then the slices (SPEC_SLICES) its run claims
    n = argv[argv.index("--spec") + 1]
    tickets = [n] + env.get("SPEC_SLICES", "").split()
else:
    tickets = [a for a in argv if a.isdigit()]
    n = str(min(int(t) for t in tickets))
with open(env["DISPATCH_LOG"], "a") as f:
    f.write(json.dumps({"n": n, "tickets": tickets, "argv": argv}) + "\n")
if env.get("DISPATCH_REFUSE"):
    sys.stderr.write("implement-dispatch: no herdr server is running (herdr status)\n"); sys.exit(1)
branch = ("spec-" if spec else "implement-") + n
wt = os.path.join(repo, ".claude", "worktrees", branch)
if os.path.exists(wt):
    sys.stderr.write("implement-dispatch: %s already exists\n" % wt); sys.exit(1)
st = json.load(open(env["FAKE_STATE"]))
for t in tickets + env.get("EXTRA_CLOSE", "").split():
    issue = st["issues"][t]
    if "ready-for-agent" in issue["labels"]:
        issue["labels"].remove("ready-for-agent")
    if "in-progress" not in issue["labels"]:
        issue["labels"].append("in-progress")
    issue.setdefault("assignees", []).append("me")
if env.get("LIGHT"):
    for t in tickets:
        st["issues"][t]["state"] = "closed"
if env.get("NOTE_EXTRA"):
    st.setdefault("comments", []).append([n, env["NOTE_EXTRA"]])
json.dump(st, open(env["FAKE_STATE"], "w"))
subprocess.run(["git", "worktree", "add", "-q", "--no-track", "-b", branch, wt, "origin/main"], cwd=repo, check=True)
if env.get("DISPATCH_FAIL_AFTER_CLAIM"):
    sys.stderr.write("herdr agent start failed after the workspace exists\n"); sys.exit(1)
if env.get("LIGHT") or n in env.get("FAIL_TICKETS", "").split():
    sys.exit(0)
os.chdir(wt)
if env.get("RESET_TO_OLD"):
    subprocess.run(["git", "reset", "-q", "--hard", "HEAD~1"], check=True)
open("work-%s.txt" % n, "w").write("built\n")
subprocess.run(["git", "add", "."], check=True)
subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "build %s" % n], check=True)
subprocess.run(["git", "push", "-q", "-f", "origin", "HEAD:" + branch], check=True)
head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
closes = ([] if env.get("NO_ANCHOR") else [int(n)]) + [int(t) for t in tickets if t != n and not env.get("UNCLOSED")]
closes += [int(t) for t in env.get("EXTRA_CLOSE", "").split()]
st = json.load(open(env["FAKE_STATE"]))
st["prs"][branch] = {"number": 100 + int(n), "url": "https://example.test/pull/%d" % (100 + int(n)),
                     "head": head, "closes": closes, "draft": n in env.get("DRAFT_TICKETS", "").split(),
                     "status": env.get("STATUS", "CLEAN")}
json.dump(st, open(env["FAKE_STATE"], "w"))
"""

# Stands in for herdr. `agent get` answers for the worker: HERDR_STATUS (default
# idle), HERDR_WORKING_POLLS (that many `working` answers first), HERDR_GONE
# (agent_not_found), HERDR_DOWN (any other failure), HERDR_FLAKY (that many
# failures first), HERDR_HOLD_FILE (`working` for as long as that file exists).
# Every call is logged.
STUB_HERDR = r"""#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
env = os.environ
with open(env["HERDR_LOG"], "a") as f:
    f.write(json.dumps(args) + "\n")
if args[:2] == ["agent", "get"]:
    flaky = env["HERDR_LOG"] + ".flaky"
    failed = int(open(flaky).read()) if os.path.exists(flaky) else 0
    if env.get("HERDR_DOWN") or failed < int(env.get("HERDR_FLAKY", 0)):
        open(flaky, "w").write(str(failed + 1))
        sys.stderr.write("herdr: no server\n"); sys.exit(1)
    if env.get("HERDR_GONE"):
        sys.stderr.write(json.dumps({"error": {"code": "agent_not_found", "message": "not found"}}) + "\n"); sys.exit(1)
    counter = env["HERDR_LOG"] + ".polls"
    seen = int(open(counter).read()) if os.path.exists(counter) else 0
    open(counter, "w").write(str(seen + 1))
    held = os.path.exists(env.get("HERDR_HOLD_FILE", "/nonexistent"))
    status = "working" if held or seen < int(env.get("HERDR_WORKING_POLLS", 0)) else env.get("HERDR_STATUS", "idle")
    print(json.dumps({"result": {"agent": {"agent_status": status, "pane_id": "w9:p1"}}}))
"""

STUB_CLEANUP = """#!/bin/sh
echo "$@" >> "$CLEANUP_LOG"
[ -z "$CLEANUP_FAIL" ] || { echo "cleanup exploded" >&2; exit 1; }
"""


def write(path, text, mode=0o644):
    with open(path, "w") as f:
        f.write(text)
    os.chmod(path, mode)


def read(path):
    with open(path) as f:
        return f.read()


SPEC = {"labels": ["ready-for-agent", "spec"], "body": "the spec\n## Blocked by\n\n- None\n"}


class Sandbox:
    """A repo, a bare origin, stubs on PATH and an isolated HOME."""

    def __init__(self, tmp_path):
        self.tmp = tmp_path
        t = str(tmp_path)
        self.rewrite = None
        self.home = os.path.join(t, "home")
        os.mkdir(self.home)
        write(os.path.join(self.home, ".gitconfig"), "[user]\n\tname = t\n\temail = t@example.test\n")
        self.env = {**os.environ, "HOME": self.home, "GIT_CONFIG_GLOBAL": os.path.join(self.home, ".gitconfig"),
                    "GIT_CONFIG_NOSYSTEM": "1", "XDG_CONFIG_HOME": os.path.join(self.home, "xdg")}
        self.bin = os.path.join(t, "bin")
        os.mkdir(self.bin)
        for name, body in (("gh", FAKE_GH), ("claude", STUB_CLAUDE), ("merge-cleanup", STUB_CLEANUP),
                           ("herdr", STUB_HERDR), ("implement-dispatch", STUB_DISPATCH)):
            write(os.path.join(self.bin, name), body, 0o755)
        self.origin = os.path.join(t, "origin.git")
        self.repo = os.path.join(t, "repo")
        self.git(t, "init", "-q", "--bare", "-b", "main", self.origin)
        self.git(t, "clone", "-q", self.origin, self.repo)
        self.git(self.repo, "checkout", "-q", "-b", "main")
        write(os.path.join(self.repo, "README"), "x\n")
        self.git(self.repo, "add", ".")
        self.git(self.repo, "commit", "-qm", "init")
        write(os.path.join(self.repo, "marker"), "m\n")
        self.git(self.repo, "add", ".")
        self.git(self.repo, "commit", "-qm", "marker")
        self.git(self.repo, "push", "-q", "origin", "main")
        self.git(self.repo, "remote", "set-head", "origin", "main")
        self.git(self.repo, "config", "land.testcmd", "true")
        self.set_origin("me/repo")
        self.state_path = os.path.join(t, "state.json")
        self.dispatch_log = os.path.join(t, "claude.log")
        self.cleanup_log = os.path.join(t, "cleanup.log")
        self.herdr_log = os.path.join(t, "herdr.log")
        self.seam_log = os.path.join(t, "seam.log")
        self.chooser_log = os.path.join(t, "chooser.log")
        self.write_state({})

    def git(self, cwd, *args):
        return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                              env=self.env).stdout.strip()

    def set_origin(self, slug, serves=None):
        """origin reads as github.com/<slug> but fetches from the bare repo."""
        url = f"https://github.com/{slug}.git"
        self.git(self.repo, "remote", "set-url", "origin", url)
        if self.rewrite:
            self.git(self.repo, "config", "--unset-all", self.rewrite)
        self.rewrite = f"url.{serves or self.origin}.insteadOf"
        self.git(self.repo, "config", self.rewrite, url)

    def write_state(self, issues, prs=None, comments=None, login="me"):
        full = {str(n): {"title": f"ticket {n}", "state": "open", "body": "## Blocked by\n\n- None\n",
                         "labels": ["ready-for-agent"], **i} for n, i in issues.items()}
        self.save({"login": login, "issues": full, "prs": prs or {}, "comments": comments or []})

    def save(self, st):
        write(self.state_path, json.dumps(st))

    def state(self):
        return json.loads(read(self.state_path))

    def drain_env(self, env=None):
        return {**self.env, "PATH": self.bin + os.pathsep + os.environ["PATH"], "FAKE_STATE": self.state_path,
                "DISPATCH_LOG": self.dispatch_log, "CLEANUP_LOG": self.cleanup_log, "HERDR_LOG": self.herdr_log,
                "SEAM_LOG": self.seam_log, "CHOOSER_LOG": self.chooser_log,
                "DRAIN_POLL_SECONDS": "0.05", "DRAIN_IDLE_GRACE_SECONDS": "0.3", "DRAIN_SPEC_WALL_CLOCK_SECONDS": "20",
                "DRAIN_LOG_DIR": os.path.join(self.tmp, "logs"), **(env or {})}

    def drain(self, *argv, env=None):
        return subprocess.run([sys.executable, DRAIN, "--repo", self.repo, *argv],
                              capture_output=True, text=True, env=self.drain_env(env))

    def drain_live(self, *argv, env=None):
        """Start drain and hand back the process, its stdout a pipe to read while it runs."""
        return subprocess.Popen([sys.executable, DRAIN, "--repo", self.repo, *argv], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, env=self.drain_env(env))

    def ended_lines(self, result):
        return [x for x in result.stdout.splitlines() if x.startswith("bundle ended:")]

    def dispatch_runs(self):
        """The `implement-dispatch` calls, one per bundle started."""
        return [json.loads(line) for line in read(self.dispatch_log).splitlines()] if os.path.exists(self.dispatch_log) else []

    def chooser_runs(self):
        return [json.loads(line) for line in read(self.chooser_log).splitlines()] if os.path.exists(self.chooser_log) else []

    def herdr_calls(self):
        return [json.loads(line) for line in read(self.herdr_log).splitlines()] if os.path.exists(self.herdr_log) else []

    def worktree(self, n):
        return os.path.join(self.repo, ".claude", "worktrees", f"implement-{n}")

    def labels(self, n):
        return self.state()["issues"][str(n)]["labels"]

    def handed_comment(self, n):
        return [b for i, b in self.state()["comments"] if i == str(n) and "could not land" in b]

    def spec_state(self, slices=(2, 3), extra=None):
        """A spec parent in the `spec` bucket is a bundle in its own right (#1477): drain starts
        it with `implement-dispatch --spec` and merges the integration PR its run reports. The
        stub dispatch claims `SPEC_SLICES` as the spec run would and its PR closes them with the spec."""
        self.write_state({1: SPEC, **{n: {"parent": 1} for n in slices}, **(extra or {})})


    def seam_runs(self):
        return [x.rstrip() for x in read(self.seam_log).splitlines()] if os.path.exists(self.seam_log) else []

    def lockfile_repo(self, lock=True, where=""):
        """A main with `package-lock.json` (or not) in the `where` directory,
        and an `npm` stub on PATH whose `ci` makes `node_modules` in its cwd and
        logs the call; the seam command logs `seam` only when
        `<where>/node_modules` is there."""
        write(os.path.join(self.bin, "npm"),
              '#!/bin/sh\necho "npm $*" >> "$SEAM_LOG"\ntest "$NPM_RED" = 1 && exit 1\n'
              'test "$1" = ci && mkdir node_modules\n', 0o755)
        if lock:
            os.makedirs(os.path.join(self.repo, where), exist_ok=True)
            write(os.path.join(self.repo, where, "package-lock.json"), "{}\n")
            self.git(self.repo, "add", ".")
            self.git(self.repo, "commit", "-qm", "lockfile")
            self.git(self.repo, "push", "-q", "origin", "main")
        self.git(self.repo, "config", "land.testcmd", f'test -d {os.path.join(where, "node_modules")} && echo seam >> "$SEAM_LOG"')


@pytest.fixture
def sb(tmp_path):
    return Sandbox(tmp_path)


def test_once_builds_checks_merges_and_cleans_up(sb):
    sb.write_state({1: {}, 2: {}})
    r = sb.drain("--once")
    assert r.returncode == 0, r.stderr
    st = sb.state()
    assert [m[0] for m in st["merged"]] == [[1]]
    assert sb.labels(2) == ["ready-for-agent"]
    assert "implement-1" in read(sb.cleanup_log)
    run = sb.dispatch_runs()[0]
    assert run["argv"] == ["--repo", sb.repo, "--controller", "drain", "1"]
    assert sb.chooser_runs()[0]["argv"][2:] == ["--permission-mode", "auto"]
    assert ["agent", "get", "repo-1"] in sb.herdr_calls()
    assert "merged:\n  #1  https://example.test/pull/101  m" + st["merged"][0][1] in r.stdout


def test_the_agents_bundle_is_one_pr_and_the_rest_stay_ready(sb):
    sb.write_state({1: {}, 2: {}, 3: {}, 4: {}})
    r = sb.drain("--once", env={"TAKE": "2 3"})
    assert r.returncode == 0, r.stderr
    st = sb.state()
    assert st["merged"][0][0] == [1, 2, 3]
    assert [i["state"] for i in st["issues"].values()] == ["closed"] * 3 + ["open"]
    assert sb.labels(4) == ["ready-for-agent"]
    assert sb.dispatch_runs()[0]["argv"][-3:] == ["1", "2", "3"]
    prompt = sb.chooser_runs()[0]["prompt"]
    for line in ("#1 is the anchor", "- #2 ticket 2", "- #3 ticket 3", "- #4 ticket 4", "at most 7 of them"):
        assert line in prompt
    assert ["1", "drain bundle: 1 2 3 (of 3 candidates)"] in sb.state()["comments"][-1:]
    assert "#1 #2 #3" in r.stdout


def test_the_chooser_prompt_carries_each_candidates_body_and_comments_capped(sb):
    long_body = "needle " + "x" * 2000 + " TAILMARK\n## Blocked by\n\n- None\n"
    sb.write_state({1: {}, 2: {"body": "Fix the parser\nin   two lines\n## Blocked by\n\n- None\n"}, 3: {"body": long_body}},
                     comments=[["2", "later: also handle tabs"]])
    r = sb.drain("--once")
    assert r.returncode == 0, r.stderr
    prompt = sb.chooser_runs()[0]["prompt"]
    assert "- #2 ticket 2: Fix the parser in two lines ## Blocked by - None later: also handle tabs" in prompt
    assert "needle" in prompt
    assert "TAILMARK" not in prompt
    assert len(prompt) < 1500


def test_the_choose_log_holds_the_prompt_the_chooser_judged_from_even_when_it_fails(sb):
    sb.write_state({1: {}, 2: {"body": "distinctive-excerpt\n## Blocked by\n\n- None\n"}})
    sb.drain("--once", env={"CHOOSER_FAIL": "1"})
    log = read(os.path.join(sb.tmp, "logs", "me__repo-implement-1-choose.log"))
    assert "- #2 ticket 2: distinctive-excerpt" in log


def test_a_candidate_with_no_body_and_no_comments_is_listed_as_empty_not_blank(sb):
    # A ticket unblocked by native dependencies alone can have an empty body; the
    # fake gh's frontier needs a `Blocked by` body to offer one, so call excerpt directly.
    import importlib.util
    spec = importlib.util.spec_from_file_location("drain_under_test", DRAIN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.gh_json = lambda *a, **k: {"body": "", "comments": []}
    ctx = type("Ctx", (), {"repo": "o/r"})()
    assert mod.excerpt(ctx, 2) == "(empty body, no comments)"


def test_a_candidate_whose_body_cannot_be_read_is_listed_as_unread(sb):
    sb.write_state({1: {}, 2: {}, 3: {"body": "readable body\n## Blocked by\n\n- None\n"}})
    r = sb.drain("--once", env={"FAIL_VIEW": "2"})
    assert r.returncode == 0, r.stderr
    prompt = sb.chooser_runs()[0]["prompt"]
    assert "- #2 ticket 2: (body not read:" in prompt
    assert "- #3 ticket 3: readable body ## Blocked by - None" in prompt


def test_a_chooser_that_fails_or_says_nothing_usable_bundles_the_anchor_alone(sb):
    for env in ({"CHOOSER_FAIL": "1", "TAKE": "2"}, {"CHOOSER_SAY": "no idea", "TAKE": "2"}):
        sb.write_state({1: {}, 2: {}})
        sb.drain("--once", env=env)
        assert sb.dispatch_runs()[-1]["tickets"] == ["1"], env
        assert sb.labels(2) == ["ready-for-agent"], env
        os.remove(sb.dispatch_log)
        sb.git(sb.repo, "worktree", "remove", "--force", sb.worktree(1))
        sb.git(sb.repo, "branch", "-D", "implement-1")


def test_a_chooser_pick_that_was_not_offered_or_is_below_the_anchor_is_dropped(sb):
    sb.write_state({1: {}, 2: {}, 3: {}})
    sb.drain("--anchor", "2", "--once", env={"CHOOSER_SAY": "drain bundle: 2 1 9 3 3"})
    assert sb.dispatch_runs()[0]["tickets"] == ["2", "3"]
    assert sb.labels(1) == ["ready-for-agent"]


def test_a_chooser_past_its_wall_clock_bundles_the_anchor_alone_and_says_why(sb):
    sb.write_state({1: {}, 2: {}})
    r = sb.drain("--once", env={"CHOOSER_SLEEP": "1", "TAKE": "2", "DRAIN_CHOOSER_SECONDS": "1"})
    assert r.returncode == 0, r.stderr + r.stdout
    assert sb.dispatch_runs()[0]["tickets"] == ["1"]
    assert any("drain chooser: #1 alone: " in b and "wall clock" in b
                        for i, b in sb.state()["comments"] if i == "1"), sb.state()["comments"]


def test_a_chooser_that_fails_leaves_a_comment_saying_so(sb):
    sb.write_state({1: {}, 2: {}})
    sb.drain("--once", env={"CHOOSER_FAIL": "1", "TAKE": "2"})
    notes = [b for i, b in sb.state()["comments"] if i == "1" and b.startswith("drain chooser:")]
    assert len(notes) == 1
    assert "the chooser exited 1" in notes[0]
    assert [b for i, b in sb.state()["comments"] if b.startswith("drain bundle:")] == ["drain bundle: 1 (of 1 candidates)"], "the chooser note's digits must never read as bundle members"


def test_the_choosers_bundle_is_cut_to_bundle_max(sb):
    sb.write_state({1: {}, 2: {}, 3: {}})
    sb.drain("--once", "--bundle-max", "2", env={"TAKE": "2 3"})
    assert sb.dispatch_runs()[0]["tickets"] == ["1", "2"]
    assert "at most 1 of them" in sb.chooser_runs()[0]["prompt"]
    assert sb.labels(3) == ["ready-for-agent"]


def test_a_pr_over_bundle_max_is_a_failed_build(sb):
    # The bundle comments name three tickets, one more than the cap, and the PR closes all three.
    sb.write_state({1: {}, 2: {}, 3: {}})
    sb.drain("--once", "--bundle-max", "2", env={"TAKE": "2", "EXTRA_CLOSE": "3", "NOTE_EXTRA": "drain bundle: 1 3"})
    assert "merged" not in sb.state()
    assert "over --bundle-max 2" in sb.handed_comment(1)[0]


def test_a_pr_closing_a_ticket_no_bundle_comment_names_is_a_failed_build_even_under_the_cap(sb):
    sb.write_state({1: {}, 2: {}, 3: {}})
    sb.drain("--once", "--bundle-max", "5", env={"TAKE": "2", "EXTRA_CLOSE": "3"})
    assert "which no drain bundle: comment on #1 names" in sb.handed_comment(1)[0]


def test_a_ticket_the_agent_claimed_but_the_pr_did_not_close_goes_back_to_ready(sb):
    sb.write_state({1: {}, 2: {}})
    r = sb.drain("--once", env={"TAKE": "2", "UNCLOSED": "1"})
    st = sb.state()
    assert st["merged"][0][0] == [1]
    assert sb.labels(2) == ["ready-for-agent"]
    assert st["issues"]["2"]["assignees"] == []
    assert "stopped" not in r.stdout


def test_a_pr_that_does_not_close_the_anchor_is_a_failed_build(sb):
    sb.write_state({1: {}, 2: {}})
    sb.drain("--once", env={"TAKE": "2", "NO_ANCHOR": "1"})
    assert "merged" not in sb.state()
    assert "does not close the anchor #1" in sb.handed_comment(1)[0]


def test_a_failed_bundle_hands_every_claimed_ticket_to_chris_in_one_line(sb):
    sb.write_state({1: {}, 2: {}, 3: {}})
    r = sb.drain("--once", env={"TAKE": "2", "DRAFT_TICKETS": "1"})
    st = sb.state()
    for n in (1, 2):
        assert "ready-for-human" in sb.labels(n)
        assert "in-progress" not in sb.labels(n)
        assert st["issues"][str(n)]["assignees"] == []
        assert "still a draft" in sb.handed_comment(n)[0]
        assert "\n" not in sb.handed_comment(n)[0]
    assert sb.labels(3) == ["ready-for-agent"]
    assert "handed to Chris:\n  #1 #2  " in r.stdout


def test_a_ticket_failing_twice_is_handed_over_and_the_loop_moves_on(sb):
    sb.write_state({1: {}, 2: {}})
    r = sb.drain("--max", "2", env={"FAIL_TICKETS": "1"})
    assert r.returncode == 0, r.stderr
    assert "ready-for-human" in sb.labels(1)
    assert [m[0] for m in sb.state()["merged"]] == [[2]]
    assert [c["n"] for c in sb.dispatch_runs()] == ["1", "2"]
    assert any(c[:3] == ["agent", "prompt", "repo-1"] for c in sb.herdr_calls())


def test_a_pr_that_is_not_clean_is_a_failed_build(sb):
    sb.write_state({1: {}})
    sb.drain("--once", env={"STATUS": "BLOCKED"})
    assert "merged" not in sb.state()
    assert "BLOCKED, not CLEAN" in sb.handed_comment(1)[0]


def test_a_red_seam_is_a_failed_build(sb):
    sb.write_state({1: {}})
    sb.git(sb.repo, "config", "land.testcmd", "false")
    sb.drain("--once", env={"RESET_TO_OLD": "1"})  # main moved past the PR's base, so the seam runs
    assert "merged" not in sb.state()
    assert "seam `false` failed" in sb.handed_comment(1)[0]


def test_the_seam_runs_on_the_pr_merged_into_current_main(sb):
    # The PR is built on the commit before main's tip: `marker` comes from
    # main, `work-1.txt` from the PR, so only the merge holds both.
    sb.write_state({1: {}})
    sb.git(sb.repo, "config", "land.testcmd", "test -e marker && test -e work-1.txt")
    sb.drain("--once", env={"RESET_TO_OLD": "1"})
    assert [m[0] for m in sb.state().get("merged", [])] == [[1]]


def test_blocked_and_claimed_and_human_tickets_are_skipped(sb):
    sb.write_state({1: {"body": "## Blocked by\n\n- #2\n"}, 2: {"labels": ["in-progress"]},
                      3: {"labels": ["ready-for-agent", "ready-for-human"]}, 4: {}})
    sb.drain("--max", "5")
    assert [c["n"] for c in sb.dispatch_runs()] == ["4"]


def test_a_ticket_taken_since_the_pick_is_not_claimed_over(sb):
    sb.write_state({1: {}, 2: {}})
    sb.drain("--once", env={"TAKE_AFTER_PICK": "1"})
    assert [c["n"] for c in sb.dispatch_runs()] == ["2"]
    assert "in-progress" in sb.labels(1)


def test_a_merge_cleanup_failure_is_a_note_not_a_rebuild(sb):
    sb.write_state({1: {}})
    r = sb.drain("--once", env={"CLEANUP_FAIL": "1"})
    assert r.returncode == 0, r.stderr
    assert len(sb.dispatch_runs()) == 1
    assert "merge-cleanup failed: cleanup exploded" in r.stdout
    assert [m[0] for m in sb.state()["merged"]] == [[1]]


def test_a_punctuated_chooser_answer_still_bundles_every_ticket(sb):
    sb.write_state({1: {}, 2: {}, 3: {}})
    sb.drain("--once", env={"CHOOSER_SAY": "drain bundle: 1, 2,\nand 3.\ndrain bundle: 1, 2, 3.",
                              "DRAFT_TICKETS": "1"})
    for n in (1, 2, 3):
        assert "ready-for-human" in sb.labels(n)


def test_a_single_ticket_bundle_records_the_candidates_the_chooser_saw(sb):
    sb.write_state({1: {}, 2: {}, 3: {}, 4: {}})
    sb.drain("--once", env={"TAKE": ""})
    assert ["1", "drain bundle: 1 (of 3 candidates)"] in sb.state()["comments"]


def test_a_chooser_that_echoes_the_count_does_not_pick_it_as_a_ticket(sb):
    sb.write_state({1: {}, 2: {}, 3: {}, 4: {}})
    sb.drain("--once", env={"CHOOSER_SAY": "drain bundle: 1 (of 3 candidates)"})
    assert sb.dispatch_runs()[0]["tickets"] == ["1"]


def test_a_bundle_with_no_candidates_says_zero(sb):
    sb.write_state({1: {}})
    sb.drain("--once")
    assert ["1", "drain bundle: 1 (of 0 candidates)"] in sb.state()["comments"]


def test_a_candidate_count_is_never_read_as_a_ticket(sb):
    # The count 3 equals ticket 3, another worker's live ticket: a failed
    # build of 1 must not hand it to Chris as part of 1's bundle.
    sb.write_state({1: {}, 2: {}, 3: {"labels": ["in-progress"]}, 4: {}, 5: {}})
    sb.drain("--once", env={"FAIL_TICKETS": "1", "TAKE": ""})
    assert ["1", "drain bundle: 1 (of 3 candidates)"] in sb.state()["comments"]
    assert sb.labels(3) == ["in-progress"]
    assert sb.handed_comment(3) == []


def test_a_bundle_comment_left_by_an_earlier_run_touches_nothing(sb):
    # Ticket 5 is another worker's live ticket; the old note naming it
    # predates this run's claim of ticket 1, so a failed bundle leaves it be.
    sb.write_state({1: {}, 5: {"labels": ["in-progress"]}}, comments=[["1", "drain bundle: 5"]])
    sb.drain("--once", env={"FAIL_TICKETS": "1"})
    assert "ready-for-human" in sb.labels(1)
    assert sb.labels(5) == ["in-progress"]
    assert sb.handed_comment(5) == []


def test_two_bundles_in_a_row_handed_over_stop_the_loop(sb):
    sb.write_state({1: {}, 2: {}, 3: {}, 4: {}})
    r = sb.drain(env={"FAIL_TICKETS": "1 2 3 4"})
    assert r.returncode == 1
    assert "stopped: 2 bundles in a row" in r.stdout
    assert sb.labels(3) == ["ready-for-agent"]
    assert sb.labels(4) == ["ready-for-agent"]


def test_a_dispatch_refusal_stops_the_run_and_leaves_the_ticket_ready(sb):
    sb.write_state({1: {}, 2: {}})
    r = sb.drain(env={"DISPATCH_REFUSE": "1"})
    assert r.returncode == 1
    assert "stopped: implement-dispatch refused: implement-dispatch: no herdr server is running" in r.stdout
    assert sb.labels(1) == ["ready-for-agent"]
    assert len(sb.dispatch_runs()) == 1, "a refusal is the environment's: no second ticket is tried"


def test_the_bundle_is_announced_while_its_worker_is_still_building(sb):
    sb.write_state({1: {"title": "first"}, 2: {"title": "second"}})
    hold = os.path.join(sb.tmp, "hold")
    write(hold, "")
    proc = sb.drain_live("--once", env={"TAKE": "2", "HERDR_HOLD_FILE": hold})
    try:
        ready, _, _ = select.select([proc.stdout], [], [], 20)
        assert ready, "no line from drain while its worker was still working"
        line = proc.stdout.readline()
        assert "merged" not in sb.state(), "the bundle merged while its worker was held working"
    finally:
        os.remove(hold)
        out, _ = proc.communicate(timeout=60)
    for part in ("#1 first", "#2 second", "repo-1"):
        assert part in line
    assert proc.returncode == 0


def test_a_merged_bundle_gets_an_end_line_with_its_pr_and_sha(sb):
    sb.write_state({1: {}})
    r = sb.drain("--once")
    sha = sb.state()["merged"][0][1]
    ended = sb.ended_lines(r)
    assert len(ended) == 1, r.stdout
    for part in ("#1", "merged", "https://example.test/pull/101", "m" + sha):
        assert part in ended[0]


def test_a_bundle_handed_to_chris_gets_an_end_line_with_the_reason(sb):
    sb.write_state({1: {}})
    r = sb.drain("--once", env={"DRAFT_TICKETS": "1"})
    ended = sb.ended_lines(r)
    assert len(ended) == 1, r.stdout
    assert "handed to Chris" in ended[0]
    assert "draft" in ended[0]


def test_a_bundle_cut_short_by_a_stop_gets_a_stopped_end_line(sb):
    sb.write_state({1: {}})
    r = sb.drain("--once", env={"HERDR_FLAKY": "99"})
    assert r.returncode == 1
    ended = sb.ended_lines(r)
    assert len(ended) == 1, r.stdout
    assert "stopped" in ended[0]


def test_a_bundle_whose_dispatch_failed_after_the_claim_is_still_announced_before_it_ends(sb):
    sb.write_state({1: {"title": "first"}, 2: {"title": "second"}})
    r = sb.drain("--once", env={"TAKE": "2", "DISPATCH_FAIL_AFTER_CLAIM": "1"})
    lines = [x for x in r.stdout.splitlines() if x.startswith("bundle ")]
    assert [x.split(":")[0] for x in lines] == ["bundle started", "bundle ended"], r.stdout
    assert "#1 first" in lines[0]
    assert "#2 second" in lines[0]


def test_a_refused_dispatch_announces_no_bundle(sb):
    sb.write_state({1: {}})
    r = sb.drain(env={"DISPATCH_REFUSE": "1"})
    assert "bundle started:" not in r.stdout
    assert "bundle ended:" not in r.stdout


def test_a_worker_still_working_is_waited_for_until_it_goes_idle(sb):
    sb.write_state({1: {}})
    r = sb.drain("--once", env={"HERDR_WORKING_POLLS": "4"})
    assert r.returncode == 0, r.stderr
    assert [m[0] for m in sb.state()["merged"]] == [[1]]
    gets = [c for c in sb.herdr_calls() if c[:2] == ["agent", "get"]]
    assert len(gets) >= 5


def test_an_idle_worker_with_no_pr_is_a_failed_build_not_a_wait_forever(sb):
    sb.write_state({1: {}})
    sb.drain("--once", env={"FAIL_TICKETS": "1"})
    assert "is idle with no PR" in sb.handed_comment(1)[0]


def test_a_worker_that_is_gone_with_no_pr_is_a_failed_build(sb):
    sb.write_state({1: {}})
    sb.drain("--once", env={"FAIL_TICKETS": "1", "HERDR_GONE": "1"})
    assert "the worker repo-1 is gone" in sb.handed_comment(1)[0]
    assert not any(c[:2] == ["agent", "prompt"] for c in sb.herdr_calls()), "nothing to prompt"


def test_a_herdr_that_cannot_be_asked_stops_the_run(sb):
    sb.write_state({1: {}})
    r = sb.drain("--once", env={"HERDR_DOWN": "1"})
    assert r.returncode == 1
    assert "stopped: herdr agent get repo-1 failed" in r.stdout
    assert "ready-for-human" not in sb.labels(1)


def test_a_light_tier_worker_that_landed_on_main_with_no_pr_is_a_merge(sb):
    sb.write_state({1: {}})
    r = sb.drain("--once", env={"LIGHT": "1"})
    assert r.returncode == 0, r.stderr
    assert "#1  (landed on main, no PR)" in r.stdout
    assert "implement-1" in read(sb.cleanup_log)


def test_a_rerun_with_a_gone_worker_and_no_pr_hands_the_ticket_over(sb):
    sb.write_state({1: {"labels": ["in-progress"]}, 2: {}}, comments=[["1", "drain anchor: implement-1"]])
    sb.drain("--once", env={"HERDR_GONE": "1"})
    assert sb.dispatch_runs() == [], "a resumed ticket is waited on, never dispatched twice"
    assert "ready-for-human" in sb.labels(1)


def test_a_merged_ticket_the_open_list_still_carries_is_not_resumed(sb):
    sb.write_state({1: {}})
    r = sb.drain("--max", "3", env={"STALE_LISTING": "1"})
    assert r.returncode == 0, r.stderr
    assert len(sb.dispatch_runs()) == 1
    assert [m[0] for m in sb.state()["merged"]] == [[1]]
    assert len(sb.ended_lines(r)) == 1, r.stdout
    assert "landed on main, no PR" not in r.stdout


def test_a_closed_ticket_the_open_list_carries_is_not_resumed_by_a_fresh_run(sb):
    sb.write_state({1: {"state": "closed", "labels": ["in-progress"]}, 2: {}},
                     comments=[["1", "drain anchor: implement-1"]])
    r = sb.drain("--once", env={"STALE_LISTING": "1"})
    assert r.returncode == 0, r.stderr
    assert [c["n"] for c in sb.dispatch_runs()] == ["2"], r.stdout
    assert [m[0] for m in sb.state()["merged"]] == [[2]]


def test_an_open_ticket_the_list_carries_after_losing_in_progress_is_not_resumed(sb):
    sb.write_state({1: {"labels": []}, 2: {}}, comments=[["1", "drain anchor: implement-1"]])
    r = sb.drain("--once", env={"STALE_LABELS": "1"})
    assert r.returncode == 0, r.stderr
    assert [c["n"] for c in sb.dispatch_runs()] == ["2"], r.stdout


def test_an_anchor_this_run_ended_is_not_resumed_even_when_its_reread_is_stale(sb):
    sb.write_state({1: {}})
    r = sb.drain("--max", "3", env={"STALE_LISTING": "1", "STALE_VIEW": "1"})
    assert r.returncode == 0, r.stderr
    assert len(sb.ended_lines(r)) == 1, r.stdout
    assert "landed on main, no PR" not in r.stdout


def test_a_rerun_checks_an_open_pr_without_rebuilding(sb):
    sb.write_state({1: {"labels": ["in-progress"]}}, comments=[["1", "drain anchor: implement-1"]])
    wt = sb.worktree(1)
    sb.git(sb.repo, "worktree", "add", "-q", "-b", "implement-1", wt, "origin/main")
    write(os.path.join(wt, "w.txt"), "w\n")
    sb.git(wt, "add", ".")
    sb.git(wt, "commit", "-qm", "worker commit")
    sb.git(wt, "push", "-q", "origin", "HEAD:implement-1")
    st = sb.state()
    st["prs"]["implement-1"] = {"number": 101, "url": "https://example.test/pull/101", "closes": [1],
                                "head": sb.git(wt, "rev-parse", "HEAD"), "draft": False, "status": "CLEAN"}
    sb.save(st)
    r = sb.drain("--once")
    assert r.returncode == 0, r.stderr
    assert sb.dispatch_runs() == []
    assert [m[0] for m in sb.state()["merged"]] == [[1]]


def test_a_live_workers_ticket_is_not_adopted(sb):
    # In-progress with a worktree, but no drain anchor comment: a worker
    # `implement-dispatch` started. drain leaves it and takes ticket 2.
    sb.write_state({1: {"labels": ["in-progress"]}, 2: {}})
    sb.git(sb.repo, "worktree", "add", "-q", "-b", "implement-1", sb.worktree(1), "origin/main")
    sb.drain("--once")
    assert [c["n"] for c in sb.dispatch_runs()] == ["2"]
    assert sb.labels(1) == ["in-progress"]


def test_a_ticket_drain_handed_to_chris_is_not_adopted_when_it_is_readied_again(sb):
    sb.write_state({1: {"labels": ["in-progress"]}},
                     comments=[["1", "drain anchor: implement-1"], ["1", "drain could not land this ticket (x)"]])
    sb.git(sb.repo, "worktree", "add", "-q", "-b", "implement-1", sb.worktree(1), "origin/main")
    sb.drain("--once")
    assert sb.dispatch_runs() == []
    assert sb.labels(1) == ["in-progress"]


def test_a_failed_claim_comment_leaves_the_ticket_ready(sb):
    sb.write_state({1: {}})
    r = sb.drain("--once", env={"FAIL_VERB": "comment"})
    assert sb.labels(1) == ["ready-for-agent"]
    assert "stopped:" in r.stdout


def test_a_pr_closing_a_ticket_the_bundle_comment_does_not_name_is_a_failed_build(sb):
    sb.write_state({1: {}, 2: {}})
    sb.drain("--once", env={"EXTRA_CLOSE": "2"})
    assert "merged" not in sb.state()
    assert "which no drain bundle: comment on #1 names" in sb.handed_comment(1)[0]
    for n in (1, 2):
        assert "ready-for-human" in sb.labels(n)


def test_a_ticket_another_worker_holds_is_not_touched_by_a_merge(sb):
    sb.write_state({1: {}, 2: {}, 3: {"labels": ["in-progress"], "assignees": ["me"]}})
    sb.drain("--once", env={"TAKE": "2"})
    assert sb.state()["merged"][0][0] == [1, 2]
    assert sb.labels(3) == ["in-progress"]
    assert sb.state()["issues"]["3"]["assignees"] == ["me"]


def test_the_lock_and_agent_names_match_implement_dispatch(sb, tmp_path, monkeypatch):
    # drain cannot import the Rust it mirrors; this pins what it copies.
    source = read(os.path.join(HERE, "..", "flow", "lane", "src", "bin", "implement_dispatch.rs"))
    sys.path.insert(0, HERE)
    import drain
    # The lock drain takes is the path implement_dispatch.rs formats, not a
    # name only the test knows: run drain's own lock under a scratch HOME and
    # compare the file it creates with the Rust format string.
    assert "{}/.implement-dispatch-claim-{}.lock" in source
    assert "slug.replace('/', \"__\")" in source
    import types
    home = tmp_path / "lock-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    with drain.claim_lock(types.SimpleNamespace(repo="owner/name")):
        pass
    assert os.path.exists(os.path.join(home, ".implement-dispatch-claim-owner__name.lock"))
    # The worker's herdr agent name drain looks for is the one the Rust formats.
    assert "(32usize).saturating_sub(suffix.len())" in source
    assert 'Mode::Plain => format!("-{n}")' in source


def test_refuses_a_repo_the_user_does_not_own(sb):
    sb.write_state({1: {}})
    sb.set_origin("someone-else/repo")
    r = sb.drain("--once")
    assert r.returncode != 0
    assert sb.dispatch_runs() == []
    assert "someone-else" in r.stderr


# --- #1415: targeted seam, one full run per drain run, --anchor ------------


def test_the_seam_is_skipped_when_main_has_not_moved_past_the_pr(sb):
    sb.write_state({1: {}, 2: {}})
    sb.git(sb.repo, "config", "land.testcmd", 'echo "$0" >> "$SEAM_LOG"')
    r = sb.drain("--max", "2")
    assert [m[0] for m in sb.state()["merged"]] == [[1], [2]]
    # Two bundles, neither with a moved main: the only run is the end-of-run full one.
    assert len(sb.seam_runs()) == 1, r.stdout


def test_the_default_seam_is_narrowed_with_changed_and_the_full_run_is_not(sb):
    sb.write_state({1: {}})
    os.makedirs(os.path.join(sb.repo, "tests"))
    write(os.path.join(sb.repo, "tests", "all.sh"), '#!/bin/sh\necho "all.sh $*" >> "$SEAM_LOG"\n', 0o755)
    sb.git(sb.repo, "add", ".")
    sb.git(sb.repo, "commit", "-qm", "gate")
    sb.git(sb.repo, "push", "-q", "origin", "main")
    sb.git(sb.repo, "config", "--unset", "land.testcmd")
    sb.drain("--once", env={"RESET_TO_OLD": "1"})  # main moved: the per-merge check runs
    assert sb.seam_runs() == ["all.sh --changed origin/main", "all.sh"]

def test_a_lockfile_gets_its_dependencies_installed_before_the_seam_runs(sb):
    sb.write_state({1: {}})
    sb.lockfile_repo()
    r = sb.drain("--once", env={"RESET_TO_OLD": "1"})  # per-PR seam, then the full run
    assert sb.seam_runs() == ["npm ci", "seam", "npm ci", "seam"], r.stdout
    assert [m[0] for m in sb.state()["merged"]] == [[1]]


def test_a_nested_lockfile_gets_its_dependencies_installed_in_its_own_directory(sb):
    sb.write_state({1: {}})
    sb.lockfile_repo(where="test-audit")
    r = sb.drain("--once", env={"RESET_TO_OLD": "1"})
    assert sb.seam_runs() == ["npm ci", "seam", "npm ci", "seam"], r.stdout
    assert [m[0] for m in sb.state()["merged"]] == [[1]]


def test_every_tracked_lockfile_gets_its_own_install(sb):
    sb.write_state({1: {}})
    sb.lockfile_repo(where="test-audit")
    write(os.path.join(sb.repo, "package-lock.json"), "{}\n")
    sb.git(sb.repo, "add", ".")
    sb.git(sb.repo, "commit", "-qm", "root lockfile")
    sb.git(sb.repo, "push", "-q", "origin", "main")
    sb.git(sb.repo, "config", "land.testcmd",
           'test -d node_modules && test -d test-audit/node_modules && echo seam >> "$SEAM_LOG"')
    r = sb.drain("--once", env={"RESET_TO_OLD": "1"})
    assert sb.seam_runs() == ["npm ci", "npm ci", "seam", "npm ci", "npm ci", "seam"], r.stdout


def test_a_repo_without_a_lockfile_installs_nothing(sb):
    sb.write_state({1: {}})
    sb.lockfile_repo(lock=False)
    sb.git(sb.repo, "config", "land.testcmd", 'echo seam >> "$SEAM_LOG"')
    sb.drain("--once", env={"RESET_TO_OLD": "1"})
    assert sb.seam_runs() == ["seam", "seam"]


def test_a_failed_install_is_a_failed_build_and_the_seam_never_runs(sb):
    sb.write_state({1: {}})
    sb.lockfile_repo()
    sb.git(sb.repo, "config", "land.testcmd", 'echo seam >> "$SEAM_LOG"')  # logs even without node_modules
    sb.drain("--once", env={"RESET_TO_OLD": "1", "NPM_RED": "1"})
    assert "merged" not in sb.state()
    assert "`npm ci` failed" in sb.handed_comment(1)[0]
    runs = sb.seam_runs()  # a ticket gets two tries
    assert (runs and set(runs) == {"npm ci"}), runs


def test_a_failed_install_before_the_full_run_stops_the_run_red(sb):
    sb.write_state({1: {}})
    sb.lockfile_repo()
    sb.git(sb.repo, "config", "land.testcmd", 'echo seam >> "$SEAM_LOG"')
    r = sb.drain("--once", env={"NPM_RED": "1"})  # main has not moved: only the full run installs
    assert r.returncode == 1, r.stdout
    assert "stopped: the full suite is red on main" in r.stdout
    assert sb.seam_runs() == ["npm ci"]


def test_an_npm_that_cannot_start_is_a_failed_build_not_a_crash(sb):
    sb.write_state({1: {}})
    sb.lockfile_repo()
    os.remove(os.path.join(sb.bin, "npm"))
    sb.drain("--once", env={"RESET_TO_OLD": "1", "PATH": sb.bin + os.pathsep + "/usr/bin" + os.pathsep + "/bin"})
    assert "merged" not in sb.state()
    assert "`npm ci` could not start" in sb.handed_comment(1)[0]


def test_one_full_run_after_the_last_bundle_and_a_red_one_stops_with_the_merges_named(sb):
    sb.write_state({1: {}, 2: {}})
    sb.git(sb.repo, "config", "land.testcmd", 'echo run >> "$SEAM_LOG"; test -z "$SEAM_RED"')
    r = sb.drain("--max", "2", env={"SEAM_RED": "1"})
    assert [m[0] for m in sb.state()["merged"]] == [[1], [2]], "both merges landed before the full run"
    assert len(sb.seam_runs()) == 1
    assert r.returncode == 1
    assert "stopped: the full suite is red on main" in r.stdout
    for url in ("https://example.test/pull/101", "https://example.test/pull/102"):
        assert url in r.stdout


def test_a_green_full_run_records_main_and_a_later_red_one_names_the_merges_since(sb):
    sb.write_state({1: {}, 2: {}})
    sb.git(sb.repo, "config", "land.testcmd", 'test -z "$SEAM_RED"')
    assert sb.drain("--once").returncode == 0
    green = read(os.path.join(sb.tmp, "logs", "last-green-me__repo")).strip()
    assert green == sb.git(sb.repo, "rev-parse", "origin/main")
    # Two merges land on main since that green run (the fake `gh` never moves main itself).
    for subject in ("first other merge", "second other merge"):
        sb.git(sb.repo, "commit", "-q", "--allow-empty", "-m", subject)
    sb.git(sb.repo, "push", "-q", "origin", "main")
    r = sb.drain("--once", env={"SEAM_RED": "1"})
    assert "stopped: the full suite is red on main" in r.stdout
    assert "Merges since the last green full run: " in r.stdout
    # Named from last-green's sha, not just this run's own merge: with the file unread
    # the list would hold only the PR url.
    for subject in ("first other merge", "second other merge"):
        assert subject in r.stdout


def test_the_full_run_log_is_named_for_its_repo(sb):
    sb.write_state({1: {}})
    sb.git(sb.repo, "config", "land.testcmd", 'echo full-run-output')
    assert sb.drain("--once").returncode == 0
    logs = os.path.join(sb.tmp, "logs")
    assert "full-run-output" in read(os.path.join(logs, "full-suite-me__repo.log"))
    assert not os.path.exists(os.path.join(logs, "full-suite.log")), "the shared name would be overwritten by the next repo"


def gate_repo(sb, listed, message="gate"):
    """Commit a `tests/all.sh` stub to main: with `--list --changed <base>` it
    prints `listed` (what `--changed` selects at this commit) and logs its
    arguments to `$SEAM_LOG`; otherwise it fails the suite `SEAM_RED` names."""
    os.makedirs(os.path.join(sb.repo, "tests"), exist_ok=True)
    write(os.path.join(sb.repo, "tests", "all.sh"),
          '#!/bin/sh\ncase "$1" in --list) echo "$*" >> "$SEAM_LOG"; printf "%s\\n" ' + " ".join(listed) + '; exit 0;; esac\n'
          'test -z "$SEAM_RED" && exit 0\necho "FAIL $SEAM_RED"; exit 1\n', 0o755)
    sb.git(sb.repo, "add", ".")
    sb.git(sb.repo, "commit", "-q", "--allow-empty", "-m", message)
    sb.git(sb.repo, "push", "-q", "origin", "main")
    if subprocess.run(["git", "config", "land.testcmd"], cwd=sb.repo, capture_output=True).returncode == 0:
        sb.git(sb.repo, "config", "--unset", "land.testcmd")  # the default seam is `bash tests/all.sh`
    return sb.git(sb.repo, "rev-parse", "HEAD")


def red_after_a_green(sb, *listings):
    """A green full run, then one merge per listing (each rewrites the stub, so
    the listing is what `--changed` selects at that merge), then a red full run."""
    sb.write_state({1: {}, 2: {}})
    gate_repo(sb, ["alpha/a.test.sh"])
    assert sb.drain("--once").returncode == 0  # records last-green
    merges = [gate_repo(sb, listed, f"merge {i}") for i, listed in enumerate(listings)]
    r = sb.drain("--once", env={"SEAM_RED": "zeta/z.test.sh"})
    return r, merges


def test_a_red_full_run_no_merges_gate_selects_is_a_selector_miss(sb):
    r, _ = red_after_a_green(sb, ["alpha/a.test.sh"], ["tests/t.test.sh"])
    assert "stopped: the full suite is red on main" in r.stdout
    assert "selector miss: `--changed` would not have selected zeta/z.test.sh for any of the 2 merges" in r.stdout


def test_the_selector_is_asked_per_merge_with_that_merges_parent_as_the_base(sb):
    _, merges = red_after_a_green(sb, ["alpha/a.test.sh"], ["alpha/a.test.sh"])
    asked = [x for x in sb.seam_runs() if x.startswith("--list")]
    assert asked == [f"--list --changed {m}^1" for m in merges]


def test_a_suite_selected_for_only_some_merges_is_not_called_clean_or_a_miss(sb):
    r, merges = red_after_a_green(sb, ["zeta/z.test.sh"], ["alpha/a.test.sh"])
    assert "selector miss:" not in r.stdout
    assert f"for 1 of 2 merges ({merges[0][:8]})" in r.stdout
    assert "(bisect to settle)" in r.stdout


def test_a_suite_every_merge_selects_is_reported_selected(sb):
    r, _ = red_after_a_green(sb, ["zeta/z.test.sh"], ["zeta/z.test.sh"])
    assert "stopped: the full suite is red on main" in r.stdout
    assert "selector miss:" not in r.stdout
    assert "would have selected zeta/z.test.sh for every merge" in r.stdout


def test_a_red_full_run_with_no_green_on_record_says_the_selector_was_not_checked(sb):
    sb.write_state({1: {}})
    gate_repo(sb, ["alpha/a.test.sh"])
    r = sb.drain("--once", env={"SEAM_RED": "zeta/z.test.sh"})
    assert "stopped: the full suite is red on main" in r.stdout
    assert "selector not checked: no green full run on record" in r.stdout
    assert "selector miss:" not in r.stdout


def test_a_full_run_log_that_cannot_be_read_is_not_reported_as_one_without_a_failure_line(sb, monkeypatch):
    sys.path.insert(0, HERE)
    import drain as drain_module
    ctx = drain_module.Ctx(sb.repo, "me/repo", "main", os.path.join(sb.tmp, "logs"), 1, None)
    monkeypatch.setattr(drain_module, "seam_cmd", lambda c: drain_module.FULL_SEAM)
    verdict = drain_module.selector_verdict(ctx, "0" * 40, "1" * 40)  # no log was ever written
    assert "could not be read" in verdict
    assert "no `FAIL" not in verdict


def test_no_merge_means_no_full_run(sb):
    sb.write_state({})
    sb.git(sb.repo, "config", "land.testcmd", 'echo run >> "$SEAM_LOG"')
    sb.drain()
    assert sb.seam_runs() == []


def test_anchor_starts_the_bundle_from_that_ticket_and_only_the_first(sb):
    sb.write_state({1: {}, 2: {}, 3: {}})
    r = sb.drain("--anchor", "3", "--max", "2")
    assert r.returncode == 0, r.stderr
    assert [c["n"] for c in sb.dispatch_runs()] == ["3", "1"]
    assert [c["tickets"] for c in sb.dispatch_runs()] == [["3"], ["1"]]


def test_anchor_that_is_not_ready_or_is_blocked_is_refused_before_any_work(sb):
    sb.write_state({1: {}, 2: {"labels": ["in-progress"]}, 3: {"body": "## Blocked by\n\n- #1\n"}})
    for n in ("2", "3", "9"):
        r = sb.drain("--anchor", n)
        assert r.returncode == 1, n
        assert f"--anchor #{n} is not an open, ready, unblocked ticket" in r.stdout
    assert sb.dispatch_runs() == []
    assert sb.labels(1) == ["ready-for-agent"]


def test_a_ready_slice_is_never_the_anchor_and_never_joins_a_bundle(sb):
    # Ruling 7 of #1457: a slice is built inside its spec run only, even
    # one older than every lone ticket and one the chooser asks for.
    spec = {"labels": ["spec"], "body": "the spec"}
    sb.write_state({1: {"parent": 9}, 2: {}, 3: {"parent": 9}, 4: {}, 9: spec})
    r = sb.drain("--once", env={"TAKE": "3"})
    assert r.returncode == 0, r.stderr
    assert [c["tickets"] for c in sb.dispatch_runs()] == [["2"]]
    prompt = sb.chooser_runs()[0]["prompt"]
    assert "#2 is the anchor" in prompt
    assert "- #4 ticket 4" in prompt
    assert "#1 " not in prompt
    assert "#3 " not in prompt
    assert sb.labels(1) == ["ready-for-agent"]
    assert sb.labels(3) == ["ready-for-agent"]
    r = sb.drain("--anchor", "3")
    assert r.returncode == 1
    assert "--anchor #3 is not an open, ready, unblocked ticket" in r.stdout

# --- review fixes (#1415) --------------------------------------------------


def test_a_failed_check_prompts_the_worker_with_the_reason_and_waits_for_it_to_start_working(sb):
    sb.write_state({1: {}})
    sb.drain("--once", env={"DRAFT_TICKETS": "1"})
    prompts = [c for c in sb.herdr_calls() if c[:2] == ["agent", "prompt"]]
    assert len(prompts) == 1
    assert "the PR is up but drain's check of it failed" in prompts[0][3]
    assert "still a draft" in prompts[0][3]
    assert prompts[0][4:7] == ["--wait", "--until", "working"]


def test_a_missing_pr_prompts_with_the_reason_it_is_not_up(sb):
    sb.write_state({1: {}})
    sb.drain("--once", env={"FAIL_TICKETS": "1"})
    prompt = next(c for c in sb.herdr_calls() if c[:2] == ["agent", "prompt"])
    assert "the PR is not up yet" in prompt[3]
    assert "is idle with no PR" in prompt[3]


def test_a_blocked_worker_is_a_failed_build_not_a_wait_for_the_wall_clock(sb):
    sb.write_state({1: {}})
    sb.drain("--once", env={"FAIL_TICKETS": "1", "HERDR_STATUS": "blocked"})
    assert "is blocked with no PR" in sb.handed_comment(1)[0]


def test_a_bundle_handed_to_chris_closes_its_workers_pane(sb):
    sb.write_state({1: {}})
    sb.drain("--once", env={"FAIL_TICKETS": "1"})
    assert ["pane", "close", "w9:p1"] in sb.herdr_calls()


def test_a_ticket_whose_workspace_is_kept_is_not_picked_and_an_anchor_naming_it_is_refused(sb):
    sb.write_state({1: {}, 2: {}})
    sb.git(sb.repo, "worktree", "add", "-q", "-b", "implement-1", sb.worktree(1), "origin/main")
    r = sb.drain("--anchor", "1")
    assert r.returncode == 1
    assert "--anchor #1 is not an open, ready, unblocked ticket without a kept workspace" in r.stdout
    assert sb.dispatch_runs() == []
    sb.drain("--once")
    assert [c["n"] for c in sb.dispatch_runs()] == ["2"]


def test_a_transient_look_failure_does_not_fail_the_build(sb):
    sb.write_state({1: {}})
    r = sb.drain("--once", env={"HERDR_FLAKY": "2"})
    assert r.returncode == 0, r.stdout
    assert [m[0] for m in sb.state()["merged"]] == [[1]]


def test_a_dispatch_that_fails_after_the_claim_is_this_bundles_failed_build(sb):
    sb.write_state({1: {}, 2: {}})
    r = sb.drain("--once", env={"DISPATCH_FAIL_AFTER_CLAIM": "1", "HERDR_GONE": "1"})
    assert "stopped" not in r.stdout
    assert len(sb.dispatch_runs()) == 1, "a failure after the claim is not retried by dispatching again"
    assert "ready-for-human" in sb.labels(1)
    assert sb.handed_comment(1)[0].count("Last failure") == 1


def test_a_drain_run_from_a_linked_worktree_names_the_primary_checkout(sb):
    sb.write_state({1: {}})
    linked = os.path.join(sb.tmp, "linked")
    sb.git(sb.repo, "worktree", "add", "-q", "--detach", linked, "origin/main")
    r = sb.drain("--once", "--repo", linked)
    assert r.returncode == 0, r.stdout + r.stderr
    assert sb.dispatch_runs()[0]["argv"][:2] == ["--repo", sb.repo]
    assert ["agent", "get", "repo-1"] in sb.herdr_calls()


def test_an_empty_queue_says_so(sb):
    r = sb.drain()
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "nothing to drain"
    assert sb.dispatch_runs() == []


def test_a_queue_of_one_spec_and_its_slices_is_dispatched_as_a_spec_run_and_merged(sb):
    sb.spec_state()
    r = sb.drain("--once", env={"SPEC_SLICES": "2 3"})
    assert r.returncode == 0, r.stderr
    assert [c["argv"] for c in sb.dispatch_runs()] == [["--repo", sb.repo, "--controller", "drain", "--spec", "1"]]
    assert sb.chooser_runs() == [], "a spec's slices are its own bundle: no chooser"
    st = sb.state()
    assert [i["state"] for i in st["issues"].values()] == ["closed"] * 3
    assert ["1", "drain anchor: spec-1"] in st["comments"]
    assert "spec-1" in read(sb.cleanup_log)
    assert ["agent", "get", "repo-spec-1"] in sb.herdr_calls()
    assert "bundle started: #1 ticket 1  pane repo-spec-1" in r.stdout
    assert "merged:\n  #1 #2 #3  https://example.test/pull/101" in r.stdout


def test_the_lowest_numbered_unit_goes_first_whether_a_ticket_or_a_spec(sb):
    sb.write_state({1: {}, 2: SPEC, 3: {"parent": 2}, 4: {"parent": 2}, 5: {}})
    r = sb.drain(env={"SPEC_SLICES": "3 4"})
    assert r.returncode == 0, r.stderr
    runs = sb.dispatch_runs()
    assert [c["n"] for c in runs] == ["1", "2", "5"]
    assert ["--spec" in c["argv"] for c in runs] == [False, True, False]
    prompt = sb.chooser_runs()[0]["prompt"]
    assert "#2 " not in prompt
    assert "#3 " not in prompt


def test_a_spec_without_the_ready_label_is_not_dispatched(sb):
    # `implement-dispatch --spec` refuses a spec that is not `ready-for-agent`.
    sb.write_state({1: {"labels": ["spec"]}, 2: {"parent": 1}, 3: {"parent": 1}})
    r = sb.drain()
    assert "nothing to drain" in r.stdout
    assert "waiting: ready slices of spec #1, which drain cannot start" in r.stdout
    assert sb.dispatch_runs() == []


def test_a_slice_of_a_closed_spec_is_named_not_left_behind(sb):
    # #1485: the slice reads `stranded`, and drain says so beside `waiting:`.
    sb.write_state({1: {**SPEC, "state": "closed"}, 2: {"parent": 1}})
    r = sb.drain()
    assert "nothing to drain" in r.stdout
    assert "stranded: #2" in r.stdout
    assert "closed" in r.stdout
    assert sb.dispatch_runs() == []


def test_a_stranded_slice_is_named_even_when_another_ticket_is_started(sb):
    sb.write_state({1: {**SPEC, "state": "closed"}, 2: {"parent": 1}, 3: {}})
    r = sb.drain("--once")
    assert "stranded: #2" in r.stdout
    assert r.stdout.count("stranded: #2") == 1


def test_a_blocked_spec_is_not_dispatched(sb):
    sb.write_state({1: {**SPEC, "body": "## Blocked by\n\n- #9\n"}, 2: {"parent": 1}, 9: {"labels": []}})
    r = sb.drain()
    assert "nothing to drain" in r.stdout
    assert sb.dispatch_runs() == []


def test_a_spec_pr_may_close_more_tickets_than_bundle_max_when_all_are_its_slices(sb):
    sb.spec_state(slices=(2, 3, 4, 5))
    r = sb.drain("--once", "--bundle-max", "2", env={"SPEC_SLICES": "2 3 4 5"})
    assert r.returncode == 0, r.stderr
    assert sb.state()["merged"][0][0] == [1, 2, 3, 4, 5]


def test_a_spec_pr_that_closes_a_ticket_that_is_not_its_slice_is_a_failed_build(sb):
    sb.spec_state(slices=(2,), extra={9: {}})
    r = sb.drain("--once", env={"SPEC_SLICES": "2", "EXTRA_CLOSE": "9"})
    assert r.returncode == 0, r.stderr
    assert "closes #9 which is not a slice of spec #1" in sb.handed_comment(1)[0]
    assert "merged" not in sb.state()


def test_a_spec_pr_that_does_not_close_the_spec_is_a_failed_build(sb):
    sb.spec_state()
    sb.drain("--once", env={"SPEC_SLICES": "2 3", "NO_ANCHOR": "1"})
    assert "does not close the anchor #1" in sb.handed_comment(1)[0]


def test_a_spec_run_that_fails_hands_the_spec_and_its_claimed_slices_over_and_closes_every_pane(sb):
    # Ticket 8 is another run's claim; 9's parent line names another repo, so its parent cannot be read.
    sb.spec_state(extra={8: {"labels": ["in-progress"]},
                           9: {"labels": ["in-progress"], "body": "Part of other/repo#12\n"}})
    sb.drain("--once", env={"SPEC_SLICES": "2 3", "FAIL_TICKETS": "1"})
    for n in (8, 9):
        assert sb.labels(n) == ["in-progress"], "not this spec's: left alone"
        assert ["agent", "get", f"repo-{n}"] not in sb.herdr_calls()
    for n in (1, 2, 3):
        assert "ready-for-human" in sb.labels(n)
        assert "in-progress" not in sb.labels(n)
        assert len(sb.handed_comment(n)) == 1
    assert "The worktree spec-1 is kept" in sb.handed_comment(1)[0]
    closes = [c for c in sb.herdr_calls() if c[:2] == ["pane", "close"]]
    assert len(closes) == 3, "the spec run's pane and each slice worker's"
    assert ["agent", "get", "repo-3"] in sb.herdr_calls()


def test_a_one_slice_spec_whose_run_lands_it_without_an_integration_pr_is_reported_landed(sb):
    sb.spec_state(slices=(2,))
    r = sb.drain("--once", env={"SPEC_SLICES": "2", "LIGHT": "1"})
    assert r.returncode == 0, r.stderr
    assert "#1  (landed on main, no PR)" in r.stdout
    assert "spec-1" in read(sb.cleanup_log)


def test_an_anchor_note_that_names_another_ticket_or_is_malformed_is_not_resumed(sb):
    for note in ("drain anchor: spec-2", "drain anchor: implement-1 extra", "drain anchor: whatever"):
        sb.write_state({1: {"labels": ["in-progress"]}}, comments=[["1", note]])
        sb.drain("--once", env={"HERDR_GONE": "1"})
        assert sb.dispatch_runs() == [], note
        assert sb.handed_comment(1) == [], note


def test_a_spec_whose_workspace_is_kept_is_not_picked_again(sb):
    sb.spec_state()
    os.makedirs(sb.repo + "/.claude/worktrees/spec-1")
    r = sb.drain()
    assert "nothing to drain" in r.stdout


def test_a_rerun_resumes_a_spec_it_started_and_never_dispatches_it_twice(sb):
    sb.write_state({1: {**SPEC, "labels": ["spec", "in-progress"]},
                      2: {"parent": 1, "labels": ["in-progress"]}},
                     comments=[["1", "drain anchor: spec-1"]])
    sb.drain("--once", env={"HERDR_GONE": "1"})
    assert sb.dispatch_runs() == []
    assert "the worker repo-spec-1 is gone" in sb.handed_comment(1)[0]


def test_a_spec_the_run_did_not_start_is_never_taken(sb):
    # A burn's spec run: in-progress, no `drain anchor:` comment, and its
    # slices still read `slice` on the frontier.
    sb.write_state({1: {**SPEC, "labels": ["spec", "in-progress"]}, 2: {"parent": 1}})
    r = sb.drain()
    assert "nothing to drain" in r.stdout
    assert sb.dispatch_runs() == []


def test_anchor_may_name_a_spec(sb):
    sb.write_state({1: {}, 2: SPEC, 3: {"parent": 2}})
    r = sb.drain("--anchor", "2", "--once", env={"SPEC_SLICES": "3"})
    assert r.returncode == 0, r.stderr
    assert [c["n"] for c in sb.dispatch_runs()] == ["2"]
    assert sb.labels(1) == ["ready-for-agent"]


# `wait_for_worker`'s wall clock, in-process: a three-hour clock has no
# command-line witness.


@pytest.fixture
def d(monkeypatch):
    """The drain module with every wait knob shortened for one test; monkeypatch restores them."""
    import drain
    monkeypatch.setattr(drain, "POLL_SECONDS", 0.05)
    return drain


@pytest.fixture
def ctx():
    return type("Ctx", (), {"repo": "o/r", "root": "/x/repo"})()


def test_a_worker_that_never_goes_idle_fails_at_the_wall_clock(d, monkeypatch):
    monkeypatch.setattr(d, "WALL_CLOCK_SECONDS", 0.3)
    monkeypatch.setattr(d, "agent_status", lambda name: "working")
    with pytest.raises(d.DrainError) as caught:
        d.wait_for_worker(None, "implement-1", "repo-1", [1])
    assert "passed the 0.3s wall clock" in str(caught.value)


def test_a_spec_run_idle_while_its_slice_workers_work_is_not_a_failed_build(d, ctx, monkeypatch):
    monkeypatch.setattr(d, "IDLE_GRACE_SECONDS", 0.2)
    monkeypatch.setattr(d, "agent_status", lambda name: "idle")
    monkeypatch.setattr(d, "gh_json", lambda *args: {"state": "open"})
    start = time.monotonic()
    monkeypatch.setattr(d, "slices_working", lambda ctx, spec: time.monotonic() - start < 0.6)
    monkeypatch.setattr(d, "open_pr", lambda ctx, branch: {"number": 1} if time.monotonic() - start > 0.8 else None)
    assert d.wait_for_worker(ctx, "spec-1", "repo-spec-1", [1], spec=1) == "pr"


@pytest.mark.parametrize("statuses, expected", [
    ({"repo-2": "idle", "repo-3": "working"}, True),
    ({"repo-2": "idle", "repo-3": "blocked"}, False),
    ({"repo-2": "done", "repo-3": None}, False),
])
def test_a_slice_worker_counts_as_working_only_while_it_is_working(d, ctx, monkeypatch, statuses, expected):
    monkeypatch.setattr(d, "claimed_slices", lambda ctx, spec: [2, 3])
    monkeypatch.setattr(d, "agent_status", statuses.get)
    assert d.slices_working(ctx, 1) is expected, statuses


def test_the_same_idle_wait_with_no_slice_working_fails_at_the_grace(d, ctx, monkeypatch):
    monkeypatch.setattr(d, "IDLE_GRACE_SECONDS", 0.2)
    monkeypatch.setattr(d, "agent_status", lambda name: "idle")
    monkeypatch.setattr(d, "gh_json", lambda *args: {"state": "open"})
    monkeypatch.setattr(d, "slices_working", lambda ctx, spec: False)
    monkeypatch.setattr(d, "open_pr", lambda ctx, branch: None)
    with pytest.raises(d.DrainError) as caught:
        d.wait_for_worker(ctx, "spec-1", "repo-spec-1", [1], spec=1)
    assert "is idle with no PR" in str(caught.value)


def test_a_spec_run_gets_the_spec_wall_clock_not_the_tickets(d, ctx, monkeypatch):
    monkeypatch.setattr(d, "WALL_CLOCK_SECONDS", 0.1)
    monkeypatch.setattr(d, "SPEC_WALL_CLOCK_SECONDS", 0.4)
    monkeypatch.setattr(d, "agent_status", lambda name: "working")
    started = time.monotonic()
    with pytest.raises(d.DrainError) as caught:
        d.wait_for_worker(ctx, "spec-1", "repo-spec-1", [1], spec=1)
    assert "passed the 0.4s wall clock" in str(caught.value)
    assert time.monotonic() - started >= 0.4


def test_run_group_kills_what_a_command_started(d, tmp_path):
    pidfile = str(tmp_path / "pid")
    with pytest.raises(d.DrainError):
        d.run_group(["sh", "-c", f"sleep 30 & echo $! > {pidfile}; sleep 30"], str(tmp_path), 1)
    pid = int(read(pidfile))
    for _ in range(30):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.1)
    pytest.fail("the command's grandchild survived the wall clock")
