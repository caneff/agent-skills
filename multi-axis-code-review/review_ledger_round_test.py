"""A second review round's sidecar, named `-r2` with the first round's ids continued (#1549),
lands in the ledger as a round-2 row beside the round-1 row. Seam: `review_ledger.py append`
over a throwaway cache, transcripts directory and ledger.
"""
import json
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, "review_ledger.py")


def write(path, ids):
    with open(path, "w") as fh:
        for i in ids:
            fh.write(json.dumps({"id": i, "axis": "standards", "severity": "hard", "file": "a.py",
                                 "title": f"title {i}"}) + "\n")


def test_a_continued_id_r2_sidecar_is_a_round_two_row_with_its_own_ids(tmp_path):
    cache, transcripts, ledger = tmp_path / "cache", tmp_path / "tr", tmp_path / "ledger.jsonl"
    (cache / "skills").mkdir(parents=True)
    transcripts.mkdir()
    write(cache / "skills" / "findings-standards-1448.jsonl", [f"S{i}" for i in range(1, 12)])
    write(cache / "skills" / "findings-standards-1448-r2.jsonl", ["S12", "S13"])
    for rnd in ("1", "2"):
        done = subprocess.run(
            ["python3", LEDGER, "append", "--repo", "skills", "--ticket", "1448", "--type", "standards",
             "--round", rnd, "--cache", str(cache), "--transcripts", str(transcripts), "--ledger", str(ledger)],
            capture_output=True, text=True)
        assert done.returncode == 0, done.stderr
    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    got = {r["round"]: [f["id"] for f in r["findings"]] for r in rows}
    assert got == {1: [f"S{i}" for i in range(1, 12)], 2: ["S12", "S13"]}, got
