# `importlib.import_module("unittest.mock")`, with a test that passes under
# pytest: only the gate's unittest check can make a run of it go red.
import importlib

mock = importlib.import_module("unittest.mock")


def test_passes():
    assert mock.patch is not None
