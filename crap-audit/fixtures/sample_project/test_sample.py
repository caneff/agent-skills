from sample import outer, branchless_fn


def test_outer():
    inner = outer()
    assert inner(4) == 1


def test_branchless():
    assert branchless_fn() == 42
