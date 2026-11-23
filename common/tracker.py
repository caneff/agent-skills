"""The one way a Python script asks GitHub about its issues, PRs and workflow runs, and writes
comments, issues and merges back (#1785, #1786, spec #1730).

`GhTracker` runs `gh`; `MemoryTracker` answers the same calls from a list, so a test of a caller
drives the real seam without faking a binary. A `gh` that cannot answer (it failed, timed out,
printed nothing, or printed something that is not the shape asked for) raises `TrackerError`:
never an empty answer, since an empty queue and an unreadable one are different facts. Issues are
GitHub REST objects."""
import datetime
import json
from urllib.parse import quote

import shellcmd

CLAIMED_LABEL = "in-progress"


class TrackerError(Exception):
    """The tracker could not answer; str() says why in one line."""


def labels(issue):
    """The set of label names on a REST or `gh issue view` issue. An issue that does not carry a
    list of named labels raises: a missing field is not an issue with no labels."""
    listed = issue.get("labels") if isinstance(issue, dict) else None
    if not isinstance(listed, list) or not all(isinstance(x, dict) and "name" in x for x in listed):
        raise TrackerError(f"issue #{issue.get('number') if isinstance(issue, dict) else '?'} does not say its labels")
    return {x["name"] for x in listed}


def gh_text(args, cwd=None):
    """`gh <args>`'s stdout, run in `cwd` when given. Raises TrackerError when gh cannot answer: the
    one place a `CmdError` becomes a `TrackerError`."""
    try:
        return shellcmd.gh(list(args), cwd=cwd).stdout
    except shellcmd.CmdError as exc:
        raise TrackerError(str(exc)) from None


def _parsed(args, out):
    """`out` parsed as JSON, empty output being None. Raises TrackerError on unreadable JSON."""
    try:
        return json.loads(out or "null")
    except ValueError as exc:
        raise TrackerError(f"gh {' '.join(args)}: unreadable JSON ({type(exc).__name__}: {exc}); "
                           f"stdout began: {out[:200]!r}") from None


def gh_json(args):
    """`gh <args>` parsed as JSON (empty output is None). Raises TrackerError when gh cannot answer."""
    return _parsed(args, gh_text(args))


class GhTracker:
    """The issues, PRs and runs of one repo, read and written through `gh`. Every call goes through
    `run(args)`, which returns gh's stdout and is the seam a test of this adapter replaces;
    `repo_identity` alone passes `cwd=<checkout>` too, so a replacement accepts that keyword."""

    def __init__(self, repo=None, run=gh_text):
        self.repo = repo
        self._run = run

    def _json(self, args):
        return _parsed(args, self._run(args))

    def _path(self, tail):
        return f"repos/{quote(self.repo, safe='/')}/{tail}"

    def _pages(self, path, what):
        """Every item of every page of `path`. A non-list page is an error, and so is empty output:
        `--slurp` prints `[[]]` for an empty list, so nothing printed is no answer."""
        pages = self._json(["api", "--paginate", "--slurp", path])
        if not isinstance(pages, list) or not all(isinstance(p, list) for p in pages):
            raise TrackerError(f"gh answered with something other than pages of {what}")
        return [item for page in pages for item in page]

    def issues(self, label):
        """Every open issue with `label` (pull requests included), from the REST endpoint: the
        GraphQL one `gh issue list` uses carries no `issue_dependencies_summary`. The label is
        percent-encoded, since a raw `#` is a fragment marker gh drops, answering a broader queue."""
        return self._pages(self._path(f"issues?state=open&per_page=100&labels={quote(label, safe='')}"), "issues")

    def claimed(self):
        """Every open issue carrying the in-progress label: the one claimed-queue read."""
        return self.issues(CLAIMED_LABEL)

    def issue(self, number):
        """One issue's REST object."""
        answer = self._json(["api", self._path(f"issues/{int(number)}")])
        if not isinstance(answer, dict) or "number" not in answer:
            raise TrackerError(f"issue #{number}: gh answered with no issue")
        return answer

    def state(self, number):
        """`"open"`, `"closed"`, or None when it cannot be read: a number that names nothing here is
        not a closed blocker, and neither is a failed lookup."""
        try:
            return (self._json(["api", self._path(f"issues/{int(number)}")]) or {}).get("state")
        except TrackerError:
            return None

    def parent_link(self, ticket):
        """The issue `ticket` is a sub-issue of, or None on the endpoint's 404 (no link). Any other
        failure raises: a call that did not answer is not "no parent"."""
        try:
            answer = self._json(["api", self._path(f"issues/{int(ticket['number'])}/parent")])
        except TrackerError as exc:
            # gh's own status marker, not a bare "404": a failed call's message can carry a URL.
            if "(HTTP 404)" in str(exc):
                return None
            raise
        if not isinstance(answer, dict) or "number" not in answer:
            raise TrackerError("the parent endpoint answered with no issue")
        return answer

    def native_blockers(self, ticket):
        """The numbers of `ticket`'s open native blockers, every page. A blocker outside this repo
        or a malformed entry raises: its number could collide with a local one."""
        out = []
        for b in self._pages(self._path(f"issues/{int(ticket['number'])}/dependencies/blocked_by?per_page=100"), "issues"):
            if not isinstance(b, dict) or not isinstance(b.get("number"), int):
                raise TrackerError("a native blocker came back malformed")
            if not str(b.get("repository_url") or "").endswith(f"/repos/{self.repo}"):
                raise TrackerError(f"native blocker #{b['number']} is outside {self.repo}")
            if b.get("state") == "open":
                out.append(b["number"])
        return out

    def merged_bodies(self, base):
        """The bodies of the PRs merged into `base`."""
        prs = self._json(["pr", "list", "--repo", self.repo, "--base", base, "--state", "merged",
                         "--json", "body", "--limit", "200"])
        if not isinstance(prs, list):
            raise TrackerError("the merged-PR list was not a list")
        return [pr.get("body") or "" for pr in prs if isinstance(pr, dict)]

    def open_prs(self, head):
        """`[{number, url, baseRefName}]` for the open PRs from branch `head`."""
        prs = self._json(["pr", "list", "--repo", self.repo, "--head", head, "--state", "open",
                         "--json", "number,url,baseRefName"])
        if not isinstance(prs, list):
            raise TrackerError("the open-PR list was not a list")
        return prs

    def _view(self, kind, number, fields):
        answer = self._json([kind, "view", str(number), "--repo", self.repo, "--json", fields])
        if not isinstance(answer, dict):
            raise TrackerError(f"gh {kind} view {number}: answered with something other than an object")
        return answer

    def issue_view(self, number, fields):
        """`gh issue view`'s object with the comma-separated `fields` (`body,comments` carries each
        comment's author, time and hidden marker, which the REST object does not)."""
        return self._view("issue", number, fields)

    def pr_view(self, pr, fields):
        """`gh pr view`'s object with `fields`. `pr` may be a number, a URL or a branch."""
        return self._view("pr", pr, fields)

    def pr_comments(self, pr):
        """The bodies of PR `pr`'s comments, oldest first; a comment with no body reads as ''."""
        comments = self._view("pr", pr, "comments").get("comments")
        if not isinstance(comments, list) or not all(isinstance(c, dict) for c in comments):
            raise TrackerError(f"PR #{pr}: gh answered with no list of comments")
        return [c.get("body") or "" for c in comments]

    def runs(self, workflow, branch, event="schedule", limit=1):
        """The newest `limit` runs of `workflow` on `branch` for `event`, as gh's run objects."""
        runs = self._json(["run", "list", "--repo", self.repo, "--workflow", workflow, "--event", event,
                          "--branch", branch, "--limit", str(limit),
                          "--json", "databaseId,status,conclusion,headSha,createdAt,url"])
        if not isinstance(runs, list):
            raise TrackerError("the run list was not a list")
        return runs

    def run_failed_log(self, run_id):
        """The failed steps' log of run `run_id`. An empty log raises: nothing to read is not a log."""
        text = self._run(["run", "view", str(run_id), "--repo", self.repo, "--log-failed"])
        if not text.strip():
            raise TrackerError(f"run {run_id}: gh printed no log")
        return text.strip()

    def _create(self, title, labels, body_args):
        args = ["issue", "create", "--repo", self.repo, "--title", title, *body_args]
        for label in labels:
            args += ["--label", label]
        url = self._run(args).strip()
        if not url:
            raise TrackerError("gh issue create printed no URL")
        return url

    def create_issue(self, title, body, labels):
        """File an issue and return its URL."""
        return self._create(title, labels, ["--body", body])

    def create_issue_from_file(self, title, body_file, labels):
        """`create_issue` with the body read by gh from `body_file`; returns the URL."""
        return self._create(title, labels, ["--body-file", body_file])

    def comment_from_file(self, number, body_file):
        """`comment` with the body read by gh from `body_file`."""
        self._run(["issue", "comment", str(number), "--repo", self.repo, "--body-file", body_file])

    def relabel(self, number, add, remove, unassign=None):
        """Add the labels `add`, remove the labels `remove` and, when `unassign` names a login
        (`@me` included), drop that assignee, in one `gh issue edit`."""
        args = ["issue", "edit", str(number), "--repo", self.repo]
        for label in remove:
            args += ["--remove-label", label]
        for label in add:
            args += ["--add-label", label]
        if unassign:
            args += ["--remove-assignee", unassign]
        self._run(args)

    def closed_events(self, number):
        """The `closed` events of issue `number`, every page, oldest first."""
        events = self._pages(self._path(f"issues/{int(number)}/events"), "events")
        if not all(isinstance(e, dict) for e in events):
            raise TrackerError(f"issue #{number}: an event came back malformed")
        return [e for e in events if e.get("event") == "closed"]

    def repo_identity(self, checkout):
        """`(owner login, name)` of the GitHub repo the checkout `checkout` is a clone of. A reply
        that does not name both raises."""
        try:
            reply = _parsed(["repo", "view"], self._run(["repo", "view", "--json", "owner,name"], cwd=checkout))
            owner, name = reply["owner"]["login"], reply["name"]
        except (KeyError, TypeError):
            raise TrackerError("gh repo view: the reply does not name an owner and a repo") from None
        if not isinstance(owner, str) or not isinstance(name, str):
            raise TrackerError("gh repo view: the reply does not name an owner and a repo")
        return owner, name

    def label_names(self):
        """The set of the repo's label names (up to 1000)."""
        rows = self._json(["label", "list", "--repo", self.repo, "--limit", "1000", "--json", "name"])
        if not isinstance(rows, list) or not all(isinstance(r, dict) and "name" in r for r in rows):
            raise TrackerError("gh label list answered with something other than named labels")
        return {r["name"] for r in rows}

    def open_issues(self, fields, limit):
        """The open issues as `gh issue list --json <fields>` prints them, at most `limit`."""
        rows = self._json(["issue", "list", "--repo", self.repo, "--state", "open", "--limit", str(limit),
                           "--json", fields])
        if not isinstance(rows, list):
            raise TrackerError("gh issue list answered with something other than a list")
        return rows

    def search_prs(self, since, limit):
        """The `repository` of up to `limit` PRs the viewer authored since `since` (`YYYY-MM-DD`),
        across every repo; the caller owns the cut-off check, since `limit` is gh's own cap."""
        rows = self._json(["search", "prs", "--author", "@me", "--created", f">={since}",
                          "--json", "repository", "--limit", str(limit)])
        if not isinstance(rows, list):
            raise TrackerError("gh search prs answered with something other than a list")
        return rows

    def workflow_texts(self):
        """The text of every workflow file in `.github/workflows` on the repo's default branch; `[]`
        only when the directory does not exist (a 404). Any other failure raises: an unreadable
        directory is not a repo with no workflows."""
        try:
            entries = self._json(["api", self._path("contents/.github/workflows")])
        except TrackerError as exc:
            if "404" in str(exc) or "Not Found" in str(exc):
                return []
            raise
        if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
            raise TrackerError("the workflow directory listing was not a list of files")
        return [self._run(["api", "-H", "Accept: application/vnd.github.raw", self._path(f"contents/{quote(e['path'])}")])
                for e in entries if e.get("type") == "file" and str(e.get("name", "")).endswith((".yml", ".yaml"))]

    def viewer_login(self):
        """The login `gh` is authenticated as."""
        login = self._run(["api", "user", "--jq", ".login"]).strip()
        if not login:
            raise TrackerError("gh api user printed no login")
        return login

    def comment(self, number, body):
        """Comment on issue or PR `number`."""
        self._run(["issue", "comment", str(number), "--repo", self.repo, "--body", body])

    def merge(self, pr, head):
        """Squash-merge `pr`, only if its head is still `head`."""
        self._run(["pr", "merge", str(pr), "--repo", self.repo, "--squash", "--match-head-commit", head])


class MemoryTracker:
    """`GhTracker`'s answers from a list of REST issue dicts. An issue may carry `parent` (a number)
    and `blockers` (open native blocker numbers); `prs` are `{number, url, head}`; `merged` maps a
    base branch to its merged PR bodies; `broken` maps an operation name (`op` or `op:<key>`, the
    key a ticket number or base branch) to the message it raises.
    `pr_views` maps a PR number to its `gh pr view` object, `pr_comments` to its comment bodies,
    `runs` is the workflow-run list and `logs` maps a run id to its failed log.
    `comments`, `merges` and the issues `create_issue` adds record what was written; a comment is
    also appended to its issue's own `comments`, as `issue_view` reads it back. An issue may carry
    `events` (its timeline). `identity` is the `(owner, name)` every checkout answers, `workflows` the text of each workflow
    file, and `labels_defined` the repo's label names."""

    def __init__(self, issues=(), prs=(), viewer="me", merged=None, broken=None, repo="owner/repo",
                 pr_views=None, pr_comments=None, runs=(), logs=None, identity=None, labels_defined=(), workflows=()):
        self.repo = repo
        self._issues = {i["number"]: i for i in issues}
        self._prs = list(prs)
        self._viewer = viewer
        self._merged = merged or {}
        self._broken = broken or {}
        self._pr_views = pr_views or {}
        self._pr_comments = pr_comments or {}
        self._runs = list(runs)
        self._logs = logs or {}
        self._identity = identity
        self._workflows = list(workflows)
        self._labels_defined = set(labels_defined)
        self.comments = []
        self.merges = []

    def _check(self, op, key=None):
        for name in (f"{op}:{key}", op):
            if name in self._broken:
                raise TrackerError(self._broken[name])

    def issues(self, label):
        self._check("issues")
        return [i for i in self._issues.values() if i["state"] == "open" and label in labels(i)]

    def claimed(self):
        self._check("claimed")
        return self.issues(CLAIMED_LABEL)

    def issue(self, number):
        self._check("issue")
        if number not in self._issues:
            raise TrackerError(f"issue #{number}: Not Found (HTTP 404)")
        return self._issues[number]

    def state(self, number):
        return self._issues[number]["state"] if number in self._issues else None

    def parent_link(self, ticket):
        self._check("parent_link", ticket["number"])
        parent = self._issues.get(ticket["number"], {}).get("parent")
        return self._issues[parent] if parent else None

    def native_blockers(self, ticket):
        self._check("native_blockers", ticket["number"])
        return list(self._issues.get(ticket["number"], {}).get("blockers", []))

    def merged_bodies(self, base):
        self._check("merged_bodies", base)
        return list(self._merged.get(base, []))

    def open_prs(self, head):
        self._check("open_prs")
        return [{"number": p["number"], "url": p["url"], "baseRefName": p.get("base")}
                for p in self._prs if p.get("head") == head]

    def issue_view(self, number, fields):
        self._check("issue_view", number)
        if number not in self._issues:
            raise TrackerError(f"issue #{number}: Not Found (HTTP 404)")
        return {f: self._issues[number].get(f) for f in fields.split(",")}

    def pr_view(self, pr, fields):
        self._check("pr_view", pr)
        if pr not in self._pr_views:
            raise TrackerError(f"PR #{pr}: Not Found (HTTP 404)")
        return self._pr_views[pr]

    def pr_comments(self, pr):
        self._check("pr_comments", pr)
        if pr not in self._pr_comments:
            raise TrackerError(f"PR #{pr}: Not Found (HTTP 404)")
        return list(self._pr_comments[pr])

    def runs(self, workflow, branch, event="schedule", limit=1):
        self._check("runs")
        return self._runs[:limit]

    def run_failed_log(self, run_id):
        self._check("run_failed_log", run_id)
        if run_id not in self._logs:
            raise TrackerError(f"run {run_id}: gh printed no log")
        return self._logs[run_id]

    def create_issue(self, title, body, labels):
        self._check("create_issue")
        number = max(self._issues, default=0) + 1
        self._issues[number] = {"number": number, "title": title, "body": body, "state": "open",
                                "labels": [{"name": x} for x in labels]}
        return f"https://github.com/{self.repo}/issues/{number}"

    def viewer_login(self):
        self._check("viewer_login")
        return self._viewer

    def comment(self, number, body):
        self._check("comment")
        self.comments.append((number, body))
        if number in self._issues:
            posted = self._issues[number].setdefault("comments", [])
            # One second apart, so a reader that sorts by time keeps the posting order.
            stamp = (datetime.datetime(2000, 1, 1) + datetime.timedelta(seconds=len(posted))).isoformat()
            posted.append({"author": {"login": self._viewer}, "body": body, "createdAt": stamp + "Z",
                           "isMinimized": False})

    def create_issue_from_file(self, title, body_file, labels):
        return self.create_issue(title, self._read(body_file), labels)

    def comment_from_file(self, number, body_file):
        self.comment(number, self._read(body_file))

    def _read(self, path):
        try:
            with open(path, encoding="utf-8") as f:
                return f.read()
        except OSError as exc:
            raise TrackerError(f"cannot read {path}: {exc}") from None

    def relabel(self, number, add, remove, unassign=None):
        self._check("relabel", number)
        if number not in self._issues:
            raise TrackerError(f"issue #{number}: Not Found (HTTP 404)")
        i = self._issues[number]
        kept = [x for x in i["labels"] if x["name"] not in set(remove)]
        i["labels"] = kept + [{"name": a} for a in add if a not in {x["name"] for x in kept}]
        if unassign:
            login = self._viewer if unassign == "@me" else unassign
            i["assignees"] = [a for a in i.get("assignees", []) if a.get("login") != login]

    def closed_events(self, number):
        self._check("closed_events", number)
        if number not in self._issues:
            raise TrackerError(f"issue #{number}: Not Found (HTTP 404)")
        return [e for e in self._issues[number].get("events", []) if e.get("event") == "closed"]

    def repo_identity(self, checkout):
        self._check("repo_identity")
        if self._identity is None:
            raise TrackerError(f"{checkout}: no repo identity")
        return self._identity

    def workflow_texts(self):
        self._check("workflow_texts")
        return list(self._workflows)

    def label_names(self):
        self._check("label_names")
        return set(self._labels_defined)

    def open_issues(self, fields, limit):
        self._check("open_issues")
        names = fields.split(",")
        return [{f: i.get(f) for f in names} for i in self._issues.values() if i["state"] == "open"][:limit]

    def merge(self, pr, head):
        self._check("merge")
        self.merges.append((pr, head))
