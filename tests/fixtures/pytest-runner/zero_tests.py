# A `*_test.py` from which pytest collects nothing: a helper and no test.
# pytest exits 5 on it, which the gate must read as red.


def helper():
    return 1
