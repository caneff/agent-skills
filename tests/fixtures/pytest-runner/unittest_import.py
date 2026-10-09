# A suite that imports unittest but whose one test passes under pytest, so
# only the gate's unittest check can make a run of it go red.
import unittest


def test_passes():
    assert unittest.TestCase is not None
