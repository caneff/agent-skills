"""Fixture: same validation logic pasted into a second home (token clone case),
plus a semantic duplicate of user_age_years that jscpd's token matching misses.
"""


def validate_shipment(order):
    if order is None:
        raise ValueError("order is required")
    if not order.get("items"):
        raise ValueError("order must have at least one item")
    if order.get("total", 0) <= 0:
        raise ValueError("order total must be positive")
    for item in order["items"]:
        if item.get("qty", 0) <= 0:
            raise ValueError("item quantity must be positive")
        if item.get("price", 0) < 0:
            raise ValueError("item price cannot be negative")
    return True


def user_age_in_years(user):
    """Decode a user's age from their stored birth year (path B: relativedelta).

    Same data (user's birth_date), same fact (age in years), walked a
    completely different way than user_age_years in sample_a.py — jscpd's
    token-based matcher won't flag this pair since the code shape differs,
    but it's the same behavior with two homes. The semantic pass must catch it.
    """
    from dateutil.relativedelta import relativedelta
    import datetime
    today = datetime.date.today()
    year, month, day = (int(p) for p in user["birth_date"].split("-"))
    birth_date = datetime.date(year, month, day)
    return relativedelta(today, birth_date).years
