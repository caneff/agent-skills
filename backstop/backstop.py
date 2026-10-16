#!/usr/bin/env python3
"""`backstop.py --repo <checkout> --jobs <k> [--notify <cmd>]`: the nightly
full run of one repo's seam (#1594, spec #1592).

Per change the lane runs only the repo's narrowed command; this is the one
full run, once a night, for a repo with no CI. It fetches origin, runs the
`**Seam**` command that `AGENTS.md` § End-to-end seam declares on the tip of
`origin/<default>`, in a throwaway worktree, and reads the night as one of
three outcomes:

    green          the seam exited 0, printed something, and no line starts
                   `FAIL `: the tip is recorded as the last green sha
    red            the seam exited non-zero and named its failing suites with
                   `FAIL <suite>` lines
    inconclusive   anything else: no seam declared, the worktree or the
                   command could not start, a non-zero exit with no `FAIL`
                   line, an exit 0 that printed nothing or printed a `FAIL`

A red night files one `bug` + `ready-for-agent` ticket in the repo, naming the
failing suites and the merges since the last green sha (the first-parent
commits on `<default>` since it, each carrying its PR number as a squash merge
does), and notifies. A failing suite already named by an open backstop ticket
(one whose body carries the `<!-- backstop suites: [...] -->` marker) is not
filed again: a red night whose every failing suite is named by one files
nothing and notifies that it is still red, naming those tickets. An
inconclusive night is notified and never recorded green (`AGENTS.md`
§ Recurring defect classes, class 1). A failure to list the open tickets,
file one or notify is said on stderr and in the exit code, never swallowed.

`--jobs <k>` is required, never `nproc`: it reaches the seam as `TESTS_JOBS`,
the job count `tests/all.sh` reads, so the full run never crowds the agents
sharing the box. A seam that ignores `TESTS_JOBS` is that repo's to fix.
`--notify` is the notifier, called as `<cmd> <title> <body>`; it defaults to
this repo's `flow/bin/notify-send`. The record is `last-green-<owner>__<name>`
under `$BACKSTOP_DIR` (default `~/.cache/backstop`), beside the night's log,
`full-seam-<owner>__<name>.log`. Only a repo whose origin owner is the `gh`
login is run: filing a ticket is outward-facing.

Exit 0 green, 1 red, 2 inconclusive, 3 when a red or inconclusive night's
ticket or notification could not be sent.
"""
import argparse
import json
import os
import re
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
for _dir in ("drain", "implement", "implement-spec"):
    sys.path.insert(0, os.path.join(_HERE, os.pardir, _dir))
# The worktree run, the origin reader and the seam section's grammar each have
# one copy; the backstop takes them over rather than keeping a second one.
from drain import Ctx, DrainError, one_line, origin_slug, run, run_in_scratch_tree  # noqa: E402
from closing_ticket import declaration  # noqa: E402
from selector_check import failing_suites  # noqa: E402

NOTIFY_SEND = os.path.join(_HERE, os.pardir, "flow", "bin", "notify-send")
GREEN, RED, INCONCLUSIVE, UNSENT = 0, 1, 2, 3


def positive(text):
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be a positive integer, got {text}")
    return value


def seam_command(root, tip):
    """The `**Seam**` command `AGENTS.md` declares at `tip`: its first backtick
    span, or the whole value with none. Raises `DrainError` naming the gap."""
    try:
        text = run(["git", "show", f"{tip}:AGENTS.md"], cwd=root)
    except DrainError as exc:
        raise DrainError(f"no AGENTS.md at {tip[:12]}: {one_line(exc, 150)}") from exc
    value = (declaration(text) or {}).get("seam", "")
    span = re.search(r"`([^`]+)`", value)
    command = (span.group(1) if span else value).strip()
    if not command.strip("*_ "):
        raise DrainError("AGENTS.md § End-to-end seam declares no `Seam` command")
    return command


def night(ctx, jobs):
    """`(outcome, tip, detail)`: `detail` is the failing suites on red, else
    the reason, for an inconclusive night."""
    tip = None
    try:
        run(["git", "fetch", "-q", "origin"], cwd=ctx.root)
        tip = run(["git", "rev-parse", ctx.default], cwd=ctx.root)
        cmd = seam_command(ctx.root, tip)
    except DrainError as exc:
        return INCONCLUSIVE, tip, f"the seam could not start: {one_line(exc, 200)}"
    log = os.path.join(ctx.log_dir, f"full-seam-{slug(ctx)}.log")
    os.environ["TESTS_JOBS"] = str(jobs)
    try:
        run_in_scratch_tree(ctx, cmd, log, rev=tip)
        exited = 0
    except DrainError as exc:
        exited = one_line(exc, 200)
    failed, _ = failing_suites(log)
    try:
        printed = os.path.getsize(log) > 0
    except OSError:
        printed = False
    if exited == 0:
        if failed:
            return INCONCLUSIVE, tip, f"`{cmd}` exited 0 but its log names failing suites ({', '.join(failed)})"
        if not printed:
            return INCONCLUSIVE, tip, f"`{cmd}` exited 0 and printed nothing"
        return GREEN, tip, None
    if failed:
        return RED, tip, failed
    return INCONCLUSIVE, tip, f"{exited}, and its log ({log}) names no `FAIL <suite>` line"


def slug(ctx):
    return ctx.repo.replace("/", "__")


def last_green_path(ctx):
    return os.path.join(ctx.log_dir, f"last-green-{slug(ctx)}")


_MARKER = re.compile(r"<!-- backstop suites: (.*?) -->")


def open_backstop_tickets(ctx):
    """`{suite: ticket number}` over the open `bug` tickets carrying the
    marker. A marker that does not parse names nothing, so its suites are
    filed again: a duplicate ticket, never a failure left unfiled."""
    listed = json.loads(run(["gh", "issue", "list", "--repo", ctx.repo, "--state", "open", "--label", "bug",
                             "--limit", "500", "--json", "number,body"]))
    named = {}
    for issue in listed:
        m = _MARKER.search(issue.get("body") or "")
        try:
            suites = json.loads(m.group(1)) if m else []
        except ValueError:
            suites = []
        for suite in suites if isinstance(suites, list) else []:
            named.setdefault(suite, issue["number"])
    return named


def merges_since(ctx, last, tip):
    """The first-parent commits on `<default>` after `last`, oldest first, as
    `<sha> <subject>` lines, or a line saying why they cannot be listed."""
    if not last:
        return ["(no green run on record, so the merges since one cannot be listed)"]
    try:
        listed = run(["git", "log", "--first-parent", "--reverse", "--format=%H %s", f"{last}..{tip}"], cwd=ctx.root)
    except DrainError as exc:
        return [f"(the merges since {last} could not be listed: {one_line(exc, 150)})"]
    return listed.splitlines() or [f"(none: {tip} is the last green sha)"]


def ticket_body(ctx, tip, last, failed):
    lines = [f"The nightly backstop ran the full seam of `{ctx.repo}` on `{ctx.default}` at {tip} and it went red.",
             "", "## Failing suites", ""]
    lines += [f"- `{s}`" for s in failed]
    lines += ["", f"## Merges since the last green sha ({last or 'none on record'})", ""]
    lines += [f"- {x}" for x in merges_since(ctx, last, tip)]
    lines += ["", "## Log", "",
              f"`{os.path.join(ctx.log_dir, f'full-seam-{slug(ctx)}.log')}` on the machine the backstop ran on.",
              "", f"<!-- backstop suites: {json.dumps(failed)} -->", ""]
    return "\n".join(lines)


def file_ticket(ctx, tip, last, failed):
    """The new ticket's URL."""
    with tempfile.NamedTemporaryFile("w", dir=ctx.log_dir, prefix="backstop-body-", suffix=".md",
                                     delete=False) as f:
        f.write(ticket_body(ctx, tip, last, failed))
    try:
        title = f"backstop: full seam red on {ctx.default.split('/')[-1]}: {', '.join(failed)}"
        return run(["gh", "issue", "create", "--repo", ctx.repo, "--title", one_line(title, 200),
                    "--label", "bug", "--label", "ready-for-agent", "--body-file", f.name])
    finally:
        os.remove(f.name)


def notify(cmd, title, body):
    """`None` when sent, else why not."""
    try:
        run([cmd, title, body])
    except DrainError as exc:
        return one_line(exc, 200)
    return None


def report_red(ctx, tip, failed, notifier):
    """File or name the ticket, notify; the exit code."""
    try:
        last = open(last_green_path(ctx)).read().strip() or None
    except OSError:
        last = None
    title = f"backstop: {ctx.repo} red"
    try:
        named = open_backstop_tickets(ctx)
        new = [s for s in failed if s not in named]
        if new:
            url = file_ticket(ctx, tip, last, failed)
            body = f"{', '.join(failed)} failing at {tip[:12]}; filed {url}"
        else:
            held = sorted({named[s] for s in failed})
            body = f"still red: {', '.join(failed)} at {tip[:12]}, open in " + ", ".join(f"#{n}" for n in held)
    except (DrainError, ValueError, OSError) as exc:
        body = f"{', '.join(failed)} failing at {tip[:12]}; no ticket filed: {one_line(exc, 200)}"
        print(f"backstop.py: {body}", file=sys.stderr)
        why = notify(notifier, title, body)
        if why:
            print(f"backstop.py: notification not sent: {why}", file=sys.stderr)
        return UNSENT
    print(f"backstop: {body}")
    why = notify(notifier, title, body)
    if why:
        print(f"backstop.py: notification not sent: {why}", file=sys.stderr)
        return UNSENT
    return RED


def report_inconclusive(repo, why, notifier):
    """Notify a night that is neither green nor red; the exit code."""
    print(f"backstop.py: {repo} inconclusive: {why}", file=sys.stderr)
    sent = notify(notifier, f"backstop: {repo} inconclusive", why)
    if sent:
        print(f"backstop.py: notification not sent: {sent}", file=sys.stderr)
        return UNSENT
    return INCONCLUSIVE


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo", required=True, help="the repo's checkout")
    parser.add_argument("--jobs", type=positive, required=True, help="the seam's job count (TESTS_JOBS)")
    parser.add_argument("--notify", default=NOTIFY_SEND, help="the notifier, called as <cmd> <title> <body>")
    args = parser.parse_args(argv)
    try:
        root = os.path.abspath(args.repo)
        repo = origin_slug(root)
        login = run(["gh", "api", "user", "--jq", ".login"])
        if repo.split("/")[0] != login:
            raise DrainError(f"{repo} is not owned by {login}; the backstop files tickets only on the caller's own repos")
        default = run(["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"], cwd=root)
        state_dir = os.environ.get("BACKSTOP_DIR") or os.path.expanduser("~/.cache/backstop")
        os.makedirs(state_dir, exist_ok=True)
    except DrainError as exc:
        return report_inconclusive(args.repo, f"the seam could not start: {one_line(exc, 200)}", args.notify)
    ctx = Ctx(root, repo, default, state_dir, None, None)
    outcome, tip, detail = night(ctx, args.jobs)
    if outcome == INCONCLUSIVE:
        return report_inconclusive(repo, f"{detail} (at {tip or 'no tip read'})", args.notify)
    if outcome == GREEN:
        with open(last_green_path(ctx), "w") as f:
            f.write(tip + "\n")
        print(f"backstop: {repo} green at {tip}")
        return GREEN
    if outcome == RED:
        return report_red(ctx, tip, detail, args.notify)
    return outcome


if __name__ == "__main__":
    sys.exit(main())
