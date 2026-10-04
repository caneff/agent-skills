#!/usr/bin/env python3
"""The closing report's counts:

    python3 burndown/counts.py <run-id> --repo <checkout> | --reviews-dir <dir>

prints the closing report's two counts, fixed and moved, read from each
landed clump's dispositions sidecar (`implement/SKILL.md` § Review's
`dispositions-<lowest ticket>.jsonl`, the one the worker writes and
`implement/fix-check.sh` checks), and names every clump closed with
no landing as skipped. Nothing here writes one.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import runfile  # noqa: E402


def default_reviews_dir(checkout):
    """`~/.cache/agent-reviews/<repo>`, keyed the same way
    `multi-axis-code-review/SKILL.md`'s own dir expansion is: the basename of
    the directory holding the common `.git`, which is also right for a
    submodule or a `--separate-git-dir` checkout where the primary
    checkout's own name is not the key. `checkout` is `runfile.checkout_top`'s
    answer, so it is already a checkout of the repo the run targets."""
    top = subprocess.run(
        ["git", "-C", checkout, "rev-parse", "--path-format=absolute",
         "--git-common-dir"], capture_output=True, text=True, check=True,
        env=runfile.clean_git_env()).stdout.strip()
    repo = os.path.basename(os.path.dirname(top))
    return os.path.join(os.path.expanduser("~/.cache/agent-reviews"), repo)


def counts(run, reviews_dir):
    """The closing report's counts, read from each **landed** clump's
    dispositions sidecar: **fixed** is every `fixed` line, **moved** is every
    `moved` line (a finding added to the open ticket for its component).
    `disputed` lands in neither: a disputed finding shipped nothing.

    A sidecar written before #1401 is still read, so a burn that was running
    when the review changed can close: its `filed` lines count as moved, and
    its `leftover` and `handed-back` lines are returned as `carried`, which
    `render_counts` prints. Nothing sweeps them any more; the run file's own
    `leftovers` list still holds the leftover ones.

    A clump closed with no landing (`runfile.py close`, #1310) has no PR and
    so no sidecar: it is listed under `closed` as `(lowest, reason)`, by
    name, so the report says which clumps it did not read.

    A landed clump with no sidecar on disk is refused by clump number, never
    counted as zero: the merge check refuses a PR with no sidecar, empty when
    its reviewers found nothing, so a missing one means this run's own
    bookkeeping is missing (defect class 1)."""
    fixed = moved = carried = 0
    missing, closed = [], []
    for entry in run["clumps"]:
        if entry.get("closed"):
            closed.append((entry["tickets"][0], entry["closed"]))
        if not entry["landed"]:
            continue
        lowest = entry["tickets"][0]
        path = runfile.dispositions_path(reviews_dir, lowest)
        if not os.path.exists(path):
            missing.append(lowest)
            continue
        for _, obj in runfile.read_dispositions(path, legacy=True):
            outcome = obj["outcome"]
            if outcome == "fixed":
                fixed += 1
            elif outcome in ("moved", "filed"):
                moved += 1
            elif outcome in ("leftover", "handed-back"):
                carried += 1
    if missing:
        raise runfile.RunFileError(
            "landed clump(s) " +
            ", ".join(f"#{n}" for n in missing) +
            " have no dispositions sidecar under " + reviews_dir +
            " — counts refused rather than read as zero")
    return {"fixed": fixed, "moved": moved, "carried": carried, "closed": closed}


def render_counts(c):
    line = f"fixed: {c['fixed']}  moved: {c['moved']}"
    if c["carried"]:
        line += (f"\npre-#1401 leftover or handed-back, swept by nothing: {c['carried']} "
                 "(the run file's leftovers list still holds the leftover ones)")
    if c["closed"]:
        line += "\nskipped, closed without a landing: " + ", ".join(
            f"#{n} ({reason})" for n, reason in c["closed"])
    return line


def main(argv):
    import argparse

    parser = argparse.ArgumentParser(
        prog="counts.py", description="A run's closing-report counts")
    parser.add_argument("run_id")
    where = parser.add_mutually_exclusive_group()
    where.add_argument("--repo",
                       help="the target repo's primary checkout; its name keys "
                            "~/.cache/agent-reviews/<repo>")
    where.add_argument("--reviews-dir",
                       help="the sidecar directory itself, instead of --repo")

    args = parser.parse_args(argv[1:])

    root = runfile.env_root()
    try:
        run = runfile.load(args.run_id, root)
    except runfile.RunFileError as exc:
        print(f"counts.py: {exc}", file=sys.stderr)
        return 1

    # No default from the cwd: the controller may run from a different
    # primary checkout than the run's target (#1093), and a wrong cwd reads
    # another repo's sidecars or reports every landed clump missing.
    if args.reviews_dir:
        reviews_dir = os.path.expanduser(args.reviews_dir)
    elif args.repo:
        # The run's recorded target is what `--repo` must name (#1190): a
        # wrong checkout reads another repo's sidecars. Tops are compared, so
        # a subdirectory or a trailing slash is the same target.
        try:
            top = runfile.checkout_top(args.repo)
            recorded = runfile.target_repo(run)
        except runfile.RunFileError as exc:
            print(f"counts.py: --repo {args.repo}: {exc}", file=sys.stderr)
            return 1
        if top != recorded:
            print(f"counts.py: --repo {args.repo} is {top}, but run "
                  f"{args.run_id} targets {recorded}", file=sys.stderr)
            return 1
        try:
            reviews_dir = default_reviews_dir(top)
        except (subprocess.CalledProcessError, OSError) as exc:
            print(f"counts.py: --repo {args.repo} is not a git checkout: {exc}",
                  file=sys.stderr)
            return 1
    else:
        print("counts.py: needs --repo <primary checkout> (or "
              "--reviews-dir): the cwd's repo is not the run's target",
              file=sys.stderr)
        return 1
    try:
        c = counts(run, reviews_dir)
    except runfile.RunFileError as exc:
        print(f"counts.py: {exc}", file=sys.stderr)
        return 1
    print(render_counts(c))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
