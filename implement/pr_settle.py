#!/usr/bin/env python3
"""`pr_settle.py <pr> --repo <owner/name> [--head <sha>] [--merge]`: wait for a
PR to read CLEAN, then optionally squash-merge it (#1526).

One wait for both callers, `drain/drain.py` and `implement/SKILL.md` § The
merge, which used to raise on UNKNOWN and "poll a few seconds" respectively.
Prints one line, `draft=<bool> state=<mergeStateStatus> head=<sha>`, whatever
the outcome, and exits 0 only on a PR that is not a draft, reads CLEAN and
(with `--head`) still has that head; with `--merge` it has then been merged.
Exit 1 is a limit or a refusal, named on stderr with the last state read; exit
2 is a usage error. `--merge` refuses a repo whose owner is not the `gh` login
(`require_own_repo`): the merge happens inside this process, out of the
ownership hook's sight, so the rule is kept here.

What it waits for:
- `UNKNOWN` (GitHub still computing), or a non-CLEAN state with no check
  registered yet: re-read for up to 60 s.
- `UNSTABLE` or `BLOCKED` with a check still running: until the checks finish,
  capped at 15 minutes. CI on these repos is GitHub Actions and ran about
  2 minutes in the 2026-10-08 drain run that handed three PRs over on
  UNSTABLE, so the cap is generous.
- A "Base branch was modified" refusal at `gh pr merge`: re-settled and
  retried, up to 3 times.
It does not wait for a failed check, a draft, a closed or merged PR, or
`BEHIND`/`DIRTY`: nothing waited on resolves those.
"""
import argparse
import json
import os
import subprocess
import sys
import time

UNKNOWN_SECONDS = 60
CHECKS_SECONDS = 15 * 60
MERGE_RETRIES = 3
POLL_SECONDS = float(os.environ.get("PR_SETTLE_POLL", 5))  # a test sets it to 0
BASE_MODIFIED = "Base branch was modified"
FIELDS = "isDraft,mergeStateStatus,headRefOid,state,statusCheckRollup"
# A completed CheckRun's conclusions that are not failures. Anything else, a
# value this table has never seen included, is a failure, never a pass.
PASSING = {"SUCCESS", "NEUTRAL", "SKIPPED"}
FAILING_CONTEXT = {"FAILURE", "ERROR"}
PENDING_CONTEXT = {"PENDING", "EXPECTED"}


class SettleError(Exception):
    """The PR did not settle; the message names the last state read."""

    def __init__(self, message, view=None):
        super().__init__(message)
        self.view = view


def classify(rollup):
    """`(pending, failed)`: the names of the checks still running and of those
    that completed badly, read from a `statusCheckRollup`."""
    pending, failed = [], []
    for check in rollup:
        if check.get("__typename") == "StatusContext" or ("state" in check and "status" not in check):
            name, state = check.get("context") or check.get("name") or "?", check.get("state")
            if state in FAILING_CONTEXT:
                failed.append(name)
            elif state != "SUCCESS":
                pending.append(name)
            continue
        name = check.get("name") or "?"
        if check.get("status") != "COMPLETED":
            pending.append(name)
        elif check.get("conclusion") not in PASSING:
            failed.append(name)
    return pending, failed


def line(view):
    return f"draft={str(bool(view['isDraft'])).lower()} state={view['mergeStateStatus']} head={view['headRefOid']}"


def settle(read, sleep=time.sleep, now=time.monotonic, poll=POLL_SECONDS):
    """Re-read `read()` (a `gh pr view` as a dict) until the PR is CLEAN and
    return that view, or raise `SettleError` on a limit or a refusal."""
    start = quiet_since = now()
    while True:
        view = read()
        missing = [k for k in FIELDS.split(",") if k not in view]
        if missing:  # an answer without a field is not a CLEAN one
            raise SettleError(f"gh pr view returned no {', '.join(missing)}", view)
        state = view["mergeStateStatus"]
        if view["state"] != "OPEN":
            raise SettleError(f"is {view['state']}", view)
        if view["isDraft"]:
            raise SettleError("is still a draft", view)
        pending, failed = classify(view["statusCheckRollup"])
        if failed:
            raise SettleError(f"has a failed check: {', '.join(failed)} (state {state})", view)
        if state == "CLEAN":
            return view
        t = now()
        if pending:
            quiet_since = t
            if t - start >= CHECKS_SECONDS:
                raise SettleError(f"is {state} with {', '.join(pending)} still running after "
                                  f"{CHECKS_SECONDS} s, not CLEAN", view)
        elif state == "UNKNOWN" or not view["statusCheckRollup"]:
            if t - quiet_since >= UNKNOWN_SECONDS:
                raise SettleError(f"is {state} after {UNKNOWN_SECONDS} s, not CLEAN", view)
        else:  # every check is in and passed, and the state is still not CLEAN: waiting changes nothing
            raise SettleError(f"is {state}, not CLEAN", view)
        sleep(poll)


def merge(read, gh_merge, head, sleep=time.sleep, now=time.monotonic, poll=POLL_SECONDS):
    """Settle, then `gh_merge(head)` -> `(exit code, output)`; a "Base branch
    was modified" refusal settles again and retries, up to `MERGE_RETRIES`
    times. The merge is bound to `head`: a PR whose head moved is refused."""
    refusal = ""
    for attempt in range(MERGE_RETRIES + 1):
        view = settle(read, sleep=sleep, now=now, poll=poll)
        if view["headRefOid"] != head:
            raise SettleError(f"head moved from {head} to {view['headRefOid']}", view)
        code, text = gh_merge(head)
        if code == 0:
            return view
        refusal = text.strip()
        if BASE_MODIFIED not in refusal:
            raise SettleError(f"gh pr merge failed: {refusal}", view)
        sleep(poll)
    raise SettleError(f"gh pr merge refused {MERGE_RETRIES + 1} times: {refusal}")


def gh_reader(pr, repo, extra=""):
    """A `read()` for `settle`; `extra` names further `--json` fields a caller
    wants on the view it gets back."""
    fields = FIELDS + ("," + extra if extra else "")

    def read():
        out = subprocess.run(["gh", "pr", "view", str(pr), "--repo", repo, "--json", fields],
                             capture_output=True, text=True)
        if out.returncode != 0:
            raise SettleError(f"gh pr view failed: {(out.stderr or out.stdout).strip()}")
        try:
            return json.loads(out.stdout)
        except ValueError as exc:
            raise SettleError(f"gh pr view returned no JSON: {exc}") from exc
    return read


def gh_merger(pr, repo):
    def do(head):
        out = subprocess.run(["gh", "pr", "merge", str(pr), "--repo", repo, "--squash",
                              "--match-head-commit", head], capture_output=True, text=True)
        return out.returncode, (out.stderr or "") + (out.stdout or "")
    return do


def require_own_repo(repo):
    """`--merge` runs `gh pr merge` inside this process, where the ownership
    hook (`flow/claude/hooks/block-dangerous-git.sh`, which reads a command
    line for the words `gh pr merge`) cannot see it. So the same rule is kept
    here, failing closed: a repo whose owner is not the `gh` login, or a login
    `gh` cannot give, is not merged."""
    out = subprocess.run(["gh", "api", "user", "--jq", ".login"], capture_output=True, text=True)
    login = out.stdout.strip()
    if out.returncode != 0 or not login:
        raise SettleError(f"refusing to merge: could not read the gh login ({(out.stderr or '').strip()})")
    owner = repo.split("/")[-2] if repo.count("/") >= 1 else ""
    if owner.lower() != login.lower():
        raise SettleError(f"refusing to merge {repo}: owner {owner or '?'} is not the gh login {login}; "
                          "that merge is the owner's to run")


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("pr")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--head", help="the sha the PR must still have (required with --merge)")
    ap.add_argument("--merge", action="store_true", help="squash-merge once CLEAN")
    ap.add_argument("--poll", type=float, default=POLL_SECONDS, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    if args.merge and not args.head:
        ap.error("--merge needs --head <sha>: the merge is bound to the head the seam ran on")
    read = gh_reader(args.pr, args.repo)
    last = {}

    def tracked():
        last.clear()
        last.update(read())
        return last
    try:
        if args.merge:
            require_own_repo(args.repo)
            view = merge(tracked, gh_merger(args.pr, args.repo), args.head, poll=args.poll)
        else:
            view = settle(tracked, poll=args.poll)
            if args.head and view["headRefOid"] != args.head:
                raise SettleError(f"head moved from {args.head} to {view['headRefOid']}", view)
    except SettleError as exc:
        shown = exc.view or last
        if shown.get("mergeStateStatus"):
            print(line(shown))
        print(f"pr-settle: {args.pr}: {exc}", file=sys.stderr)
        return 1
    print(line(view))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
