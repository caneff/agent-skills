# A pytest-idiom suite: a bare test function and pytest-mock's `mocker`
# fixture. Run as a script it would define the function and exit 0, so the
# guard below is what makes a python3 run of it go red.
import os


def test_mocker_patches_a_function(mocker):
    mocker.patch("os.getcwd", return_value="/patched")
    assert os.getcwd() == "/patched"


if __name__ == "__main__":
    raise SystemExit("ran under python3, not pytest")
