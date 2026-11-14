"""The one way a Python script asks the GitHub tracker about issues (#1785, spec #1730).

`GhTracker` runs `gh`; `MemoryTracker` answers the same calls from a list, so a test of a caller
drives the real seam without faking a binary. A `gh` that cannot answer (it failed, timed out, or
printed something that is not the shape asked for) raises `TrackerError`: never an empty answer,
since an empty queue and an unreadable one are different facts. Issues are GitHub REST objects."""
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


def gh_json(args):
    """`gh <args>` parsed as JSON (empty output is None). Raises TrackerError when gh cannot answer."""
    try:
        out = shellcmd.gh(list(args)).stdout
    except shellcmd.CmdError as exc:
        raise TrackerError(str(exc)) from None
    try:
        return json.loads(out or "null")
    except ValueError:
        raise TrackerError(f"gh {' '.join(args)}: unreadable JSON") from None


class GhTracker:
    """The issues of one repo, read and written through `gh`. `run(args)` returns parsed JSON and is
    the seam a test of this adapter replaces."""

    def __init__(self, repo, run=gh_json):
        self.repo = repo
        self._run = run

    def _path(self, tail):
        return f"repos/{quote(self.repo, safe='/')}/{tail}"

    def _pages(self, path, what):
        """Every item of every page of `path`; a non-list page is an error."""
        pages = self._run(["api", "--paginate", "--slurp", path])
        if pages is None:
            return []
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
        answer = self._run(["api", self._path(f"issues/{int(number)}")])
        if not isinstance(answer, dict) or "number" not in answer:
            raise TrackerError(f"issue #{number}: gh answered with no issue")
        return answer

    def state(self, number):
        """`"open"`, `"closed"`, or None when it cannot be read: a number that names nothing here is
        not a closed blocker, and neither is a failed lookup."""
        try:
            return (self._run(["api", self._path(f"issues/{int(number)}")]) or {}).get("state")
        except (TrackerError, OSError):
            return None

    def parent_link(self, ticket):
        """The issue `ticket` is a sub-issue of, or None on the endpoint's 404 (no link). Any other
        failure raises: a call that did not answer is not "no parent"."""
        try:
            answer = self._run(["api", self._path(f"issues/{int(ticket['number'])}/parent")])
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
        prs = self._run(["pr", "list", "--repo", self.repo, "--base", base, "--state", "merged",
                         "--json", "body", "--limit", "200"])
        if not isinstance(prs, list):
            raise TrackerError("the merged-PR list was not a list")
        return [pr.get("body") or "" for pr in prs if isinstance(pr, dict)]

    def open_prs(self, head):
        """`[{number, url}]` for the open PRs from branch `head`."""
        prs = self._run(["pr", "list", "--repo", self.repo, "--head", head, "--state", "open",
                         "--json", "number,url"])
        if not isinstance(prs, list):
            raise TrackerError("the open-PR list was not a list")
        return prs

    def viewer_login(self):
        """The login `gh` is authenticated as."""
        try:
            login = shellcmd.gh(["api", "user", "--jq", ".login"]).stdout.strip()
        except shellcmd.CmdError as exc:
            raise TrackerError(str(exc)) from None
        if not login:
            raise TrackerError("gh api user printed no login")
        return login

    def comment(self, number, body):
        """Comment on issue or PR `number`."""
        self._write(["issue", "comment", str(number), "--repo", self.repo, "--body", body])

    def merge(self, pr, head):
        """Squash-merge `pr`, only if its head is still `head`."""
        self._write(["pr", "merge", str(pr), "--repo", self.repo, "--squash", "--match-head-commit", head])

    @staticmethod
    def _write(args):
        try:
            shellcmd.gh(args)
        except shellcmd.CmdError as exc:
            raise TrackerError(str(exc)) from None


class MemoryTracker:
    """`GhTracker`'s answers from a list of REST issue dicts. An issue may carry `parent` (a number)
    and `blockers` (open native blocker numbers); `prs` are `{number, url, head}`; `merged` maps a
    base branch to its merged PR bodies; `broken` maps an operation name (`op` or `op:<key>`, the key a ticket number or base branch) to the message it raises.
    `comments` and `merges` record what was written."""

    def __init__(self, issues=(), prs=(), viewer="me", merged=None, broken=None, repo="owner/repo"):
        self.repo = repo
        self._issues = {i["number"]: i for i in issues}
        self._prs = list(prs)
        self._viewer = viewer
        self._merged = merged or {}
        self._broken = broken or {}
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
        return [{"number": p["number"], "url": p["url"]} for p in self._prs if p.get("head") == head]

    def viewer_login(self):
        self._check("viewer_login")
        return self._viewer

    def comment(self, number, body):
        self._check("comment")
        self.comments.append((number, body))

    def merge(self, pr, head):
        self._check("merge")
        self.merges.append((pr, head))
