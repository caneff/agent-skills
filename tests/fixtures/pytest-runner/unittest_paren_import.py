# `from unittest.mock import(patch)` inside a block, with a test that passes
# under pytest: only the gate's unittest check can make a run of it go red.
if True:
    from unittest.mock import(patch)


def test_passes():
    assert patch is not None
