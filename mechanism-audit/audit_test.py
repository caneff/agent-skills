"""Tests for mechanism-audit's candidate pass and findings validation."""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from audit import candidates, validate  # noqa: E402

SAMPLE = os.path.join(HERE, "fixtures", "sample")
FINDINGS = os.path.join(HERE, "fixtures", "findings.jsonl")


def _rows():
    return [json.loads(line) for line in open(FINDINGS, encoding="utf-8")]


def test_the_three_seeded_rules_are_candidates_with_their_lines():
    found = {(c["file"], c["line"]) for c in candidates(SAMPLE)}
    assert {("AGENTS.md", 3), ("AGENTS.md", 5), ("AGENTS.md", 7)} <= found


def test_a_heading_with_no_trigger_word_is_not_a_candidate():
    assert ("AGENTS.md", 1) not in {(c["file"], c["line"]) for c in candidates(SAMPLE)}


def test_a_repo_without_instruction_files_is_read_on_its_comments(tmp_path):
    (tmp_path / "a.py").write_text(
        'x = 1\n# falls back to the cache if absent\n"""Doc.\n\nRefuses a bad id.\n"""\ny = 2  # plain note\n',
        encoding="utf-8")
    got = {(c["file"], c["line"]) for c in candidates(str(tmp_path))}
    assert got == {("a.py", 2), ("a.py", 5)}


def test_a_trigger_word_in_plain_code_is_not_a_candidate(tmp_path):
    (tmp_path / "a.py").write_text('otherwise = "every thing must go"\n', encoding="utf-8")
    assert candidates(str(tmp_path)) == []


def test_a_worktree_copy_of_the_repo_is_not_read_twice(tmp_path):
    (tmp_path / "worktrees" / "w").mkdir(parents=True)
    (tmp_path / "worktrees" / "w" / "AGENTS.md").write_text("Never skip this.\n", encoding="utf-8")
    assert candidates(str(tmp_path)) == []


def test_the_seeded_findings_are_valid():
    assert validate(_rows()) == []


@pytest.mark.parametrize("mutate, message", [
    (lambda r: r["extra"].pop("searched"), "searched"),
    (lambda r: r["extra"].update(searched=[]), "searched"),
    (lambda r: r["extra"].update(searched=[{"where": "rg x", "result": ""}]), "result"),
    (lambda r: r["extra"].update(searched=[{"result": "none"}]), "where"),
    (lambda r: r.pop("extra"), "searched"),
    (lambda r: r.update(category="vibes"), "category"),
    (lambda r: r.update(line="3"), "line"),
    (lambda r: r.update(failure=""), "failure"),
])
def test_a_gap_finding_missing_its_evidence_is_rejected(mutate, message):
    row = _rows()[0]
    mutate(row)
    errors = validate([row])
    assert len(errors) == 1 and message in errors[0], errors


def test_the_validate_cli_names_a_corrupt_line_and_exits_1(tmp_path):
    import subprocess
    log = tmp_path / "findings.jsonl"
    log.write_text(open(FINDINGS, encoding="utf-8").read() + "not json\n", encoding="utf-8")
    r = subprocess.run([sys.executable, os.path.join(HERE, "audit.py"), "validate", str(log)],
                       capture_output=True, text=True)
    assert r.returncode == 1 and "corrupt line 4: not json" in r.stdout, r.stdout
    ok = subprocess.run([sys.executable, os.path.join(HERE, "audit.py"), "validate", FINDINGS],
                        capture_output=True, text=True)
    assert (ok.returncode, ok.stdout) == (0, "")
