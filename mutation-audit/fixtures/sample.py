"""Fixture for mutation-audit: one function with weak test coverage (mutants
survive) and one with strong coverage (mutants killed) — the mix
fixtures/answer-key.md documents."""


def is_adult(age):
    """Strongly tested: both branches of the boundary are covered."""
    return age >= 18


def clamp(value, low, high):
    """Weakly tested: only the pass-through path is exercised, so the
    boundary mutants on the low/high checks survive."""
    if value < low:
        return low
    if value > high:
        return high
    return value
