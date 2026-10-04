#!/usr/bin/env python3
"""Tests for `drain` (#1403). Seam: the command line, `drain.py [--once]
[--max n] [--repo path]`, run as a subprocess against a real git repo with a
bare origin, a fake `gh` (a JSON state file), a stub `claude` that builds a
ticket the way a worker would (commit, push, open a PR), and a stub
`merge-cleanup`. Each case is a queue in, labels / merges / summary out.
"""
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
DRAIN = os.path.join(HERE, "drain.py")

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
state.setdefault("log", []).append(args)
if args[:2] == ["repo", "view"]:
    print(state["repo"])
elif args[:2] == ["api", "user"]:
    print(state["login"])
elif args[0] == "api":
    url = args[-1]
    m = re.search(r"/issues/(\d+)(/parent)?$", url)
    if "--paginate" in args:
        label = re.search(r"labels=([^&]+)", url).group(1)
        issues = [dict(number=int(n), title=i["title"], body=i["body"], state="open",
                       labels=[dict(name=x) for x in i["labels"]])
                  for n, i in state["issues"].items()
                  if i["state"] == "open" and label in i["labels"]]
        out([issues])
    elif m and m.group(2):
        sys.stderr.write("gh: Not Found (HTTP 404)\n"); sys.exit(1)
    elif m:
        out({"state": state["issues"][m.group(1)]["state"]})
elif args[:2] == ["issue", "edit"]:
    issue = state["issues"][args[2]]
    for i, a in enumerate(args):
        if a == "--add-label" and args[i + 1] not in issue["labels"]:
            issue["labels"].append(args[i + 1])
        if a == "--remove-label" and args[i + 1] in issue["labels"]:
            issue["labels"].remove(args[i + 1])
    save()
elif args[:2] == ["issue", "comment"]:
    state.setdefault("comments", []).append([args[2], opt("--body")])
    save()
elif args[:2] == ["issue", "view"]:
    issue = state["issues"][args[2]]
    out({"state": issue["state"], "labels": [dict(name=x) for x in issue["labels"]],
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

# Acts as the agent: builds the anchor named in the prompt plus the tickets in
# TAKE (claims each, records `drain bundle:` on the anchor), unless the anchor
# is in FAIL_TICKETS (exit 1, no PR). DRAFT_TICKETS opens a draft PR; NO_ANCHOR
# makes the PR close only the taken tickets; UNCLOSED leaves taken tickets out
# of the PR's closing keywords.
STUB_CLAUDE = r'''#!/usr/bin/env python3
import json, os, subprocess, sys
prompt = sys.argv[sys.argv.index("-p") + 1]
n = prompt.split("--tier")[0].split()[1]
env = os.environ
take = env.get("TAKE", "").split()
with open(env["CLAUDE_LOG"], "a") as f:
    f.write(json.dumps({"n": n, "prompt": prompt, "cwd": os.getcwd(), "argv": sys.argv[1:]}) + "\n")
if n in env.get("FAIL_TICKETS", "").split():
    sys.exit(1)
st = json.load(open(env["FAKE_STATE"]))
for t in take:
    labels = st["issues"][t]["labels"]
    if "ready-for-agent" in labels:
        labels.remove("ready-for-agent")
        labels.append("in-progress")
if take:
    st.setdefault("comments", []).append([n, "drain bundle: " + " ".join([n] + take)])
json.dump(st, open(env["FAKE_STATE"], "w"))
branch = "implement-" + n
open("work-%s.txt" % n, "w").write("built\n")
subprocess.run(["git", "add", "."], check=True)
subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "build %s" % n], check=True)
subprocess.run(["git", "push", "-q", "origin", "HEAD:" + branch], check=True)
head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
closes = ([] if env.get("NO_ANCHOR") else [int(n)]) + ([] if env.get("UNCLOSED") else [int(t) for t in take])
st = json.load(open(env["FAKE_STATE"]))
st["prs"][branch] = {"number": 100 + int(n), "url": "https://example.test/pull/%d" % (100 + int(n)),
                     "head": head, "closes": closes, "draft": n in env.get("DRAFT_TICKETS", "").split(),
                     "status": "CLEAN"}
json.dump(st, open(env["FAKE_STATE"], "w"))
'''

STUB_CLEANUP = '''#!/bin/sh
echo "$@" >> "$CLEANUP_LOG"
'''


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


class DrainTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.bin = os.path.join(t, "bin")
        os.mkdir(self.bin)
        for name, body in (("gh", FAKE_GH), ("claude", STUB_CLAUDE), ("merge-cleanup", STUB_CLEANUP)):
            p = os.path.join(self.bin, name)
            with open(p, "w") as f:
                f.write(body)
            os.chmod(p, 0o755)
        origin = os.path.join(t, "origin.git")
        self.repo = os.path.join(t, "repo")
        git(t, "init", "-q", "--bare", "-b", "main", origin)
        git(t, "clone", "-q", origin, self.repo)
        for k, v in (("user.email", "t@example.test"), ("user.name", "t")):
            git(self.repo, "config", k, v)
        git(self.repo, "checkout", "-q", "-b", "main")
        with open(os.path.join(self.repo, "README"), "w") as f:
            f.write("x\n")
        for d, f in (("alpha", "a.py"), ("alpha", "b.py"), ("alpha", "c.py"), ("beta", "d.py")):
            os.makedirs(os.path.join(self.repo, d), exist_ok=True)
            with open(os.path.join(self.repo, d, f), "w") as fh:
                fh.write("x\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "init")
        git(self.repo, "push", "-q", "origin", "main")
        git(self.repo, "remote", "set-head", "origin", "main")
        git(self.repo, "config", "land.testcmd", "true")
        self.state_path = os.path.join(t, "state.json")
        self.claude_log = os.path.join(t, "claude.log")
        self.cleanup_log = os.path.join(t, "cleanup.log")
        self.write_state(issues={}, repo="me/repo", login="me")

    def tearDown(self):
        self.tmp.cleanup()

    def write_state(self, issues, repo="me/repo", login="me", prs=None):
        full = {n: {"title": f"ticket {n}", "state": "open",
                    "body": "## Blocked by\n\n- None\n", "labels": ["ready-for-agent"], **i}
                for n, i in issues.items()}
        with open(self.state_path, "w") as f:
            json.dump({"repo": repo, "login": login, "issues": {str(k): v for k, v in full.items()},
                       "prs": prs or {}}, f)

    def read(self, path):
        with open(path) as f:
            return f.read()

    def save(self, st):
        with open(self.state_path, "w") as f:
            json.dump(st, f)

    def state(self):
        with open(self.state_path) as f:
            return json.load(f)

    def drain(self, *argv, env=None):
        e = {**os.environ, "PATH": self.bin + os.pathsep + os.environ["PATH"],
             "FAKE_STATE": self.state_path, "CLAUDE_LOG": self.claude_log,
             "CLEANUP_LOG": self.cleanup_log, "DRAIN_LOG_DIR": os.path.join(self.tmp.name, "logs"),
             **(env or {})}
        return subprocess.run([sys.executable, DRAIN, "--repo", self.repo, *argv],
                              capture_output=True, text=True, env=e)

    def claude_runs(self):
        if not os.path.exists(self.claude_log):
            return []
        with open(self.claude_log) as f:
            return [json.loads(line) for line in f]

    def test_once_builds_checks_merges_and_cleans_up(self):
        self.write_state({1: {}, 2: {}})
        r = self.drain("--once")
        self.assertEqual(r.returncode, 0, r.stderr)
        st = self.state()
        self.assertEqual([m[0] for m in st["merged"]], [[1]])  # oldest only
        self.assertEqual(st["issues"]["2"]["labels"], ["ready-for-agent"])
        self.assertIn("implement-1", self.read(self.cleanup_log))
        run = self.claude_runs()[0]
        self.assertTrue(run["cwd"].endswith(".claude/worktrees/implement-1"))
        self.assertNotIn("--dangerously-skip-permissions", run["argv"])
        self.assertIn("merged", r.stdout)
        self.assertIn("m" + st["merged"][0][1], r.stdout)

    def test_two_failed_builds_hand_the_ticket_to_chris_and_move_on(self):
        self.write_state({1: {}, 2: {}})
        r = self.drain("--max", "2", env={"FAIL_TICKETS": "1"})
        self.assertEqual(r.returncode, 0, r.stderr)
        st = self.state()
        self.assertIn("ready-for-human", st["issues"]["1"]["labels"])
        self.assertNotIn("in-progress", st["issues"]["1"]["labels"])
        self.assertTrue(any(n == "1" and "could not land" in b for n, b in st["comments"]))
        self.assertEqual([m[0] for m in st["merged"]], [[2]])
        self.assertEqual([c["n"] for c in self.claude_runs()], ["1", "1", "2"])
        self.assertIn("handed to Chris:\n  #1", r.stdout)

    def test_a_draft_pr_is_a_failed_build(self):
        self.write_state({1: {}})
        r = self.drain("--once", env={"DRAFT_TICKETS": "1"})
        st = self.state()
        self.assertNotIn("merged", st)
        self.assertIn("ready-for-human", st["issues"]["1"]["labels"])
        self.assertIn("draft", st["comments"][-1][1].lower())

    def test_a_red_seam_is_a_failed_build(self):
        self.write_state({1: {}})
        git(self.repo, "config", "land.testcmd", "false")
        self.drain("--once")
        st = self.state()
        self.assertNotIn("merged", st)
        self.assertIn("ready-for-human", st["issues"]["1"]["labels"])

    def test_blocked_and_claimed_tickets_are_skipped(self):
        self.write_state({1: {"body": "## Blocked by\n\n- #2\n"}, 2: {"labels": ["in-progress"]},
                          3: {"labels": ["ready-for-agent"]}})
        self.drain("--max", "5")
        self.assertEqual([c["n"] for c in self.claude_runs()], ["3"])

    def test_rerun_resumes_the_in_progress_ticket_without_rebuilding(self):
        self.write_state({1: {}})
        r = self.drain("--once", env={"FAIL_TICKETS": "1"})  # leaves worktree behind, then hands off
        self.write_state({1: {"labels": ["in-progress"]}},
                         prs={})
        os.remove(self.claude_log)
        # a killed run: worktree exists and its PR is already up
        wt = os.path.join(self.repo, ".claude", "worktrees", "implement-1")
        self.assertTrue(os.path.isdir(wt), "failed build keeps its workspace")
        with open(os.path.join(wt, "w.txt"), "w") as f:
            f.write("w\n")
        git(wt, "add", ".")
        git(wt, "commit", "-qm", "worker commit")
        git(wt, "push", "-q", "origin", "HEAD:implement-1")
        st = self.state()
        st["prs"]["implement-1"] = {"number": 101, "url": "https://example.test/pull/101",
                                    "head": git(wt, "rev-parse", "HEAD"), "closes": [1], "draft": False,
                                    "status": "CLEAN"}
        self.save(st)
        r = self.drain("--once")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.claude_runs(), [])
        self.assertEqual([m[0] for m in self.state()["merged"]], [[1]])

    def test_rerun_resumes_a_worktree_with_no_pr_by_running_the_build_in_it(self):
        self.write_state({1: {"labels": ["in-progress"]}})
        wt = os.path.join(self.repo, ".claude", "worktrees", "implement-1")
        git(self.repo, "worktree", "add", "-q", "-b", "implement-1", wt, "origin/main")
        r = self.drain("--once")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([c["n"] for c in self.claude_runs()], ["1"])
        self.assertEqual([m[0] for m in self.state()["merged"]], [[1]])

    def test_once_builds_the_agents_bundle_in_one_pr_and_leaves_the_rest_ready(self):
        self.write_state({1: {}, 2: {}, 3: {}, 4: {}})
        r = self.drain("--once", env={"TAKE": "2 3"})
        self.assertEqual(r.returncode, 0, r.stderr)
        st = self.state()
        self.assertEqual(st["merged"][0][0], [1, 2, 3])
        self.assertEqual([i["state"] for i in st["issues"].values()], ["closed"] * 3 + ["open"])
        self.assertEqual(st["issues"]["4"]["labels"], ["ready-for-agent"])
        prompt = self.claude_runs()[0]["prompt"]
        self.assertTrue(prompt.startswith("/implement 1 --tier heavy"))
        for line in ("- #2 ticket 2", "- #3 ticket 3", "- #4 ticket 4"):
            self.assertIn(line, prompt)
        self.assertIn("at most 8 tickets", prompt)
        self.assertIn("one commit per ticket", prompt)
        self.assertIn("#1 #2 #3", r.stdout)

    def test_a_pr_over_bundle_max_is_a_failed_build(self):
        self.write_state({1: {}, 2: {}, 3: {}})
        self.drain("--once", "--bundle-max", "2", env={"TAKE": "2 3"})
        st = self.state()
        self.assertNotIn("merged", st)
        self.assertIn("at most 2 tickets", self.claude_runs()[0]["prompt"])
        self.assertTrue(any("over --bundle-max 2" in b for _, b in st["comments"]))

    def test_a_ticket_the_agent_claimed_but_the_pr_did_not_close_goes_back_to_ready(self):
        self.write_state({1: {}, 2: {}})
        self.drain("--once", env={"TAKE": "2", "UNCLOSED": "1"})
        st = self.state()
        self.assertEqual(st["merged"][0][0], [1])
        self.assertEqual(st["issues"]["2"]["labels"], ["ready-for-agent"])

    def test_a_pr_that_does_not_close_the_anchor_is_a_failed_build(self):
        self.write_state({1: {}, 2: {}})
        self.drain("--once", env={"TAKE": "2", "NO_ANCHOR": "1"})
        st = self.state()
        self.assertNotIn("merged", st)
        self.assertTrue(any("does not close the anchor #1" in b for _, b in st["comments"]))

    def test_a_failed_bundle_hands_every_claimed_ticket_to_chris(self):
        self.write_state({1: {}, 2: {}, 3: {}})
        self.drain("--once", env={"TAKE": "2", "DRAFT_TICKETS": "1"})
        st = self.state()
        for n in "12":
            self.assertIn("ready-for-human", st["issues"][n]["labels"])
            self.assertNotIn("in-progress", st["issues"][n]["labels"])
        self.assertEqual(st["issues"]["3"]["labels"], ["ready-for-agent"])

    def test_refuses_a_repo_the_user_does_not_own(self):
        self.write_state({1: {}}, repo="someone-else/repo")
        r = self.drain("--once")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.claude_runs(), [])
        self.assertIn("someone-else", r.stderr)

    def test_empty_queue_stops_with_an_empty_summary(self):
        self.write_state({})
        r = self.drain()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.claude_runs(), [])


if __name__ == "__main__":
    unittest.main()
