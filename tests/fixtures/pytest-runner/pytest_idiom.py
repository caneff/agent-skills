# A pytest-idiom suite: a bare test function and pytest-mock's `mocker`
# fixture.
import os


def test_mocker_patches_a_function(mocker):
    mocker.patch("os.getcwd", return_value="/patched")
    assert os.getcwd() == "/patched"
