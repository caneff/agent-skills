#!/usr/bin/env python3
"""Tests for `drain` (#1403, #1415). Seam: the command line, `drain.py [--once]
[--max n] [--bundle-max k] [--anchor n] [--repo path]`, run as a subprocess
against a real git repo with a bare origin, a fake `gh` (a JSON state file), a
stub `claude` that answers the bundle chooser, a stub `implement-dispatch` that
claims the bundle and builds as the worker would (commit, push, PR), a stub
`herdr` that reports the worker's status, and a stub `merge-cleanup`. Each case
is a queue in, labels / merges / summary out. `HOME` and the global git config
are the test's own, so no case reads the real ones. A last class tests the wait
on a worker in-process, since a three-hour clock has no command-line witness.
"""
import json
import os
import select
import subprocess
import sys
import tempfile
import time
import unittest

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
                  if (i["state"] == "open" or n in os.environ.get("STALE_LISTING", "").split()) and label in i["labels"]]
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
        out(dict(number=parent, labels=names(state["issues"][str(parent)])))
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
    if args[2] in os.environ.get("STALE_VIEW", "").split():  # a read GitHub has not caught up on
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
# the commit before main's tip).
STUB_DISPATCH = r"""#!/usr/bin/env python3
import json, os, subprocess, sys
env, argv = os.environ, sys.argv[1:]
repo = argv[argv.index("--repo") + 1]
tickets = [a for a in argv if a.isdigit()]
n = str(min(int(t) for t in tickets))
with open(env["DISPATCH_LOG"], "a") as f:
    f.write(json.dumps({"n": n, "tickets": tickets, "argv": argv}) + "\n")
if env.get("DISPATCH_REFUSE"):
    sys.stderr.write("implement-dispatch: no herdr server is running (herdr status)\n"); sys.exit(1)
branch = "implement-" + n
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


class Sandbox(unittest.TestCase):
    """A repo, a bare origin, stubs on PATH and an isolated HOME."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
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

    def tearDown(self):
        self.tmp.cleanup()

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
                "DRAIN_POLL_SECONDS": "0.05", "DRAIN_IDLE_GRACE_SECONDS": "0.3",
                "DRAIN_LOG_DIR": os.path.join(self.tmp.name, "logs"), **(env or {})}

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


class DrainTest(Sandbox):
    def test_once_builds_checks_merges_and_cleans_up(self):
        self.write_state({1: {}, 2: {}})
        r = self.drain("--once")
        self.assertEqual(r.returncode, 0, r.stderr)
        st = self.state()
        self.assertEqual([m[0] for m in st["merged"]], [[1]])  # the oldest only
        self.assertEqual(self.labels(2), ["ready-for-agent"])
        self.assertIn("implement-1", read(self.cleanup_log))
        run = self.dispatch_runs()[0]
        self.assertEqual(run["argv"], ["--repo", self.repo, "--controller", "drain", "1"])
        self.assertEqual(self.chooser_runs()[0]["argv"][2:], ["--permission-mode", "auto"])
        self.assertIn(["agent", "get", "repo-1"], self.herdr_calls())  # the worker's herdr agent name
        self.assertIn("merged:\n  #1  https://example.test/pull/101  m" + st["merged"][0][1], r.stdout)

    def test_the_agents_bundle_is_one_pr_and_the_rest_stay_ready(self):
        self.write_state({1: {}, 2: {}, 3: {}, 4: {}})
        r = self.drain("--once", env={"TAKE": "2 3"})
        self.assertEqual(r.returncode, 0, r.stderr)
        st = self.state()
        self.assertEqual(st["merged"][0][0], [1, 2, 3])
        self.assertEqual([i["state"] for i in st["issues"].values()], ["closed"] * 3 + ["open"])
        self.assertEqual(self.labels(4), ["ready-for-agent"])
        self.assertEqual(self.dispatch_runs()[0]["argv"][-3:], ["1", "2", "3"])
        prompt = self.chooser_runs()[0]["prompt"]
        for line in ("#1 is the anchor", "- #2 ticket 2", "- #3 ticket 3", "- #4 ticket 4", "at most 7 of them"):
            self.assertIn(line, prompt)
        self.assertIn(["1", "drain bundle: 1 2 3"], self.state()["comments"][-1:])
        self.assertIn("#1 #2 #3", r.stdout)

    def test_the_chooser_prompt_carries_each_candidates_body_and_comments_capped(self):
        long_body = "needle " + "x" * 2000 + " TAILMARK\n## Blocked by\n\n- None\n"
        self.write_state({1: {}, 2: {"body": "Fix the parser\nin   two lines\n## Blocked by\n\n- None\n"}, 3: {"body": long_body}},
                         comments=[["2", "later: also handle tabs"]])
        r = self.drain("--once")
        self.assertEqual(r.returncode, 0, r.stderr)
        prompt = self.chooser_runs()[0]["prompt"]
        self.assertIn("- #2 ticket 2: Fix the parser in two lines ## Blocked by - None later: also handle tabs", prompt)
        self.assertIn("needle", prompt)
        self.assertNotIn("TAILMARK", prompt)
        self.assertLess(len(prompt), 1500)

    def test_the_choose_log_holds_the_prompt_the_chooser_judged_from_even_when_it_fails(self):
        self.write_state({1: {}, 2: {"body": "distinctive-excerpt\n## Blocked by\n\n- None\n"}})
        self.drain("--once", env={"CHOOSER_FAIL": "1"})
        log = read(os.path.join(self.tmp.name, "logs", "implement-1-choose.log"))
        self.assertIn("- #2 ticket 2: distinctive-excerpt", log)

    def test_a_candidate_whose_body_cannot_be_read_is_listed_as_unread(self):
        self.write_state({1: {}, 2: {}, 3: {"body": "readable body\n## Blocked by\n\n- None\n"}})
        r = self.drain("--once", env={"FAIL_VIEW": "2"})
        self.assertEqual(r.returncode, 0, r.stderr)
        prompt = self.chooser_runs()[0]["prompt"]
        self.assertIn("- #2 ticket 2: (body not read:", prompt)
        self.assertIn("- #3 ticket 3: readable body ## Blocked by - None", prompt)

    def test_a_chooser_that_fails_or_says_nothing_usable_bundles_the_anchor_alone(self):
        for env in ({"CHOOSER_FAIL": "1", "TAKE": "2"}, {"CHOOSER_SAY": "no idea", "TAKE": "2"}):
            self.write_state({1: {}, 2: {}})
            self.drain("--once", env=env)
            self.assertEqual(self.dispatch_runs()[-1]["tickets"], ["1"], env)
            self.assertEqual(self.labels(2), ["ready-for-agent"], env)
            os.remove(self.dispatch_log)
            self.git(self.repo, "worktree", "remove", "--force", self.worktree(1))
            self.git(self.repo, "branch", "-D", "implement-1")

    def test_a_chooser_pick_that_was_not_offered_or_is_below_the_anchor_is_dropped(self):
        self.write_state({1: {}, 2: {}, 3: {}})
        self.drain("--anchor", "2", "--once", env={"CHOOSER_SAY": "drain bundle: 2 1 9 3 3"})
        self.assertEqual(self.dispatch_runs()[0]["tickets"], ["2", "3"])
        self.assertEqual(self.labels(1), ["ready-for-agent"])

    def test_a_chooser_past_its_wall_clock_bundles_the_anchor_alone_and_says_why(self):
        self.write_state({1: {}, 2: {}})
        r = self.drain("--once", env={"CHOOSER_SLEEP": "1", "TAKE": "2", "DRAIN_CHOOSER_SECONDS": "1"})
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertEqual(self.dispatch_runs()[0]["tickets"], ["1"])
        self.assertTrue(any("drain chooser: #1 alone: " in b and "wall clock" in b
                            for i, b in self.state()["comments"] if i == "1"), self.state()["comments"])

    def test_a_chooser_that_fails_leaves_a_comment_saying_so(self):
        self.write_state({1: {}, 2: {}})
        self.drain("--once", env={"CHOOSER_FAIL": "1", "TAKE": "2"})
        notes = [b for i, b in self.state()["comments"] if i == "1" and b.startswith("drain chooser:")]
        self.assertEqual(len(notes), 1)
        self.assertIn("the chooser exited 1", notes[0])
        self.assertEqual([b for i, b in self.state()["comments"] if b.startswith("drain bundle:")], [],
                         "the chooser note's digits must never read as bundle members")

    def test_the_choosers_bundle_is_cut_to_bundle_max(self):
        self.write_state({1: {}, 2: {}, 3: {}})
        self.drain("--once", "--bundle-max", "2", env={"TAKE": "2 3"})
        self.assertEqual(self.dispatch_runs()[0]["tickets"], ["1", "2"])
        self.assertIn("at most 1 of them", self.chooser_runs()[0]["prompt"])
        self.assertEqual(self.labels(3), ["ready-for-agent"])

    def test_a_pr_over_bundle_max_is_a_failed_build(self):
        # The bundle comments name three tickets, one more than the cap, and the PR closes all three.
        self.write_state({1: {}, 2: {}, 3: {}})
        self.drain("--once", "--bundle-max", "2", env={"TAKE": "2", "EXTRA_CLOSE": "3", "NOTE_EXTRA": "drain bundle: 1 3"})
        self.assertNotIn("merged", self.state())
        self.assertIn("over --bundle-max 2", self.handed_comment(1)[0])

    def test_a_pr_closing_a_ticket_no_bundle_comment_names_is_a_failed_build_even_under_the_cap(self):
        self.write_state({1: {}, 2: {}, 3: {}})
        self.drain("--once", "--bundle-max", "5", env={"TAKE": "2", "EXTRA_CLOSE": "3"})
        self.assertIn("which no drain bundle: comment on #1 names", self.handed_comment(1)[0])

    def test_a_ticket_the_agent_claimed_but_the_pr_did_not_close_goes_back_to_ready(self):
        self.write_state({1: {}, 2: {}})
        r = self.drain("--once", env={"TAKE": "2", "UNCLOSED": "1"})
        st = self.state()
        self.assertEqual(st["merged"][0][0], [1])
        self.assertEqual(self.labels(2), ["ready-for-agent"])
        self.assertEqual(st["issues"]["2"]["assignees"], [])
        self.assertNotIn("stopped", r.stdout)

    def test_a_pr_that_does_not_close_the_anchor_is_a_failed_build(self):
        self.write_state({1: {}, 2: {}})
        self.drain("--once", env={"TAKE": "2", "NO_ANCHOR": "1"})
        self.assertNotIn("merged", self.state())
        self.assertIn("does not close the anchor #1", self.handed_comment(1)[0])

    def test_a_failed_bundle_hands_every_claimed_ticket_to_chris_in_one_line(self):
        self.write_state({1: {}, 2: {}, 3: {}})
        r = self.drain("--once", env={"TAKE": "2", "DRAFT_TICKETS": "1"})
        st = self.state()
        for n in (1, 2):
            self.assertIn("ready-for-human", self.labels(n))
            self.assertNotIn("in-progress", self.labels(n))
            self.assertEqual(st["issues"][str(n)]["assignees"], [])
            self.assertIn("still a draft", self.handed_comment(n)[0])
            self.assertNotIn("\n", self.handed_comment(n)[0])
        self.assertEqual(self.labels(3), ["ready-for-agent"])
        self.assertIn("handed to Chris:\n  #1 #2  ", r.stdout)

    def test_a_ticket_failing_twice_is_handed_over_and_the_loop_moves_on(self):
        self.write_state({1: {}, 2: {}})
        r = self.drain("--max", "2", env={"FAIL_TICKETS": "1"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("ready-for-human", self.labels(1))
        self.assertEqual([m[0] for m in self.state()["merged"]], [[2]])
        self.assertEqual([c["n"] for c in self.dispatch_runs()], ["1", "2"])  # one dispatch; the second try prompts it
        self.assertTrue(any(c[:3] == ["agent", "prompt", "repo-1"] for c in self.herdr_calls()))

    def test_a_pr_that_is_not_clean_is_a_failed_build(self):
        self.write_state({1: {}})
        self.drain("--once", env={"STATUS": "BLOCKED"})
        self.assertNotIn("merged", self.state())
        self.assertIn("BLOCKED, not CLEAN", self.handed_comment(1)[0])

    def test_a_red_seam_is_a_failed_build(self):
        self.write_state({1: {}})
        self.git(self.repo, "config", "land.testcmd", "false")
        self.drain("--once", env={"RESET_TO_OLD": "1"})  # main moved past the PR's base, so the seam runs
        self.assertNotIn("merged", self.state())
        self.assertIn("seam `false` failed", self.handed_comment(1)[0])

    def test_the_seam_runs_on_the_pr_merged_into_current_main(self):
        # The PR is built on the commit before main's tip: `marker` comes from
        # main, `work-1.txt` from the PR, so only the merge holds both.
        self.write_state({1: {}})
        self.git(self.repo, "config", "land.testcmd", "test -e marker && test -e work-1.txt")
        self.drain("--once", env={"RESET_TO_OLD": "1"})
        self.assertEqual([m[0] for m in self.state().get("merged", [])], [[1]])

    def test_blocked_and_claimed_and_human_tickets_are_skipped(self):
        self.write_state({1: {"body": "## Blocked by\n\n- #2\n"}, 2: {"labels": ["in-progress"]},
                          3: {"labels": ["ready-for-agent", "ready-for-human"]}, 4: {}})
        self.drain("--max", "5")
        self.assertEqual([c["n"] for c in self.dispatch_runs()], ["4"])

    def test_a_ticket_taken_since_the_pick_is_not_claimed_over(self):
        self.write_state({1: {}, 2: {}})
        self.drain("--once", env={"TAKE_AFTER_PICK": "1"})
        self.assertEqual([c["n"] for c in self.dispatch_runs()], ["2"])
        self.assertIn("in-progress", self.labels(1))

    def test_a_merge_cleanup_failure_is_a_note_not_a_rebuild(self):
        self.write_state({1: {}})
        r = self.drain("--once", env={"CLEANUP_FAIL": "1"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(self.dispatch_runs()), 1)
        self.assertIn("merge-cleanup failed: cleanup exploded", r.stdout)
        self.assertEqual([m[0] for m in self.state()["merged"]], [[1]])

    def test_a_punctuated_chooser_answer_still_bundles_every_ticket(self):
        self.write_state({1: {}, 2: {}, 3: {}})
        self.drain("--once", env={"CHOOSER_SAY": "drain bundle: 1, 2,\nand 3.\ndrain bundle: 1, 2, 3.",
                                  "DRAFT_TICKETS": "1"})
        for n in (1, 2, 3):
            self.assertIn("ready-for-human", self.labels(n))

    def test_a_bundle_comment_left_by_an_earlier_run_touches_nothing(self):
        # Ticket 5 is another worker's live ticket; the old note naming it
        # predates this run's claim of ticket 1, so a failed bundle leaves it be.
        self.write_state({1: {}, 5: {"labels": ["in-progress"]}}, comments=[["1", "drain bundle: 5"]])
        self.drain("--once", env={"FAIL_TICKETS": "1"})
        self.assertIn("ready-for-human", self.labels(1))
        self.assertEqual(self.labels(5), ["in-progress"])
        self.assertEqual(self.handed_comment(5), [])

    def test_two_bundles_in_a_row_handed_over_stop_the_loop(self):
        self.write_state({1: {}, 2: {}, 3: {}, 4: {}})
        r = self.drain(env={"FAIL_TICKETS": "1 2 3 4"})
        self.assertEqual(r.returncode, 1)
        self.assertIn("stopped: 2 bundles in a row", r.stdout)
        self.assertEqual(self.labels(3), ["ready-for-agent"])
        self.assertEqual(self.labels(4), ["ready-for-agent"])

    def test_a_dispatch_refusal_stops_the_run_and_leaves_the_ticket_ready(self):
        self.write_state({1: {}, 2: {}})
        r = self.drain(env={"DISPATCH_REFUSE": "1"})
        self.assertEqual(r.returncode, 1)
        self.assertIn("stopped: implement-dispatch refused: implement-dispatch: no herdr server is running", r.stdout)
        self.assertEqual(self.labels(1), ["ready-for-agent"])
        self.assertEqual(len(self.dispatch_runs()), 1, "a refusal is the environment's: no second ticket is tried")

    def test_the_bundle_is_announced_while_its_worker_is_still_building(self):
        self.write_state({1: {"title": "first"}, 2: {"title": "second"}})
        hold = os.path.join(self.tmp.name, "hold")
        write(hold, "")
        proc = self.drain_live("--once", env={"TAKE": "2", "HERDR_HOLD_FILE": hold})
        try:
            ready, _, _ = select.select([proc.stdout], [], [], 20)
            self.assertTrue(ready, "no line from drain while its worker was still working")
            line = proc.stdout.readline()
            self.assertNotIn("merged", self.state(), "the bundle merged while its worker was held working")
        finally:
            os.remove(hold)
            out, _ = proc.communicate(timeout=60)
        for part in ("#1 first", "#2 second", "repo-1"):
            self.assertIn(part, line)
        self.assertEqual(proc.returncode, 0)

    def test_a_merged_bundle_gets_an_end_line_with_its_pr_and_sha(self):
        self.write_state({1: {}})
        r = self.drain("--once")
        sha = self.state()["merged"][0][1]
        ended = self.ended_lines(r)
        self.assertEqual(len(ended), 1, r.stdout)
        for part in ("#1", "merged", "https://example.test/pull/101", "m" + sha):
            self.assertIn(part, ended[0])

    def test_a_bundle_handed_to_chris_gets_an_end_line_with_the_reason(self):
        self.write_state({1: {}})
        r = self.drain("--once", env={"DRAFT_TICKETS": "1"})
        ended = self.ended_lines(r)
        self.assertEqual(len(ended), 1, r.stdout)
        self.assertIn("handed to Chris", ended[0])
        self.assertIn("draft", ended[0])

    def test_a_bundle_cut_short_by_a_stop_gets_a_stopped_end_line(self):
        self.write_state({1: {}})
        r = self.drain("--once", env={"HERDR_FLAKY": "99"})
        self.assertEqual(r.returncode, 1)
        ended = self.ended_lines(r)
        self.assertEqual(len(ended), 1, r.stdout)
        self.assertIn("stopped", ended[0])

    def test_a_bundle_whose_dispatch_failed_after_the_claim_is_still_announced_before_it_ends(self):
        self.write_state({1: {"title": "first"}, 2: {"title": "second"}})
        r = self.drain("--once", env={"TAKE": "2", "DISPATCH_FAIL_AFTER_CLAIM": "1"})
        lines = [x for x in r.stdout.splitlines() if x.startswith("bundle ")]
        self.assertEqual([x.split(":")[0] for x in lines], ["bundle started", "bundle ended"], r.stdout)
        self.assertIn("#1 first", lines[0])
        self.assertIn("#2 second", lines[0])

    def test_a_refused_dispatch_announces_no_bundle(self):
        self.write_state({1: {}})
        r = self.drain(env={"DISPATCH_REFUSE": "1"})
        self.assertNotIn("bundle started:", r.stdout)
        self.assertNotIn("bundle ended:", r.stdout)

    def test_a_worker_still_working_is_waited_for_until_it_goes_idle(self):
        self.write_state({1: {}})
        r = self.drain("--once", env={"HERDR_WORKING_POLLS": "4"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([m[0] for m in self.state()["merged"]], [[1]])
        gets = [c for c in self.herdr_calls() if c[:2] == ["agent", "get"]]
        self.assertGreaterEqual(len(gets), 5)

    def test_an_idle_worker_with_no_pr_is_a_failed_build_not_a_wait_forever(self):
        self.write_state({1: {}})
        self.drain("--once", env={"FAIL_TICKETS": "1"})
        self.assertIn("is idle with no PR", self.handed_comment(1)[0])

    def test_a_worker_that_is_gone_with_no_pr_is_a_failed_build(self):
        self.write_state({1: {}})
        self.drain("--once", env={"FAIL_TICKETS": "1", "HERDR_GONE": "1"})
        self.assertIn("the worker repo-1 is gone", self.handed_comment(1)[0])
        self.assertFalse(any(c[:2] == ["agent", "prompt"] for c in self.herdr_calls()), "nothing to prompt")

    def test_a_herdr_that_cannot_be_asked_stops_the_run(self):
        self.write_state({1: {}})
        r = self.drain("--once", env={"HERDR_DOWN": "1"})
        self.assertEqual(r.returncode, 1)
        self.assertIn("stopped: herdr agent get repo-1 failed", r.stdout)
        self.assertNotIn("ready-for-human", self.labels(1))

    def test_a_light_tier_worker_that_landed_on_main_with_no_pr_is_a_merge(self):
        self.write_state({1: {}})
        r = self.drain("--once", env={"LIGHT": "1"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("#1  (landed on main, no PR)", r.stdout)
        self.assertIn("implement-1", read(self.cleanup_log))

    def test_a_rerun_with_a_gone_worker_and_no_pr_hands_the_ticket_over(self):
        self.write_state({1: {"labels": ["in-progress"]}, 2: {}}, comments=[["1", "drain anchor: implement-1"]])
        self.drain("--once", env={"HERDR_GONE": "1"})
        self.assertEqual(self.dispatch_runs(), [], "a resumed ticket is waited on, never dispatched twice")
        self.assertIn("ready-for-human", self.labels(1))

    def test_a_merged_ticket_the_open_list_still_carries_is_not_resumed(self):
        self.write_state({1: {}})
        r = self.drain(env={"STALE_LISTING": "1"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(self.dispatch_runs()), 1)
        self.assertEqual([m[0] for m in self.state()["merged"]], [[1]])
        self.assertEqual(len(self.ended_lines(r)), 1, r.stdout)
        self.assertNotIn("landed on main, no PR", r.stdout)

    def test_an_anchor_this_run_ended_is_not_resumed_even_when_its_reread_is_stale(self):
        self.write_state({1: {}})
        r = self.drain(env={"STALE_LISTING": "1", "STALE_VIEW": "1"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(self.ended_lines(r)), 1, r.stdout)
        self.assertNotIn("landed on main, no PR", r.stdout)

    def test_a_rerun_checks_an_open_pr_without_rebuilding(self):
        self.write_state({1: {"labels": ["in-progress"]}}, comments=[["1", "drain anchor: implement-1"]])
        wt = self.worktree(1)
        self.git(self.repo, "worktree", "add", "-q", "-b", "implement-1", wt, "origin/main")
        write(os.path.join(wt, "w.txt"), "w\n")
        self.git(wt, "add", ".")
        self.git(wt, "commit", "-qm", "worker commit")
        self.git(wt, "push", "-q", "origin", "HEAD:implement-1")
        st = self.state()
        st["prs"]["implement-1"] = {"number": 101, "url": "https://example.test/pull/101", "closes": [1],
                                    "head": self.git(wt, "rev-parse", "HEAD"), "draft": False, "status": "CLEAN"}
        self.save(st)
        r = self.drain("--once")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.dispatch_runs(), [])
        self.assertEqual([m[0] for m in self.state()["merged"]], [[1]])

    def test_a_live_workers_ticket_is_not_adopted(self):
        # In-progress with a worktree, but no drain anchor comment: a worker
        # `implement-dispatch` started. drain leaves it and takes ticket 2.
        self.write_state({1: {"labels": ["in-progress"]}, 2: {}})
        self.git(self.repo, "worktree", "add", "-q", "-b", "implement-1", self.worktree(1), "origin/main")
        self.drain("--once")
        self.assertEqual([c["n"] for c in self.dispatch_runs()], ["2"])
        self.assertEqual(self.labels(1), ["in-progress"])

    def test_a_ticket_drain_handed_to_chris_is_not_adopted_when_it_is_readied_again(self):
        self.write_state({1: {"labels": ["in-progress"]}},
                         comments=[["1", "drain anchor: implement-1"], ["1", "drain could not land this ticket (x)"]])
        self.git(self.repo, "worktree", "add", "-q", "-b", "implement-1", self.worktree(1), "origin/main")
        self.drain("--once")
        self.assertEqual(self.dispatch_runs(), [])
        self.assertEqual(self.labels(1), ["in-progress"])

    def test_a_failed_claim_comment_leaves_the_ticket_ready(self):
        self.write_state({1: {}})
        r = self.drain("--once", env={"FAIL_VERB": "comment"})
        self.assertEqual(self.labels(1), ["ready-for-agent"])
        self.assertIn("stopped:", r.stdout)

    def test_a_pr_closing_a_ticket_the_bundle_comment_does_not_name_is_a_failed_build(self):
        self.write_state({1: {}, 2: {}})
        self.drain("--once", env={"EXTRA_CLOSE": "2"})
        self.assertNotIn("merged", self.state())
        self.assertIn("which no drain bundle: comment on #1 names", self.handed_comment(1)[0])
        for n in (1, 2):
            self.assertIn("ready-for-human", self.labels(n))

    def test_a_ticket_another_worker_holds_is_not_touched_by_a_merge(self):
        self.write_state({1: {}, 2: {}, 3: {"labels": ["in-progress"], "assignees": ["me"]}})
        self.drain("--once", env={"TAKE": "2"})
        self.assertEqual(self.state()["merged"][0][0], [1, 2])
        self.assertEqual(self.labels(3), ["in-progress"])
        self.assertEqual(self.state()["issues"]["3"]["assignees"], ["me"])

    def test_the_lock_and_agent_names_match_implement_dispatch(self):
        # drain cannot import the Rust it mirrors; this pins what it copies.
        source = read(os.path.join(HERE, "..", "flow", "lane", "src", "bin", "implement_dispatch.rs"))
        sys.path.insert(0, HERE)
        import drain
        # The lock drain takes is the path implement_dispatch.rs formats, not a
        # name only the test knows: run drain's own lock under a scratch HOME and
        # compare the file it creates with the Rust format string.
        self.assertIn("{}/.implement-dispatch-claim-{}.lock", source)
        self.assertIn("slug.replace('/', \"__\")", source)
        import types
        home = tempfile.mkdtemp()
        old_home, os.environ["HOME"] = os.environ.get("HOME"), home
        try:
            with drain.claim_lock(types.SimpleNamespace(repo="owner/name")):
                pass
        finally:
            os.environ["HOME"] = old_home
        self.assertTrue(os.path.exists(os.path.join(home, ".implement-dispatch-claim-owner__name.lock")))
        # The worker's herdr agent name drain looks for is the one the Rust formats.
        self.assertIn("(32usize).saturating_sub(suffix.len())", source)
        self.assertIn('Mode::Plain => format!("-{n}")', source)

    def test_refuses_a_repo_the_user_does_not_own(self):
        self.write_state({1: {}})
        self.set_origin("someone-else/repo")
        r = self.drain("--once")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.dispatch_runs(), [])
        self.assertIn("someone-else", r.stderr)

    # --- #1415: targeted seam, one full run per drain run, --anchor ------------

    def seam_runs(self):
        return [x.rstrip() for x in read(self.seam_log).splitlines()] if os.path.exists(self.seam_log) else []

    def test_the_seam_is_skipped_when_main_has_not_moved_past_the_pr(self):
        self.write_state({1: {}, 2: {}})
        self.git(self.repo, "config", "land.testcmd", 'echo "$0" >> "$SEAM_LOG"')
        r = self.drain("--max", "2")
        self.assertEqual([m[0] for m in self.state()["merged"]], [[1], [2]])
        # Two bundles, neither with a moved main: the only run is the end-of-run full one.
        self.assertEqual(len(self.seam_runs()), 1, r.stdout)

    def test_the_default_seam_is_narrowed_with_changed_and_the_full_run_is_not(self):
        self.write_state({1: {}})
        os.makedirs(os.path.join(self.repo, "tests"))
        write(os.path.join(self.repo, "tests", "all.sh"), '#!/bin/sh\necho "all.sh $*" >> "$SEAM_LOG"\n', 0o755)
        self.git(self.repo, "add", ".")
        self.git(self.repo, "commit", "-qm", "gate")
        self.git(self.repo, "push", "-q", "origin", "main")
        self.git(self.repo, "config", "--unset", "land.testcmd")
        self.drain("--once", env={"RESET_TO_OLD": "1"})  # main moved: the per-merge check runs
        self.assertEqual(self.seam_runs(), ["all.sh --changed origin/main", "all.sh"])

    def lockfile_repo(self, lock=True):
        """A main with `package-lock.json` (or not), and an `npm` stub on PATH
        whose `ci` makes `node_modules` and logs the call; the seam command
        logs `seam` only when `node_modules` is there."""
        write(os.path.join(self.bin, "npm"),
              '#!/bin/sh\necho "npm $*" >> "$SEAM_LOG"\ntest "$NPM_RED" = 1 && exit 1\n'
              'test "$1" = ci && mkdir node_modules\n', 0o755)
        if lock:
            write(os.path.join(self.repo, "package-lock.json"), "{}\n")
            self.git(self.repo, "add", ".")
            self.git(self.repo, "commit", "-qm", "lockfile")
            self.git(self.repo, "push", "-q", "origin", "main")
        self.git(self.repo, "config", "land.testcmd", 'test -d node_modules && echo seam >> "$SEAM_LOG"')

    def test_a_lockfile_gets_its_dependencies_installed_before_the_seam_runs(self):
        self.write_state({1: {}})
        self.lockfile_repo()
        r = self.drain("--once", env={"RESET_TO_OLD": "1"})  # per-PR seam, then the full run
        self.assertEqual(self.seam_runs(), ["npm ci", "seam", "npm ci", "seam"], r.stdout)
        self.assertEqual([m[0] for m in self.state()["merged"]], [[1]])

    def test_a_repo_without_a_lockfile_installs_nothing(self):
        self.write_state({1: {}})
        self.lockfile_repo(lock=False)
        self.git(self.repo, "config", "land.testcmd", 'echo seam >> "$SEAM_LOG"')
        self.drain("--once", env={"RESET_TO_OLD": "1"})
        self.assertEqual(self.seam_runs(), ["seam", "seam"])

    def test_a_failed_install_is_a_failed_build_and_the_seam_never_runs(self):
        self.write_state({1: {}})
        self.lockfile_repo()
        self.git(self.repo, "config", "land.testcmd", 'echo seam >> "$SEAM_LOG"')  # logs even without node_modules
        self.drain("--once", env={"RESET_TO_OLD": "1", "NPM_RED": "1"})
        self.assertNotIn("merged", self.state())
        self.assertIn("`npm ci` failed", self.handed_comment(1)[0])
        runs = self.seam_runs()  # a ticket gets two tries
        self.assertTrue(runs and set(runs) == {"npm ci"}, runs)

    def test_a_failed_install_before_the_full_run_stops_the_run_red(self):
        self.write_state({1: {}})
        self.lockfile_repo()
        self.git(self.repo, "config", "land.testcmd", 'echo seam >> "$SEAM_LOG"')
        r = self.drain("--once", env={"NPM_RED": "1"})  # main has not moved: only the full run installs
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("stopped: the full suite is red on main", r.stdout)
        self.assertEqual(self.seam_runs(), ["npm ci"])

    def test_an_npm_that_cannot_start_is_a_failed_build_not_a_crash(self):
        self.write_state({1: {}})
        self.lockfile_repo()
        os.remove(os.path.join(self.bin, "npm"))
        self.drain("--once", env={"RESET_TO_OLD": "1", "PATH": self.bin + os.pathsep + "/usr/bin" + os.pathsep + "/bin"})
        self.assertNotIn("merged", self.state())
        self.assertIn("`npm ci` could not start", self.handed_comment(1)[0])

    def test_one_full_run_after_the_last_bundle_and_a_red_one_stops_with_the_merges_named(self):
        self.write_state({1: {}, 2: {}})
        self.git(self.repo, "config", "land.testcmd", 'echo run >> "$SEAM_LOG"; test -z "$SEAM_RED"')
        r = self.drain("--max", "2", env={"SEAM_RED": "1"})
        self.assertEqual([m[0] for m in self.state()["merged"]], [[1], [2]], "both merges landed before the full run")
        self.assertEqual(len(self.seam_runs()), 1)
        self.assertEqual(r.returncode, 1)
        self.assertIn("stopped: the full suite is red on main", r.stdout)
        for url in ("https://example.test/pull/101", "https://example.test/pull/102"):
            self.assertIn(url, r.stdout)

    def test_a_green_full_run_records_main_and_a_later_red_one_names_the_merges_since(self):
        self.write_state({1: {}, 2: {}})
        self.git(self.repo, "config", "land.testcmd", 'test -z "$SEAM_RED"')
        self.assertEqual(self.drain("--once").returncode, 0)
        green = read(os.path.join(self.tmp.name, "logs", "last-green-me__repo")).strip()
        self.assertEqual(green, self.git(self.repo, "rev-parse", "origin/main"))
        # Two merges land on main since that green run (the fake `gh` never moves main itself).
        for subject in ("first other merge", "second other merge"):
            self.git(self.repo, "commit", "-q", "--allow-empty", "-m", subject)
        self.git(self.repo, "push", "-q", "origin", "main")
        r = self.drain("--once", env={"SEAM_RED": "1"})
        self.assertIn("stopped: the full suite is red on main", r.stdout)
        self.assertIn("Merges since the last green full run: ", r.stdout)
        # Named from last-green's sha, not just this run's own merge: with the file unread
        # the list would hold only the PR url.
        for subject in ("first other merge", "second other merge"):
            self.assertIn(subject, r.stdout)

    def test_no_merge_means_no_full_run(self):
        self.write_state({})
        self.git(self.repo, "config", "land.testcmd", 'echo run >> "$SEAM_LOG"')
        self.drain()
        self.assertEqual(self.seam_runs(), [])

    def test_anchor_starts_the_bundle_from_that_ticket_and_only_the_first(self):
        self.write_state({1: {}, 2: {}, 3: {}})
        r = self.drain("--anchor", "3", "--max", "2")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([c["n"] for c in self.dispatch_runs()], ["3", "1"])
        self.assertEqual([c["tickets"] for c in self.dispatch_runs()], [["3"], ["1"]])

    def test_anchor_that_is_not_ready_or_is_blocked_is_refused_before_any_work(self):
        self.write_state({1: {}, 2: {"labels": ["in-progress"]}, 3: {"body": "## Blocked by\n\n- #1\n"}})
        for n in ("2", "3", "9"):
            r = self.drain("--anchor", n)
            self.assertEqual(r.returncode, 1, n)
            self.assertIn(f"--anchor #{n} is not an open, ready, unblocked ticket", r.stdout)
        self.assertEqual(self.dispatch_runs(), [])
        self.assertEqual(self.labels(1), ["ready-for-agent"])

    def test_a_ready_slice_is_never_the_anchor_and_never_joins_a_bundle(self):
        # Ruling 7 of #1457: a slice is built inside its spec run only, even
        # one older than every lone ticket and one the chooser asks for.
        spec = {"labels": ["spec"], "body": "the spec"}
        self.write_state({1: {"parent": 9}, 2: {}, 3: {"parent": 9}, 4: {}, 9: spec})
        r = self.drain("--once", env={"TAKE": "3"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([c["tickets"] for c in self.dispatch_runs()], [["2"]])
        prompt = self.chooser_runs()[0]["prompt"]
        self.assertIn("#2 is the anchor", prompt)
        self.assertIn("- #4 ticket 4", prompt)
        self.assertNotIn("#1 ", prompt)
        self.assertNotIn("#3 ", prompt)
        self.assertEqual(self.labels(1), ["ready-for-agent"])
        self.assertEqual(self.labels(3), ["ready-for-agent"])
        r = self.drain("--anchor", "3")
        self.assertEqual(r.returncode, 1)
        self.assertIn("--anchor #3 is not an open, ready, unblocked ticket", r.stdout)

    # --- review fixes (#1415) --------------------------------------------------

    def test_a_failed_check_prompts_the_worker_with_the_reason_and_waits_for_it_to_start_working(self):
        self.write_state({1: {}})
        self.drain("--once", env={"DRAFT_TICKETS": "1"})
        prompts = [c for c in self.herdr_calls() if c[:2] == ["agent", "prompt"]]
        self.assertEqual(len(prompts), 1)
        self.assertIn("the PR is up but drain's check of it failed", prompts[0][3])
        self.assertIn("still a draft", prompts[0][3])
        self.assertEqual(prompts[0][4:7], ["--wait", "--until", "working"])

    def test_a_missing_pr_prompts_with_the_reason_it_is_not_up(self):
        self.write_state({1: {}})
        self.drain("--once", env={"FAIL_TICKETS": "1"})
        prompt = next(c for c in self.herdr_calls() if c[:2] == ["agent", "prompt"])
        self.assertIn("the PR is not up yet", prompt[3])
        self.assertIn("is idle with no PR", prompt[3])

    def test_a_blocked_worker_is_a_failed_build_not_a_wait_for_the_wall_clock(self):
        self.write_state({1: {}})
        self.drain("--once", env={"FAIL_TICKETS": "1", "HERDR_STATUS": "blocked"})
        self.assertIn("is blocked with no PR", self.handed_comment(1)[0])

    def test_a_bundle_handed_to_chris_closes_its_workers_pane(self):
        self.write_state({1: {}})
        self.drain("--once", env={"FAIL_TICKETS": "1"})
        self.assertIn(["pane", "close", "w9:p1"], self.herdr_calls())

    def test_a_ticket_whose_workspace_is_kept_is_not_picked_and_an_anchor_naming_it_is_refused(self):
        self.write_state({1: {}, 2: {}})
        self.git(self.repo, "worktree", "add", "-q", "-b", "implement-1", self.worktree(1), "origin/main")
        r = self.drain("--anchor", "1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("--anchor #1 is not an open, ready, unblocked ticket without a kept workspace", r.stdout)
        self.assertEqual(self.dispatch_runs(), [])
        self.drain("--once")
        self.assertEqual([c["n"] for c in self.dispatch_runs()], ["2"])

    def test_a_transient_look_failure_does_not_fail_the_build(self):
        self.write_state({1: {}})
        r = self.drain("--once", env={"HERDR_FLAKY": "2"})
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual([m[0] for m in self.state()["merged"]], [[1]])

    def test_a_dispatch_that_fails_after_the_claim_is_this_bundles_failed_build(self):
        self.write_state({1: {}, 2: {}})
        r = self.drain("--once", env={"DISPATCH_FAIL_AFTER_CLAIM": "1", "HERDR_GONE": "1"})
        self.assertNotIn("stopped", r.stdout)
        self.assertEqual(len(self.dispatch_runs()), 1, "a failure after the claim is not retried by dispatching again")
        self.assertIn("ready-for-human", self.labels(1))
        self.assertEqual(self.handed_comment(1)[0].count("Last failure"), 1)

    def test_a_drain_run_from_a_linked_worktree_names_the_primary_checkout(self):
        self.write_state({1: {}})
        linked = os.path.join(self.tmp.name, "linked")
        self.git(self.repo, "worktree", "add", "-q", "--detach", linked, "origin/main")
        r = self.drain("--once", "--repo", linked)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.dispatch_runs()[0]["argv"][:2], ["--repo", self.repo])
        self.assertIn(["agent", "get", "repo-1"], self.herdr_calls())

    def test_an_empty_queue_says_so(self):
        r = self.drain()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "nothing to drain")
        self.assertEqual(self.dispatch_runs(), [])


class WaitTest(Sandbox):
    """`wait_for_worker`'s wall clock, in-process: a three-hour clock has no
    command-line witness."""

    def setUp(self):
        super().setUp()
        import drain
        self.drain_mod = drain
        self.old = (drain.WALL_CLOCK_SECONDS, drain.POLL_SECONDS, drain.agent_status)

    def tearDown(self):
        self.drain_mod.WALL_CLOCK_SECONDS, self.drain_mod.POLL_SECONDS, self.drain_mod.agent_status = self.old
        super().tearDown()

    def test_a_worker_that_never_goes_idle_fails_at_the_wall_clock(self):
        self.drain_mod.WALL_CLOCK_SECONDS, self.drain_mod.POLL_SECONDS = 0.3, 0.05
        self.drain_mod.agent_status = lambda name: "working"
        with self.assertRaises(self.drain_mod.DrainError) as caught:
            self.drain_mod.wait_for_worker(None, "implement-1", "repo-1", [1])
        self.assertIn("passed the 0.3s wall clock", str(caught.exception))

    def test_run_group_kills_what_a_command_started(self):
        pidfile = os.path.join(self.tmp.name, "pid")
        with self.assertRaises(self.drain_mod.DrainError):
            self.drain_mod.run_group(["sh", "-c", f"sleep 30 & echo $! > {pidfile}; sleep 30"], self.tmp.name, 1)
        pid = int(read(pidfile))
        for _ in range(30):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.1)
        self.fail("the command's grandchild survived the wall clock")


if __name__ == "__main__":
    unittest.main()
