"""`review_ledger.py correct` (#1658): an append-only correction of a mutation row's outcome.
Seams: the command line over a throwaway ledger, then every reader (`report`, `escapes` input
via `read_ledger`) over the same ledger. HOME is a temp dir."""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "review_ledger.py")
sys.path.insert(0, HERE)
import review_ledger  # noqa: E402

FALSE_ROW = "skills/130/worker-mutation/1/fixm2"


def run(tmp_path, *args):
    env = dict(os.environ, HOME=str(tmp_path / "home"))
    return subprocess.run([sys.executable, SCRIPT, *map(str, args)], capture_output=True, text=True, env=env)


def ledger_with_false_red(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    r = run(tmp_path, "append", "--repo", "skills", "--ticket", 130, "--type", "worker-mutation",
            "--mutation-id", "fixm2", "--outcome", "red", "--seconds", 5, "--ledger", ledger)
    assert r.returncode == 0, r.stderr
    return ledger


def correct(tmp_path, ledger, outcome="green", row=FALSE_ROW, reason="helper passed red unconditionally", ticket=130):
    return run(tmp_path, "correct", "--repo", "skills", "--ticket", ticket, "--row", row,
               "--outcome", outcome, "--reason", reason, "--ledger", ledger)


def report(tmp_path, ledger):
    r = run(tmp_path, "report", "--ledger", ledger, "--format", "json")
    assert r.returncode == 0, r.stderr
    return {t["type"]: t for t in json.loads(r.stdout)["types"]}["worker-mutation"]


def test_correction_supersedes_the_row_in_report_and_leaves_the_original_line_untouched(tmp_path):
    ledger = ledger_with_false_red(tmp_path)
    before = ledger.read_text()
    assert report(tmp_path, ledger)["red_rate"] == 1.0
    r = correct(tmp_path, ledger)
    assert r.returncode == 0, r.stderr
    after = ledger.read_text()
    assert before.strip() in after  # the false row's line is still there, byte for byte
    assert len(after.splitlines()) == 2
    assert report(tmp_path, ledger)["red_rate"] == 0.0


def test_read_ledger_serves_the_corrected_outcome_and_hides_the_correction_row(tmp_path):
    ledger = ledger_with_false_red(tmp_path)
    assert correct(tmp_path, ledger, "green").returncode == 0
    rows = review_ledger.read_ledger(ledger)
    assert [(r["row_id"], r["outcome"]) for r in rows] == [(FALSE_ROW, "green")]


def test_a_later_correction_supersedes_an_earlier_one(tmp_path):
    ledger = ledger_with_false_red(tmp_path)
    assert correct(tmp_path, ledger, "green").returncode == 0
    assert correct(tmp_path, ledger, "unknown", reason="second look").returncode == 0
    assert [r["outcome"] for r in review_ledger.read_ledger(ledger)] == ["unknown"]


def test_a_later_append_or_harvest_write_keeps_the_correction_row(tmp_path):
    ledger = ledger_with_false_red(tmp_path)
    assert correct(tmp_path, ledger).returncode == 0
    r = run(tmp_path, "append", "--repo", "skills", "--ticket", 130, "--type", "worker-mutation",
            "--mutation-id", "other", "--outcome", "red", "--seconds", 1, "--ledger", ledger)
    assert r.returncode == 0, r.stderr
    assert len(ledger.read_text().splitlines()) == 3
    assert sorted(r["outcome"] for r in review_ledger.read_ledger(ledger)) == ["green", "red"]


def test_refuses_a_row_that_is_not_in_the_ledger_and_writes_nothing(tmp_path):
    ledger = ledger_with_false_red(tmp_path)
    before = ledger.read_text()
    r = correct(tmp_path, ledger, row="skills/130/worker-mutation/1/nope")
    assert r.returncode == 2 and "nope" in r.stderr
    assert ledger.read_text() == before


def test_refuses_a_row_of_another_ticket_or_repo(tmp_path):
    ledger = ledger_with_false_red(tmp_path)
    assert correct(tmp_path, ledger, ticket=131).returncode == 2
    r = run(tmp_path, "correct", "--repo", "other", "--ticket", 130, "--row", FALSE_ROW, "--outcome", "green",
            "--reason", "x", "--ledger", ledger)
    assert r.returncode == 2


def test_refuses_a_row_that_is_not_a_mutation_row(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    r = run(tmp_path, "append", "--repo", "skills", "--ticket", 7, "--type", "codex-gate", "--skip-reason", "size",
            "--ledger", ledger)
    assert r.returncode == 0, r.stderr
    row_id = json.loads(ledger.read_text().splitlines()[0])["row_id"]
    before = ledger.read_text()
    r = correct(tmp_path, ledger, row=row_id, ticket=7)
    assert r.returncode == 2 and "mutation" in r.stderr
    assert ledger.read_text() == before


def test_refuses_an_empty_reason_and_a_bad_outcome(tmp_path):
    ledger = ledger_with_false_red(tmp_path)
    assert correct(tmp_path, ledger, reason="  ").returncode == 2
    assert correct(tmp_path, ledger, outcome="maybe").returncode == 2
    assert len(ledger.read_text().splitlines()) == 1


def test_a_correction_naming_a_missing_row_fails_the_reader_loud(tmp_path):
    ledger = ledger_with_false_red(tmp_path)
    orphan = {"row_id": "skills/130/correction/1/x", "type": "correction", "corrects": "skills/130/gone",
              "outcome": "green", "reason": "r"}
    with open(ledger, "a") as fh:
        fh.write(json.dumps(orphan) + "\n")
    try:
        review_ledger.read_ledger(ledger)
    except ValueError as e:
        assert "gone" in str(e)
    else:
        raise AssertionError("an orphan correction was read as nothing")


def test_a_hand_built_row_with_no_row_id_still_reads(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(json.dumps({"repo": "skills", "ticket": 1, "type": "spec"}) + "\n")
    assert review_ledger.read_ledger(ledger) == [{"repo": "skills", "ticket": 1, "type": "spec"}]


def test_a_mutation_re_run_under_the_same_id_is_not_read_as_corrected(tmp_path):
    ledger = ledger_with_false_red(tmp_path)
    assert correct(tmp_path, ledger, "green").returncode == 0
    r = run(tmp_path, "append", "--repo", "skills", "--ticket", 130, "--type", "worker-mutation",
            "--mutation-id", "fixm2", "--outcome", "red", "--seconds", 6, "--ledger", ledger)
    assert r.returncode == 0, r.stderr
    [row] = review_ledger.read_ledger(ledger)
    assert row["outcome"] == "red" and "corrected" not in row
    assert row["stale_corrections"] == [FALSE_ROW + "/correction/1"]
    assert report(tmp_path, ledger)["red_rate"] == 1.0


def test_the_eleventh_correction_wins_over_the_second_whatever_the_file_order(tmp_path):
    ledger = ledger_with_false_red(tmp_path)
    outcomes = ["green", "red", "unknown"]
    for k in range(11):
        assert correct(tmp_path, ledger, outcomes[k % 3], reason=f"round {k}").returncode == 0
    lines = ledger.read_text().splitlines()
    assert len(lines) == 12  # no correction overwrote another
    ids = [json.loads(x)["row_id"][len(FALSE_ROW):] for x in lines]
    assert ids.index("/correction/10") < ids.index("/correction/2")  # text order: 10 sorts before 2
    assert [r["outcome"] for r in review_ledger.read_ledger(ledger)] == [outcomes[10 % 3]]


def write_rows(ledger, *rows):
    with open(ledger, "a") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def test_a_correction_of_a_row_that_is_not_a_mutation_row_fails_the_reader_loud(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    write_rows(ledger, {"row_id": "skills/1/spec/1/x", "type": "spec"},
               {"row_id": "c1", "type": "correction", "corrects": "skills/1/spec/1/x", "outcome": "green",
                "reason": "r", "target_sha256": "x"})
    try:
        review_ledger.read_ledger(ledger)
    except ValueError as e:
        assert "only a mutation row" in str(e)
    else:
        raise AssertionError("a correction of a spec row was read as nothing")


def test_a_correction_with_an_outcome_no_mutation_has_fails_the_reader_loud(tmp_path):
    ledger = ledger_with_false_red(tmp_path)
    target = review_ledger.read_ledger_raw(ledger)[0]
    write_rows(ledger, {"row_id": "c1", "type": "correction", "corrects": FALSE_ROW, "outcome": "fixed",
                        "reason": "r", "target_sha256": review_ledger.row_digest(target)})
    try:
        review_ledger.read_ledger(ledger)
    except ValueError as e:
        assert "'fixed'" in str(e)
    else:
        raise AssertionError("a bad correction outcome was read as nothing")


def test_harvest_keeps_the_correction_row(tmp_path):
    ledger = ledger_with_false_red(tmp_path)
    assert correct(tmp_path, ledger).returncode == 0
    cache, transcripts = tmp_path / "cache", tmp_path / "tr"
    (cache / "skills").mkdir(parents=True)
    transcripts.mkdir()
    (cache / "skills" / "findings-standards-9.jsonl").write_text(json.dumps(
        {"id": "S1", "axis": "standards", "severity": "hard", "file": "a.py", "title": "t"}) + "\n")
    r = run(tmp_path, "harvest", "--cache", cache, "--transcripts", transcripts, "--ledger", ledger,
            "--review-file", tmp_path / "review.md")
    assert r.returncode == 0, r.stderr
    raw = review_ledger.read_ledger_raw(ledger)
    assert sorted(r["type"] for r in raw) == ["correction", "standards", "worker-mutation"]  # harvest ran
    assert [r["outcome"] for r in review_ledger.read_ledger(ledger) if r["type"] == "worker-mutation"] == ["green"]
