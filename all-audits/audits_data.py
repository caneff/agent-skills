"""The audit set (#558): name, gated flag, short-set membership,
ground-truth override paths for the two gated (staleness-cached) audits, and
whether the audit reads only Python (#1751: all-audits/SKILL.md § Not applicable).
Adding an audit is one entry here — no other file needs to change.
"""

AUDITS = [
    {"name": "ponytail-audit", "gated": False, "short": True, "ground_truth": [], "python_only": False},
    {"name": "test-audit", "gated": False, "short": False, "ground_truth": [], "python_only": False},
    {"name": "comment-audit", "gated": False, "short": False, "ground_truth": [], "python_only": False},
    {"name": "thermo-nuclear-code-quality-review", "gated": False, "short": True, "ground_truth": [], "python_only": False},
    {"name": "improve-codebase-architecture", "gated": False, "short": True, "ground_truth": [], "python_only": False},
    {"name": "audit-instructions", "gated": False, "short": False, "ground_truth": [], "python_only": False},
    {"name": "dead-code", "gated": False, "short": False, "ground_truth": [], "python_only": True},
    {"name": "duplication", "gated": False, "short": False, "ground_truth": [], "python_only": False},
    {"name": "error-handling", "gated": False, "short": False, "ground_truth": [], "python_only": False},
    {"name": "docstring-coverage", "gated": False, "short": False, "ground_truth": [], "python_only": True},
    {"name": "domain-drift", "gated": True, "short": False, "ground_truth": ["GLOSSARY.md", "docs/adr/"], "python_only": False},
    {"name": "type-tightness", "gated": True, "short": False, "ground_truth": [], "python_only": True},
    {"name": "crap-audit", "gated": False, "short": False, "ground_truth": [], "python_only": False},
]

AUDIT_NAMES = [a["name"] for a in AUDITS]
SHORT_SET = [a["name"] for a in AUDITS if a["short"]]
PYTHON_ONLY = [a["name"] for a in AUDITS if a["python_only"]]
GATED = {a["name"]: a["ground_truth"] for a in AUDITS if a["gated"]}
