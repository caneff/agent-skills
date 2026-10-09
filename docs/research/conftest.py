import pytest

from review_ledger_support import Env


@pytest.fixture
def env(tmp_path):
    return Env(tmp_path)
