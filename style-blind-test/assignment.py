"""Deterministic, session-hashed output-style assignment.

Pure function: given a session_id, decide which output style to use and
whether the SessionStart hook should be on, independently, and stably
across the hook's `source` field (startup/clear/resume/compact) because
`source` is never consulted.
"""
import hashlib

STYLES = ("clarity-and-grace", "orwell-ste", "plain-speak", "default")


def _digest_int(salt: str, session_id: str) -> int:
    h = hashlib.sha256((salt + session_id).encode()).hexdigest()
    return int(h, 16)


def assignment(session_id: str) -> tuple[str, bool]:
    style = STYLES[_digest_int("style:", session_id) % len(STYLES)]
    hook_on = bool(_digest_int("hook:", session_id) % 2)
    return style, hook_on
