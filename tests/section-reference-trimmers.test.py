"""Pins the order of the label trimmers in check-section-references.py."""
import importlib.util
import re
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "checker", Path(__file__).with_name("check-section-references.py")
)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)

names = [name for name, _ in checker.LABEL_TRIMMERS]
assert names == [
    "cross-reference conjunction",
    "trailing conjunction",
    "possessive",
    "sentence punctuation",
], names

# The step locator reads the label before sentence punctuation cuts it, so
# "§ Before the PR: step 5" keeps its step; punctuation last is why.
match = re.search(checker.SECTION, "See § Before the PR: step 5 for details.")
targets = checker.reference_targets(match)
assert ("Before the PR", [5]) in targets, targets
print("ok")
