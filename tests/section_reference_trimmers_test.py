"""Pins the label trimmers of check-section-references.py: which run, in what order."""
import importlib.util
import re
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "checker", Path(__file__).with_name("check-section-references.py")
)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)

assert [name for name, _ in checker.PROSE_TRIMMERS] == [
    "cross-reference conjunction",
    "trailing conjunction",
    "possessive",
]
assert checker.PUNCTUATION_TRIMMER[0] == "sentence punctuation"

# A trimmer added to PROSE_TRIMMERS must actually run.
checker.PROSE_TRIMMERS += (("footnote", lambda v: v.split(" [^", 1)[0]),)
match = re.search(checker.SECTION, "See § Alpha [^1] for details")
assert ("Alpha", []) in checker.reference_targets(match)
checker.PROSE_TRIMMERS = checker.PROSE_TRIMMERS[:-1]

# The step locator reads before punctuation cuts the label.
match = re.search(checker.SECTION, "See § Before the PR: step 5 for details.")
assert ("Before the PR", [5]) in checker.reference_targets(match)
print("ok")
