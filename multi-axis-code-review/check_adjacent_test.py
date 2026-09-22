#!/usr/bin/env python3
"""Tests for the verification pass's adjacent-fix check (#1025). Seam: the
command line the verification brief (SKILL.md § 6) tells the verifier to
run — a repo, a fixed point and a dispositions sidecar in, one line per
adjacent fix and an exit status out.

The sidecar is the shared fixture `implement/fixtures/dispositions-sidecar.jsonl`,
the one grammar every sidecar reader parses. Its shas are placeholders, so
each case binds the fixture's adjacent line to a commit in a fixture repo
it builds; every other line is passed through untouched, which is itself a
case: a non-adjacent line with a sha that resolves to nothing is not the
check's business.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CHECK = os.path.join(HERE, "check_adjacent.py")
FIXTURE = os.path.join(HERE, "..", "implement", "fixtures", "dispositions-sidecar.jsonl")

FIXTURES = []


def clean_fixtures():
    left = []
    while FIXTURES:
        root = FIXTURES.pop()
        if os.path.isfile(root):
            os.remove(root)
        shutil.rmtree(root, ignore_errors=True)
        if os.path.exists(root):
            left.append(root)
    return left


def git(root, *args):
    return subprocess.run(["git", "-C", root, *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def commit(root, files, message):
    for path, text in files.items():
        full = os.path.join(root, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as fh:
            fh.write(text)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message)
    return git(root, "rev-parse", "HEAD")


def lines(n, word="line"):
    return "".join(f"{word} {i}\n" for i in range(n))


def repo():
    """A fixture repo: `base` holds a.py and b.py; the branch's first commit
    changes a.py, so a.py is in the diff and b.py is not."""
    root = tempfile.mkdtemp(prefix="check-adjacent-fixture-")
    FIXTURES.append(root)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "fixture@example.invalid")
    git(root, "config", "user.name", "fixture")
    commit(root, {"a.py": lines(40), "b.py": lines(40)}, "base")
    git(root, "branch", "base")
    commit(root, {"a.py": lines(40) + "ticket work\n"}, "ticket work")
    return root


def fixture_lines():
    with open(FIXTURE) as fh:
        return [json.loads(raw) for raw in fh if raw.strip()]


def sidecar(root, sha):
    """The shared fixture with its adjacent line bound to `sha`."""
    bound = []
    for obj in fixture_lines():
        if obj.get("scope") == "adjacent":
            obj = {**obj, "sha": sha}
        bound.append(json.dumps(obj))
    path = os.path.join(root, "..", os.path.basename(root) + "-dispositions.jsonl")
    FIXTURES.append(path)
    with open(path, "w") as fh:
        fh.write("\n".join(bound) + "\n")
    return path


def run(root, path):
    return subprocess.run([sys.executable, CHECK, "--repo", root, "--base", "base", path],
                          capture_output=True, text=True)


def adjacent_id():
    ids = [o["id"] for o in fixture_lines() if o.get("scope") == "adjacent"]
    assert len(ids) == 1, f"the fixture must carry exactly one adjacent line, has {ids}"
    return ids[0]


def assert_breached(result, why):
    assert result.returncode == 1, (result.returncode, result.stdout, result.stderr)
    assert f"BREACH {adjacent_id()}:" in result.stdout, result.stdout
    assert why in result.stdout, result.stdout


# --- Cases -----------------------------------------------------------------

def test_a_small_one_file_fix_in_a_file_already_in_the_diff_passes():
    root = repo()
    sha = commit(root, {"a.py": lines(40) + "ticket work\nfix\n"}, "adjacent fix")
    result = run(root, sidecar(root, sha))
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert f"{adjacent_id()}: ok" in result.stdout, result.stdout


def test_a_fix_touching_a_second_file_breaches():
    root = repo()
    sha = commit(root, {"a.py": lines(40) + "ticket work\nfix\n",
                        "a_test.py": "assert fix\n"}, "fix plus test file")
    assert_breached(run(root, sidecar(root, sha)), "touches 2 files")


def test_twenty_changed_lines_breach_and_nineteen_do_not():
    root = repo()
    # 10 lines rewritten: 10 insertions plus 10 deletions is 20 changed lines.
    base_text = lines(40) + "ticket work\n"
    twenty = lines(10, "new") + base_text.split("\n", 10)[10]
    sha = commit(root, {"a.py": twenty}, "twenty")
    assert_breached(run(root, sidecar(root, sha)), "20 changed lines")

    root = repo()
    sha = commit(root, {"a.py": base_text + lines(19, "added")}, "nineteen")
    result = run(root, sidecar(root, sha))
    assert result.returncode == 0, (result.stdout, result.stderr)


def test_a_fix_in_a_file_the_diff_had_not_touched_breaches():
    root = repo()
    sha = commit(root, {"b.py": lines(40) + "fix\n"}, "fix elsewhere")
    assert_breached(run(root, sidecar(root, sha)), "was not in the diff")


def test_a_sha_that_is_not_on_the_branch_breaches():
    root = repo()
    git(root, "checkout", "-q", "-b", "side")
    sha = commit(root, {"a.py": lines(40) + "ticket work\nfix\n"}, "off branch")
    git(root, "checkout", "-q", "main")
    assert_breached(run(root, sidecar(root, sha)), "not on the branch")


def test_a_sha_that_resolves_to_nothing_breaches():
    root = repo()
    assert_breached(run(root, sidecar(root, "deadbeef")), "does not resolve")


def test_an_adjacent_line_with_no_sha_breaches_rather_than_passing():
    root = repo()
    path = sidecar(root, "")
    assert_breached(run(root, path), "no sha")


def test_an_unreadable_line_fails_rather_than_being_skipped():
    root = repo()
    sha = commit(root, {"a.py": lines(40) + "ticket work\nfix\n"}, "adjacent fix")
    path = sidecar(root, sha)
    with open(path, "a") as fh:
        fh.write('{"id": "S9", "outcome": "fixed", "sco\n')
    result = run(root, path)
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert f"BREACH line {len(fixture_lines()) + 1}:" in result.stdout, result.stdout


def test_a_sidecar_with_no_adjacent_line_passes_and_says_so():
    root = repo()
    path = os.path.join(root, "..", os.path.basename(root) + "-plain.jsonl")
    FIXTURES.append(path)
    with open(path, "w") as fh:
        fh.write(json.dumps({"id": "S1", "outcome": "fixed", "sha": "nope"}) + "\n")
    result = run(root, path)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "no adjacent fixes" in result.stdout, result.stdout


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    try:
        for test in tests:
            test()
            print(f"ok  {test.__name__}")
        print(f"{len(tests)} passed")
    finally:
        left = clean_fixtures()
        if left:
            print(f"fixtures left behind: {', '.join(left)}", file=sys.stderr)
            raise SystemExit(1)


if __name__ == "__main__":
    main()
