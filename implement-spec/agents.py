#!/usr/bin/env python3
"""Agent counting: how many agents the box is running, and whether it has
room for more. The process, herdr and session-file counts, and `box_check`
and the caps it holds, live here so a reader of the box (`loop.py`, `drain`,
the backstop) imports them without the dispatch loop (#1770). `loop.py box`
is the CLI over them.

Why each rule reads the way it does: `references/loop.md`.
"""
import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "common"))
import shellcmd  # noqa: E402


class AgentError(Exception):
    """A count or probe that could not be taken: refused, never read as
    zero or as a dead agent."""


# The box's two caps, from `~/.claude/CLAUDE.md`'s memory rules, which is
# their source: this is the one place in the repo that holds the numbers, and
# the prose says what `loop.py box` enforces rather than restating them.
PROCESS_CAP = 28
# A slot's peak, not its steady state: the worker plus the three review axes
# `/multi-axis-code-review` runs at once, plus one for the Codex pass that
# runs beside them.
# A slot charged at 1 while it peaks at 5 is how three slots put 20 processes
# on a box the check had read as 15 (#933). The one place the multiplier is
# stated: `box_check` and the status line both read it here.
SLOT_PEAK_PROCESSES = 5
VM_BUDGET_GB = 24


AGENT_COUNTER = "`ps -eo comm=` lines equal to claude"
HERDR_COUNTER = ("`herdr agent list` working panes plus claude pids no "
                "pane resolves to")
UNSTATED_COUNTER = "count supplied by the caller"


def _run_counted(cmd):
    """(status, stdout) for a counting command — `ps` or `herdr` — run with
    a 10s timeout; the default `ps`/`run` both counters take when the
    caller passes none. An `OSError` (the binary is missing) or a
    subprocess failure reads as a failed run, not a crash: the caller
    decides whether that is refusable."""
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, f"{exc}"
    return done.returncode, done.stdout


def count_agent_processes(ps=None):
    """The agent processes on the box, counted by command name: one per
    `claude` session (subagents run inside it). Counting by name and not by
    argument (`pgrep -f claude`) keeps plugin scripts and hook shims, whose
    arguments merely mention a claude path, out of the count.

    A count that could not be taken raises: a failed or empty `ps` is not
    "0 agents, the box is wide open". `ps` takes the command and returns
    (exit status, stdout).
    """
    if ps is None:
        ps = _run_counted
    status, out = ps(["ps", "-eo", "comm="])
    names = [line.strip() for line in out.splitlines() if line.strip()]
    if status != 0 or not names:
        raise AgentError(
            "could not count the agent processes on the box (`ps -eo comm=` "
            "failed or listed nothing), and an unmeasured box is not an "
            "empty one: refusing to dispatch — pass --processes <n> with a "
            "count you took")
    agents = sum(1 for name in names if name == "claude")
    if agents == 0:
        # The controller running this is itself a claude session, so a
        # healthy listing with none means the name did not match (a wrapper,
        # a renamed launcher) and the cap would never fire.
        raise AgentError(
            f"`ps -eo comm=` listed {len(names)} processes and none named "
            "claude, yet this controller is one: the count cannot be "
            "trusted, so refusing to dispatch — pass --processes <n> with a "
            "count you took")
    return agents


def _proc_start(pid, proc_root="/proc"):
    """Field 22 of `/proc/<pid>/stat` — the kernel's own start-time
    fingerprint for that pid, the same field `agent-status.md`'s liveness
    check and `worker-alert-lib.sh`/`resolve-controller` compare a
    registry record's `procStart` against. `None` when the process is
    gone or `/proc` cannot be read.

    The `comm` field (2nd) is parenthesised and can itself contain spaces
    or parens, so this splits on the *last* `)` rather than on whitespace
    — the same reader `ps`'s own `comm=` parsing sidesteps by never
    touching this file at all.
    """
    try:
        with open(f"{proc_root}/{pid}/stat") as fh:
            text = fh.read()
    except OSError:
        return None
    end = text.rfind(")")
    if end == -1:
        return None
    fields = text[end + 1:].split()
    return fields[19] if len(fields) > 19 else None


def _session_pids(sessions_dir=None, proc_start=None):
    """`{sessionId: pid}` off the live sessions registry
    (`~/.claude/sessions/<pid>.json`), the same file `agent-status.md`
    reads and `resolve-controller` resolves through — validated against
    `/proc/<pid>/stat`'s own start time the same way both of those do.
    A pid recycles: after a WSL restart or an ordinary pid reuse, a stale
    record can still name a pid that is alive again as a completely
    different process. Matching on the name alone let that stale record
    claim the live process's pid, dropping it out of
    `count_working_herdr_agents`'s `unlisted` bucket while the record's
    own (often idle) status added nothing for it — a live process
    silently uncounted (Codex gate finding on 9391bd8). A record whose
    `procStart` does not match is not a match; its pid stays unresolved.

    Read fresh on every call — a pane's session can end between ticks —
    and skipped rather than raised on a directory or file this run cannot
    read: a registry gap fails a session's *match*, which
    `count_working_herdr_agents` already fails closed on, not the whole
    count. `proc_start` takes a pid and returns field 22 or `None`
    (default `_proc_start`, reading `/proc` directly).
    """
    sessions_dir = sessions_dir or os.path.expanduser("~/.claude/sessions")
    if proc_start is None:
        proc_start = _proc_start
    mapping = {}
    try:
        names = os.listdir(sessions_dir)
    except OSError:
        return mapping
    for name in names:
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(sessions_dir, name)) as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        sid, pid = data.get("sessionId"), data.get("pid")
        if not (isinstance(sid, str) and sid and isinstance(pid, int)):
            continue
        if proc_start(pid) != data.get("procStart"):
            continue
        mapping[sid] = pid
    return mapping


def count_working_herdr_agents(ps=None, herdr=None, sessions=None):
    """(working, unlisted): the box's working agents, herdr's own way —
    herdr counts by pane, one entry per Claude session, a review
    fan-out's subagents folded into that one entry rather than listed on
    their own. `working` is every listed pane whose `agent_status` is
    not `idle` or `done` — those two are the only statuses read as not
    working; a missing, null or unrecognised status fails closed as
    working rather than vanishing from the count (Codex gate finding on
    7a6bedd) — plus every listed pane whose session cannot be resolved to
    a pid (a resolution failure fails closed the same way, counted as
    working rather than dropped). `unlisted` is every `claude` pid `ps`
    shows that no listed pane resolved to — a subagent or headless run
    herdr does not pane-list, which still burns a core and fails closed
    the same way (#1075 controller ruling, correcting the ticket's
    original premise that herdr lists a subagent as its own agent).

    `ps`/`herdr` take a command and return (status, stdout), the contract
    `count_agent_processes` uses; `sessions` takes nothing and returns
    `{sessionId: pid}` (default `_session_pids`). Raises when either `ps`
    or herdr cannot be asked or answers something unusable, or when the
    herdr listing is empty or resolves to none of the box's actual
    `claude` pids while `ps` shows some exist — herdr's registry read as
    broken, not the box read as idle, the same shape of refusal
    `count_agent_processes` gives an all-idle `ps` listing.
    """
    if ps is None:
        ps = _run_counted
    if herdr is None:
        herdr = _run_counted
    if sessions is None:
        sessions = _session_pids

    pid_status, pid_out = ps(["ps", "-eo", "pid,comm"])
    if pid_status != 0 or not pid_out.strip():
        raise AgentError(
            "could not list claude pids on the box (`ps -eo pid,comm` "
            "failed or listed nothing), and an unmeasured box is not an "
            "empty one: refusing to dispatch — pass --processes <n> with a "
            "count you took")
    claude_pids = set()
    for line in pid_out.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[0].isdigit() and parts[1].strip() == "claude":
            claude_pids.add(int(parts[0]))
    if not claude_pids:
        # The controller running this is itself a claude session, so a
        # healthy listing with none means the name did not match.
        raise AgentError(
            "`ps -eo pid,comm` listed processes and none named claude, yet "
            "this controller is one: the pid count cannot be trusted, so "
            "refusing to dispatch — pass --processes <n> with a count you "
            "took")

    status, out = herdr(["herdr", "agent", "list"])
    if status != 0:
        raise AgentError(
            f"herdr agent list failed: {(out or '').strip() or 'no output'}")
    try:
        answer = json.loads(out)
    except (TypeError, ValueError) as exc:
        raise AgentError(f"herdr agent list did not answer JSON: {exc}") from exc
    result = answer.get("result") if isinstance(answer, dict) else None
    agents = result.get("agents") if isinstance(result, dict) else None
    if not isinstance(agents, list):
        raise AgentError(
            f"herdr agent list answered {answer!r}, no agents list to count")

    sid_to_pid = sessions()
    working = 0
    matched_pids = set()
    for agent in agents:
        if not isinstance(agent, dict):
            continue
        session = agent.get("agent_session")
        sid = session.get("value") if isinstance(session, dict) else None
        pid = sid_to_pid.get(sid) if isinstance(sid, str) else None
        if pid is None:
            working += 1  # unresolved: fail closed, counted working
            continue
        matched_pids.add(pid)
        # Only "idle" and "done" exclude a pane. A missing, null or
        # unrecognised status is not known idle, so it counts as working —
        # the same fail-closed reading an unresolved pane already gets;
        # equality against "working" alone let a wedged or unclassified
        # pane read as neither working nor unlisted and vanish from the
        # count (Codex gate finding, 7a6bedd).
        if agent.get("agent_status") not in ("idle", "done"):
            working += 1

    if not matched_pids:
        raise AgentError(
            f"herdr agent list named {len(agents)} agent(s) but none "
            f"resolved to any of the {len(claude_pids)} claude pid(s) `ps` "
            "shows on the box — herdr's registry reads as broken, not the "
            "box as idle; pass --processes <n> with a count you took")

    return working, len(claude_pids - matched_pids)


def projected_processes(processes, workers, live):
    """(reserve, projected): the one place the peak arithmetic lives, read by
    the gate and by the status line so they cannot disagree."""
    reserve = live * (SLOT_PEAK_PROCESSES - 1)
    return reserve, processes + reserve + workers * SLOT_PEAK_PROCESSES


def box_check(processes, committed_gb, workers=1,
              counter=UNSTATED_COUNTER, live=0):
    """Whether the box has room for one more worker, and every reason it does
    not.

    `processes` is the agent processes on the box — Claude sessions, not OS
    processes, and not only this run's. The cap is Chris's "no more than 28
    cores TOTAL" on a box shared with other agents, so a dispatch that fits
    this run's own count can still be the 29th agent on the machine, while
    the ~190 OS processes of an idle box are not what it counts.
    `workers` is how many this tick would start: three picks are three
    processes and three `ulimit -v` caps, so asking about one more worker
    passes a tick that starts three.

    Each new worker is charged at its **peak**, `SLOT_PEAK_PROCESSES`, and
    each of the `live` workers already running keeps the headroom between
    the one process it holds now and that peak: its review fan-out is a
    schedule the controller does not see. A live worker mid-fan-out is
    already in `processes`, so this over-reserves by what it is running now;
    an early refusal is the safe error, a dispatch into a peak is not.
    """
    refusals = []
    reserve, projected = projected_processes(processes, workers, live)
    if projected > PROCESS_CAP:
        refusals.append(
            f"{processes} agent processes on the box already ({counter}), "
            f"plus {reserve} of review fan-out headroom for {live} live "
            f"workers, plus {workers} new at a peak of "
            f"{SLOT_PEAK_PROCESSES} each would pass the cap of "
            f"{PROCESS_CAP}, which "
            "counts agent processes — Claude sessions, subagents included "
            "— not OS processes")
    if committed_gb > VM_BUDGET_GB:
        refusals.append(
            f"{committed_gb} GB of ulimit -v caps committed is over the "
            f"~{VM_BUDGET_GB} GB budget")
    return {"ok": not refusals, "refusals": refusals}


def process_count(text):
    """A `--processes` override: 0 is a deliberate count, a negative one would
    sit under the cap and disarm the gate."""
    count = int(text)
    if count < 0:
        raise argparse.ArgumentTypeError(
            f"--processes {count} is negative; give the agent processes you "
            "counted, 0 or more")
    return count


def live_count(text):
    """A `--live` count: negative would subtract reserve and disarm the gate,
    the same typo `process_count` refuses."""
    count = int(text)
    if count < 0:
        raise argparse.ArgumentTypeError(
            f"--live {count} is negative; give the live workers you "
            "counted, 0 or more")
    return count


def agent_count(args, herdr=None, ps=None, sessions=None):
    """(count, counter label, working, unlisted): the override when one
    was passed, else herdr's (working panes + unlisted claude pids) —
    see `count_working_herdr_agents`, which a #1075 controller ruling
    corrected from a plain working-panes count once measurement showed
    herdr does not list a subagent as its own agent. `working`/`unlisted`
    are `None` when `count` did not come from that split — an override, or
    the process-count fallback — so the peak line prints a flat number
    rather than a fabricated one.

    A herdr or `ps`-pid failure falls back to the plain process count (all
    `claude` on the box, idle included) for `count` — an unmeasured box is
    not an empty one, so the fallback is a measurement, never a default
    that reads as zero — and the counter label names the fallback so a
    refusal says which counter it used.
    """
    if args.processes is not None:
        return args.processes, "passed by --processes", None, None
    try:
        working, unlisted = count_working_herdr_agents(
            ps=ps, herdr=herdr, sessions=sessions)
    except AgentError as exc:
        total = count_agent_processes(ps)
        return total, (f"herdr could not answer ({exc}); fell back to "
                       + AGENT_COUNTER), None, None
    return working + unlisted, HERDR_COUNTER, working, unlisted


def box_room(processes, committed_gb, want,
             counter=UNSTATED_COUNTER, live=0):
    """How many of `want` workers the box has room for, and the refusals if
    that is none. Fewer than asked is the normal answer on a shared box, and
    holding the extra slots empty is the point."""
    for workers in range(want, 0, -1):
        verdict = box_check(processes, committed_gb, workers, counter,
                            live)
        if verdict["ok"]:
            return workers, []
    return 0, box_check(processes, committed_gb, 1, counter,
                        live)["refusals"]


def render_peak(count, live, room, working=None, unlisted=None):
    """The peak arithmetic as a controller's status line carries it: the
    measured count, what each live worker may still add, and the workers
    the box can take at their peak. `working`/`unlisted` print the split
    beside it, when both are given, so a controller can see how many of
    the count are herdr-listed working panes versus unlisted claude pids
    (a subagent or headless run herdr does not pane-list) (#1075)."""
    reserve, projected = projected_processes(count, room, live)
    split = (f" ({working} working, {unlisted} unlisted)"
            if working is not None and unlisted is not None else "")
    return (f"peak: {count} agent processes measured{split}, {live} live "
            f"{'worker' if live == 1 else 'workers'} holding {reserve} of "
            f"fan-out headroom, cap {PROCESS_CAP} — {room} more at "
            f"{SLOT_PEAK_PROCESSES} each projects {projected}")


def herdr_get(agent, timeout):
    """`herdr agent get <name>` through `shellcmd.herdr_agent`, in the answer
    shape `verdict` reads: `{"result": {"agent": ...}}`, or an
    `agent_not_found` error for an agent herdr has no pane for. herdr that
    cannot be asked (a timeout, an unparseable answer, any other error) is an
    `AgentError`.

    `timeout` is what the sweep has left of its whole deadline, not a fresh
    allowance: "bounded" has to mean the wall clock too, and a herdr that
    never answers would otherwise hold the controller inside a tool call,
    where no worker can reach it at all."""
    try:
        record = shellcmd.herdr_agent(agent, timeout=timeout)
    except shellcmd.CmdError as exc:
        raise AgentError(str(exc)) from None
    if record is None:
        return {"error": {"code": "agent_not_found",
                          "message": f"no agent named {agent}"}}
    return {"result": {"agent": record}}


# The pane states `herdr agent get` reports that the sweep passes through as
# its verdict. A state herdr grows later reads as `unknown` and is reported
# with the word herdr used, rather than being silently folded into `working` —
# which is the reading that would let a stuck worker pass as healthy.
_AGENT_STATES = frozenset({"working", "idle", "blocked", "done"})


def verdict(answer):
    """One `herdr agent get` answer read as a verdict and the detail behind
    it: the sweep's reading of `herdr_get`."""
    if not isinstance(answer, dict):
        return "unknown", f"herdr answered {answer!r}"
    error = answer.get("error")
    if isinstance(error, dict):
        code = error.get("code", "")
        if code == "agent_not_found":
            return "vanished", error.get("message", code)
        return "unreachable", error.get("message", code) or "herdr errored"
    result = answer.get("result")
    if not isinstance(result, dict):
        return "unknown", f"herdr answered {answer!r}"
    nested = result.get("agent")
    status = nested.get("agent_status") if isinstance(nested, dict) else None
    if status is None:
        status = result.get("agent_status")
    if status in _AGENT_STATES:
        return status, str(status)
    return "unknown", f"herdr reports agent_status {status!r}"
