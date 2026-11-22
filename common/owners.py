"""Whose repos are the caller's own: the `gh` login's, and every owner on
`owned-owners.txt` beside this file (#2005). One list, read here by the Python
checks and by `flow/claude/hooks/block-dangerous-git.sh` in bash.

It fails closed: an empty owner is never owned, and a list that cannot be read
raises `OwnersError` rather than reading as an empty one, so a lost file never
grants a push and never passes for "no org is listed" silently."""
import os

OWNERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "owned-owners.txt")


class OwnersError(Exception):
    pass


def owned_owners(path=None):
    """The listed owners, lowercased; `#` starts a comment. `path` defaults to
    `OWNERS_FILE` as it stands at the call."""
    path = path or OWNERS_FILE
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise OwnersError(f"the owned-owners list {path} cannot be read ({exc})") from exc
    return {name for name in (line.split("#", 1)[0].strip().lower() for line in lines) if name}


def is_owned(owner, login, path=None):
    """Is a repo whose owner is `owner` the `login`'s own. The login needs no
    list; any other owner does, so only that case can raise `OwnersError`."""
    owner = (owner or "").lower()
    if not owner:
        return False
    if owner == (login or "").lower():
        return True
    return owner in owned_owners(path)
