"""Tests for `mutation_run`: the mutation record, target ordering, and `run`."""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "harness"))
import mutation_run  # noqa: E402


def _git(repo, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, check=False, env=env)


def _init_repo(path, files):
    os.makedirs(path, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "t@example.invalid")
    _git(path, "config", "user.name", "t")
    for rel in files:
        open(os.path.join(path, rel), "w").write("x = 1\n")
    return _commit(path, "init")


def _commit(repo, msg):
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", msg)
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _rec(sha, date):
    return {"sha": sha, "date": date}


def test_order_never_run_then_changed_then_oldest_run():
    cands = ["a.py", "b.py", "c.py", "d.py"]
    record = {"a.py": _rec("s", "2026-10-01"), "b.py": _rec("s", "2026-09-01"), "c.py": _rec("s", "2026-10-02")}
    assert mutation_run.order_targets(cands, [], record, {"c.py"}) == ["d.py", "c.py", "b.py", "a.py"]


def test_order_recency_outranks_prepass_risk_and_nothing_is_dropped():
    record = {"risky.py": _rec("s", "2026-10-11")}
    assert mutation_run.order_targets(["risky.py", "boring.py"], ["risky.py", "boring.py"], record, set()) == [
        "boring.py", "risky.py"]


def test_order_prepass_rank_breaks_ties_inside_each_group():
    cands = ["a.py", "b.py", "c.py", "d.py", "e.py"]
    record = {"c.py": _rec("s", "2026-09-01"), "d.py": _rec("s", "2026-09-01"), "e.py": _rec("s", "2026-08-01")}
    assert mutation_run.order_targets(cands, ["b.py", "a.py", "d.py", "c.py"], record, set()) == [
        "b.py", "a.py", "e.py", "d.py", "c.py"]


def test_order_unranked_follow_ranked_and_a_malformed_entry_counts_as_never_run():
    record = {"b.py": {"sha": "s"}, "c.py": _rec("s", "2026-09-01")}
    assert mutation_run.order_targets(["a.py", "b.py", "c.py"], ["b.py"], record, set()) == ["b.py", "a.py", "c.py"]


def test_parse_rank_keeps_only_candidates_once_in_printed_order():
    assert mutation_run.parse_rank("b.py\n  a.py \nfake.py\nb.py\n\n", ["a.py", "b.py", "c.py"]) == ["b.py", "a.py"]


def test_stamp_keys_a_dotted_path_as_the_repo_relative_one_and_keeps_other_keys():
    record = {"dead-code": {"report_dir": "/r"}}
    mutation_run.stamp(record, "./a.py", "abc", "2026-10-01")
    assert record["dead-code"] == {"report_dir": "/r"}
    assert record[mutation_run.MUTATION_KEY] == {"a.py": _rec("abc", "2026-10-01")}
    assert mutation_run.recorded_runs(record) == {"a.py": _rec("abc", "2026-10-01")}


def test_recorded_runs_of_a_missing_or_non_dict_value_is_empty():
    assert mutation_run.recorded_runs({}) == {}
    assert mutation_run.recorded_runs({mutation_run.MUTATION_KEY: ["a.py"]}) == {}


def test_changed_since_recorded_sha_and_unresolvable_sha_reads_as_changed(tmp_path):
    repo = str(tmp_path / "repo")
    sha = _init_repo(repo, ["a.py", "b.py"])
    open(os.path.join(repo, "b.py"), "w").write("x = 2\n")
    _commit(repo, "b changes")
    runs = {"a.py": _rec(sha, "d"), "b.py": _rec(sha, "d"), "c.py": _rec("deadbeef", "d"), "d.py": {"date": "d"},
            "e.py": _rec("", "d")}
    assert mutation_run.changed(repo, runs, {}, _git_runner) == {"b.py", "c.py", "d.py", "e.py"}


def test_a_changed_sibling_test_counts_as_the_module_changed(tmp_path):
    repo = str(tmp_path / "repo")
    sha = _init_repo(repo, ["m.py", "test_m.py", "n.py", "test_n.py"])
    open(os.path.join(repo, "test_m.py"), "w").write("x = 2\n")
    _commit(repo, "weaken m's test")
    runs = {"m.py": _rec(sha, "d"), "n.py": _rec(sha, "d")}
    siblings = {"m.py": ["test_m.py"], "n.py": ["test_n.py"]}
    assert mutation_run.changed(repo, runs, siblings, _git_runner) == {"m.py"}


def _git_runner(cmd):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return subprocess.run(cmd, capture_output=True, text=True, check=False, env=env)


def _tests_repo(path, modules):
    _init_repo(path, [])
    for m in modules:
        open(os.path.join(path, m), "w").write("x = 1\n")
        open(os.path.join(path, f"test_{m}"), "w").write("def test_x(): pass\n")
    _commit(path, "mods")


def test_run_orders_the_plans_candidates_by_the_record_and_reports_no_tests(tmp_path):
    repo = str(tmp_path / "repo")
    _tests_repo(repo, ["m.py", "n.py", "o.py"])
    open(os.path.join(repo, "lonely.py"), "w").write("x = 1\n")
    sha = _commit(repo, "lonely")
    record = {mutation_run.MUTATION_KEY: {"m.py": _rec(sha, "2026-10-01T00:00:00+00:00")}}
    result = mutation_run.run(repo, record, runner=_git_runner)
    assert result.targets == ["n.py", "o.py", "m.py"]  # m.py ran and is unchanged: last
    assert result.no_tests == ["lonely.py"]
    assert result.total == 4


def test_run_ranks_through_rank_fn_and_never_adds_a_module(tmp_path):
    repo = str(tmp_path / "repo")
    _tests_repo(repo, ["m.py", "n.py"])
    seen = []

    def rank(candidates):
        seen.append(candidates)
        return ["n.py", "ghost.py"]

    result = mutation_run.run(repo, {}, runner=_git_runner, rank_fn=rank)
    assert seen == [["m.py", "n.py"]]
    assert result.targets == ["n.py", "m.py"]


def test_run_with_explicit_modules_keeps_them_as_given(tmp_path):
    repo = str(tmp_path / "repo")
    _tests_repo(repo, ["m.py", "n.py"])
    result = mutation_run.run(repo, {}, runner=_git_runner, modules=["n.py", "z.py"])
    assert result.targets == ["n.py", "z.py"]
