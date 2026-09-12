#!/usr/bin/env python3
"""Apply the contextual-review decisions for the 30-day pushback taxonomy.

The broad extractor intentionally over-includes ordinary questions.  This
small, explicit audit trail selects only exchanges reviewed as a correction,
repeated instruction, frustration, stop, or missed/restated request, and
attaches the reviewed (non-exclusive) mode(s).
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


REVIEWED: dict[str, tuple[str, ...]] = {
    # Lost or misread instruction / domain correction.
    "ff011de0-fb70-4216-ae33-24136ed02401.jsonl:27": ("live-instruction",),
    "e9944871-b320-499e-8d58-69c3306179e5.jsonl:157": ("live-instruction", "scope-stop"),
    "ce931843-8ee7-4296-b47f-73328c097830.jsonl:2607": ("live-instruction",),
    "ce931843-8ee7-4296-b47f-73328c097830.jsonl:2896": ("live-instruction", "long-run-constraints"),
    "ce931843-8ee7-4296-b47f-73328c097830.jsonl:3845": ("live-instruction", "scope-stop"),
    "ce931843-8ee7-4296-b47f-73328c097830.jsonl:8361": ("live-instruction",),
    "5009bdf9-fce1-48e3-81cd-363f62ca50b7.jsonl:343": ("live-instruction",),
    "86dbf8f0-6eae-4190-a3c2-232cd9b05002.jsonl:238": ("live-instruction", "workflow"),
    "f828b568-b668-4dc2-b590-290ec94a8dbc.jsonl:341": ("live-instruction",),
    "179b4aab-8be8-4769-a8e8-b6d509348d7c.jsonl:730": ("live-instruction", "visual-target"),
    "179b4aab-8be8-4769-a8e8-b6d509348d7c.jsonl:888": ("live-instruction",),
    "179b4aab-8be8-4769-a8e8-b6d509348d7c.jsonl:999": ("live-instruction",),
    "b55b4d31-d70d-4b2a-9292-0fb83ef6b28e.jsonl:505": ("live-instruction",),
    # The explanation repaired detail, not the causal question.
    "f2459af0-12dc-44de-9694-cbd90c84e6ae.jsonl:245": ("live-instruction", "explanation-repair"),
    "f2459af0-12dc-44de-9694-cbd90c84e6ae.jsonl:351": ("explanation-repair",),
    "f2459af0-12dc-44de-9694-cbd90c84e6ae.jsonl:530": ("explanation-repair",),
    "f2459af0-12dc-44de-9694-cbd90c84e6ae.jsonl:2937": ("explanation-repair",),
    "f2459af0-12dc-44de-9694-cbd90c84e6ae.jsonl:3064": ("live-instruction", "explanation-repair"),
    "d4beb51d-7635-4f2b-a8bf-08614db5a3e2.jsonl:942": ("explanation-repair",),
    "ce931843-8ee7-4296-b47f-73328c097830.jsonl:6245": ("explanation-repair",),
    # Continued / substituted action instead of obeying the requested scope.
    "8c0d9fac-dfdd-44e2-9cd6-aa1ab104db36.jsonl:1417": ("scope-stop",),
    "ce931843-8ee7-4296-b47f-73328c097830.jsonl:2078": ("scope-stop",),
    "ce931843-8ee7-4296-b47f-73328c097830.jsonl:3827": ("scope-stop",),
    "afce54a2-0526-4a6d-8deb-4d38ff6a669e.jsonl:100": ("scope-stop",),
    "6b67d2fa-3126-4d4e-a473-19e9fb20d2fb.jsonl:384": ("scope-stop",),
    "18af8aeb-cc97-4f34-a57a-67bf5aa787ae.jsonl:402": ("scope-stop", "workflow"),
    # Existing workflow was replaced or forgotten.
    "5c72e2b6-51f8-4651-a171-8be319b418ae.jsonl:452": ("workflow",),
    "33eab49e-7832-4af6-96a0-8a0eb46c7540.jsonl:328": ("workflow",),
    # Facts, state, and operational inputs were asserted without checking.
    "91b07b79-ab0e-438f-ad9a-d7d283166ccc.jsonl:119": ("unverified-state",),
    "ce931843-8ee7-4296-b47f-73328c097830.jsonl:5234": ("unverified-state", "long-run-constraints"),
    "ce931843-8ee7-4296-b47f-73328c097830.jsonl:5326": ("unverified-state", "long-run-constraints"),
    "ce931843-8ee7-4296-b47f-73328c097830.jsonl:5334": ("unverified-state", "long-run-constraints"),
    "ce931843-8ee7-4296-b47f-73328c097830.jsonl:5585": ("unverified-state",),
    "ce931843-8ee7-4296-b47f-73328c097830.jsonl:5809": ("unverified-state",),
    "ce931843-8ee7-4296-b47f-73328c097830.jsonl:5942": ("long-run-constraints",),
    "ef64564d-da2c-421f-8665-a2e63291f2fb.jsonl:1492": ("unverified-state",),
    "ef64564d-da2c-421f-8665-a2e63291f2fb.jsonl:1501": ("unverified-state",),
    # Visual / interaction outcome diverged from the stated target.
    "370096f1-1073-4f1a-90a8-91ecdcccf715.jsonl:729": ("visual-target",),
    "05cabd8e-313c-4e6d-9bed-0c35bb699ebb.jsonl:752": ("visual-target",),
    "05cabd8e-313c-4e6d-9bed-0c35bb699ebb.jsonl:859": ("visual-target",),
    "6b67d2fa-3126-4d4e-a473-19e9fb20d2fb.jsonl:695": ("visual-target",),
    "8750c4dd-29c7-4c7a-b137-2371f1b236e0.jsonl:1638": ("visual-target",),
    "8750c4dd-29c7-4c7a-b137-2371f1b236e0.jsonl:1812": ("visual-target",),
    # The response / delivery mechanism imposed needless work on the user.
    "d9cef269-2ea4-4f2c-bfb4-c0ef8e8977f7.jsonl:693": ("delivery-verbosity",),
    "8c0d9fac-dfdd-44e2-9cd6-aa1ab104db36.jsonl:1790": ("delivery-verbosity",),
    "8750c4dd-29c7-4c7a-b137-2371f1b236e0.jsonl:686": ("delivery-verbosity",),
    "b5886ab0-4361-40e4-92f2-9a85a2cb1e61.jsonl:913": ("delivery-verbosity",),
    # One useful but non-recurring observation.
    "b5dfd868-8b34-4865-ae79-e1e1215ea22f.jsonl:440": ("harness-leak",),
}


def main() -> None:
    here = Path(__file__).parent
    source = json.loads((here / "2026-09-12-pushback-evidence-30d.json").read_text())
    accepted = []
    for event in source["events"]:
        key = f"{Path(event['session_file']).name}:{event['transcript_line']}"
        if key in REVIEWED:
            accepted.append({**event, "modes": REVIEWED[key]})
    missing = set(REVIEWED) - {
        f"{Path(event['session_file']).name}:{event['transcript_line']}"
        for event in accepted
    }
    if missing:
        raise SystemExit(f"Reviewed events absent from extractor: {sorted(missing)}")
    output = {
        "method": source["method"],
        "reviewed_event_count": len(accepted),
        "reviewed_session_count": len({event["session_file"] for event in accepted}),
        "mode_event_counts": dict(Counter(mode for event in accepted for mode in event["modes"])),
        "events": accepted,
    }
    (here / "2026-09-12-pushback-evidence-30d-reviewed.json").write_text(
        json.dumps(output, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
