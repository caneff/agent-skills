"""Fixture for error-handling: one unjustified swallow, one justified one.

Both are flagged by ruff/bandit — a plain linter treats them the same. The
point of this fixture is that pass two (the semantic judgment pass) must
tell them apart by reading each in context, not that the tools already can.
"""


def load_config(path):
    """Unjustified: swallows every exception with no reason, no re-raise, no log."""
    try:
        with open(path) as f:
            return f.read()
    except Exception:
        pass


def notify_best_effort(webhook, payload):
    """Justified: an optional telemetry ping. A tool flags this the same as
    load_config's swallow above — broad except, silent pass — but the comment
    documents a deliberate reason: notification failures must never break the
    caller's primary operation."""
    try:
        webhook.send(payload)
    except Exception:
        # best-effort notification; network/webhook failures are expected and
        # must never fail the caller's primary operation
        pass
