def outer():
    def inner(x):
        if x > 3:
            return 1
        elif x > 2:
            return 2
        elif x > 1:
            return 3
        elif x > 0:
            return 4
        elif x < 0:
            return 5
        return 0
    return inner


def uncovered_fn(a, b, c):
    if a:
        return 1
    if b:
        return 2
    if c:
        return 3
    return 0


def branchless_fn():
    return 42
