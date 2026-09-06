"""The audit set (#558): name, gated flag, short-set membership, and
ground-truth override paths for the two gated (staleness-cached) audits.
Adding an audit is one entry here — no other file needs to change.
"""

AUDITS = [
    {"name": "ponytail-audit", "gated": False, "short": True, "ground_truth": []},
    {"name": "test-audit", "gated": False, "short": False, "ground_truth": []},
    {"name": "comment-audit", "gated": False, "short": False, "ground_truth": []},
    {"name": "thermo-nuclear-code-quality-review", "gated": False, "short": True, "ground_truth": []},
    {"name": "improve-codebase-architecture", "gated": False, "short": True, "ground_truth": []},
    {"name": "audit-instructions", "gated": False, "short": False, "ground_truth": []},
    {"name": "dead-code", "gated": False, "short": False, "ground_truth": []},
    {"name": "duplication", "gated": False, "short": False, "ground_truth": []},
    {"name": "error-handling", "gated": False, "short": False, "ground_truth": []},
    {"name": "docstring-coverage", "gated": False, "short": False, "ground_truth": []},
    {"name": "domain-drift", "gated": True, "short": False, "ground_truth": ["CONTEXT.md", "docs/adr/"]},
    {"name": "type-tightness", "gated": True, "short": False, "ground_truth": []},
    {"name": "crap-audit", "gated": False, "short": False, "ground_truth": []},
]

AUDIT_NAMES = [a["name"] for a in AUDITS]
SHORT_SET = [a["name"] for a in AUDITS if a["short"]]
GATED = {a["name"]: a["ground_truth"] for a in AUDITS if a["gated"]}
