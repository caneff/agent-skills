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
    (lambda r: r["extra"].update(searched=[{"where": "rg x", "result": "", "ok": True}] * 2), "result"),
    (lambda r: r["extra"].update(searched=[{"result": "none", "ok": True}] * 2), "where"),
    (lambda r: r.pop("extra"), "searched"),
    (lambda r: r.update(category="vibes"), "category"),
    (lambda r: r.update(line="3"), "line"),
    (lambda r: r.update(line=True), "line"),
    (lambda r: r.update(file="/abs/AGENTS.md"), "file"),
    (lambda r: r.update(failure=""), "failure"),
    (lambda r: r.pop("bucket"), "bucket"),
    (lambda r: r.update(bucket="Gap"), "bucket"),
    (lambda r: r.update(bucket="carried"), "bucket"),
    (lambda r: r.update(category="has-mechanism"), "bucket"),
    (lambda r: r["extra"]["searched"][0].pop("ok"), "ok"),
    (lambda r: r["extra"]["searched"][0].update(ok=False), "failed"),
    (lambda r: r["extra"].update(searched=r["extra"]["searched"][:1]), "two"),
])
def test_a_gap_finding_missing_its_evidence_is_rejected(mutate, message):
    row = _rows()[0]
    mutate(row)
    errors = validate([row])
    assert errors and all(message in e for e in errors), errors


def test_a_dot_claude_instruction_file_is_read(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "CLAUDE.md").write_text("Never skip this.\n", encoding="utf-8")
    assert [(c["file"], c["line"]) for c in candidates(str(tmp_path))] == [(".claude/CLAUDE.md", 1)]


def test_flow_claude_docs_are_instruction_files_only_on_a_path_boundary(tmp_path):
    for d in ("flow/claude", "myflow/claude"):
        (tmp_path / d).mkdir(parents=True)
        (tmp_path / d / "X.md").write_text("Never skip this.\n", encoding="utf-8")
    assert [c["file"] for c in candidates(str(tmp_path))] == ["flow/claude/X.md"]


def test_single_quote_docstrings_and_block_comments_are_read(tmp_path):
    (tmp_path / "a.py").write_text("\'\'\'Doc.\nRefuses a bad id.\n\'\'\'\n", encoding="utf-8")
    (tmp_path / "b.js").write_text("/* header\n * Falls back to the cache.\n */\n", encoding="utf-8")
    got = {(c["file"], c["line"]) for c in candidates(str(tmp_path))}
    assert got == {("a.py", 2), ("b.js", 2)}


def test_a_dangling_symlink_does_not_abort_pass_one(tmp_path):
    (tmp_path / "AGENTS.md").write_text("Never skip this.\n", encoding="utf-8")
    os.symlink(str(tmp_path / "gone.md"), str(tmp_path / "SKILL.md"))
    assert [c["file"] for c in candidates(str(tmp_path))] == ["AGENTS.md"]


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads every directory")
def test_an_unreadable_directory_stops_pass_one_rather_than_being_skipped(tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir()
    (locked / "AGENTS.md").write_text("Never skip this.\n", encoding="utf-8")
    locked.chmod(0)
    try:
        with pytest.raises(OSError):
            candidates(str(tmp_path))
    finally:
        locked.chmod(0o700)


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


def test_the_validate_cli_rejects_an_invalid_row(tmp_path):
    import subprocess
    row = _rows()[0]
    row["extra"].pop("searched")
    log = tmp_path / "findings.jsonl"
    log.write_text(json.dumps(row) + "\n", encoding="utf-8")
    r = subprocess.run([sys.executable, os.path.join(HERE, "audit.py"), "validate", str(log)],
                       capture_output=True, text=True)
    assert r.returncode == 1 and "row 1" in r.stdout and "searched" in r.stdout, r.stdout
