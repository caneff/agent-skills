"""Fixture: a copy-pasted validation block (token clone case)."""


def validate_order(order):
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


def user_age_years(user):
    """Decode a user's age from their stored birth year (path A: subtraction)."""
    import datetime
    current_year = datetime.date.today().year
    birth_year = int(user["birth_date"].split("-")[0])
    return current_year - birth_year
