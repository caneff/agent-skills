import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import owners  # noqa: E402


@pytest.fixture
def listed(monkeypatch, tmp_path):
    """Point the reader at a list holding `text`."""
    def use(text):
        f = tmp_path / "list"
        f.write_bytes(text.encode())
        monkeypatch.setattr(owners, "OWNERS_FILE", str(f))
    return use


def test_the_login_owns_its_own_repos_in_any_case_though_not_listed(listed):
    listed("org-a\n")
    assert owners.is_owned("Me", "me")
    assert not owners.is_owned("caneff", "me")


def test_an_org_on_the_list_is_owned_in_any_case():
    assert owners.is_owned("ChinStrap45", "caneff")


def test_an_owner_neither_the_login_nor_listed_is_not_owned():
    assert not owners.is_owned("someone-else", "caneff")


def test_an_empty_owner_is_never_owned_even_by_an_empty_login():
    assert not owners.is_owned("", "")


def test_the_shipped_list_holds_the_ruled_owners_and_no_other():
    assert owners.owned_owners() == {"caneff", "chinstrap45"}


def test_comments_blank_lines_padding_and_crlf_name_no_owner(listed):
    """The hook's reader is held to the same text by block-dangerous-git.test.sh."""
    listed("# owners\r\n\r\n  Org-A  # an org\r\n\tOrg-B\r\n")
    assert owners.owned_owners() == {"org-a", "org-b"}
    assert owners.is_owned("org-a", "me") and owners.is_owned("ORG-B", "me")


@pytest.mark.parametrize("owner", ["chinstrap45", "caneff"])
def test_an_unreadable_list_fails_closed_for_every_owner(monkeypatch, tmp_path, owner):
    monkeypatch.setattr(owners, "OWNERS_FILE", str(tmp_path / "missing"))
    with pytest.raises(owners.OwnersError, match="cannot be read"):
        owners.is_owned(owner, "caneff")
