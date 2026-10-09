# `import unittest.mock`, with a test that passes under pytest: only the
# gate's unittest check can make a run of it go red.
import unittest.mock


def test_passes():
    assert unittest.mock.patch is not None
