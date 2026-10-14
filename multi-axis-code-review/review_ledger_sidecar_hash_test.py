"""An appended axis row records the sha256 of the findings sidecar it was appended for (#1555), so
`implement/fix_check.py` can tell this wave's row from an earlier dispatch's. Seam: `review_ledger.py
append` over a throwaway cache, transcripts directory and ledger.
"""
import hashlib
import json
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, "review_ledger.py")


def append(tmp_path, axis, ids):
    cache, transcripts, ledger = tmp_path / "cache", tmp_path / "tr", tmp_path / "ledger.jsonl"
    (cache / "skills").mkdir(parents=True, exist_ok=True)
    transcripts.mkdir(exist_ok=True)
    sidecar = cache / "skills" / f"findings-{axis}-9.jsonl"
    sidecar.write_text("".join(json.dumps({"id": i, "axis": axis, "severity": "hard", "file": "a.py",
                                           "title": f"t {i}"}) + "\n" for i in ids))
    done = subprocess.run(["python3", LEDGER, "append", "--repo", "skills", "--ticket", "9", "--type", axis,
                           "--cache", str(cache), "--transcripts", str(transcripts), "--ledger", str(ledger)],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return sidecar, [json.loads(line) for line in ledger.read_text().splitlines()]


def test_an_appended_row_carries_the_sha256_of_its_sidecar(tmp_path):
    sidecar, rows = append(tmp_path, "spec", ["P1"])
    assert [r["sidecar_sha256"] for r in rows] == [hashlib.sha256(sidecar.read_bytes()).hexdigest()]


def test_an_empty_sidecar_is_hashed_too(tmp_path):
    sidecar, rows = append(tmp_path, "spec", [])
    assert rows and rows[0]["sidecar_sha256"] == hashlib.sha256(b"").hexdigest()


def test_a_skip_row_has_no_sidecar_and_no_hash(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    done = subprocess.run(["python3", LEDGER, "append", "--repo", "skills", "--ticket", "9", "--type", "spec",
                           "--skip-reason", "ablation", "--ledger", str(ledger)], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    assert "sidecar_sha256" not in json.loads(ledger.read_text())
