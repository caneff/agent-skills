import sys


def main(owner, user):
    if owner != user:
        sys.exit(1)
