#!/usr/bin/env python3
"""Per-repo staleness cache for the expensive all-audits passes (spec #365, T6).

Two jobs, split so the pure parts stay table-testable:

- `repo_key` / `load_record` / `save_record` — the cache's read/write seam. A
  repo maps to one stable key; the key names one JSON file under the cache base
  holding one record per gated audit (`last_sha`, `timestamp`, `report_dir`).
- the `decide` / `update` CLI — the thin I/O shell `run-audits.sh` calls. It
  gathers git state and the record's age, hands them to the pure `should_run`
  (which owns every skip/run branch, already table-tested), and prints the
  verdict. Git calls and the clock live here, never in `should_run`.
"""
import datetime as _dt
import hashlib
import json
import os
import subprocess
import sys

import should_run as _sr

CACHE_BASE = os.path.join(
    os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "all-audits"
)


def repo_key(repo_path):
    """Stable filesystem-safe key for a repo's absolute path.

    Same path in -> same key out, distinct paths -> distinct keys. The basename
    keeps the key human-readable in `ls ~/.cache/all-audits`; an 8-char digest
    of the full absolute path keeps two same-named repos in different trees from
    colliding.
    """
    digest = hashlib.sha1(repo_path.encode("utf-8")).hexdigest()[:8]
    base = os.path.basename(repo_path.rstrip("/")) or "repo"
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in base)
    return f"{safe}-{digest}"


def load_record(path):
    """Load the per-repo record dict from `path`. Missing file -> empty dict."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_record(path, record):
    """Write `record` to `path` as JSON, creating parent dirs as needed."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)


def _git_state(repo, last_sha):
    """Gather the pure inputs `should_run` needs from a live repo."""
    dirty = bool(
        subprocess.run(
            ["git", "-C", repo, "status", "--porcelain"],
            capture_output=True, text=True, check=False,
        ).stdout.strip()
    )
    changed = []
    if last_sha:
        out = subprocess.run(
            ["git", "-C", repo, "diff", "--name-only", f"{last_sha}..HEAD"],
            capture_output=True, text=True, check=False,
        ).stdout
        changed = [ln for ln in out.splitlines() if ln.strip()]
    return {"dirty": dirty, "changed_files": changed}


def _head_sha(repo):
    return subprocess.run(
        ["git", "-C", repo, "rev-parse", "HEAD"],
        capture_output=True, text=True, check=False,
    ).stdout.strip()


def _age_days(timestamp):
    then = _dt.datetime.fromisoformat(timestamp)
    now = _dt.datetime.now(_dt.timezone.utc)
    if then.tzinfo is None:
        then = then.replace(tzinfo=_dt.timezone.utc)
    return (now - then).total_seconds() / 86400.0


def _record_file(repo):
    return os.path.join(CACHE_BASE, repo_key(repo) + ".json")


def _decide(repo, audit, ground_truth, threshold, backstop):
    """Print RUN or SKIP<TAB>sha<TAB>report_dir for one gated audit.

    The caller (`run-audits.sh`) owns `--force`: it only calls `decide` when the
    cache is in play, so there is no force branch to handle here.
    """
    record = load_record(_record_file(repo))
    entry = record.get(audit)
    cache_record = None
    if entry:
        cache_record = {"last_sha": entry["last_sha"], "age_days": _age_days(entry["timestamp"])}
    git_state = _git_state(repo, entry["last_sha"] if entry else None)
    cfg = {"ground_truth": ground_truth, "threshold": threshold, "backstop_days": backstop}
    run, reason = _sr.should_run(cfg, cache_record, git_state)
    if run:
        print(f"RUN\t{reason}")
    else:
        print(f"SKIP\t{entry['last_sha']}\t{entry['report_dir']}\t{reason}")


def _update(repo, audit, report_dir):
    """Record that `audit` just ran fresh at HEAD, its report saved to report_dir."""
    path = _record_file(repo)
    record = load_record(path)
    record[audit] = {
        "last_sha": _head_sha(repo),
        "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "report_dir": report_dir,
    }
    save_record(path, record)


def _selfcheck():
    import tempfile

    # repo_key: stable and path-distinct.
    assert repo_key("/home/x/repo") == repo_key("/home/x/repo"), "key must be stable"
    assert repo_key("/home/x/repo") != repo_key("/home/y/repo"), "distinct paths -> distinct keys"
    k = repo_key("/home/x/my repo!")
    assert "/" not in k and " " not in k, f"key must be filesystem-safe: {k!r}"
    assert "repo" in k, f"key should stay human-readable: {k!r}"

    # load_record: missing file -> empty dict.
    with tempfile.TemporaryDirectory() as d:
        missing = os.path.join(d, "nope.json")
        assert load_record(missing) == {}, "missing record file -> {}"

        # save then load round-trips.
        rec = {"domain-drift": {"last_sha": "abc", "timestamp": "2026-01-01T00:00:00+00:00", "report_dir": "/x"}}
        path = os.path.join(d, "sub", "repo.json")   # parent dir does not exist yet
        save_record(path, rec)
        assert load_record(path) == rec, "save then load must round-trip through a fresh dir"

    print("ok")


def main(argv):
    if argv[1:2] == ["--selfcheck"]:
        _selfcheck()
        return
    if argv[1:2] == ["key"]:
        print(repo_key(os.path.abspath(argv[2])))
        return
    if argv[1:2] == ["decide"]:
        # decide <repo> <audit> <ground_truth_csv> <threshold> <backstop>
        repo, audit, gt, thr, bak = argv[2:7]
        ground_truth = [s for s in gt.split(",") if s]
        _decide(os.path.abspath(repo), audit, ground_truth, int(thr), int(bak))
        return
    if argv[1:2] == ["update"]:
        # update <repo> <audit> <report_dir>
        repo, audit, report_dir = argv[2:5]
        _update(os.path.abspath(repo), audit, report_dir)
        return
    print("usage: cache.py [--selfcheck|key <repo>|decide ...|update ...]", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main(sys.argv)
