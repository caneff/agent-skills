def blocked_by_from_body(body):
    return [w for w in body.split() if w.startswith("#")]


def dispatch(ticket, blocked_by=None):
    return ticket, blocked_by
