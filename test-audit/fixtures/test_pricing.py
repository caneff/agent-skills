"""Fixture: unit-level tests for the pricing module.

Deliberately mixed quality — see ../answer-key.md for the expected bucket
of each test. Do not "fix" these in place; they exist to be judged.
"""

from pricing import apply_discount


def test_apply_discount_computes_amount_off():
    # KEEP — direct unit test, one behavior, fails for exactly one reason.
    result = apply_discount(price=100, percent_off=10)

    assert result == 90


def test_apply_discount_handles_edge_cases():
    # CUT — conditional test logic. Whichever branch runs, the test always
    # finds a way to pass, so it cannot fail when the real behavior breaks.
    price = 100
    percent_off = 150  # over 100%, should be rejected or clamped

    if percent_off > 100:
        result = apply_discount(price, min(percent_off, 100))
        assert result >= 0
    else:
        result = apply_discount(price, percent_off)
        assert result <= price
