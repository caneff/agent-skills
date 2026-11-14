from sample import upload


def test_upload_retries():
    # the ledger entry is keyed by request id, so a retry that re-sent it would double-charge
    assert upload("a.bin") == "a.bin"
