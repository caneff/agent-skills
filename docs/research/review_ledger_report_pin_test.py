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
