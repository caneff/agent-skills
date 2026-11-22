"""Whose repos are the caller's own: the `gh` login's, and every owner on
`owned-owners.txt` beside this file (#2005). One list, read here by the Python
checks and by `flow/claude/hooks/block-dangerous-git.sh` in bash.

It fails closed: an empty owner is never owned, and a list that cannot be read
raises `OwnersError` for every owner, the login's included, as the ticket
rules ("an unreadable list or a `gh` error means not owned"), rather than
reading as an empty list."""
import os

OWNERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "owned-owners.txt")


class OwnersError(Exception):
    pass


def owned_owners():
    """The listed owners, lowercased: `#` starts a comment, and a line's
    surrounding whitespace (a CRLF's `\\r` included) is no part of its owner.
    Reads `OWNERS_FILE` as it stands at the call."""
    try:
        with open(OWNERS_FILE, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise OwnersError(f"the owned-owners list {OWNERS_FILE} cannot be read ({exc})") from exc
    return {name for name in (line.split("#", 1)[0].strip().lower() for line in lines) if name}


def is_owned(owner, login):
    """Is a repo whose owner is `owner` the `login`'s own: the login, or an
    owner on the list. Raises `OwnersError` when the list cannot be read."""
    listed = owned_owners()
    owner = (owner or "").lower()
    return bool(owner) and (owner == (login or "").lower() or owner in listed)
