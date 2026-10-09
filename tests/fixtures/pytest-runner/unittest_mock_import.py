# Imports only `unittest.mock`, with a test that passes under pytest: only the
# gate's unittest check can make a run of it go red.
from unittest.mock import patch


def test_passes():
    assert patch is not None
