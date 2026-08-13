"""Pass-one fixture: pytest mechanical smells for audit.py.

Mirrors vitest_smells.test.js — exists to demonstrate the mechanical scanner's
output, not to feed the judgment-pass answer key.
"""


def test_computes_the_amount_off():
    assert apply_discount(100, 10) == 90


def test_runs_the_discount_path():
    result = apply_discount(100, 10)


def test_is_internally_consistent():
    x = apply_discount(100, 10)
    assert x == x


def test_is_a_placeholder():
    pass
