"""fanout-brief.py (#1550): the one source of a parallel sub-worker's brief.
Seam: the CLI, with HOME pointed at a temp dir so no render writes the real
review cache. Each case asserts the line it is about, so a render that fails
for another reason does not pass for the one under test (`AGENTS.md` §
Recurring defect classes, class 3).
"""
import os
import re
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
RENDER = os.path.join(HERE, "fanout-brief.py")
TEST_COMMAND = "python3 -m pytest implement/foo_test.py"


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return tmp_path / "home" / ".cache" / "agent-reviews"


@pytest.fixture
def wt(tmp_path):
    path = tmp_path / "wt"
    path.mkdir()
    return str(path)


def run(wt, *assigns, worker="alpha", ticket="1550", test_command=TEST_COMMAND, repo="skills", extra=()):
    args = ["python3", RENDER, "--repo", repo, "--worktree", wt, "--ticket", ticket,
            "--for", worker, "--test-command", test_command, *extra]
    for a in assigns:
        args += ["--assign", a]
    done = subprocess.run(args, capture_output=True, text=True)
    return done.returncode, done.stdout, done.stderr


def brief_at(line):
    path = re.search(r"(/\S+\.md)", line)
    assert path, f"the dispatch line names no brief path: {line!r}"
    with open(path.group(1)) as fh:
        return fh.read(), path.group(1)


def test_a_brief_lists_own_files_marks_others_off_limits_and_carries_test_and_mutation_rule(wt):
    code, out, err = run(wt, "alpha=a.py,b.py", "beta=c.py")
    assert code == 0, err
    text, _ = brief_at(out)
    mine = re.search(r"^Your files:(.*?)(?=^## |\Z)", text, re.M | re.S).group(1)
    assert "a.py" in mine and "b.py" in mine and "c.py" not in mine, text
    off = re.search(r"^## Off limits[^\n]*\n(.*?)(?=^## |\Z)", text, re.M | re.S).group(1)
    assert "c.py" in off and "a.py" not in off, text
    assert TEST_COMMAND in text, text
    assert "scratch copy" in text and "never mutate the live file" in text.lower(), text


def test_the_no_git_write_and_no_subagent_rules_are_stated(wt):
    _, out, _ = run(wt, "alpha=a.py", "beta=c.py")
    text, _ = brief_at(out)
    assert "no git write" in text.lower() and "no nested subagent" in text.lower(), text


def test_two_workers_sharing_a_file_is_refused_and_nothing_is_written(wt, home):
    code, out, err = run(wt, "alpha=a.py,b.py", "beta=b.py")
    assert code == 2 and out == "", (code, out)
    assert "b.py" in err and "alpha" in err and "beta" in err, err
    assert not home.exists() or not list(home.rglob("*.md")), list(home.rglob("*"))


def test_a_worker_with_no_files_is_refused(wt):
    code, out, err = run(wt, "alpha=a.py", "beta=")
    assert code == 2 and out == "", (code, out)
    assert "beta" in err and "no files" in err, err


def test_the_worker_must_be_one_of_the_assigned(wt):
    code, out, err = run(wt, "alpha=a.py", "beta=c.py", worker="gamma")
    assert code == 2 and out == "", (code, out)
    assert "gamma" in err, err


def test_a_second_render_for_the_same_ticket_and_worker_does_not_overwrite_the_first(wt):
    _, first, _ = run(wt, "alpha=a.py", "beta=c.py")
    _, second, _ = run(wt, "alpha=a.py,z.py", "beta=c.py")
    t1, p1 = brief_at(first)
    t2, p2 = brief_at(second)
    assert p1 != p2, (p1, p2)
    assert "z.py" not in open(p1).read() and "z.py" in t2


def refused(wt, *assigns, **kw):
    code, out, err = run(wt, *assigns, **kw)
    assert code == 2 and out == "", (code, out, err)
    return err


def test_a_split_with_one_worker_is_refused(wt):
    assert "two workers" in refused(wt, "alpha=a.py")


def test_an_empty_test_command_is_refused(wt):
    assert "test command" in refused(wt, "alpha=a.py", "beta=c.py", test_command="  ")


def test_the_mutation_rule_names_how_to_point_the_test_at_the_copy(wt):
    _, out, _ = run(wt, "alpha=a.py", "beta=c.py")
    text, _ = brief_at(out)
    assert f'cp -a {wt} "$(mktemp -d)/copy"' in text, text
    assert "not run" in text, text


def test_a_dot_slash_spelling_of_a_file_is_the_same_file(wt):
    err = refused(wt, "alpha=./a.py", "beta=a.py")
    assert "a.py" in err and "alpha" in err and "beta" in err, err


def test_a_directory_owner_overlaps_a_file_beneath_it(wt):
    err = refused(wt, "alpha=implement/", "beta=implement/x.py")
    assert "implement" in err and "alpha" in err and "beta" in err, err


def test_a_file_listed_twice_by_one_worker_is_listed_once(wt):
    code, out, err = run(wt, "alpha=a.py,a.py", "beta=c.py")
    assert code == 0, err
    text, _ = brief_at(out)
    assert text.count("- `a.py`") == 1, text


def test_a_worktree_that_is_not_a_directory_is_refused(wt):
    assert "not a directory" in refused(wt + "/missing", "alpha=a.py", "beta=c.py")


def test_a_worker_assigned_twice_is_refused(wt):
    assert "assigned twice" in refused(wt, "alpha=a.py", "alpha=b.py", "beta=c.py")


def test_a_malformed_assign_is_refused(wt):
    assert "<worker>=<file>" in refused(wt, "alpha", "beta=c.py")


def test_a_repo_that_would_leave_the_cache_is_refused(wt):
    assert "repo" in refused(wt, "alpha=a.py", "beta=c.py", repo="/abs/outside")


# --- the fix-round task (#1620) ---------------------------------------------

ASSIGNS = ("alpha=a.py", "beta=c.py")


def task(wt, *extra, worker="alpha"):
    code, out, err = run(wt, *ASSIGNS, worker=worker, extra=extra)
    assert code == 0, err
    return brief_at(out)[0]


def refused_task(wt, *extra):
    return refused(wt, *ASSIGNS, extra=extra)


def section(text, heading):
    m = re.search(rf"^## {heading}[^\n]*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    assert m, f"no '## {heading}' section: {text}"
    return m.group(0)


def test_findings_are_listed_by_id_for_their_own_worker_only(wt):
    text = task(wt, "--finding", "alpha:S1=rename the flag", "--finding", "beta:P2=drop the dead branch")
    body = section(text, "Findings to fix")
    assert "S1" in body and "rename the flag" in body, body
    assert "P2" not in text and "drop the dead branch" not in text, text


def test_a_ruled_finding_is_marked_flag_if_you_disagree_and_an_unruled_one_is_not(wt):
    text = task(wt, "--finding", "alpha:S1=plain finding", "--ruled", "alpha:C3=controller says use a set",
                "--finding", "beta:P2=other")
    body = section(text, "Findings to fix")
    lines = {l.split("`")[1]: l for l in body.splitlines() if l.startswith("- `")}
    assert "flag if you disagree" in lines["C3"].lower(), body
    assert "flag if you disagree" not in lines["S1"].lower(), body


def test_the_findings_report_names_every_id_and_asks_fixed_or_disputed(wt):
    text = task(wt, "--finding", "alpha:S1=x", "--finding", "alpha:S2=y", "--ruled", "alpha:C3=z",
                "--finding", "beta:P2=w")
    body = section(text, "Findings report")
    for fid in ("S1", "S2", "C3"):
        assert f"`{fid}`" in body, body
    assert "P2" not in body and "fixed" in body and "disputed" in body, body


def test_the_skeleton_report_points_at_the_findings_report(wt):
    text = task(wt, "--finding", "alpha:S1=x", "--finding", "beta:P2=w")
    report = section(text, "Report")
    assert "Findings report" in report, report


def test_the_brief_caps_test_workers_and_wall_clock(wt):
    text = task(wt, "--workers", "2", "--ceiling", "300")
    assert "at most 2 workers" in text and "300 seconds" in text, text


def test_the_default_caps_are_one_worker_and_600_seconds(wt):
    text = task(wt)
    assert "at most 1 worker " in text and "600 seconds" in text, text


def test_a_finding_id_given_twice_is_refused(wt):
    err = refused_task(wt, "--finding", "alpha:S1=x", "--finding", "beta:S1=y")
    assert "S1" in err and "twice" in err, err


def test_a_finding_for_an_unassigned_worker_is_refused(wt):
    err = refused_task(wt, "--finding", "gamma:S1=x", "--finding", "alpha:S2=y", "--finding", "beta:S3=z")
    assert "gamma" in err and "not among the assigned workers" in err, err


def test_a_worker_left_with_no_finding_is_refused_once_findings_are_given(wt):
    err = refused_task(wt, "--finding", "alpha:S1=x")
    assert "beta" in err and "no finding" in err, err


@pytest.mark.parametrize("spec", ["alpha S1 x", "alpha:S1", "alpha:S1=", "alpha:S1=   ", ":S1=x", "alpha:=x"])
def test_a_finding_without_worker_id_or_text_is_refused(wt, spec):
    err = refused_task(wt, "--finding", spec, "--finding", "beta:P2=y")
    assert "<worker>:<id>=<text>" in err, err


def test_an_id_with_a_character_outside_the_plain_set_is_refused_naming_the_id(wt):
    err = refused_task(wt, "--finding", "alpha:S`1=x", "--finding", "beta:P2=y")
    assert "S`1" in err and "letters, digits" in err and "<worker>:<id>=<text>" not in err, err


def test_a_brief_without_findings_has_no_findings_section(wt):
    text = brief_at(run(wt, *ASSIGNS)[1])[0]
    assert "## Findings to fix" not in text and "## Findings report" not in text, text


def test_the_findings_text_with_markdown_headings_stays_inside_its_bullet(wt):
    text = task(wt, "--finding", "alpha:S1=line one\n## Report\nline two", "--finding", "beta:P2=y")
    assert len(re.findall(r"^## Report", text, re.M)) == 1, text


def test_a_zero_worker_cap_is_refused_naming_the_flag_and_value(wt):
    err = refused_task(wt, "--workers", "0")
    assert "--workers (0)" in err and "at least 1" in err, err


def test_a_zero_ceiling_is_refused(wt):
    err = refused_task(wt, "--ceiling", "0")
    assert "--ceiling (0)" in err, err


def test_a_worker_name_holding_a_colon_is_refused_at_assign(wt):
    err = refused(wt, "a:b=x.py", "beta=c.py", worker="beta")
    assert "a:b" in err and "':'" in err, err
