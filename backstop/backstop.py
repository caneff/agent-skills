#!/usr/bin/env python3
"""`backstop.py --repo <checkout> --jobs <k> [--notify <cmd>]`: the nightly
full run of one repo's seam (#1594, spec #1592).

Per change the lane runs only the repo's narrowed command; this is the one
full run, once a night. It fetches origin and reads the tip of
`origin/<default>`. A repo with CI, one whose tree there carries a
`.github/workflows/` file with a `schedule:` trigger, already ran its full gate
on GitHub (#1596): the night is its latest completed scheduled run on
`<default>` (`gh run list --event schedule`), and no seam runs locally. Any
other repo has its `**Seam**` command, as `AGENTS.md` § End-to-end seam
declares it, run on the tip in a throwaway worktree. Either way the night is
one of three outcomes:

    green          the seam exited 0, printed something, and no line starts
                   `FAIL `: the tip is recorded as the last green sha
    red            the seam exited non-zero and named its failing suites with
                   `FAIL <suite>` lines
    inconclusive   anything else: no seam declared, the worktree or the
                   command could not start, a non-zero exit with no `FAIL`
                   line, an exit 0 that printed nothing or printed a `FAIL`;
                   for a CI repo, no completed scheduled run, one over
                   `MAX_RUN_HOURS` old or on a sha not on `<default>`, a
                   conclusion other than success or failure, or a failure
                   whose failed log cannot be read or names no `FAIL` line

A CI run's sha, not the tip, is what a green night records and what a red
night lists the merges up to.

A red night files one `bug` + `ready-for-agent` ticket in the repo, naming the
failing suites and the merges since the last green sha (the first-parent
commits on `<default>` since it, each carrying its PR number as a squash merge
does), and notifies. Each failing suite carries its selector verdict, read
from the last `selector:` comment that `implement/selector_check.py comment`
left on each of those merges' PRs:

    hit       the suite is in at least one merge's listing
    miss      every merge has a listing and the suite is in none of them
    unknown   it is in no listing, but a merge has none (no comment, a
              `not checked` one, the old pre-#1593 verdict format, comments
              that could not be read, a commit naming no PR), there is no
              green sha to list merges from, or no merge landed since it

An unknown is never a miss: a merge whose listing is absent may have selected
the suite (class 1). The verdict of each suite a ticket is filed for is
appended to `selector-verdicts-<owner>__<name>.jsonl` under `$BACKSTOP_DIR`,
once per filing so a repeat red night does not count its miss again; its
`miss` rows are the running count the notification states. A failing suite already named by an open backstop ticket
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
import datetime
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
# A daily schedule's run is under a day old; past two, the schedule has stopped
# (GitHub disables one after 60 days without a push) and the run is old news.
MAX_RUN_HOURS = 48


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


def has_ci(ctx, tip):
    """Whether a workflow file at `tip` carries a `schedule:` trigger."""
    try:
        names = run(["git", "ls-tree", "--name-only", f"{tip}:.github/workflows"], cwd=ctx.root).splitlines()
    except DrainError:
        return False
    for name in names:
        if name.endswith((".yml", ".yaml")):
            text = run(["git", "show", f"{tip}:.github/workflows/{name}"], cwd=ctx.root)
            if re.search(r"^\s*schedule\s*:", text, re.M):
                return True
    return False


_GH_LOG_PREFIX = re.compile(r"^[^\t]*\t[^\t]*\t(\d{4}-\d\d-\d\dT[\d:.]+Z ?)?")


def ci_night(ctx):
    """`night` for a repo with CI, read from its latest completed scheduled
    run; the log ref is the run's URL."""
    branch = ctx.default.split("/", 1)[-1]
    try:
        runs = json.loads(run(["gh", "run", "list", "--repo", ctx.repo, "--event", "schedule", "--branch", branch,
                               "--status", "completed", "--limit", "1",
                               "--json", "databaseId,conclusion,headSha,createdAt,url"]))
    except (DrainError, ValueError) as exc:
        return INCONCLUSIVE, None, f"the scheduled run could not be read: {one_line(exc, 200)}", None
    if not runs:
        return INCONCLUSIVE, None, f"no completed scheduled run on {branch}", None
    latest = runs[0]
    sha, url = latest.get("headSha"), latest.get("url")
    try:
        created = datetime.datetime.fromisoformat(latest["createdAt"].replace("Z", "+00:00"))
        age = datetime.datetime.now(datetime.timezone.utc) - created
    except (KeyError, AttributeError, ValueError):
        return INCONCLUSIVE, sha, f"the scheduled run {url} carries no readable `createdAt`", url
    if age > datetime.timedelta(hours=MAX_RUN_HOURS):
        return INCONCLUSIVE, sha, (f"the latest scheduled run {url} is from {latest['createdAt']}, "
                                   f"over {MAX_RUN_HOURS} hours ago"), url
    try:
        run(["git", "merge-base", "--is-ancestor", str(sha), ctx.default], cwd=ctx.root)
    except DrainError:
        return INCONCLUSIVE, None, f"the scheduled run {url} read {sha}, which is not on {ctx.default}", url
    conclusion = latest.get("conclusion")
    if conclusion == "success":
        return GREEN, sha, None, url
    if conclusion != "failure":
        return INCONCLUSIVE, sha, f"the scheduled run {url} concluded `{conclusion}`", url
    log = os.path.join(ctx.log_dir, f"full-seam-{slug(ctx)}.log")
    try:
        text = run(["gh", "run", "view", str(latest["databaseId"]), "--repo", ctx.repo, "--log-failed"])
    except (DrainError, KeyError) as exc:
        return INCONCLUSIVE, sha, f"the scheduled run {url} failed, but its failed log could not be read: " \
                                  f"{one_line(exc, 150)}", url
    with open(log, "w") as f:
        f.writelines(_GH_LOG_PREFIX.sub("", x) + "\n" for x in text.splitlines())
    failed, _ = failing_suites(log)
    if not failed:
        return INCONCLUSIVE, sha, f"the scheduled run {url} failed, but its log names no `FAIL <suite>` line", url
    return RED, sha, failed, url


def night(ctx, jobs):
    """`(outcome, sha, detail, log ref)`: `sha` is the commit the full run
    read, `detail` the failing suites on red, else the reason, for an
    inconclusive night."""
    tip = None
    try:
        run(["git", "fetch", "-q", "origin"], cwd=ctx.root)
        tip = run(["git", "rev-parse", ctx.default], cwd=ctx.root)
        if has_ci(ctx, tip):
            return ci_night(ctx)
        cmd = seam_command(ctx.root, tip)
    except DrainError as exc:
        return INCONCLUSIVE, tip, f"the seam could not start: {one_line(exc, 200)}", None
    log = os.path.join(ctx.log_dir, f"full-seam-{slug(ctx)}.log")
    ref = f"`{log}` on the machine the backstop ran on"
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
            return INCONCLUSIVE, tip, f"`{cmd}` exited 0 but its log names failing suites ({', '.join(failed)})", ref
        if not printed:
            return INCONCLUSIVE, tip, f"`{cmd}` exited 0 and printed nothing", ref
        return GREEN, tip, None, ref
    if failed:
        return RED, tip, failed, ref
    return INCONCLUSIVE, tip, f"{exited}, and its log ({log}) names no `FAIL <suite>` line", ref


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
    """`(lines, None)`: the first-parent commits on `<default>` after `last`,
    oldest first, as `<sha> <subject>` lines; or `([], why)` they cannot be
    listed."""
    if not last:
        return [], "no green run on record, so the merges since one cannot be listed"
    try:
        listed = run(["git", "log", "--first-parent", "--reverse", "--format=%H %s", f"{last}..{tip}"], cwd=ctx.root)
    except DrainError as exc:
        return [], f"the merges since {last} could not be listed: {one_line(exc, 150)}"
    return listed.splitlines(), None


_PR = re.compile(r"\(#(\d+)\)\s*$")


def pr_listing(ctx, number):
    """`(suites, None)` from the PR's last `selector:` comment, or `(None,
    why)` when it has no readable listing."""
    try:
        comments = json.loads(run(["gh", "pr", "view", number, "--repo", ctx.repo, "--json", "comments"]))["comments"]
        bodies = [c.get("body") or "" for c in comments]
    except (DrainError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return None, f"#{number}'s comments could not be read ({one_line(exc, 100)})"
    last = next((b for b in reversed(bodies) if b.startswith("selector:")), "")
    fence = re.search(r"\n```\n(.*?)\n?```", last, re.S)
    if not last.startswith("selector: listed ") or not fence:
        return None, f"#{number} has no `selector:` listing"
    return {x.strip() for x in fence.group(1).splitlines() if x.strip()}, None


def verdicts(ctx, last, tip, failed):
    """`{suite: (verdict, detail)}` over the merges since `last`."""
    merges, why = merges_since(ctx, last, tip)
    if why or not merges:
        why = why or f"no merge landed since the last green sha {last}"
        return {s: ("unknown", why) for s in failed}
    listings, gaps = {}, []
    for line in merges:
        m = _PR.search(line)
        if not m:
            gaps.append(f"{line[:12]} names no PR")
            continue
        suites, gap = pr_listing(ctx, m.group(1))
        if gap:
            gaps.append(gap)
        else:
            listings[f"#{m.group(1)}"] = suites
    out = {}
    for suite in failed:
        hits = [n for n, suites in listings.items() if suite in suites]
        if hits:
            out[suite] = ("hit", f"selected by {', '.join(hits)}")
        elif gaps:
            readable = f" (none of {', '.join(listings)} selected it)" if listings else ""
            out[suite] = ("unknown", "; ".join(gaps) + readable)
        else:
            out[suite] = ("miss", f"selected by none of {', '.join(listings)}")
    return out


def verdicts_path(ctx):
    return os.path.join(ctx.log_dir, f"selector-verdicts-{slug(ctx)}.jsonl")


def record_verdicts(ctx, tip, judged, suites):
    """Append the filed suites' verdicts; the running `miss` count."""
    path = verdicts_path(ctx)
    with open(path, "a") as f:
        for s in suites:
            f.write(json.dumps({"sha": tip, "suite": s, "verdict": judged[s][0],
                                "date": datetime.date.today().isoformat()}) + "\n")
    with open(path) as f:
        return sum(json.loads(x).get("verdict") == "miss" for x in f if x.strip())


def ticket_body(ctx, tip, last, failed, judged, ref):
    lines = [f"The nightly backstop read the full seam of `{ctx.repo}` on `{ctx.default}` at {tip} and it went red.",
             "", "## Failing suites", "",
             "Each with its selector verdict: `hit` when a merge below selected it, `miss` when every merge has a "
             "listing and none did, `unknown` when a merge's listing is missing.", ""]
    lines += [f"- `{s}`: {judged[s][0]}, {judged[s][1]}" for s in failed]
    lines += ["", f"## Merges since the last green sha ({last or 'none on record'})", ""]
    merges, why = merges_since(ctx, last, tip)
    lines += [f"- {x}" for x in merges] or [f"- ({why or f'none: {tip} is the last green sha'})"]
    lines += ["", "## Log", "", f"{ref}.", "", f"<!-- backstop suites: {json.dumps(failed)} -->", ""]
    return "\n".join(lines)


def file_ticket(ctx, tip, last, failed, judged, ref):
    """The new ticket's URL."""
    with tempfile.NamedTemporaryFile("w", dir=ctx.log_dir, prefix="backstop-body-", suffix=".md",
                                     delete=False) as f:
        f.write(ticket_body(ctx, tip, last, failed, judged, ref))
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


def report_red(ctx, tip, failed, notifier, ref):
    """File or name the ticket, notify; the exit code."""
    try:
        with open(last_green_path(ctx)) as f:
            last = f.read().strip() or None
    except OSError:
        last = None
    title = f"backstop: {ctx.repo} red"
    try:
        named = open_backstop_tickets(ctx)
        new = [s for s in failed if s not in named]
        if new:
            judged = verdicts(ctx, last, tip, failed)
            url = file_ticket(ctx, tip, last, failed, judged, ref)
            body = f"{', '.join(failed)} failing at {tip[:12]}; filed {url}"
            try:
                misses = record_verdicts(ctx, tip, judged, new)
            except (OSError, ValueError) as exc:
                print(f"backstop.py: selector verdicts not recorded: {one_line(exc, 200)}", file=sys.stderr)
                body += "; selector verdicts not recorded"
            else:
                body += f"; {misses} selector {'miss' if misses == 1 else 'misses'} on record"
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
    outcome, tip, detail, ref = night(ctx, args.jobs)
    if outcome == INCONCLUSIVE:
        return report_inconclusive(repo, f"{detail} (at {tip or 'no tip read'})", args.notify)
    if outcome == GREEN:
        with open(last_green_path(ctx), "w") as f:
            f.write(tip + "\n")
        print(f"backstop: {repo} green at {tip}")
        return GREEN
    if outcome == RED:
        return report_red(ctx, tip, detail, args.notify, ref)
    return outcome


if __name__ == "__main__":
    sys.exit(main())
