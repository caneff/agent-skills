"""comment-audit's answer key against its fixtures, and its apply rules.

The audit is prompt-only, so the key is the grader: each row must name a real
comment line and follow the citation rule (a citation that carries a why is a
salvage, a whole delete only when only the number remains). The last tests
pin the shape of SKILL.md's Applying the cuts section: nine numbered rules,
each stated in the direction it gives.
"""
import re
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
CUT = {"restatement", "banner", "historical", "citation", "inferable-why",
       "filler", "commented-out-code", "stale"}
KEEP = {"why", "warning", "workaround", "domain-rule", "api-contract"}
GONE = "— gone —"
MARKERS = ('#', '//', '"""')


def _rows():
    rows = []
    for line in (FIXTURES / "answer-key.md").read_text(encoding="utf-8").splitlines():
        if not re.match(r"\| \d+ \|", line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        _, name, lineno, bucket, category, after = cells
        rows.append((name.strip("`"), int(lineno), bucket, category, after))
    return rows


def _comment(name, lineno):
    return (FIXTURES / name).read_text(encoding="utf-8").splitlines()[lineno - 1]


def _bare(text):
    """What a citation leaves once every number and pointer word is stripped."""
    text = re.sub(r"#\d+|\b(?:issue|spec|decision|decisions|see|fixes)\b|\d+", "", text)
    return re.sub(r"[^A-Za-z]", "", re.sub(r"^\s*(?:#|//+/?|\"\"\")", "", text))


ROWS = _rows()


def test_key_parses():
    assert len(ROWS) == 8


@pytest.mark.parametrize("name,lineno,bucket,category,after", ROWS)
def test_row_points_at_a_comment(name, lineno, bucket, category, after):
    assert any(m in _comment(name, lineno) for m in MARKERS)


@pytest.mark.parametrize("name,lineno,bucket,category,after", ROWS)
def test_row_vocabulary(name, lineno, bucket, category, after):
    vocab = {"cut": CUT, "keep": KEEP, "load-bearing": {"directive"}}
    assert category in vocab[bucket]
    assert bool(after) == (bucket == "cut")


@pytest.mark.parametrize("name,lineno,bucket,category,after",
                         [r for r in ROWS if r[3] == "citation"])
def test_citation_salvage_iff_a_why_remains(name, lineno, bucket, category, after):
    carries_why = len(_bare(_comment(name, lineno))) > 0
    assert (after != GONE) == carries_why
    assert not re.search(r"#\d|\b(?:issue|spec|decision)s? \d", after)


def test_three_mis_cuts_are_keyed():
    keyed = {(n, c) for n, _, _, c, _ in ROWS}
    assert ("sample.py", "citation") in keyed  # module docstring with a citation
    assert ("test_sample.py", "why") in keyed  # test-intent comment
    assert ("sample.rs", "api-contract") in keyed  # API contract on a /// line
    # The same file and category can be held by another row, so pin each
    # mis-cut to its own key row: line, bucket and (for the docstring) its salvage.
    by_row = {(n, ln): (b, c, a) for n, ln, b, c, a in ROWS}
    assert by_row[("sample.py", 1)][:2] == ("cut", "citation")
    assert by_row[("sample.py", 1)][2] != GONE, "the docstring is a salvage, not a whole delete"
    assert by_row[("test_sample.py", 5)][:2] == ("keep", "why")
    assert by_row[("sample.rs", 1)][:2] == ("keep", "api-contract")


SKILL = Path(__file__).parent / "SKILL.md"
RULE_TOPICS = [  # one phrase per standing apply rule, in list order, stating its direction
    r"text, never its line number",
    r"edit comments only",
    r"never touch a load-bearing line",
    r"keep an issue citation",
    r"never cut it whole",
    r"keep the docstring of a symbol",
    r"rewrite a historical or stale comment to the current fact",
    r"when in doubt, keep",
    r"run the repo's lint",
]


def _applying_section():
    text = SKILL.read_text(encoding="utf-8")
    m = re.search(r"^## Applying the cuts.*?(?=^## )", text, re.S | re.M)
    assert m, "no 'Applying the cuts' section"
    return m.group(0)


def _numbered_rules():
    return re.findall(r"^(\d+)\. (.*?)(?=^\d+\. |^\S|\Z)", _applying_section(),
                      re.S | re.M)


def test_apply_rules_are_one_numbered_list():
    rules = _numbered_rules()
    assert [n for n, _ in rules] == [str(i) for i in range(1, len(RULE_TOPICS) + 1)]


@pytest.mark.parametrize("i,topic", list(enumerate(RULE_TOPICS)))
def test_each_rule_is_stated_in_its_place(i, topic):
    _, body = _numbered_rules()[i]
    assert re.search(topic, " ".join(body.split()), re.I)


def test_section_states_the_brief_shape():
    section = " ".join(_applying_section().split())
    assert "rows slice" in section
    assert "apply per comment-audit's Applying the cuts" in section


def test_opt_in_contract_is_still_referenced():
    section = " ".join(_applying_section().split())
    assert "all-audits/SKILL.md`'s \"Opt-in edits\" section" in section
