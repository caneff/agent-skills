# `from unittest import ...`, with a test that passes under pytest: only the
# gate's unittest check can make a run of it go red.
from unittest import TestCase


def test_passes():
    assert TestCase is not None
