# A pytest-idiom suite whose one test fails. Run as a script it defines the
# function and exits 0, so only a runner that collects and runs it goes red.


def test_fails():
    assert 1 == 2
