#!/usr/bin/env python3
"""Codex usage preflight (#1204): may a Codex run start?

Run before every Codex launch — the review wave's adversarial pass
(`SKILL.md` § The Codex pass) and the Codex lane (`codex-lane.md`). Reads
the usage cache `flow/ccstatusline-table/helpers/codex-usage.py` keeps under
`$CODEX_HOME`; when that cache is missing, stale or unreadable it refreshes
it through the helper's own live fetch, which still answers at the cap.

One line on stdout, and an exit status the caller branches on:

  0   proceed — usage is under RESERVE_PERCENT (under 100% with `--audit`); a PR's
      line ends with why: `churn <n> >= <threshold>` or `needs-codex label forced
      it, churn <n> < <threshold>` (#1405)
  20  capped — usage is at or above RESERVE_PERCENT (#1359; 100% included, so
      the weekly audit reads the skip), at 100% under `--audit`, or the
      kill-switch file is present (#1354); launch nothing, write no duration row
  30  unknown — no fresh, well-formed reading; launch nothing
  40  under the size threshold (#1358) — a PR pass only; launch nothing

`--base <ref> --tickets <n>...` marks the launch as a PR's gate pass: from the
PR's workspace, the gate sums the added plus deleted lines of `<ref>...HEAD`
in files that are neither Markdown nor tests (what `tests/all.sh` discovers —
`*_test.py`, `*.test.sh`, a mod's `*.test.ts`, `audit.py` — or anything under
a `tests/` directory). Below SIZE_THRESHOLD it answers 40, `under size threshold (<churn>
< <threshold>)`, before any usage read, so a skipped PR costs no RPC — unless
any of the clump's tickets carries FORCE_LABEL, which sends it on to the usage
read. The label bypasses the size check only; the kill switch, the reserve
ceiling and the cap still answer 20. With no arguments there is no size check:
the Codex lane's launches have no PR diff to measure.
A `git` or `gh` failure, or a diff that changes no files at all (HEAD is the
base, so this is not the PR's workspace), is 30 `size check failed: ...`,
never a size verdict.

The kill switch is `~/.config/agent-skills/codex-reviews-off`, any content:
while it exists every check is 20, answered before the size check or any
cache read or live fetch, so a disabled gate costs no RPC. Removing the file
re-enables Codex reviews.

`--size --base <ref>` answers only the size question (#1401),
for the first ablation (`SKILL.md` § Review): 40 `under size threshold
(<churn> < <threshold>)`, 0 `at or above size threshold (...)`, 30 when it
could not measure. It reads no usage, ignores the kill switch and the forcing
label, and writes nothing: a small PR is small whether or not Codex may run.

A missing, stale or malformed reading is 30, never 0: it is not headroom.

RESERVE_PERCENT is the reserve ceiling: every launch stops there, its line
`usage <pct>% at or above reserve ceiling <ceiling>%, resets <when>`, so the
weekly audit of skipped PRs always has quota left. `--audit` marks the audit's
own launch and lifts the ceiling to the 100% cap; it takes no size check, since
the audit reviews merged PRs, not one PR's workspace. FORCE_LABEL never lifts it.

`--percent` prints the worst window's percentage and its reset time
(`12.5 1790000000`), or `unknown` with exit 30, and is always 0 or 30. It
ignores the cache and reads live, since a cached reading can be 30 minutes
old and a pass is shorter than that. It also ignores the kill switch: a reading
is not a launch. The controller takes it just before a
Codex launch and just after the run, and both go into the pass's record for
`review_ledger.py` (#1269). The reset time names the window, so two readings
of different windows are never subtracted.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

# The helper's 1.3s RPC_TIMEOUT is tuned to a statusline tick; a loaded box
# answers in 0.6-1.2s, and a spurious timeout here skips a pass (exit 30).
REFRESH_TIMEOUT = 5.0
HELPER = Path(__file__).resolve().parent.parent / "flow/ccstatusline-table/helpers/codex-usage.py"

# A PR pass runs only on this much churn (#1358, basis
# docs/research/2026-10-03-codex-yield-by-pr-size.md), unless FORCE_LABEL forces it.
SIZE_THRESHOLD = 300
# Launches stop here so the weekly audit keeps the rest of the window (#1359);
# `--audit` lifts it.
RESERVE_PERCENT = 70
FORCE_LABEL = "needs-codex"

PROCEED, CAPPED, UNKNOWN, SMALL = 0, 20, 30, 40


def kill_switch() -> Path:
    return Path.home() / ".config/agent-skills/codex-reviews-off"


def load_helper():
    spec = importlib.util.spec_from_file_location("codex_usage", HELPER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def worst_window(helper, limits: object, now: float) -> tuple[float, float] | None:
    """(worst usedPercent, its resetsAt) across the windows, or None.

    A window that is present but malformed, or whose reset has passed (its
    percentage describes a window that no longer exists), voids the whole
    reading; an absent window (`secondary: null`) is simply not there.
    """
    if not isinstance(limits, dict):
        return None
    worst = None
    for key in ("primary", "secondary"):
        win = limits.get(key)
        if win is None:
            continue
        parsed = helper.valid_window(win)
        if parsed is None:
            return None
        pct, resets = parsed
        if resets <= now:
            return None
        if worst is None or pct > worst[0]:
            worst = (pct, resets)
    return worst


def reading(live_only: bool = False) -> tuple[float, float] | None:
    """(worst usedPercent, its resetsAt) from the cache, refreshed live when it
    is missing or stale, or None when no fresh, well-formed reading exists.
    `live_only` skips the cache: a reading taken around an event must not be
    older than the event."""
    helper = load_helper()
    helper.RPC_TIMEOUT = REFRESH_TIMEOUT
    now = time.time()
    worst = None if live_only else worst_window(helper, helper.read_cache(now), now)
    if worst is None:
        live = helper.fetch_live()
        if live is not None:
            helper.write_cache(live, now)
            worst = worst_window(helper, live, now)
    return worst


def is_counted(path: str) -> bool:
    """A path whose churn counts toward the size check: not Markdown, and not a file
    `tests/all.sh` discovers as a suite or keeps under a `tests/` directory."""
    name = path.rsplit("/", 1)[-1]
    if name.endswith((".md", "_test.py", ".test.sh", ".test.ts")) or name == "audit.py":
        return False
    return not (path.startswith("tests/") or "/tests/" in path)


class SizeCheckError(Exception):
    """The size check could not measure the PR; the gate answers 30 with this message."""


def run_cmd(argv: list[str]) -> str:
    """`argv`'s stdout, or SizeCheckError carrying the command and its own stderr."""
    p = subprocess.run(argv, capture_output=True, text=True)
    if p.returncode != 0:
        raise SizeCheckError(f"`{' '.join(argv)}` exited {p.returncode}: {p.stderr.strip()}")
    return p.stdout


def churn(base: str) -> int:
    """Added plus deleted lines of counted files in `base...HEAD`, in the current directory.
    A binary file's `-` counts carry no lines to review and count as 0. A diff with no
    files at all is not a small PR — HEAD is the base, so this is not the PR's
    workspace — and raises SizeCheckError."""
    out = run_cmd(["git", "diff", "--numstat", "-z", f"{base}...HEAD"])
    if not out:
        raise SizeCheckError(f"{base}...HEAD changes no files — run from the PR's workspace")
    total = 0
    fields = out.split("\0")
    i = 0
    while i < len(fields) - 1:
        added, deleted, path = fields[i].split("\t")
        i += 1
        if not path:  # a rename: `added\tdeleted\t\0src\0dst\0`
            path = fields[i + 1]
            i += 2
        if is_counted(path) and added != "-":
            total += int(added) + int(deleted)
    return total


def forced(tickets: list[str]) -> bool:
    for n in tickets:
        out = run_cmd(["gh", "issue", "view", n, "--json", "labels"])
        if any(label["name"] == FORCE_LABEL for label in json.loads(out)["labels"]):
            return True
    return False


def check(base: str | None = None, tickets: list[str] = (), audit: bool = False) -> tuple[int, str]:
    """`base` and the clump's `tickets` mark a PR's gate pass; without `base`, no size check.
    `audit` lifts the reserve ceiling to the cap."""
    switch = kill_switch()
    if switch.exists():
        return CAPPED, f"codex reviews off by Chris's ruling ({switch}) — remove the file to re-enable"
    if base is not None:
        try:
            lines = churn(base)
            if lines >= SIZE_THRESHOLD:
                why = f"churn {lines} >= {SIZE_THRESHOLD}"
            elif forced(tickets):
                why = f"{FORCE_LABEL} label forced it, churn {lines} < {SIZE_THRESHOLD}"
            else:
                why = None
        except (SizeCheckError, OSError, ValueError, KeyError, TypeError) as exc:  # a missing tool, unreadable output
            return UNKNOWN, f"size check failed: {exc}"
        if why is None:
            return SMALL, f"under size threshold ({lines} < {SIZE_THRESHOLD})"
    else:
        why = None
    worst = reading()
    if worst is None:
        return UNKNOWN, "codex usage unknown: no fresh, readable usage cache and the live fetch failed"
    pct, resets = worst
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(resets))
    if pct >= RESERVE_PERCENT and not audit:
        # The cap included: the audit reads `ceiling` skips only, so a PR gated at 100% must read as one.
        return CAPPED, f"usage {pct:g}% at or above reserve ceiling {RESERVE_PERCENT}%, resets {when}"
    if pct >= 100:
        return CAPPED, f"codex usage {pct:g}% — capped, resets {when}"
    return PROCEED, f"codex usage {pct:g}% — ok, resets {when}" + (f"; {why}" if why else "")


def size_only(base: str) -> tuple[int, str]:
    """The size verdict alone: SMALL, or PROCEED for a PR at or above the threshold."""
    try:
        lines = churn(base)
    except SizeCheckError as exc:
        return UNKNOWN, f"size check failed: {exc}"
    if lines < SIZE_THRESHOLD:
        return SMALL, f"under size threshold ({lines} < {SIZE_THRESHOLD})"
    return PROCEED, f"at or above size threshold ({lines} >= {SIZE_THRESHOLD})"


USAGE = "usage: codex-usage-gate.py [--percent | --audit | --base <ref> --tickets <n>... | --size --base <ref>]"
# The flag sets one invocation may carry: no flags is the Codex lane's launch check.
MODES = (set(), {"percent"}, {"audit"}, {"size", "base"}, {"base", "tickets"})


class UsageError(Exception):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise UsageError(message)


def ticket(text: str) -> str:
    if not text.isdigit():
        raise argparse.ArgumentTypeError(f"not a ticket number: {text!r}")
    return text


def parse(argv: list[str]) -> argparse.Namespace:
    """The arguments in any flag order, or UsageError. No `--help` and no abbreviations: argparse's
    own exit 0 for help would read as proceed, and its exit 2 for an error is no status a caller has
    a rule for, so `main` maps every refusal to 30."""
    p = Parser(add_help=False, allow_abbrev=False)
    for flag in ("percent", "audit", "size"):
        p.add_argument(f"--{flag}", action="store_true")
    p.add_argument("--base")
    p.add_argument("--tickets", nargs="+", type=ticket)
    args = p.parse_args(argv)
    given = {k for k, v in vars(args).items() if v not in (None, False)}
    if given not in MODES:
        raise UsageError(f"unsupported combination: {sorted(given)}")
    return args


def main() -> int:
    # Any failure is exit 30: a crash's own exit 1 is a status neither caller
    # has a rule for, and an unread reading is not headroom.
    try:
        args = parse(sys.argv[1:])
    except UsageError:
        print(USAGE)
        return UNKNOWN
    if args.percent:
        try:
            worst = reading(live_only=True)
        except Exception:
            worst = None
        print("unknown" if worst is None else f"{worst[0]:g} {int(worst[1])}")
        return UNKNOWN if worst is None else PROCEED
    if args.size:
        status, line = size_only(args.base)
        print(line)
        return status
    try:
        status, line = check(args.base, args.tickets or [], args.audit)
    except Exception as exc:
        status, line = UNKNOWN, f"codex usage unknown: {type(exc).__name__}: {exc}"
    print(line)
    return status


if __name__ == "__main__":
    sys.exit(main())
