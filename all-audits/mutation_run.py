"""Mutation mode's planning, beside the sweep driver (#1746).

Owns what the driver used to hold for `--mutation`: the per-module mutation
record (which module was mutated at which sha, when), the order modules run
in, and `run`, the one call the
driver makes to learn which modules to mutate. The driver keeps the process
work (worktrees, `claude`, the pages); this module never spawns anything but
the `git diff` calls its `runner` makes.

The module list and the sibling-test rule come from `mutation-audit/audit.py`'s
public `plan(repo)`, loaded by path because its directory name is not an
import name.
"""
import collections
import datetime as _dt
import importlib.util
import os

MUTATION_KEY = "mutation_modules"
_EPOCH = _dt.datetime.min.replace(tzinfo=_dt.timezone.utc)

MutationRun = collections.namedtuple("MutationRun", "targets no_tests total")


def parse_utc(timestamp):
    """An ISO timestamp as an aware datetime; a naive one is read as UTC."""
    then = _dt.datetime.fromisoformat(timestamp)
    return then if then.tzinfo else then.replace(tzinfo=_dt.timezone.utc)


def recorded_runs(record):
    """The {module: {sha, date}} part of a cache record; a missing or
    non-dict value is no recorded runs."""
    runs = record.get(MUTATION_KEY)
    return runs if isinstance(runs, dict) else {}


def stamp(record, module, sha, date):
    """Record `module` as mutated at `sha` on `date` in `record`, beside the
    audit records it already holds. The key is the repo-relative path, so
    `./a.py` and `a.py` are one module."""
    runs = recorded_runs(record)
    runs[os.path.normpath(module)] = {"sha": sha, "date": date}
    record[MUTATION_KEY] = runs


def changed(repo, runs, siblings, runner):
    """The modules in `runs` ({module: {sha, date}}) whose file or sibling
    tests (`siblings`: {module: [test path]}) differ between their recorded
    sha and HEAD. A sha git cannot resolve, or no recorded sha, proves
    nothing, so it reads as changed, never as unchanged. `runner(cmd)` runs
    one command and returns its completed process."""
    out = set()
    for module, entry in runs.items():
        sha = entry.get("sha") if isinstance(entry, dict) else None
        if not sha:
            out.add(module)
            continue
        paths = [module, *siblings.get(module, ())]
        if runner(["git", "-C", repo, "diff", "--quiet", f"{sha}..HEAD", "--", *paths]).returncode != 0:
            out.add(module)
    return out


def _run_date(entry):
    """The run date of a record entry as an aware datetime, or None for an
    entry with no readable date — which orders as never run."""
    try:
        return parse_utc(entry["date"])
    except (KeyError, TypeError, ValueError):
        return None


def order_targets(candidates, rank, record, changed_modules):
    """Pure: the candidates in the order mutation mode should run them.

    candidates: [module]; rank: [module] in the prepass's order (may be
    empty); record: {module: {sha, date}}; changed_modules: {module} changed
    since its recorded sha. Never-run first, then changed since their sha, then
    oldest run first; the prepass rank breaks ties inside a group, unranked
    last. Recency outranks risk, and nothing is dropped.
    """
    position = {m: i for i, m in enumerate(rank)}
    dates = {m: _run_date(record.get(m)) for m in candidates}

    def key(m):
        tie = (position.get(m, len(position)), m)
        if dates[m] is None:
            return (0, _EPOCH, *tie)
        if m in changed_modules:
            return (1, _EPOCH, *tie)
        return (2, dates[m], *tie)

    return sorted(candidates, key=key)


def parse_rank(stdout, candidates):
    """The prepass's printed lines kept only when they name a candidate, each
    once, in printed order. A line outside the list is dropped."""
    allowed = set(candidates)
    return list(dict.fromkeys(
        line for line in map(str.strip, stdout.splitlines()) if line in allowed))


def _audit_plan(repo):
    """`mutation-audit/audit.py`'s public `plan(repo)`."""
    spec = importlib.util.spec_from_file_location(
        "mutation_audit_plan", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mutation-audit", "audit.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.plan(repo)


def run(repo, record, *, runner, rank_fn=None, modules=None):
    """The modules to mutate in `repo`, in run order, with the repo's no-test
    modules and worthy-module total, as a `MutationRun`.

    `record` is the repo's cache record (its recorded runs order the
    candidates); `runner(cmd)` runs a command, as `changed` takes it.
    `rank_fn(candidates)` may return the model prepass's order, which only
    breaks ties. `modules` names the targets explicitly: they run as given,
    and only the no-tests answer is planned. A planning failure raises: no
    answer is not "no candidates".
    """
    planned = _audit_plan(repo)
    if modules is not None:
        return MutationRun(list(modules), planned["no_tests"], planned["total"])
    candidates = planned["candidates"]
    rank = rank_fn(candidates) if rank_fn and candidates else []
    runs = recorded_runs(record)
    targets = order_targets(candidates, rank, runs, changed(repo, runs, planned["siblings"], runner))
    return MutationRun(targets, planned["no_tests"], planned["total"])
