"""Fixture for docstring-coverage: one undocumented public fn, one documented, one private.

The point of this fixture is that ruff D1xx flags only the undocumented
PUBLIC function — the documented public function and the private helper are
absent from its output by rule semantics alone, no hand-filtering needed.
"""


def undocumented_public(x):
    return x + 1


def documented_public(x):
    """Add one to x and return it."""
    return x + 1


def _helper(x):
    return x - 1
