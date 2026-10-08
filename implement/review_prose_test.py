#!/usr/bin/env python3
"""Pins two rules of implement/SKILL.md § Review and § The Codex pass (#1448, #1449).

The standards axis runs on every PR since Chris ended its ablation, so neither
skill may carry a rule that skips it. A kill-switch exit 20 of the usage gate
files its skip row under the `ablation` token, which `review_ledger.py` counts;
a free-text reason folds into `other` and is lost to the ablation's table.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMPLEMENT = (ROOT / "implement" / "SKILL.md").read_text()
MULTI_AXIS = (ROOT / "multi-axis-code-review" / "SKILL.md").read_text()

failures = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + (f"  {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(name)


check("implement/SKILL.md has no standards-axis skip",
      "--type standards --skip-reason" not in IMPLEMENT and "the standards axis does not run" not in IMPLEMENT)
check("implement/SKILL.md has no 'first ablation' rule", "first ablation" not in IMPLEMENT)
check("multi-axis-code-review/SKILL.md does not say an ablation skips the standards axis",
      "skips the standards axis" not in MULTI_AXIS)

flat = re.sub(r"\s+", " ", IMPLEMENT)
check("a kill-switch exit 20 takes --skip-reason ablation exactly",
      re.search(r"reviews off by Chris's ruling.{0,200}`--skip-reason ablation` exactly", flat) is not None)
check("the free-text skip-reason list no longer includes the kill-switch line",
      "That is an exit 20 or 30 of the usage gate (a reserve-ceiling exit 20's reason is `ceiling`, not the line;"
      " a kill-switch exit 20's is `ablation`," in flat)

sys.exit(1 if failures else 0)
