"""Fixture for mutation-audit: three coverage regimes the mix
fixtures/answer-key.md documents — a strongly-tested function (mutants
killed), a weakly-tested one (boundary mutants survive as `rewrite`), and
an untested one (its mutant survives as `no-coverage` — no test reaches it
at all)."""


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


def scale(x):
    """Untested: no test in the suite calls scale, so mutmut's mutant on
    this line survives with no covering test at all — a no-coverage
    survivor, not a weak assertion."""
    return x * 2
