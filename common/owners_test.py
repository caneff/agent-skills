import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import owners  # noqa: E402


def test_the_login_owns_its_own_repos_in_any_case():
    assert owners.is_owned("CANEFF", "caneff")


def test_an_org_on_the_list_is_owned_in_any_case():
    assert owners.is_owned("ChinStrap45", "caneff")


def test_an_owner_neither_the_login_nor_listed_is_not_owned():
    assert not owners.is_owned("someone-else", "caneff")


def test_an_empty_owner_is_never_owned_even_by_an_empty_login():
    assert not owners.is_owned("", "")


def test_the_shipped_list_holds_the_ruled_owners_and_no_other():
    assert owners.owned_owners() == {"caneff", "chinstrap45"}


def test_comments_and_blank_lines_name_no_owner(tmp_path):
    f = tmp_path / "list"
    f.write_text("# owners\n\n  Org-A  # an org\n")
    assert owners.owned_owners(f) == {"org-a"}
    assert owners.is_owned("org-a", "me", f)


def test_an_unreadable_list_fails_closed(tmp_path):
    with pytest.raises(owners.OwnersError, match="cannot be read"):
        owners.is_owned("chinstrap45", "caneff", tmp_path / "missing")


def test_the_login_is_owned_without_reading_the_list(tmp_path):
    assert owners.is_owned("caneff", "caneff", tmp_path / "missing")
