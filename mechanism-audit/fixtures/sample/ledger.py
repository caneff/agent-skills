"""A ledger that appends one row per run."""


def append(path, row):
    with open(path, "a", encoding="utf-8") as f:
        f.write(row + "\n")
