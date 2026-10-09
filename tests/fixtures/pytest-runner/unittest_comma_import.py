# `import os, unittest`: unittest is not the first name imported, with a test
# that passes under pytest: only the gate's unittest check can make a run of
# it go red.
import os, unittest  # noqa: E401


def test_passes():
    assert os.sep and unittest.TestCase is not None
