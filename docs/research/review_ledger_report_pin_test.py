"""Output pin for the ledger report (#1774, spec #1735). The report and its JSON form for the
shared harvest fixture are frozen in `review_ledger_golden/`; the ablation reads them, so a
refactor of the ledger must leave them byte-identical. A failure here means the output changed:
decide whether the change is wanted before touching the golden."""
from pathlib import Path

from review_ledger_support import build_cache

GOLDEN = Path(__file__).resolve().parent / "review_ledger_golden"


def test_the_text_report_and_the_json_report_are_byte_identical_to_the_golden(env):
    cache = env.tmp / "cache"
    build_cache(cache)
    env.harvest(cache)
    text = env.run("report", "--ledger", env.ledger)
    as_json = env.run("report", "--ledger", env.ledger, "--format", "json")
    assert (text.returncode, as_json.returncode) == (0, 0), text.stderr + as_json.stderr
    assert text.stdout == (GOLDEN / "report.md").read_text()
    assert as_json.stdout == (GOLDEN / "report.json").read_text()


def test_every_row_family_reports_byte_identical_to_the_pre_refactor_ledger(env):
    """#1735 C3, P5: the harvest fixture holds review rows only, so this pin covers the rest.
    `families.jsonl` is a scrubbed sample of real ledger rows, one or more of every family:
    costed and uncosted reviews, codex-gate known, clean, skipped and refused, codex-second,
    a codex-audit row with PRs, and each mutation type red, green and unknown. Its goldens were
    written by the ledger at 84c70295, before #1774's first refactor, and never by the code
    under test."""
    ledger = GOLDEN / "families.jsonl"
    for args, golden in ((["--format", "md"], "families.md"),
                         (["--format", "json"], "families.json"),
                         (["--prices", str(GOLDEN / "prices.json"), "--split", "none"], "families-priced.md")):
        done = env.run("report", "--ledger", ledger, *args)
        assert done.returncode == 0, done.stderr
        assert done.stdout == (GOLDEN / golden).read_text(), golden
