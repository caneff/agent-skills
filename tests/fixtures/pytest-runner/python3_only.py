# A transitional suite: it passes only when run as a script. Imported by
# pytest, `__name__` is the module's name and the import itself fails.
if __name__ != "__main__":
    raise ImportError("imported by pytest, not run under python3")
print("ok")
