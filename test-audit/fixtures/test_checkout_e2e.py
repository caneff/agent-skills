"""Fixture: end-to-end checkout tests.

Deliberately mixed quality — see ../answer-key.md for the expected bucket
of each test. Do not "fix" these in place; they exist to be judged.
"""

from checkout import run_checkout


def test_checkout_flow_produces_receipt_with_payment_reference():
    # KEEP — owns the wiring this e2e layer exists to prove: a checkout
    # actually reaches payment and comes back with a receipt carrying that
    # payment's reference and a paid status. Nothing at the unit layer
    # exercises this path, so this is the lowest layer that owns it.
    receipt = run_checkout(cart=[{"price": 100}], percent_off=10)

    assert receipt.payment_id is not None
    assert receipt.status == "paid"


def test_checkout_flow_applies_discount_amount():
    # CUT — duplicate coverage. This re-proves the exact discount math that
    # test_pricing.py::test_apply_discount_computes_amount_off already owns
    # at the unit layer. It cannot fail for a reason the unit test doesn't
    # already catch faster, and the wiring this e2e layer actually owns —
    # reaching payment and getting a receipt back — is already proved by
    # test_checkout_flow_produces_receipt_with_payment_reference above, in
    # this same file. Deleting this one loses no coverage either layer
    # uniquely holds.
    receipt = run_checkout(cart=[{"price": 100}], percent_off=10)

    assert receipt.total == 90
