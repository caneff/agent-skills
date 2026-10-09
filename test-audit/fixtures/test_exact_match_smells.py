"""Pass-one fixture: the four exact-match smells for audit.py.

Each smell has a positive and the nearest negative that must stay quiet. Not
in the judgment-pass answer key. `exact-match-fixtures.test.sh` pins the
scanner's output on this file line by line, so edit the two together.
"""
import pytest


# --- dead assertion in an expect-exception block ----------------------------


def test_dead_assertion_after_the_raising_call():
    with pytest.raises(ValueError, match="empty"):
        parse("")
        assert parse.calls == 1


def test_assertion_on_the_exception_outside_the_block():
    with pytest.raises(ValueError, match="empty") as info:
        parse("")
    assert info.value.args


# --- lost test --------------------------------------------------------------


def test_shadowed_by_the_next_def():
    assert parse("1") == 1


def test_shadowed_by_the_next_def():
    assert parse("2") == 2


class TestNeverCollected:
    def __init__(self):
        self.value = 1

    def test_value(self):
        assert self.value == 1


class TestCollected:
    def test_value(self):
        assert parse("1") == 1


# --- broad exception expectation --------------------------------------------


def test_passes_on_any_error():
    with pytest.raises(Exception):
        parse("")


def test_names_the_error_it_expects():
    with pytest.raises(Exception, match="empty"):
        parse("")


# --- non-strict xfail -------------------------------------------------------


@pytest.mark.xfail(reason="bug 12")
def test_green_whether_or_not_the_bug_is_fixed():
    assert parse("1") == 2


@pytest.mark.xfail(reason="bug 12", strict=True)
def test_red_once_the_bug_is_fixed():
    assert parse("1") == 2
