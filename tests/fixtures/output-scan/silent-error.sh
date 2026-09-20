#!/usr/bin/env bash
# Witnesses the `ERROR` third of the set. The shape is Python's
# `logging.error()` default, `ERROR:root:<msg>` at column 0 — see the known
# limit recorded beside `failure_signature` in tests/all.sh.
echo "ERROR:root:manifest checksum did not match, continuing with the stale copy"
exit 0
