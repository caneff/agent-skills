#!/usr/bin/env python3
"""`backstop.py --repo <checkout> --jobs <k> [--workflow <file>] [--notify
<cmd>]`: the nightly full run of one repo's seam.

Per change the lane runs only the repo's narrowed command; this is the one
full run, once a night. It fetches origin and reads the tip of
`origin/<default>`. A repo with CI is one whose caller names its full-gate
workflow with `--workflow <file>` (`ci.yml`): that workflow already ran the
full gate on GitHub on a daily schedule, so no seam runs locally and the night
is the latest scheduled run of that workflow on `<default>` (`gh run list
--workflow <file> --event schedule`), whatever its status. Without
`--workflow` the repo runs locally, whatever its workflows hold: its `**Seam**`
command, as `AGENTS.md` § End-to-end seam declares it, runs on the tip in a
throwaway worktree. Either way the night is one of three outcomes:

    green          the seam exited 0, printed something itself (`npm ci`'s
                   output before it does not count), and no line starts
                   `FAIL `: the tip is recorded as the last green sha.
                   A suite whose PASS line says it ran over its CPU budget
                   (`tests/all.sh` measures it and does not fail on it) is
                   printed and notified as such; the night stays green. A red
                   night prints them too, without a second notice. The same
                   holds for the always-on word count `tests/all.sh` prints
                   (`always-on: total <n> words, over its budget of <b>`, #2016)
    red            the seam exited non-zero and named its failing suites with
                   `FAIL <suite>` lines
    inconclusive   anything else: the repo's origin, its owner or its
                   `origin/HEAD` could not be read, no seam declared, the
                   worktree or the command could not start, a non-zero exit
                   with no `FAIL` line, an exit 0 that printed nothing or
                   printed a `FAIL`; for a CI repo, no scheduled run, a latest
                   one not yet completed, over `MAX_RUN_HOURS` old or on a sha
                   not on `<default>`, a conclusion other than success or
                   failure, a failure already reported on an earlier night, or
                   one whose failed log cannot be read or names no `FAIL` line;
                   and any exception the backstop did not expect, a failed
                   import of its neighbours included

A CI run's sha, not the tip, is what a green night records and what a red
night lists the merges up to. `MAX_RUN_HOURS` is 26: a daily schedule's latest
run is under 24 hours old plus GitHub's start delay, so an older one means the
run due since has not happened (dropped, or the schedule disabled after 60 days
without a push), and yesterday's result is not tonight's.

A red night files one `bug` + `ready-for-agent` ticket in the repo, naming the
failing suites, the merges since the last green sha (the first-parent commits
on `<default>` since it that carry a PR number, as a squash merge does) and,
under their own heading, the direct commits since it (those that name no PR),
and notifies. Each failing suite carries its selector verdict, read from the
last `selector:` comment that `implement/selector_check.py comment` left on
each merge's PR:

    hit       the suite is in at least one merge's listing
    miss      every merge has a listing and the suite is in none of them
    unknown   it is in no listing, but a merge has none (no comment, a
              `not checked` one, the old verdict format, comments that could
              not be read), there is no green sha to list merges from, or no
              PR merge landed since it

A direct commit is the non-code lane (only non-code ships directly on the
default branch), which runs no narrowed command, so it owes no listing and
does not make a verdict unknown. An unknown is never a miss: a merge whose
listing is absent may have selected the suite (class 1). The verdict of each
suite a ticket is filed for is appended to
`selector-verdicts-<owner>__<name>.jsonl` under `$BACKSTOP_DIR`, once per
filing so a repeat red night does not count its miss again; its `miss` rows
are the running count the notification states. A failing suite already named
by an open backstop ticket (one whose body carries the `<!-- backstop suites:
[...] -->` marker) is not filed again: a red night whose every failing suite
is named by one files nothing and notifies that it is still red, naming those
tickets. A red CI run, once filed or named that way, has its run id appended
to `reported-runs-<owner>__<name>`, so the same run read on a later night is
never reported again. An inconclusive night is notified and never recorded
green (`AGENTS.md` § Recurring defect classes, class 1). A failure to list the
open tickets, file one or notify is said on stderr and in the exit code, never
swallowed.

`--jobs <k>` is required, never `nproc`: it reaches the seam as `TESTS_JOBS`,
the job count `tests/all.sh` reads, so the full run never crowds the agents
sharing the box. A seam that ignores `TESTS_JOBS` is that repo's to fix.
`--notify` is the notifier, called as `<cmd> <title> <body>`; it defaults to
this repo's `flow/bin/notify-send`. The record is `last-green-<owner>__<name>`
under `$BACKSTOP_DIR` (default `~/.cache/backstop`), beside the night's log,
`full-seam-<owner>__<name>.log`. Only a repo whose origin owner is the `gh`
login is run: filing a ticket is outward-facing.

Exit 0 green, 1 red, 2 inconclusive, 3 when a red or inconclusive night's
ticket or notification, or a green night's over-budget notification, could not
be sent.
"""
import argparse
import collections
import datetime
import json
import os
import re
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
# One line per directory, each spelled out, so `tests/suite-edges.py` sees the
# edge and a change there runs this directory's suites.
sys.path.insert(0, os.path.join(_HERE, os.pardir, "common"))
sys.path.insert(0, os.path.join(_HERE, os.pardir, "implement"))
sys.path.insert(0, os.path.join(_HERE, os.pardir, "implement-spec"))
# The git and gh calls, the scratch-tree run, the origin slug and the default
# branch come from the shared helpers; the seam section's grammar has one copy
# too. A neighbour that no longer imports is an inconclusive night, said by
# `main`.
try:
    import scratch_run  # noqa: E402
    import shellcmd  # noqa: E402
    from scratch_run import one_line  # noqa: E402
    import tracker as issue_tracker  # noqa: E402  (#1786)
    import owners  # noqa: E402  (#2005)
    from closing_ticket import declaration  # noqa: E402
    from selector_check import command_of, failing_suites  # noqa: E402
    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001 - any import failure, reported by main
    _IMPORT_ERROR = exc

WALL_CLOCK_SECONDS = 3 * 60 * 60  # the seam's own bound; the helper's timeout is for its short calls
Ctx = collections.namedtuple("Ctx", "root repo default log_dir tracker")
NOTIFY_SEND = os.path.join(_HERE, os.pardir, "flow", "bin", "notify-send")
GREEN, RED, INCONCLUSIVE, UNSENT = 0, 1, 2, 3
MAX_RUN_HOURS = 26
# Echoed before the seam in its worktree: what follows it in the log is the
# seam's own output, what precedes it `npm ci`'s.
SEAM_BEGINS = "backstop: the seam output begins here"

# `sha` is the commit the full run read, `detail` the failing suites on red,
# else the reason, `ref` where the log is, `run` a CI run's id.
Night = collections.namedtuple("Night", "outcome sha detail ref run", defaults=(None, None, None, None))


class BackstopError(Exception):
    """A step failed; the message is the reason put in the night's note."""


def repo_slug(ctx):
    """`owner__name`: the repo as one file-name component."""
    return ctx.repo.replace("/", "__")


def git(args, cwd=None):
    """Stdout of `git <args>`, stripped; `BackstopError` on any failure."""
    try:
        return shellcmd.git(args, cwd=cwd).stdout.strip()
    except shellcmd.CmdError as exc:
        raise BackstopError(str(exc)) from exc


def asked(call, *args):
    """`call(*args)`, a call on the tracker; its `TrackerError` is this script's one failure."""
    try:
        return call(*args)
    except issue_tracker.TrackerError as exc:
        raise BackstopError(str(exc)) from exc


def run_in_scratch_tree(ctx, cmd, log, rev):
    """`scratch_run.run_in_scratch_tree` on `rev` under the seam's wall clock; any failure there
    is a `BackstopError`."""
    try:
        scratch_run.run_in_scratch_tree(ctx.root, rev, cmd, log, WALL_CLOCK_SECONDS)
    except scratch_run.ScratchError as exc:
        raise BackstopError(str(exc)) from exc


def positive(text):
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be a positive integer, got {text}")
    return value


def seam_command(root, tip):
    """The `**Seam**` command `AGENTS.md` declares at `tip`. Raises
    `BackstopError` naming the gap."""
    try:
        text = git(["show", f"{tip}:AGENTS.md"], cwd=root)
    except BackstopError as exc:
        raise BackstopError(f"no AGENTS.md at {tip[:12]}: {one_line(exc, 150)}") from exc
    found = declaration(text)
    if found is None:
        raise BackstopError("AGENTS.md has no `## End-to-end seam` section")
    if "seam" not in found:
        raise BackstopError("AGENTS.md § End-to-end seam declares no `Seam` line")
    command = command_of(found["seam"])
    if not command:
        raise BackstopError("the `Seam` line names no command")
    return command


def seam_log(ctx):
    return os.path.join(ctx.log_dir, f"full-seam-{repo_slug(ctx)}.log")


def last_green_path(ctx):
    return os.path.join(ctx.log_dir, f"last-green-{repo_slug(ctx)}")


def reported_runs_path(ctx):
    return os.path.join(ctx.log_dir, f"reported-runs-{repo_slug(ctx)}")


def verdicts_path(ctx):
    return os.path.join(ctx.log_dir, f"selector-verdicts-{repo_slug(ctx)}.jsonl")


def reported_runs(ctx):
    try:
        with open(reported_runs_path(ctx)) as f:
            return {x.strip() for x in f if x.strip()}
    except FileNotFoundError:
        return set()


_GH_LOG_PREFIX = re.compile(r"^[^\t]*\t[^\t]*\t(\d{4}-\d\d-\d\dT[\d:.]+Z ?)?")


def ci_night(ctx, workflow):
    """The `Night` of a repo with CI, read from the latest scheduled run of
    `workflow`; the log ref is the run's URL."""
    branch = ctx.default.split("/", 1)[-1]
    try:
        runs = asked(ctx.tracker.runs, workflow, branch)
    except BackstopError as exc:
        return Night(INCONCLUSIVE, None, f"the scheduled run could not be read: {one_line(exc, 200)}")
    if not runs:
        return Night(INCONCLUSIVE, None, f"no scheduled run of {workflow} on {branch}")
    latest = runs[0]
    sha, url, run_id = latest.get("headSha"), latest.get("url"), latest.get("databaseId")
    if latest.get("status") != "completed":
        return Night(INCONCLUSIVE, sha, f"the latest scheduled run {url} is `{latest.get('status')}`, not completed",
                     url)
    try:
        created = datetime.datetime.fromisoformat(latest["createdAt"].replace("Z", "+00:00"))
        age = datetime.datetime.now(datetime.timezone.utc) - created
    except (KeyError, AttributeError, ValueError):
        return Night(INCONCLUSIVE, sha, f"the scheduled run {url} carries no readable `createdAt`", url)
    if age > datetime.timedelta(hours=MAX_RUN_HOURS):
        return Night(INCONCLUSIVE, sha, f"the latest scheduled run {url} is from {latest['createdAt']}, "
                                        f"over {MAX_RUN_HOURS} hours ago", url)
    try:
        git(["merge-base", "--is-ancestor", str(sha), ctx.default], cwd=ctx.root)
    except BackstopError:
        return Night(INCONCLUSIVE, None, f"the scheduled run {url} read {sha}, which is not on {ctx.default}", url)
    conclusion = latest.get("conclusion")
    if conclusion == "success":
        return Night(GREEN, sha, None, url)
    if conclusion != "failure":
        return Night(INCONCLUSIVE, sha, f"the scheduled run {url} concluded `{conclusion}`", url)
    if str(run_id) in reported_runs(ctx):
        return Night(INCONCLUSIVE, sha, f"the latest scheduled run {url} failed and was already reported on an "
                                        "earlier night; no newer run has completed", url)
    try:
        text = asked(ctx.tracker.run_failed_log, run_id)
    except BackstopError as exc:
        return Night(INCONCLUSIVE, sha, f"the scheduled run {url} failed, but its failed log could not be read: "
                                        f"{one_line(exc, 150)}", url)
    log = seam_log(ctx)
    with open(log, "w") as f:
        f.writelines(_GH_LOG_PREFIX.sub("", x) + "\n" for x in text.splitlines())
    failed, _ = failing_suites(log)
    if not failed:
        return Night(INCONCLUSIVE, sha, f"the scheduled run {url} failed, but its log names no `FAIL <suite>` line",
                     url)
    return Night(RED, sha, failed, url, run_id)


def seam_printed(log):
    """Whether the seam itself wrote anything to `log`, after `SEAM_BEGINS`.
    No marker (the seam never started) is nothing printed."""
    try:
        with open(log, errors="replace") as f:
            text = f.read()
    except OSError:
        return False
    _, marker, own = text.partition(SEAM_BEGINS + "\n")
    return bool(marker) and bool(own.strip())


# `tests/all.sh` marks a suite that passed over its CPU budget on its PASS
# line; that line is the whole interface.
_OVER_BUDGET = re.compile(r"^PASS (\S.*?) \(([0-9.]+)s cpu, over its ([0-9.]+)s budget\)$")


def over_budget(log):
    """`[(suite, cpu, budget)]` the seam's PASS lines in `log` mark as over
    their CPU budget. An unreadable log names none: a green night is not
    held back by it."""
    try:
        with open(log, errors="replace") as f:
            return [m.groups() for m in map(_OVER_BUDGET.match, f.read().splitlines()) if m]
    except OSError:
        return []


# `tests/all.sh` prints the always-on word count on every run (#2016); an
# overrun is read from that line.
_ALWAYS_ON = re.compile(r"^always-on: total (\d+) words(?:, incomplete: [^,]*)?, over its budget of (\d+)$")


def always_on_overrun(log):
    """`(words, budget)` when the seam's always-on line in `log` says the count
    is over its budget, else None. An unreadable log or a missing line names
    none: the count is a report, never a reason to hold a night back."""
    try:
        with open(log, errors="replace") as f:
            for m in map(_ALWAYS_ON.match, f.read().splitlines()):
                if m:
                    return m.groups()
    except OSError:
        pass
    return None


def local_night(ctx, tip, jobs):
    try:
        cmd = seam_command(ctx.root, tip)
    except BackstopError as exc:
        return Night(INCONCLUSIVE, tip, f"the seam could not start: {one_line(exc, 200)}")
    log = seam_log(ctx)
    ref = f"`{log}` on the machine the backstop ran on"
    os.environ["TESTS_JOBS"] = str(jobs)
    marked = f"echo '{SEAM_BEGINS}'\n{cmd}"
    try:
        run_in_scratch_tree(ctx, marked, log, rev=tip)
        exited = 0
    except BackstopError as exc:
        exited = one_line(str(exc).replace(marked, cmd), 200)
    failed, _ = failing_suites(log)
    if exited == 0:
        if failed:
            return Night(INCONCLUSIVE, tip, f"`{cmd}` exited 0 but its log names failing suites "
                                            f"({', '.join(failed)})", ref)
        if not seam_printed(log):
            return Night(INCONCLUSIVE, tip, f"`{cmd}` exited 0 and printed nothing", ref)
        return Night(GREEN, tip, None, ref)
    if failed:
        return Night(RED, tip, failed, ref)
    return Night(INCONCLUSIVE, tip, f"{exited}, and its log ({log}) names no `FAIL <suite>` line", ref)


def night(ctx, jobs, workflow):
    try:
        git(["fetch", "-q", "origin"], cwd=ctx.root)
        tip = git(["rev-parse", ctx.default], cwd=ctx.root)
    except BackstopError as exc:
        return Night(INCONCLUSIVE, None, f"the tip of {ctx.default} could not be read: {one_line(exc, 200)}")
    if workflow:
        return ci_night(ctx, workflow)
    return local_night(ctx, tip, jobs)


_MARKER = re.compile(r"<!-- backstop suites: (.*?) -->")


def open_backstop_tickets(ctx):
    """`{suite: ticket number}` over the open `bug` tickets carrying the
    marker. A marker that does not parse names nothing, so its suites are
    filed again: a duplicate ticket, never a failure left unfiled."""
    named = {}
    for issue in asked(ctx.tracker.issues, "bug"):
        if "pull_request" in issue:  # the REST issue list holds pull requests too
            continue
        m = _MARKER.search(issue.get("body") or "")
        try:
            suites = json.loads(m.group(1)) if m else []
        except ValueError:
            suites = []
        for suite in suites if isinstance(suites, list) else []:
            named.setdefault(suite, issue["number"])
    return named


_PR = re.compile(r"\(#(\d+)\)\s*$")

# The first-parent commits since the last green sha, as `<sha> <subject>`
# lines: `merges` name a PR, `direct` do not; `why` they could not be listed.
Since = collections.namedtuple("Since", "merges direct why")


def commits_since(ctx, last, tip):
    if not last:
        return Since([], [], "no green run on record, so the merges since one cannot be listed")
    try:
        listed = git(["log", "--first-parent", "--reverse", "--format=%H %s", f"{last}..{tip}"], cwd=ctx.root)
    except BackstopError as exc:
        return Since([], [], f"the merges since {last} could not be listed: {one_line(exc, 150)}")
    lines = listed.splitlines()
    return Since([x for x in lines if _PR.search(x)], [x for x in lines if not _PR.search(x)], None)


def pr_listing(ctx, number):
    """`(suites, None)` from the PR's last `selector:` comment, or `(None,
    why)` when it has no readable listing."""
    try:
        bodies = asked(ctx.tracker.pr_comments, int(number))
    except BackstopError as exc:
        return None, f"#{number}'s comments could not be read ({one_line(exc, 100)})"
    last = next((b for b in reversed(bodies) if b.startswith("selector:")), "")
    fence = re.search(r"\n```\n(.*?)\n?```", last, re.S)
    if not last.startswith("selector: listed ") or not fence:
        return None, f"#{number} has no `selector:` listing"
    return {x.strip() for x in fence.group(1).splitlines() if x.strip()}, None


def verdicts(ctx, last, since, failed):
    """`{suite: (verdict, detail)}` over the PR merges in `since`; its direct
    commits owe no listing."""
    if since.why or not since.merges:
        why = since.why or f"no PR merge landed since the last green sha {last}"
        return {s: ("unknown", why) for s in failed}
    listings, gaps = {}, []
    for line in since.merges:
        number = _PR.search(line).group(1)
        suites, gap = pr_listing(ctx, number)
        if gap:
            gaps.append(gap)
        else:
            listings[f"#{number}"] = suites
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


def record_verdicts(ctx, tip, judged, suites):
    """Append the filed suites' verdicts; the running `miss` count."""
    path = verdicts_path(ctx)
    with open(path, "a") as f:
        for s in suites:
            f.write(json.dumps({"sha": tip, "suite": s, "verdict": judged[s][0],
                                "date": datetime.date.today().isoformat()}) + "\n")
    with open(path) as f:
        return sum(json.loads(x).get("verdict") == "miss" for x in f if x.strip())


def ticket_body(ctx, tip, last, failed, judged, ref, since):
    lines = [f"The nightly backstop read the full seam of `{ctx.repo}` on `{ctx.default}` at {tip} and it went red.",
             "", "## Failing suites", "",
             "Each with its selector verdict: `hit` when a merge below selected it, `miss` when every merge has a "
             "listing and none did, `unknown` when a merge's listing is missing.", ""]
    lines += [f"- `{s}`: {judged[s][0]}, {judged[s][1]}" for s in failed]
    lines += ["", f"## Merges since the last green sha ({last or 'none on record'})", ""]
    lines += [f"- {x}" for x in since.merges] or [f"- ({since.why or 'none that names a PR'})"]
    if since.direct:
        lines += ["", "## Direct commits since the last green sha", "",
                  "Commits naming no PR: the non-code lane, which runs no narrowed command and owes no listing.", ""]
        lines += [f"- {x}" for x in since.direct]
    lines += ["", "## Log", "", f"{ref}.", "", f"<!-- backstop suites: {json.dumps(failed)} -->", ""]
    return "\n".join(lines)


def file_ticket(ctx, tip, failed, body):
    """The new ticket's URL."""
    title = f"backstop: full seam red on {ctx.default.split('/')[-1]}: {', '.join(failed)}"
    return asked(ctx.tracker.create_issue, one_line(title, 200), body, ["bug", "ready-for-agent"])


def notify(cmd, title, body):
    """Send the notification; when it could not be sent, say why on stderr
    and return False. Needs nothing from the neighbours, so a failed import
    is still notified."""
    try:
        out = subprocess.run([cmd, title, body], capture_output=True, text=True)
        why = None if out.returncode == 0 else (out.stderr or out.stdout or f"exit {out.returncode}")
    except OSError as exc:
        why = exc
    if why:
        print(f"backstop.py: notification not sent: {' '.join(str(why).split())[:200]}", file=sys.stderr)
    return not why


def report_red(ctx, red, notifier):
    """File or name the ticket for a red `Night`, notify; the exit code."""
    tip, failed = red.sha, red.detail
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
            since = commits_since(ctx, last, tip)
            judged = verdicts(ctx, last, since, failed)
            url = file_ticket(ctx, tip, failed, ticket_body(ctx, tip, last, failed, judged, red.ref, since))
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
    except (BackstopError, ValueError, OSError) as exc:
        body = f"{', '.join(failed)} failing at {tip[:12]}; no ticket filed: {one_line(exc, 200)}"
        print(f"backstop.py: {body}", file=sys.stderr)
        notify(notifier, title, body)
        return UNSENT
    if red.run is not None:
        try:
            with open(reported_runs_path(ctx), "a") as f:
                f.write(f"{red.run}\n")
        except OSError as exc:
            print(f"backstop.py: run {red.run} not recorded as reported: {one_line(exc, 200)}", file=sys.stderr)
            body += f"; run {red.run} not recorded as reported"
    print(f"backstop: {body}")
    return RED if notify(notifier, title, body) else UNSENT


def report_inconclusive(repo, why, notifier):
    """Notify a night that is neither green nor red; the exit code."""
    print(f"backstop.py: {repo} inconclusive: {why}", file=sys.stderr)
    return INCONCLUSIVE if notify(notifier, f"backstop: {repo} inconclusive", why) else UNSENT


def backstop(args):
    """One night for `args.repo`; the exit code."""
    root = os.path.abspath(args.repo)
    try:
        repo = shellcmd.origin_slug(root)
    except shellcmd.CmdError as exc:
        return report_inconclusive(args.repo, f"its origin could not be read: {one_line(exc, 200)}", args.notify)
    if repo is None:
        return report_inconclusive(args.repo, "its origin is not a github.com repo", args.notify)
    try:
        login = asked(issue_tracker.GhTracker(repo).viewer_login)
    except BackstopError as exc:
        return report_inconclusive(repo, f"the `gh` login could not be read: {one_line(exc, 200)}", args.notify)
    try:
        owned = owners.is_owned(repo.split("/")[0], login)
    except owners.OwnersError as exc:
        return report_inconclusive(repo, f"ownership could not be read: {one_line(exc, 200)}", args.notify)
    if not owned:
        return report_inconclusive(repo, f"{repo} is not owned by {login} nor on the owned-owners list; the backstop "
                                         "files tickets only on the caller's own repos", args.notify)
    try:
        default = shellcmd.default_branch(root)
    except shellcmd.CmdError as exc:
        return report_inconclusive(repo, f"origin/HEAD is not set, so the default branch is unknown: "
                                         f"{one_line(exc, 300)}", args.notify)
    state_dir = os.environ.get("BACKSTOP_DIR") or os.path.expanduser("~/.cache/backstop")
    os.makedirs(state_dir, exist_ok=True)
    ctx = Ctx(root, repo, default, state_dir, issue_tracker.GhTracker(repo))
    result = night(ctx, args.jobs, args.workflow)
    # A CI night has no local log of its own (the one on disk is an earlier
    # failed run's), so it names none. A red night's seam stopped at its first
    # failure, so it names the overruns of the suites that ran before it.
    over = [] if args.workflow or result.outcome not in (GREEN, RED) else over_budget(seam_log(ctx))
    for suite, cpu, budget in over:
        print(f"backstop: over CPU budget: {suite}: {cpu}s cpu over its {budget}s budget")
    words = None if args.workflow or result.outcome not in (GREEN, RED) else always_on_overrun(seam_log(ctx))
    if words:
        print(f"backstop: always-on over budget: {words[0]} words against {words[1]}")
    if result.outcome == GREEN:
        with open(last_green_path(ctx), "w") as f:
            f.write(result.sha + "\n")
        print(f"backstop: {repo} green at {result.sha}")
        if over:
            title = f"backstop: {repo} green, {len(over)} {'suite' if len(over) == 1 else 'suites'} over " \
                    f"{'its' if len(over) == 1 else 'their'} CPU budget"
            if words:
                title += f", always-on {words[0]} words over its {words[1]} budget"
            if not notify(args.notify, title, "; ".join(f"{s}: {c}s against {b}s" for s, c, b in over)):
                return UNSENT
        elif words:
            if not notify(args.notify, f"backstop: {repo} green, always-on {words[0]} words over its {words[1]} budget",
                          f"the always-on text is {words[0]} words against a budget of {words[1]}"):
                return UNSENT
        return GREEN
    if result.outcome == RED:
        return report_red(ctx, result, args.notify)
    return report_inconclusive(repo, f"{result.detail} (at {result.sha or 'no tip read'})", args.notify)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo", required=True, help="the repo's checkout")
    parser.add_argument("--jobs", type=positive, required=True, help="the seam's job count (TESTS_JOBS)")
    parser.add_argument("--workflow", help="the file name of the workflow that runs the full gate on a daily "
                                           "schedule; without it the seam runs here")
    parser.add_argument("--notify", default=NOTIFY_SEND, help="the notifier, called as <cmd> <title> <body>")
    args = parser.parse_args(argv)
    if _IMPORT_ERROR is not None:
        return report_inconclusive(args.repo, f"backstop.py could not import its neighbours: "
                                              f"{type(_IMPORT_ERROR).__name__}: {_IMPORT_ERROR}", args.notify)
    try:
        return backstop(args)
    except Exception as exc:  # noqa: BLE001 - a crash must not exit 1, the red code (class 1)
        why = " ".join(f"backstop.py crashed: {type(exc).__name__}: {exc}".split())[:300]
        return report_inconclusive(args.repo, why, args.notify)


if __name__ == "__main__":
    sys.exit(main())
