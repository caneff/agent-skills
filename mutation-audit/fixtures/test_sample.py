"""Fixture test suite: is_adult is tested at and around the boundary so its
mutants die; clamp is only tested in-range, so its boundary mutants survive."""
from sample import clamp, is_adult


def test_is_adult_true():
    assert is_adult(20) is True


def test_is_adult_boundary():
    assert is_adult(18) is True


def test_is_adult_false():
    assert is_adult(10) is False


def test_clamp_within_range():
    assert clamp(5, 0, 10) == 5
