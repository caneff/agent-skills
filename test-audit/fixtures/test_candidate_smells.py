"""Fixture: four more smells, for audit.py's pass one and the judgment pass.

Each smell has a positive and the nearest negative that must stay quiet. The
judgment-pass rows are in `answer-key.md`; `candidate-smells-fixtures.test.sh`
pins what the scanner reports on this file line by line, so edit the three
together.
"""
from unittest.mock import MagicMock

from billing import _round_cents
from billing import public_total


# --- leaking domain knowledge (judgment pass only) --------------------------


def test_total_recomputes_the_formula():
    cart = Cart(price=100, tax_rate=0.2)

    assert cart.total() == 100 + 100 * 0.2


def test_total_matches_a_worked_example():
    cart = Cart(price=100, tax_rate=0.2)

    assert cart.total() == 120


# --- private-API access -----------------------------------------------------


def test_reads_a_private_attribute():
    cache = Cache()
    cache.put("a", 1)

    assert cache._store == {"a": 1}


def test_reads_the_public_interface():
    cache = Cache()
    cache.put("a", 1)

    assert cache.get("a") == 1
    assert cache.__class__ is Cache


class TestOwnState:
    def test_self_privates_belong_to_the_test(self):
        self._seen = parse("1")

        assert self._seen == 1


# --- a stub that supplies input is also asserted called ---------------------


def test_stub_is_also_asserted_called():
    repo = MagicMock()
    repo.get.return_value = {"id": 1}

    assert load_user(repo, 1)["id"] == 1
    repo.get.assert_called_once_with(1)


def test_stub_built_with_a_side_effect_is_checked_called():
    fetch = MagicMock(side_effect=[1])

    assert read(fetch) == 1
    assert fetch.called


def test_stub_is_never_asserted_called():
    repo = MagicMock()
    repo.get.return_value = {"id": 1}

    assert load_user(repo, 1)["id"] == 1


def test_a_different_mock_is_asserted_called():
    repo = MagicMock()
    mailer = MagicMock()
    repo.get.return_value = {"id": 1}

    assert load_user(repo, 1, mailer)["id"] == 1
    mailer.send.assert_called_once()


# --- vacuous loop assertion -------------------------------------------------


def test_every_assertion_sits_in_a_loop_over_the_output():
    items = list_items()

    for item in items:
        assert item.price > 0


def test_loop_assertions_behind_a_length_check():
    items = list_items()

    assert len(items) == 2
    for item in items:
        assert item.price > 0


def test_loop_over_literal_cases():
    for n in (1, 2, 3):
        assert double(n) > n
