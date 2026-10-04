#!/usr/bin/env python3
"""Tests for `drain` (#1403). Seam: the command line, `drain.py [--once]
[--max n] [--bundle-max k] [--repo path]`, run as a subprocess against a real
git repo with a bare origin, a fake `gh` (a JSON state file), a stub `claude`
that acts as the agent (picks a bundle, claims it, commits, pushes, opens a
PR), and a stub `merge-cleanup`. Each case is a queue in, labels / merges /
summary out. `HOME` and the global git config are the test's own, so no case
reads the real ones. A last class tests the two process helpers (`build`'s
caps, `run_group`'s group kill) in-process, since a three-hour clock has no
command-line witness.
"""
import json
import os
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
if args[:2] == ["issue", os.environ.get("FAIL_VERB")]:
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
                  for n, i in state["issues"].items() if i["state"] == "open" and label in i["labels"]]
        for t in os.environ.get("TAKE_AFTER_PICK", "").split() if label == "ready-for-agent" else []:
            if "ready-for-agent" in state["issues"][t]["labels"]:
                state["issues"][t]["labels"].remove("ready-for-agent")
                state["issues"][t]["labels"].append("in-progress")
                save()
        out([issues])
    elif m and m.group(2):
        sys.stderr.write("gh: Not Found (HTTP 404)\n"); sys.exit(1)
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
    out({"state": issue["state"], "labels": names(issue),
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

# Acts as the agent. Builds the anchor named on the /implement line plus the
# tickets in TAKE (claims each, records `drain bundle:` on the anchor), unless
# the anchor is in FAIL_TICKETS (exit 1, no PR). Knobs: DRAFT_TICKETS, STATUS
# (merge state), NO_ANCHOR / UNCLOSED (what the PR's closing keywords leave
# out), RESET_TO_OLD (build on the commit before main's tip), MESSY_NOTE (a
# multi-line, punctuated bundle comment), NO_NOTE (claims, posts none), STUB_SLEEP (hang, with a grandchild).
STUB_CLAUDE = r"""#!/usr/bin/env python3
import json, os, resource, subprocess, sys, time
prompt = sys.argv[sys.argv.index("-p") + 1]
n = prompt.split("--tier")[0].split()[1]
env = os.environ
take = env.get("TAKE", "").split()
with open(env["CLAUDE_LOG"], "a") as f:
    f.write(json.dumps({"n": n, "prompt": prompt, "cwd": os.getcwd(), "argv": sys.argv[1:],
                        "as_limit": resource.getrlimit(resource.RLIMIT_AS)[0]}) + "\n")
if env.get("STUB_SLEEP"):
    open(env["PIDFILE"], "w").write(str(subprocess.Popen(["sleep", "30"]).pid))
    time.sleep(30)
if n in env.get("FAIL_TICKETS", "").split():
    sys.exit(1)
st = json.load(open(env["FAKE_STATE"]))
for t in take:
    labels = st["issues"][t]["labels"]
    if "ready-for-agent" in labels:
        labels.remove("ready-for-agent")
        labels.append("in-progress")
        st["issues"][t].setdefault("assignees", []).append("me")
if take and not env.get("NO_NOTE"):
    note = "drain bundle: " + " ".join([n] + take)
    if env.get("MESSY_NOTE"):
        note = "drain bundle: " + ", ".join([n] + take[:-1]) + ",\nand " + take[-1] + "."
    st.setdefault("comments", []).append([n, note])
json.dump(st, open(env["FAKE_STATE"], "w"))
if env.get("RESET_TO_OLD"):
    subprocess.run(["git", "reset", "-q", "--hard", "HEAD~1"], check=True)
branch = "implement-" + n
open("work-%s.txt" % n, "w").write("built\n")
subprocess.run(["git", "add", "."], check=True)
subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "build %s" % n], check=True)
subprocess.run(["git", "push", "-q", "-f", "origin", "HEAD:" + branch], check=True)
head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
closes = ([] if env.get("NO_ANCHOR") else [int(n)]) + ([] if env.get("UNCLOSED") else [int(t) for t in take])
st = json.load(open(env["FAKE_STATE"]))
st["prs"][branch] = {"number": 100 + int(n), "url": "https://example.test/pull/%d" % (100 + int(n)),
                     "head": head, "closes": closes, "draft": n in env.get("DRAFT_TICKETS", "").split(),
                     "status": env.get("STATUS", "CLEAN")}
json.dump(st, open(env["FAKE_STATE"], "w"))
"""

STUB_CLEANUP = """#!/bin/sh
echo "$@" >> "$CLEANUP_LOG"
[ -z "$CLEANUP_FAIL" ] || { echo "cleanup exploded" >&2; exit 1; }
"""

HOOKS = ("pre-commit", "pre-push", "commit-identity-guard", "commit-identity-guard-pre-push")


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
        for name, body in (("gh", FAKE_GH), ("claude", STUB_CLAUDE), ("merge-cleanup", STUB_CLEANUP)):
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
        self.hooks = self.git(self.repo, "rev-parse", "--path-format=absolute", "--git-path", "hooks")
        os.makedirs(self.hooks, exist_ok=True)
        for h in HOOKS:
            write(os.path.join(self.hooks, h), "#!/bin/sh\nexit 0\n", 0o755)
        self.state_path = os.path.join(t, "state.json")
        self.claude_log = os.path.join(t, "claude.log")
        self.cleanup_log = os.path.join(t, "cleanup.log")
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

    def drain(self, *argv, env=None):
        e = {**self.env, "PATH": self.bin + os.pathsep + os.environ["PATH"], "FAKE_STATE": self.state_path,
             "CLAUDE_LOG": self.claude_log, "CLEANUP_LOG": self.cleanup_log,
             "DRAIN_LOG_DIR": os.path.join(self.tmp.name, "logs"), **(env or {})}
        return subprocess.run([sys.executable, DRAIN, "--repo", self.repo, *argv],
                              capture_output=True, text=True, env=e)

    def claude_runs(self):
        return [json.loads(line) for line in read(self.claude_log).splitlines()] if os.path.exists(self.claude_log) else []

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
        run = self.claude_runs()[0]
        self.assertTrue(run["cwd"].endswith(".claude/worktrees/implement-1"))
        self.assertEqual(run["argv"][0], "-p")
        self.assertEqual(run["argv"][2:], ["--permission-mode", "auto"])
        self.assertEqual(run["as_limit"], 32 << 30)
        tracking = subprocess.run(["git", "config", "--get", "branch.implement-1.remote"], cwd=self.repo,
                                  capture_output=True, text=True, env=self.env)
        self.assertEqual(tracking.stdout, "", "the workspace branch must not track a remote")
        self.assertIn("merged:\n  #1  https://example.test/pull/101  m" + st["merged"][0][1], r.stdout)

    def test_the_agents_bundle_is_one_pr_and_the_rest_stay_ready(self):
        self.write_state({1: {}, 2: {}, 3: {}, 4: {}})
        r = self.drain("--once", env={"TAKE": "2 3"})
        self.assertEqual(r.returncode, 0, r.stderr)
        st = self.state()
        self.assertEqual(st["merged"][0][0], [1, 2, 3])
        self.assertEqual([i["state"] for i in st["issues"].values()], ["closed"] * 3 + ["open"])
        self.assertEqual(self.labels(4), ["ready-for-agent"])
        prompt = self.claude_runs()[0]["prompt"]
        self.assertTrue(prompt.startswith("/implement 1 --tier heavy"))
        for line in ("- #2 ticket 2", "- #3 ticket 3", "- #4 ticket 4", "at most 8 tickets",
                     "one commit per ticket", "file no leftover or sweep ticket", "First post one comment on #1"):
            self.assertIn(line, prompt)
        self.assertIn("#1 #2 #3", r.stdout)

    def test_max_counts_tickets_not_bundles(self):
        # The first bundle holds two tickets, so --max 2 is spent; counting
        # bundles it would go on to build ticket 3.
        self.write_state({1: {}, 2: {}, 3: {}, 4: {}})
        self.drain("--max", "2", env={"TAKE": "2"})
        self.assertEqual([m[0] for m in self.state()["merged"]], [[1, 2]])
        self.assertEqual(self.labels(3), ["ready-for-agent"])

    def test_a_bundle_max_below_one_is_refused(self):
        self.write_state({1: {}})
        self.assertNotEqual(self.drain("--bundle-max", "0").returncode, 0)
        self.assertEqual(self.claude_runs(), [])

    def test_a_pr_over_bundle_max_is_a_failed_build(self):
        self.write_state({1: {}, 2: {}, 3: {}})
        self.drain("--once", "--bundle-max", "2", env={"TAKE": "2 3"})
        self.assertNotIn("merged", self.state())
        self.assertIn("at most 2 tickets", self.claude_runs()[0]["prompt"])
        self.assertIn("over --bundle-max 2", self.handed_comment(1)[0])

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
        self.assertEqual([c["n"] for c in self.claude_runs()], ["1", "1", "2"])

    def test_a_pr_that_is_not_clean_is_a_failed_build(self):
        self.write_state({1: {}})
        self.drain("--once", env={"STATUS": "BLOCKED"})
        self.assertNotIn("merged", self.state())
        self.assertIn("BLOCKED, not CLEAN", self.handed_comment(1)[0])

    def test_a_red_seam_is_a_failed_build(self):
        self.write_state({1: {}})
        self.git(self.repo, "config", "land.testcmd", "false")
        self.drain("--once")
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
        self.assertEqual([c["n"] for c in self.claude_runs()], ["4"])

    def test_a_ticket_taken_since_the_pick_is_not_claimed_over(self):
        self.write_state({1: {}, 2: {}})
        self.drain("--once", env={"TAKE_AFTER_PICK": "1"})
        self.assertEqual([c["n"] for c in self.claude_runs()], ["2"])
        self.assertIn("in-progress", self.labels(1))

    def test_a_merge_cleanup_failure_is_a_note_not_a_rebuild(self):
        self.write_state({1: {}})
        r = self.drain("--once", env={"CLEANUP_FAIL": "1"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(self.claude_runs()), 1)
        self.assertIn("merge-cleanup failed: cleanup exploded", r.stdout)
        self.assertEqual([m[0] for m in self.state()["merged"]], [[1]])

    def test_a_messy_bundle_comment_still_hands_every_claimed_ticket_over(self):
        self.write_state({1: {}, 2: {}, 3: {}})
        self.drain("--once", env={"TAKE": "2 3", "MESSY_NOTE": "1", "DRAFT_TICKETS": "1"})
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

    def test_a_workspace_failure_hands_the_ticket_over_instead_of_stranding_it(self):
        self.write_state({1: {}})
        self.set_origin("me/repo", serves=os.path.join(self.tmp.name, "gone.git"))
        r = self.drain("--once")
        self.assertIn("ready-for-human", self.labels(1))
        self.assertIn("handed to Chris", r.stdout)
        self.assertEqual(self.claude_runs(), [])

    def test_a_rerun_resumes_a_killed_claim_that_has_no_worktree_yet(self):
        self.write_state({1: {"labels": ["in-progress"]}, 2: {}}, comments=[["1", "drain anchor: implement-1"]])
        self.drain("--once")
        self.assertEqual([c["n"] for c in self.claude_runs()], ["1"])
        self.assertEqual([m[0] for m in self.state()["merged"]], [[1]])

    def test_a_rerun_resumes_a_worktree_with_no_pr_by_building_in_it(self):
        self.write_state({1: {"labels": ["in-progress"]}}, comments=[["1", "drain anchor: implement-1"]])
        self.git(self.repo, "worktree", "add", "-q", "-b", "implement-1", self.worktree(1), "origin/main")
        r = self.drain("--once")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([c["n"] for c in self.claude_runs()], ["1"])
        self.assertEqual([m[0] for m in self.state()["merged"]], [[1]])

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
        self.assertEqual(self.claude_runs(), [])
        self.assertEqual([m[0] for m in self.state()["merged"]], [[1]])

    def test_a_live_workers_ticket_is_not_adopted(self):
        # In-progress with a worktree, but no drain anchor comment: a worker
        # `implement-dispatch` started. drain leaves it and takes ticket 2.
        self.write_state({1: {"labels": ["in-progress"]}, 2: {}})
        self.git(self.repo, "worktree", "add", "-q", "-b", "implement-1", self.worktree(1), "origin/main")
        self.drain("--once")
        self.assertEqual([c["n"] for c in self.claude_runs()], ["2"])
        self.assertEqual(self.labels(1), ["in-progress"])

    def test_a_process_still_running_in_the_worktree_stops_the_run(self):
        self.write_state({1: {"labels": ["in-progress"]}}, comments=[["1", "drain anchor: implement-1"]])
        self.git(self.repo, "worktree", "add", "-q", "-b", "implement-1", self.worktree(1), "origin/main")
        sleeper = subprocess.Popen(["sleep", "30"], cwd=self.worktree(1))
        try:
            r = self.drain("--once")
        finally:
            sleeper.kill()
            sleeper.wait()
        self.assertEqual(r.returncode, 1)
        self.assertIn("a process is still running in", r.stdout)
        self.assertEqual(self.claude_runs(), [])
        self.assertEqual(self.labels(1), ["in-progress"])

    def test_a_ticket_drain_handed_to_chris_is_not_adopted_when_it_is_readied_again(self):
        self.write_state({1: {"labels": ["in-progress"]}},
                         comments=[["1", "drain anchor: implement-1"], ["1", "drain could not land this ticket (x)"]])
        self.git(self.repo, "worktree", "add", "-q", "-b", "implement-1", self.worktree(1), "origin/main")
        self.drain("--once")
        self.assertEqual(self.claude_runs(), [])
        self.assertEqual(self.labels(1), ["in-progress"])

    def test_a_failed_claim_comment_leaves_the_ticket_ready(self):
        self.write_state({1: {}})
        r = self.drain("--once", env={"FAIL_VERB": "comment"})
        self.assertEqual(self.labels(1), ["ready-for-agent"])
        self.assertIn("stopped:", r.stdout)

    def test_a_pr_closing_a_ticket_the_bundle_comment_does_not_name_is_a_failed_build(self):
        self.write_state({1: {}, 2: {}})
        self.drain("--once", env={"TAKE": "2", "NO_NOTE": "1"})
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

    def test_the_guard_and_lock_names_match_implement_dispatch(self):
        # drain cannot import the Rust constants it mirrors; this pins them.
        source = read(os.path.join(HERE, "..", "flow", "lane", "src", "bin", "implement_dispatch.rs"))
        sys.path.insert(0, HERE)
        import drain
        for name in drain.GUARD_HOOKS:
            self.assertIn(f'"{name}"', source)
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

    def test_refuses_a_repo_the_user_does_not_own(self):
        self.write_state({1: {}})
        self.set_origin("someone-else/repo")
        r = self.drain("--once")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.claude_runs(), [])
        self.assertIn("someone-else", r.stderr)

    def test_refuses_a_repo_without_the_commit_identity_guard(self):
        self.write_state({1: {}})
        os.remove(os.path.join(self.hooks, "commit-identity-guard"))
        r = self.drain("--once")
        self.assertEqual(r.returncode, 1)
        self.assertIn("stopped: the commit-identity guard is not installed", r.stdout)
        self.assertNotIn("unexpected", r.stdout)
        self.assertEqual(self.claude_runs(), [])
        self.assertEqual(self.labels(1), ["ready-for-agent"])

    def test_an_empty_queue_says_so(self):
        r = self.drain()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "nothing to drain")
        self.assertEqual(self.claude_runs(), [])


class ProcessTest(Sandbox):
    """`build`'s wall clock and `run_group`'s group kill, in-process."""

    def setUp(self):
        super().setUp()
        import drain
        self.drain_mod = drain
        keys = ("PATH", "CLAUDE_LOG", "PIDFILE", "STUB_SLEEP")
        self.old = {k: os.environ.get(k) for k in keys}
        self.old_clock = drain.WALL_CLOCK_SECONDS

    def tearDown(self):
        for key, value in self.old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.drain_mod.WALL_CLOCK_SECONDS = self.old_clock
        super().tearDown()

    def gone_soon(self, pid):
        for _ in range(30):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return True
            time.sleep(0.1)
        return False

    def test_the_wall_clock_kills_the_builds_whole_process_group(self):
        pidfile = os.path.join(self.tmp.name, "pid")
        os.environ.update(PATH=self.bin + os.pathsep + os.environ["PATH"], CLAUDE_LOG=self.claude_log,
                          PIDFILE=pidfile, STUB_SLEEP="1")
        self.drain_mod.WALL_CLOCK_SECONDS = 1
        with self.assertRaises(self.drain_mod.DrainError) as caught:
            self.drain_mod.build(self.tmp.name, "/implement 1 --tier heavy", os.path.join(self.tmp.name, "b.log"))
        self.assertIn("passed the 1s wall clock", str(caught.exception))
        self.assertTrue(self.gone_soon(int(read(pidfile))), "the build's grandchild survived the wall clock")

    def test_run_group_kills_what_a_command_started(self):
        pidfile = os.path.join(self.tmp.name, "pid")
        with self.assertRaises(self.drain_mod.DrainError):
            self.drain_mod.run_group(["sh", "-c", f"sleep 30 & echo $! > {pidfile}; sleep 30"], self.tmp.name, 1)
        self.assertTrue(self.gone_soon(int(read(pidfile))))


if __name__ == "__main__":
    unittest.main()
