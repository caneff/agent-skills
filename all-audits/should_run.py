#!/usr/bin/env python3
"""Staleness decision for the expensive all-audits passes (spec #365, T6).

`should_run` answers one question with no guessing and no I/O: given an audit's
config, its last cached run, and the current git state, should we re-run the
audit or reuse the cached report? All state arrives as arguments — the function
makes no git or filesystem calls, so it is table-testable in isolation.

Skip (reuse cache) only when EVERY relaxing condition holds:
  - the working tree is clean, AND
  - fewer than `threshold` files changed since the last-run SHA (default 10), AND
  - no ground-truth override fired (a change to the audit's vocabulary source), AND
  - the last run is within the time backstop (default ~30 days).

Any condition failing forces a run. The returned reason names the condition that
forced the decision.
"""
import sys

DEFAULT_THRESHOLD = 10
DEFAULT_BACKSTOP_DAYS = 30


def _hits_ground_truth(changed_files, ground_truth):
    """Return the first changed file that is, or lives under, a vocabulary
    source, else None."""
    for f in changed_files:
        for src in ground_truth:
            if f == src or f.startswith(src.rstrip("/") + "/"):
                return f
    return None


def should_run(audit, cache_record, git_state):
    """Return (run: bool, reason: str). See module docstring for the rules.

    audit: {"threshold": int, "backstop_days": int, "ground_truth": [prefix]}.
    cache_record: {"last_sha", "age_days"} or None when the audit never ran.
    git_state: {"dirty": bool, "changed_files": [path]} since last_sha.
    """
    if cache_record is None:
        return True, "no cached run"

    if git_state["dirty"]:
        return True, "dirty working tree"

    hit = _hits_ground_truth(git_state["changed_files"], audit.get("ground_truth", []))
    if hit:
        return True, f"ground-truth change: {hit}"

    backstop = audit.get("backstop_days", DEFAULT_BACKSTOP_DAYS)
    if cache_record["age_days"] > backstop:
        return True, f"last run older than backstop ({cache_record['age_days']:g}d > {backstop}d)"

    threshold = audit.get("threshold", DEFAULT_THRESHOLD)
    changed = len(git_state["changed_files"])
    if changed >= threshold:
        return True, f"{changed} files changed >= threshold {threshold}"

    return False, f"unchanged: {changed} files < threshold {threshold}, clean, within backstop"


def _selfcheck():
    """Table-test every T6 branch with pure inputs — no git, no filesystem."""
    domain = {
        "name": "domain-drift",
        "threshold": DEFAULT_THRESHOLD,
        "backstop_days": DEFAULT_BACKSTOP_DAYS,
        "ground_truth": ["CONTEXT.md", "docs/adr/"],
    }
    clean = {"dirty": False, "changed_files": ["a.py", "b.py"]}
    fresh_record = {"last_sha": "abc123", "age_days": 3.0}

    # 1. under threshold, clean, within backstop, no ground-truth change -> skip.
    run, reason = should_run(domain, fresh_record, clean)
    assert run is False, reason
    assert "unchanged" in reason.lower(), reason

    # 2. files changed at/over threshold -> run.
    over = {"dirty": False, "changed_files": [f"f{i}.py" for i in range(DEFAULT_THRESHOLD)]}
    run, reason = should_run(domain, fresh_record, over)
    assert run is True
    assert "threshold" in reason.lower(), reason
    # boundary: exactly threshold-1 stays a skip.
    under = {"dirty": False, "changed_files": [f"f{i}.py" for i in range(DEFAULT_THRESHOLD - 1)]}
    assert should_run(domain, fresh_record, under)[0] is False

    # 3. ground-truth override (vocab-source change) -> run regardless of low file count.
    gt = {"dirty": False, "changed_files": ["docs/adr/0008-modifiers.md"]}
    run, reason = should_run(domain, fresh_record, gt)
    assert run is True
    assert "ground-truth" in reason.lower(), reason
    # exact-file ground truth matches too.
    gt2 = {"dirty": False, "changed_files": ["CONTEXT.md"]}
    assert should_run(domain, fresh_record, gt2)[0] is True
    # an audit with no ground-truth source never fires the override.
    plain = dict(domain, ground_truth=[])
    assert should_run(plain, fresh_record, gt)[0] is False

    # 4. dirty working tree -> run.
    run, reason = should_run(domain, fresh_record, {"dirty": True, "changed_files": []})
    assert run is True
    assert "dirty" in reason.lower(), reason

    # 5. last run older than backstop -> run.
    stale = {"last_sha": "abc123", "age_days": 45.0}
    run, reason = should_run(domain, stale, clean)
    assert run is True
    assert "backstop" in reason.lower(), reason

    # never-run audit (no cache record) -> run.
    run, reason = should_run(domain, None, clean)
    assert run is True
    assert "no cached run" in reason.lower(), reason

    print("ok")


def main(argv):
    if argv[1:2] == ["--selfcheck"]:
        _selfcheck()
        return


if __name__ == "__main__":
    main(sys.argv)
